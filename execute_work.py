import os
import re
from colors import Colors
from phase_manager import State, Phase, Context
from implementation_agent import ImplementationAgent
import logging
from utils.logging_util import LoggingUtil


class ExecuteWork(Phase):
    description = "Execute the planned work items"

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)

    def run(self, state: State, context: Context) -> dict:
        self.logger.info(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE STARTED ==={Colors.END}")

        work = state["work"]
        project_path = state["project_path"]
        facts = state["facts"]

        # Get AI provider from environment or default to anthropic
        provider = os.getenv('AI_PROVIDER', 'anthropic').lower()
        self.logger.info(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Using AI provider: {provider}")

        if provider == 'gemini':
            self.logger.info(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Gemini setup:")
            self.logger.info(f"  Make sure you have: pip install google-genai")
            self.logger.info(f"  Set environment variable: GOOGLE_API_KEY=your_api_key")
        elif provider == 'anthropic':
            self.logger.info(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Anthropic setup:")
            self.logger.info(f"  Make sure you have: pip install anthropic")
            self.logger.info(f"  Set environment variable: ANTHROPIC_API_KEY=your_api_key")

        # Parse work into an array by extracting content between <step> tags
        self.logger.info(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Parsing steps from work content...")
        step_pattern = r'<step[^>]*>(.*?)</step>'
        steps = re.findall(step_pattern, work, re.DOTALL)
        self.logger.info(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Found {len(steps)} step matches with regex")

        # Clean up the extracted steps (remove leading/trailing whitespace)
        steps = [step.strip() for step in steps]

        self.logger.info(f"{Colors.BRIGHT_GREEN}[PARSING]{Colors.END} Step parsing completed:")
        self.logger.info(f"  Found {len(steps)} steps after cleanup")

        # Print the array
        self.logger.info(f"{Colors.BRIGHT_MAGENTA}[STEPS]{Colors.END} Parsed steps array:")
        for i, step in enumerate(steps):
            self.logger.info(f"{Colors.BRIGHT_GREEN}Step {i+1}:{Colors.END}")
            self.logger.info(f"  Length: {len(step)} characters")
            self.logger.info(f"  Preview: {step[:100]}..." if len(step) > 100 else f"  Content: {step}")
            self.logger.info("-" * 40)

        # Create implementation agent with provider support
        self.logger.info(f"{Colors.BRIGHT_YELLOW}[AGENT]{Colors.END} Creating implementation agent with provider: {provider}")
        agent = ImplementationAgent(project_path, context, provider=provider, facts=facts)

        # Initialize API duration tracking
        total_api_duration = 0.0

        # Process each step
        self.logger.info(f"\n{Colors.BRIGHT_YELLOW}[PROCESSING]{Colors.END} Processing steps with implementation agent:")
        for i, step in enumerate(steps):
            with LoggingUtil.Span(f"Processing step {i+1}/{len(steps)}"):
                self.logger.info(f"{Colors.BRIGHT_CYAN}=== Processing step {i+1}/{len(steps)} ==={Colors.END}")
                self.logger.info(f"Content preview: {step[:100]}..." if len(step) > 100 else f"Content: {step}")

                # Implement the step
                result = agent.implement_step(step)
                step_api_duration = result.get('total_api_duration', 0)
                total_api_duration += step_api_duration

                self.logger.info(f"{Colors.BRIGHT_GREEN}[PROCESSING]{Colors.END} Step {i+1} processing completed")
                self.logger.info("")

        # Format duration for display
        minutes = int(total_api_duration // 60)
        seconds = int(total_api_duration % 60)

        self.logger.info(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE COMPLETED ==={Colors.END}")
        self.logger.info(f"{Colors.BRIGHT_YELLOW}[SUMMARY]{Colors.END} Final summary:")
        self.logger.info(f"  Provider used: {provider}")
        self.logger.info(f"  Steps processed: {len(steps)}")
        self.logger.info(f"  Total duration ({provider}, API): {minutes}m {seconds}s")

        return {}

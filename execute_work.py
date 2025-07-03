import os
import re
from colors import Colors
from phase_manager import State, Phase, Context
from implementation_agent import ImplementationAgent

class ExecuteWork(Phase):
    description = "Execute the planned work items"

    def run(self, state: State, context: Context) -> dict:
        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE STARTED ==={Colors.END}")

        work = state["work"]
        project_path = state["project_path"]
        facts = state["facts"]

        # Get AI provider from environment or default to anthropic
        provider = os.getenv('AI_PROVIDER', 'anthropic').lower()
        print(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Using AI provider: {provider}")

        if provider == 'gemini':
            print(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Gemini setup:")
            print(f"  Make sure you have: pip install google-genai")
            print(f"  Set environment variable: GOOGLE_API_KEY=your_api_key")
        elif provider == 'anthropic':
            print(f"{Colors.BRIGHT_CYAN}[PROVIDER]{Colors.END} Anthropic setup:")
            print(f"  Make sure you have: pip install anthropic")
            print(f"  Set environment variable: ANTHROPIC_API_KEY=your_api_key")

        # Parse work into an array by extracting content between <step> tags
        print(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Parsing steps from work content...")
        step_pattern = r'<step[^>]*>(.*?)</step>'
        steps = re.findall(step_pattern, work, re.DOTALL)
        print(f"{Colors.BRIGHT_CYAN}[PARSING]{Colors.END} Found {len(steps)} step matches with regex")

        # Clean up the extracted steps (remove leading/trailing whitespace)
        steps = [step.strip() for step in steps]

        print(f"{Colors.BRIGHT_GREEN}[PARSING]{Colors.END} Step parsing completed:")
        print(f"  Found {len(steps)} steps after cleanup")

        # Print the array
        print(f"{Colors.BRIGHT_MAGENTA}[STEPS]{Colors.END} Parsed steps array:")
        for i, step in enumerate(steps):
            print(f"{Colors.BRIGHT_GREEN}Step {i+1}:{Colors.END}")
            print(f"  Length: {len(step)} characters")
            print(f"  Preview: {step[:100]}..." if len(step) > 100 else f"  Content: {step}")
            print("-" * 40)

        # Create implementation agent with provider support
        print(f"{Colors.BRIGHT_YELLOW}[AGENT]{Colors.END} Creating implementation agent with provider: {provider}")
        agent = ImplementationAgent(project_path, context, provider=provider, facts=facts)

        # Initialize API duration tracking
        total_api_duration = 0.0

        # Process each step
        print(f"\n{Colors.BRIGHT_YELLOW}[PROCESSING]{Colors.END} Processing steps with implementation agent:")
        for i, step in enumerate(steps):
            print(f"{Colors.BRIGHT_CYAN}=== Processing step {i+1}/{len(steps)} ==={Colors.END}")
            print(f"Content preview: {step[:100]}..." if len(step) > 100 else f"Content: {step}")

            # Implement the step
            result = agent.implement_step(step)
            step_api_duration = result.get('total_api_duration', 0)
            total_api_duration += step_api_duration

            print(f"{Colors.BRIGHT_GREEN}[PROCESSING]{Colors.END} Step {i+1} processing completed")
            print()

        # Format duration for display
        minutes = int(total_api_duration // 60)
        seconds = int(total_api_duration % 60)

        print(f"{Colors.BRIGHT_MAGENTA}=== EXECUTE WORK PHASE COMPLETED ==={Colors.END}")
        print(f"{Colors.BRIGHT_YELLOW}[SUMMARY]{Colors.END} Final summary:")
        print(f"  Provider used: {provider}")
        print(f"  Steps processed: {len(steps)}")
        print(f"  Total duration ({provider}, API): {minutes}m {seconds}s")


        return {
            "provider": provider,
            "total_api_duration": total_api_duration
        }
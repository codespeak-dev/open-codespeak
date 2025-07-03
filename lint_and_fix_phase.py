import os
from io import StringIO

from pylint import run_pylint
from colors import Colors
from phase_manager import State, Phase, Context
from pylint.lint import Run
from pylint.reporters.json_reporter import JSONReporter
import json

from implementation_agent import TOOLS_DEFINITIONS, ImplementationAgent


class LintAndFix(Phase):
    description = "Run pylint on all Python files and fix issues"

    _SYSTEM_PROMPT = """
    You are an expert Python/Django developer. You're given a:
    - python file in <target_file> tags
    - structured pylint errors in <pylint> tags

    Your task is to fix pylint errors. 
    """

    _MAX_FIX_ATTEMPTS = 3

    def run_pylint(self, files_to_check: list[str]) -> list[dict]:
        # Run pylint on files that need checking
        output = StringIO()
        reporter = JSONReporter(output)
        
        try:
            Run(['--errors-only', '--persistent=no', '--clear-cache-post-run=True'] + files_to_check, reporter=reporter, exit = False)
        except Exception as e:
            print(f"    {Colors.BRIGHT_RED}❌ Error running pylint: {str(e)}{Colors.END}")
            exit(1)
        
        output.seek(0)
        return json.loads(output.read())

    def run(self, state: State, context: Context) -> dict:
        project_path = state["project_path"]
        
        # Find all Python files in the project
        # TODO(dsavvinov): can run only on LLM-generated files
        python_files = []
        for root, dirs, files in os.walk(project_path):
            # Skip common directories that shouldn't be linted
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'venv', 'env', 'node_modules']]
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        if not python_files:
            print(f"{Colors.BRIGHT_YELLOW}No Python files found to lint{Colors.END}")
            return {}
        
        # Initial run of pylint to get errors
        errors = self.run_pylint(python_files)
        if len(errors) == 0:
            print(f"    {Colors.BRIGHT_GREEN}✅ No Python lint errors found{Colors.END}")
            return {}
        else:
            print(f"    {Colors.BRIGHT_RED}❌ {len(errors)} Python lint errors found, fixing with agent...{Colors.END}")

        agent = ImplementationAgent(
            project_path=state["project_path"],
            system_prompt_override=self._SYSTEM_PROMPT,
            tools_definitions_override=[tool for tool in TOOLS_DEFINITIONS if tool['name'] == 'edit_file'],
            check_read_before_write=False,
            context=context
        )
    
        # Group errors by file path
        errors_by_file = {}
        for error in errors:
            file_path = error.get('path')
            assert file_path is not None, f"Error: missing 'path' field in object returned by pylint: {error}"
            if file_path not in errors_by_file:
                errors_by_file[file_path] = []
            errors_by_file[file_path].append(error)
        
        # Start iterating with AI on each file that has errors
        for file_path, file_errors in errors_by_file.items():
            with open(file_path, 'r') as f:
                file_content = f.read()
            
            current_errors = file_errors
            # sanitize paths
            for error in current_errors:
                if 'path' in error:
                    error['path'] = os.path.relpath(error['path'], state["project_path"])

            print(f"    Fixing {len(file_errors)} errors in {file_path}...")
            for i in range(self._MAX_FIX_ATTEMPTS):
                result = agent.run_streaming_conversation(self._SYSTEM_PROMPT, [{"role": "user", "content": f"""
                Fix the following pylint errors:
                <pylint>
                {json.dumps(current_errors, indent=2)}
                </pylint>
                <target_file>
                {file_content}
                </target_file>
                """}])

                current_errors = self.run_pylint([file_path])
                if len(current_errors) != 0:
                    print(f"    Still {len(current_errors)} errors left in {file_path}, iterating again...")
                else:
                    break
            if (len(current_errors) > 0):
                print(f"    {Colors.BRIGHT_RED}❌ Failed to fix all errors in {file_path}{Colors.END}")
                exit(1)
            else:
                print(f"    All errors are fixed in {file_path}")

        return {}

from phase_manager import State, Phase, Context
import selectors
import subprocess
import sys
import time
from typing import Tuple

from implementation_agent import ImplementationAgent
from phase_manager import State, Phase, Context


class EnsureServerStarts(Phase):
    description = "Make sure Django server can start. If it does not, modify the code and try again."

    SYSTEM_PROMPT = f"""
    You're an experienced Django developer. You have a Django project which fails to start
    (when calling python manage.py runserver). You'll be given a server output and you need to
    analyze it, then match it with the web application source files and fix files to make server start.
    """

    @staticmethod
    def launch_and_capture(args: list, cwd: str, wait_time_sec: int):
        proc = subprocess.Popen(
            args=args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True)

        # Use selectors to do non-blocking reads
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        sel.register(proc.stderr, selectors.EVENT_READ)

        start_time = time.time()
        stdout_lines = []
        stderr_lines = []

        while True:
            elapsed = time.time() - start_time
            if elapsed > wait_time_sec:
                # Stop waiting after the given time
                break

            events = sel.select(timeout=0.1)  # short timeout to be non-blocking-ish
            for key, _ in events:
                data = key.fileobj.readline()
                if not data:
                    # EOF
                    sel.unregister(key.fileobj)
                else:
                    if key.fileobj == proc.stdout:
                        stdout_lines.append(data.rstrip('\n'))
                    else:
                        stderr_lines.append(data.rstrip('\n'))

            # If both pipes closed early, stop waiting
            if not sel.get_map():
                break

        return stdout_lines, stderr_lines, proc

    def run_server(self, project_path: str) -> Tuple[bool, str | None]:
        args = [sys.executable, f"manage.py", "runserver"]
        timeout_sec = 5
        print(f"Launching server: {args} in folder {project_path} and waiting for {timeout_sec} seconds")
        proc = None
        try:
            stdout_lines, stderr_lines, proc = self.launch_and_capture(args, project_path, timeout_sec)
            # Filter out empty or only-whitespace strings from both arrays
            output_lines = [line for line in stdout_lines + stderr_lines if line.strip()]
            output = "\n".join(output_lines)
            print(f"Server output after {timeout_sec} seconds: [[[\n{output}\n]]]")
            if any("Starting development server at" in line for line in output_lines) and any(
                    "Quit the server with CONTROL-C" in line for line in output_lines):
                # successful start
                return True, None
            else:
                return False, output
        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=3)

    @staticmethod
    def try_to_fix_server(project_path: str, output: str | None) -> None:
        agent = ImplementationAgent(project_path)

        user_prompt = f"Here's the server output: \n{output}" if output else "Server did not produce any output"
        messages = [{"role": "user", "content": user_prompt}]
        result = agent.run_streaming_conversation(EnsureServerStarts.SYSTEM_PROMPT, messages)
        print(f"  Total output tokens: {result['total_output_tokens']}")
        print(f"  Total API duration: {result.get('total_api_duration', 0):.2f}s")

    def run(self, state: State, context: Context) -> dict:
        project_path = state.get("project_path")

        output = None
        attempts = 5
        for i in range(attempts):
            try:
                success, output = self.run_server(project_path)
                if success:
                    print(f"Server started successfully on attempt {i + 1}")
                    break
                else:
                    print(f"Attempt {i + 1}: Server failed to start. Output:\n{output}")
                    self.try_to_fix_server(project_path, output)
            except Exception as e:
                print(f"Attempt {i + 1}: Exception occurred: {e}")
        else:
            # If we get here, all attempts failed
            raise RuntimeError(f"Server failed to start after {attempts} attempts. Last output:[[[\n{output}\n]]]")

        return {}

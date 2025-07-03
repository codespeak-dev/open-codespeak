import selectors
import subprocess
import sys
import time
import socket
from typing import Tuple

from implementation_agent import ImplementationAgent
from phase_manager import State, Phase, Context


class EnsureServerStarts(Phase):
    description = "Make sure Django server can start. If it does not, modify the code and try again."

    # need all of them
    SUCCESSFUL_SERVER_START_PATTERNS = [
        # following two are sometimes missing
        # "Starting development server at",
        # "Quit the server with CONTROL-C",
        "System check identified no issues"
    ]

    SYSTEM_PROMPT = f"""
    You're an experienced Django developer. You have a Django project which fails to start
    (when calling python manage.py runserver). You'll be given a server output and you need to
    analyze it, then match it with the web application source files and fix files to make server start.
    """

    @staticmethod
    def find_free_port(start_port, max_tries=100):
        port = start_port
        for _ in range(max_tries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('', port))
                    return port  # Port is free
                except OSError:
                    port += 1
        raise RuntimeError(f"No free port found in range {start_port} to {port - 1}")

    @staticmethod
    def launch_and_capture(args: list, cwd: str, wait_time_sec: int, patterns_to_be_captured: list[str]):
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
        captured_patterns = []

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
                    print(f"Unregistering {'STDOUT' if key.fileobj == proc.stdout else 'STDERR'}")
                    sel.unregister(key.fileobj)
                else:
                    output_line = data.rstrip('\n')
                    if key.fileobj == proc.stdout:
                        print(f"Received STDOUT line: \"{output_line}\" after {elapsed:.2f} s since start")
                        stdout_lines.append(output_line)
                    else:
                        print(f"Received STDERR line: \"{output_line}\" after {elapsed:.2f} s since start")
                        stderr_lines.append(output_line)

                    for pattern in patterns_to_be_captured:
                        if pattern in output_line:
                            print(f"Captured pattern \"{pattern}\"")
                            captured_patterns.append(pattern)
                            break

            if len(captured_patterns) == len(patterns_to_be_captured):
                print(f"Captured all required patterns in {elapsed:.2f} s since start")
                break

            # If both pipes closed early, stop waiting
            if not sel.get_map():
                break

        return len(captured_patterns) == len(patterns_to_be_captured), stdout_lines, stderr_lines, proc

    def run_server(self, project_path: str) -> Tuple[bool, str | None]:
        port = EnsureServerStarts.find_free_port(5678)
        args = [sys.executable, f"manage.py", "runserver", str(port), "--verbosity", "3"]
        timeout_sec = 60
        print(f"Launching server: {args} in folder {project_path} and waiting for up to {timeout_sec} seconds")

        proc = None
        try:
            all_captured, stdout_lines, stderr_lines, proc = \
                EnsureServerStarts.launch_and_capture(args, project_path, timeout_sec, EnsureServerStarts.SUCCESSFUL_SERVER_START_PATTERNS)
            # Filter out empty or only-whitespace strings from both arrays
            output_lines = [line for line in (stdout_lines + stderr_lines) if line.strip()]
            output = "\n".join(output_lines)

            if all_captured:
                # successful start
                return True, None
            else:
                print(f"Did not capture required messages in {timeout_sec} s, assuming server failed to start.")
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
                    print(f"Attempt {i + 1}: Server failed to start. Output:[[[\n{output}\n]]]")
                    self.try_to_fix_server(project_path, output)
            except Exception as e:
                print(f"Attempt {i + 1}: Exception occurred: {e}")
        else:
            # If we get here, all attempts failed
            raise RuntimeError(f"Server failed to start after {attempts} attempts. Last output:[[[\n{output}\n]]]")

        return {}

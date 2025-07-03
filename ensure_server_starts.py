import selectors
import subprocess
import sys
import time
import socket
import requests
from requests import RequestException

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

    def run_server(self, project_path: str) -> [bool, str]:
        timeout_sec = 60

        port = EnsureServerStarts.find_free_port(5678)
        args = [sys.executable, f"manage.py", "runserver", str(port), "--verbosity", "3"]
        accepted_status_codes = [200, 403]
        print(f"Launching server: {args} in folder {project_path} and waiting for up to {timeout_sec} seconds")
        proc = None
        try:
            proc = subprocess.Popen(
                args=args,
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)

            time.sleep(1) # wait for start to log less errors

            # Use selectors to do non-blocking reads
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            sel.register(proc.stderr, selectors.EVENT_READ)

            start_time = time.time()
            output_lines = []

            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_sec:
                    # Stop waiting after the given time
                    return False, output_lines

                url = f'http://localhost:{port}'
                try:
                    response = requests.get(url)
                    if response.status_code in accepted_status_codes:
                        print(f"Request to {url} succeeded with status code {response.status_code}")
                        return True, None
                    else:
                        print(f"Request to {url} failed with status code {response.status_code}, response: {response.content}")

                except RequestException as e:
                    print(f"Request to {url} failed with exception {e}")

                if sel.get_map():
                    events = sel.select(timeout=0.5)  # short timeout to be non-blocking-ish
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
                                output_lines.append(output_line)
                            else:
                                print(f"Received STDERR line: \"{output_line}\" after {elapsed:.2f} s since start")
                                output_lines.append(output_line)

        finally:
            if proc:
                proc.terminate()
                proc.wait(timeout=3)

    def try_to_fix_server(self, project_path: str, output: str | None) -> None:
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

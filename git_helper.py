import os
import subprocess
import time

class GitHelper:
    """A helper class to interact with a Git repository."""

    def __init__(self, repo_path: str):
        if repo_path is None:
            raise ValueError("repo_path must not be None")
        self.repo_path = repo_path

    def _run_command(self, command: list[str]) -> tuple[int, str, str]:
        """A private helper to run shell commands in the repository directory."""
        start_time = time.monotonic()
        try:
            process = subprocess.run(
                command,
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            return process.returncode, process.stdout, process.stderr
        except subprocess.CalledProcessError as e:
            return e.returncode, e.stdout, e.stderr
        except FileNotFoundError:
            return -1, "", "Git command not found. Is Git installed and in your PATH?"
        finally:
            duration = time.monotonic() - start_time
            print(f"Command `{' '.join(command)}` finished in {duration:.3f}s")

    def save(self, title: str, description: str):
        """
        Stages all changes and commits them with a given message.
        """
        print("Staging all changes...")
        add_returncode, _, add_stderr = self._run_command(['git', 'add', '.'])
        if add_returncode != 0:
            print(f"Error staging changes: {add_stderr}")
            return

        commit_returncode, _, commit_stderr = self._run_command(['git', 'commit', '-m', title, '-m', description])
        if commit_returncode != 0:
            # It's common for commit to fail if there's nothing to commit.
            if "nothing to commit" in commit_stderr:
                print("No changes to commit.")
            else:
                print(f"Error committing changes: {commit_stderr}")
        else:
            print("Changes committed successfully.")
    
    def ensure_clean_working_tree(self):
        """
        Ensures that the git working directory is clean (no uncommitted changes or untracked files).
        Raises an exception if the working directory is not clean.
        """
        status_returncode, status_stdout, status_stderr = self._run_command(['git', 'status', '--porcelain'])
        if status_returncode != 0:
            raise RuntimeError(f"Failed to check git status: {status_stderr}")
        if status_stdout.strip():
            print("Git working directory is not clean:")
            print(status_stdout)
            raise RuntimeError("Git working directory is not clean. Please commit or stash your changes before proceeding.")
        else:
            print("Git working directory is clean.")

    def get_head_hash(self) -> str | None:
        """
        Returns the current HEAD commit hash, or None if it cannot be determined.
        """
        returncode, stdout, stderr = self._run_command(['git', 'rev-parse', 'HEAD'])
        if returncode != 0:
            print(f"Error getting HEAD hash: {stderr}")
            return None
        return stdout.strip()
    
    def find_commit_hash_by_message(self, message_substring: str) -> str | None:
        """
        Finds the hash of the most recent commit whose message contains the given substring.
        Returns the commit hash as a string, or None if not found.
        """
        # Use git log to get commit hashes and messages
        returncode, stdout, stderr = self._run_command(
            ['git', 'log', '--all', '--grep', message_substring, '--format', '%H']
        )
        if returncode != 0:
            print(f"Error running git log: {stderr}")
            return None

        lines = stdout.splitlines()
        if len(lines) == 0:
            print(f"No commit found for message substring '{message_substring}'")
            return None
        elif len(lines) > 1:
            print(f"Multiple commits found for message substring '{message_substring}':")
            for line in lines:
                print(f"  {line.strip()}")
            return None
        else:
            return lines[0].strip()
    
    def create_and_checkout_branch(self, branch_name: str):
        """
        Creates a new branch with the given name and switches to it.
        If the branch already exists, just checks it out.
        """
        # Check if branch already exists
        branch_exists = False
        returncode, stdout, stderr = self._run_command(['git', 'branch', '--list', branch_name])
        if returncode != 0:
            print(f"Error checking for branch existence: {stderr}")
            raise RuntimeError(f"Failed to check if branch '{branch_name}' exists.")
        if stdout.strip():
            branch_exists = True

        if branch_exists:
            print(f"Branch '{branch_name}' already exists. Checking it out.")
            returncode, stdout, stderr = self._run_command(['git', 'checkout', branch_name])
            if returncode != 0:
                print(f"Error checking out branch '{branch_name}': {stderr}")
                raise RuntimeError(f"Failed to checkout branch '{branch_name}'.")
        else:
            print(f"Creating and checking out new branch '{branch_name}'.")
            returncode, stdout, stderr = self._run_command(['git', 'checkout', '-b', branch_name])
            if returncode != 0:
                print(f"Error creating branch '{branch_name}': {stderr}")
                raise RuntimeError(f"Failed to create and checkout branch '{branch_name}'.")
    
    def restore(self, commit_hash: str):
        """
        Restores the repository to the given commit hash.
        """
        self._run_command(["git", "reset", "--hard", commit_hash])
        self._run_command(["git", "checkout", "."])

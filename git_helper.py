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

    def save(self, title: str, description: str):
        """
        Stages all changes and commits them with a given message.
        """
        add_returncode, _, add_stderr = self._run_command(['git', 'add', '.'])
        if add_returncode != 0:
            print(f"Error staging changes: {add_stderr}")
            return

        commit_returncode, _, commit_stderr = self._run_command(['git', 'commit', '-m', title, '-m', description, '--author="Codespeak <gen@codespeak.dev>"'])
        if commit_returncode != 0:
            raise RuntimeError(f"Error committing changes: {commit_stderr}")
    
    def ensure_clean_working_tree(self):
        """
        Ensures that the git working directory is clean (no uncommitted changes or untracked files).
        Raises an exception if the working directory is not clean.
        """
        status_returncode, status_stdout, status_stderr = self._run_command(['git', 'status', '--porcelain'])
        if status_returncode != 0:
            raise RuntimeError(f"Failed to check git status: {status_stderr}")
        if status_stdout.strip():
            raise RuntimeError(f"Git working directory is not clean. Please commit or stash your changes before proceeding.\n{status_stdout}")

    def get_head_hash(self) -> str | None:
        """
        Returns the current HEAD commit hash, or None if it cannot be determined.
        """
        returncode, stdout, stderr = self._run_command(['git', 'rev-parse', 'HEAD'])
        if returncode != 0:
            print(f"Error getting HEAD hash: {stderr}")
            return None
        return stdout.strip()
    
    def get_head_author(self) -> str | None:
        """
        Returns the author of the current HEAD commit, or None if it cannot be determined.
        """
        returncode, stdout, stderr = self._run_command(['git', 'log', '-1', '--format=%an'])
        if returncode != 0:
            print(f"Error getting HEAD author: {stderr}")
            return None
        return stdout.strip()
    
    def find_commit_hash_by_message(self, message_substring: str) -> str | None:
        """
        Finds the hash of the most recent commit whose message contains the given substring.
        Returns the commit hash as a string, or None if not found.
        """
        # Use git log to get commit hashes and messages
        returncode, stdout, stderr = self._run_command(
            ['git', 'log', '--grep', message_substring, '--format=%H']
        )
        if returncode != 0:
            print(f"Error running git log: {stderr}")
            return None

        lines = stdout.splitlines()
        if len(lines) == 0:
            print(f"No commit found for message substring '{message_substring}'")
            return None
        elif len(lines) > 1:
            print(f"    Multiple commits found for message substring '{message_substring}':")
            for line in lines:
                print(f"        {line.strip()}")
            print(f"    Taking the most recent one: {lines[0].strip()}")
            return lines[0].strip()
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
            raise RuntimeError(f"Failed to check if branch '{branch_name}' exists.\n{stderr}")
        if stdout.strip():
            branch_exists = True

        if branch_exists:
            raise RuntimeError(f"Branch '{branch_name}' already exists.")
        
        returncode, stdout, stderr = self._run_command(['git', 'checkout', '-b', branch_name])
        if returncode != 0:
            raise RuntimeError(f"Failed to create and checkout branch '{branch_name}'.\n{stderr}")
    
    def restore_state_to(self, commit_hash: str):
        """
        Restores the repository to the given commit hash.
        """
        self._run_command(["git", "reset", "--hard", commit_hash])
        self._run_command(["git", "checkout", "."])

    def get_path_diff(self, file_path: str, from_sha: str, to_sha: str) -> str:
        """
        Returns the git diff for a given file path between two commit SHAs.
        
        Args:
            file_path: Path to the file to get diff for
            from_sha: Starting commit SHA
            to_sha: Ending commit SHA
            
        Returns:
            The git diff as a string, or empty string if no diff or error
        """
        command = ['git', '--no-pager', 'diff', '--no-prefix', '--unified=0', from_sha, to_sha, '--', file_path]
        
        returncode, stdout, stderr = self._run_command(command)
        
        if returncode != 0:
            print(f"Error getting diff for {file_path}: {stderr}")
            return ""
            
        return stdout


    def git_file_content_for_revision(self, file_path: str, revision_sha: str) -> str:
        """
        Returns the content of a file at a specific git revision.
        
        Args:
            file_path: Path to the file relative to repository root
            revision_sha: Git commit SHA to get file content from
            
        Returns:
            The file content as a string, or empty string if file doesn't exist or error
        """
        command = ['git', 'show', f'{revision_sha}:{file_path}']
        
        returncode, stdout, stderr = self._run_command(command)
        
        if returncode != 0:
            print(f"Error getting file content for {file_path} at {revision_sha}: {stderr}")
            return ""
            
        return stdout
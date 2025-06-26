import argparse
import os
import dotenv
from colors import Colors
from extract_entities import ExtractEntities
from extract_project_name import ExtractProjectName
from generate_django_project import GenerateDjangoProject
from makemigrations import MakeMigrations
from migrate import Migrate
from state_machine import Done, State, run_state_machine

dotenv.load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.add_argument('filepath', help='Path to the input file')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    parser.add_argument('--incremental', help='Path to the project output dir')
    args = parser.parse_args()

    spec_file = args.filepath

    with open(spec_file, 'r') as f:
        spec = f.read()

    state = run_state_machine([
        ExtractProjectName(),        
        ExtractEntities(),
        GenerateDjangoProject(),
        MakeMigrations(),
        Migrate(),
        Done(),
    ], State({
        "spec": spec,
        "target_dir": args.target_dir,
    }))    

    project_name = state["project_name"]
    project_path = state["project_path"]

    print(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")

if __name__ == "__main__":
    main()

import argparse
import os
import dotenv
from colors import Colors
from extract_entities import ExtractEntities, RefineEntities
from extract_project_name import ExtractProjectName
from generate_django_project import GenerateDjangoProject
from makemigrations import MakeMigrations
from migrate import Migrate
from state_machine import Done, PersistentStateMachine

dotenv.load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.prog = 'codespeak'
    parser.add_argument('filepath', nargs='?', help='Path to the input file (required when not in incremental mode)')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    parser.add_argument('--incremental', help='Path to the project output dir')
    args = parser.parse_args()

    if args.incremental:
        print(f"Running in incremental mode from {args.incremental}")
        initial_state = {
            "project_path": args.incremental,
        }
    else:
        if not args.filepath:
            print("Error: filepath is required when not in incremental mode")
            parser.print_help()
            return

        spec_file = args.filepath
        with open(spec_file, 'r') as f:
            spec = f.read()

        initial_state = {
            "spec": spec,
            "target_dir": args.target_dir,
        }

    psm = PersistentStateMachine(
        [
            ExtractProjectName(),        
            ExtractEntities(),
            RefineEntities(),
            GenerateDjangoProject(),
            MakeMigrations(),
            Migrate(),
            Done(),
        ], 
        initial_state, 
        lambda state: os.path.join(state["project_path"], "codespeak_state.json") if "project_path" in state else None
    )

    state = psm.run_state_machine()

    project_name = state["project_name"]
    project_path = state["project_path"]

    print(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")

if __name__ == "__main__":
    main()

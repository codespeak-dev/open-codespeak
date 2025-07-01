import argparse
import os
import dotenv
import sys
from pathlib import Path
from colors import Colors
from data_serializer import text_file
from extract_entities import ExtractEntities
from generate_django_project import GenerateDjangoProject
from makemigrations import MakeMigrations
from migrate import Migrate
from generate_integration_tests import GenerateIntegrationTests
from reconcile_integration_tests import ReconcileIntegrationTests
from plan_screens import PlanScreens
from plan_layouts import PlanLayouts
from execute_layouts import ExecuteLayouts
from plan_work import PlanWork
from execute_work import ExecuteWork
from phase_manager import Done, PhaseManager, Context, Init
from spec_processor import SpecProcessor

dotenv.load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.prog = 'codespeak'
    parser.add_argument('filepath', nargs='?', help='Path to the input file (required when not in incremental mode)')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    parser.add_argument('--incremental', help='Path to the project output dir')
    parser.add_argument('--start', help='Start from a specific phase. Only works in incremental mode.')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    args = parser.parse_args()

    if args.incremental:
        print(f"Running in incremental mode from {args.incremental}")
        project_path = args.incremental
        init = Init({
            "project_path": project_path,
        })
    else:
        if not args.filepath:
            print("Error: filepath is required when not in incremental mode")
            parser.print_help()
            return

        spec_file = args.filepath
        with open(spec_file, 'r') as f:
            raw_spec = f.read()
        
        spec_processor = SpecProcessor()
        spec = spec_processor.process(raw_spec)

        project_path = os.path.dirname(spec_file)
        init = Init({
            "spec_file": spec_file,
            "spec": spec,
            "project_path": project_path,
            "project_name": os.path.basename(project_path),            
        }, {
            "spec": text_file("spec.md"),
        })

    pm = PhaseManager(
        [
            init,
            ExtractEntities(),
            GenerateDjangoProject(),
            MakeMigrations(),
            Migrate(),
            GenerateIntegrationTests(),
            ReconcileIntegrationTests(),
            PlanScreens(),
            PlanLayouts(),
            PlanWork(),
            ExecuteLayouts(),
            ExecuteWork(),
            Done(),
        ], 
        state_file=Path(project_path) / "codespeak_state.json",
        context=Context(verbose=args.verbose),
        start_from=args.start
    )

    state = pm.run_state_machine()

    project_name = state["project_name"]
    project_path = state["project_path"]

    print(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)

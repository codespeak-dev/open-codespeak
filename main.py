import argparse
import os
import dotenv
import sys
import logging
from pathlib import Path
from colors import Colors
from data_serializer import text_file
from extract_entities import ExtractEntities
from generate_django_project import GenerateDjangoProject
from generate_models import GenerateModels
from llm_cache.anthropic_cached import CachedAnthropic
from llm_cache.cache_utils import SubstringBasedSanitizer
from makemigrations import MakeMigrations
from migrate import Migrate
from generate_data_model_tests import GenerateDataModelTests
from reconcile_data_model_tests import ReconcileDataModelTests
from plan_screens import PlanScreens
from extract_layouts import ExtractLayouts
from extract_facts import ExtractFacts
from execute_layouts import ExecuteLayouts
from plan_work import PlanWork
from execute_work import ExecuteWork
from phase_manager import Done, PhaseManager, Context, Init, Phase, State
from spec_processor import SpecProcessor
from git_helper import GitHelper
from incremental_mode import IncrementalMode
from ensure_server_starts import EnsureServerStarts
from lint_and_fix_phase import LintAndFix
from utils.logging_util import LoggingUtil
from utils.flamegraph import Flamegraph

dotenv.load_dotenv()

def main():
    LoggingUtil.initialize_logger("./codespeak.log")

    logger = logging.getLogger("main")
    # Log the full invocation command line
    logger.info(f"{Colors.BRIGHT_YELLOW}Invocation:{Colors.END} {' '.join([os.path.basename(sys.argv[0])] + sys.argv[1:])}")

    parser = argparse.ArgumentParser(description="Generate Django project from file prompt via Claude.")
    parser.prog = 'codespeak'
    parser.add_argument('filepath', nargs='?', help='Path to the input file (required when not in incremental mode)')
    parser.add_argument('--target-dir', 
                       default=os.getenv('CODESPEAK_TARGET_DIR', '.'),
                       help='Target directory for the generated project (defaults to CODESPEAK_TARGET_DIR env var or current directory)')
    parser.add_argument('--incremental', help='Path to the project output dir')

    start_from_argument_group = parser.add_mutually_exclusive_group()
    start_from_argument_group.add_argument('--start', help='Start from a specific phase. Only works in incremental mode.')
    start_from_argument_group.add_argument('--restart-last-failed', action='store_true', help='Continue from the last failed phase. Only works in incremental mode.')
    start_from_argument_group.add_argument('--next-round', action='store_true', help='Start next round of incremental compilation. Only works in incremental mode, and only if the last round was successful.')

    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Dry run phases (no requests to LLMs)')
    args = parser.parse_args()

    if args.incremental:
        logger.info(f"Running in incremental mode from {args.incremental}")
        project_path = args.incremental
        project_name = os.path.basename(project_path)
        init = Init({
            "project_path": project_path,
        }, {
            "spec": text_file("spec.processed.md"),
        })

        if args.start:
            incremental_mode = IncrementalMode.compile_from_phase(args.start)
        elif args.restart_last_failed:
            incremental_mode = IncrementalMode.continue_from_last_failed()
        elif args.next_round:
            incremental_mode = IncrementalMode.next_round()
        else:
            logger.info(f"{Colors.BRIGHT_RED}Error: --incremental is provided, but no incremental mode is specified. Please specify one of --start, --restart-last-failed, or --next-round{Colors.END}")
            parser.print_help()
            return
    else:
        if not args.filepath:
            logger.info(f"{Colors.BRIGHT_RED}Error: filepath is required when not in incremental mode{Colors.END}")
            parser.print_help()
            return

        spec_file = args.filepath
        with open(spec_file, 'r') as f:
            raw_spec = f.read()

        spec_processor = SpecProcessor()
        spec = spec_processor.process(raw_spec)

        project_path = os.path.dirname(spec_file)
        project_name = os.path.basename(project_path)
        init = Init({
            "spec_file": spec_file,
            "spec": spec,
            "project_name": project_name,
            "project_path": project_path,
        }, {
            "spec": text_file("spec.processed.md"),
        })

        incremental_mode = IncrementalMode.clean()

    # from now, logging will be made in the project folder
    LoggingUtil.initialize_logger(f"{project_path}/codespeak.log")

    git_helper = GitHelper(project_path)

    head_hash = git_helper.get_head_hash()
    if not head_hash:
        logger.info(f"{Colors.BRIGHT_RED}Error: failed to get HEAD hash{Colors.END}")
        return
    
    key_sanitizer = SubstringBasedSanitizer([
        (os.path.abspath(project_path), "[ABSOLUTE_PROJECT_PATH]"),
        (project_path, "[PROJECT_PATH]"),
        (os.path.basename(project_path), "[PROJECT_NAME]"),
        (os.path.expanduser("~"), "[HOME]"),
    ])

    context = Context(
        git_helper=git_helper, 
        incremental_mode=incremental_mode, 
        anthropic_client = CachedAnthropic(base_dir=project_path, sanitizer=key_sanitizer),
        head_hash=head_hash, 
        dry_run=args.dry_run, 
        verbose=args.verbose)

    pm = PhaseManager(
        [
            init,
            GenerateDjangoProject(),
            ExtractEntities(),
            GenerateModels(),
            LintAndFix(),
            MakeMigrations(),
            Migrate(),
            GenerateDataModelTests(),
            ReconcileDataModelTests(),
            PlanScreens(),
            ExtractFacts(),
            ExtractLayouts(),
            ExecuteLayouts(),
            PlanWork(),
            ExecuteWork(),
            EnsureServerStarts(),
            Done(),
        ], 
        state_file=Path(project_path) / "codespeak_state.json",
        context=context,
    )

    try:
        pm.run_state_machine()
    finally:
        Flamegraph.save_report(project_name, f"{project_path}/durations.svg")

    logger.info(f"\nProject '{Colors.BOLD}{Colors.BRIGHT_CYAN}{project_name}{Colors.END}' generated in '{project_path}'.")
    logger.info(f"Start Django server via: python {project_path}/manage.py runserver")

    logger.info(f"Cache hits: {Colors.BRIGHT_GREEN}{context.anthropic_client.cache.hit_count}{Colors.END}")
    logger.info(f"Cache misses: {Colors.BRIGHT_RED}{context.anthropic_client.cache.miss_count}{Colors.END}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger = logging.getLogger("main")
        logger.info("\nInterrupted by user")
        sys.exit(1)

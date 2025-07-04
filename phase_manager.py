from __future__ import annotations
from abc import abstractmethod
from copy import deepcopy
import datetime
import difflib
import json
import os
import logging

from pathlib import Path
from typing import Any

from colors import Colors
from data_serializer import decode_data, encode_data, validate_schema_entry
from git_helper import GitHelper
from incremental_mode import IncrementalMode
from llm_cache.anthropic_cached import CachedAnthropic
from spec_processor import SpecProcessor
from utils.logging_util import LoggingUtil

class Context:
    def __init__(self, 
                 git_helper: GitHelper, 
                 incremental_mode: IncrementalMode, 
                 anthropic_client: CachedAnthropic,
                 head_hash: str, 
                 dry_run: bool = False, 
                 verbose: bool = False):
        self.verbose = verbose
        self.git_helper = git_helper
        self.dry_run = dry_run
        self.incremental_mode = incremental_mode
        self.anthropic_client = anthropic_client
        self.head_hash = head_hash

    # TODO(dsavvinov): remove the mock
    def get_old_revision_blob(self, file_path: str):
        # raise Exception("Incrementally generating screens is not supported yet")

        return self.git_helper.git_file_content_for_revision(
            file_path=file_path,
            revision_sha="e10028ff9e7b19df3ffec70799690eb9668b3510"
        )

class State:
    def __init__(self, data: dict | None = None, _internal_data: dict | None = None):
        self._data = data or {}
        self._internal_data = _internal_data or {}

    @property
    def data(self) -> dict:
        return deepcopy(self._data)

    @property
    def internal(self) -> dict:
        return deepcopy(self._internal_data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clone(self, delta: dict | None = None) -> "State":
        return self.__class__(
            data={
                **deepcopy(self._data), 
                **(delta or {})
            },
            _internal_data=deepcopy(self._internal_data)
        )
    
    def _clone_internal(self, internal_delta: dict | None = None) -> "State":
        return self.__class__(
            data=deepcopy(self._data),
            _internal_data={
                **deepcopy(self._internal_data), 
                **(internal_delta or {})
            }
        )

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

class Phase:
    @property
    def id(self) -> str:
        return self.__class__.__name__
    description: str = ""

    dry_run_aware = False # Allow running in dry run mode

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)

    @abstractmethod
    def run(self, state: State, context: Context) -> dict:
        pass

    def get_state_schema_entries(self) -> dict[str, dict]:
        return {}
    
    

class Init(Phase):
    description = "initialize project"
    dry_run_aware = True

    def __init__(self, initial_state: dict | None = None, state_schema: dict[str, dict] | None = None):
        self.initial_state = initial_state or {}
        self.state_schema = state_schema or {}

    def run(self, state: State, context: Context) -> dict:
        return self.initial_state
    
    def get_state_schema_entries(self) -> dict[str, dict]:
        return self.state_schema

class Done(Phase):
    description = "Final phase"

    def run(self, state: State, context: Context) -> dict:
        return {}

class StateMachineError(Exception):
    pass

class PhaseManager:    
    INITIAL_TRANSITION = "__initial"
    STATEMACHINE_ATTRIBUTE = "__statemachine"
    LAST_SUCCESSFUL_PHASE = "__last_successful"
    BRANCHED_FROM = "__branched_from_commit"
    HISTORY = "__history"
    SCHEMA = "__schema"
    VERSION = "__version"

    def __init__(
            self, 
            phases: list[Phase], 
            state_file: Path, 
            context: Context,
            initial_state: dict | None = None, 
        ):
        super().__init__()
        self.logger = logging.getLogger(__class__.__qualname__)
        self.phases = phases
        self.state_schema = self.calculate_schema(phases)

        self.state_file = state_file
        self.context = context
        
        self.current_state = State(
            data=initial_state or {},
            _internal_data=self.standard_fields()
        )

        if os.path.exists(state_file):
            self.logger.info(f"Loading state from {state_file}")
            self.load_state()
            self.logger.info(f"  * Last executed phase: {self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE)}")
            self.logger.info(f"  * Branched from commit: {self.current_state.get(self.BRANCHED_FROM)}")
        else:
            self.current_state[self.BRANCHED_FROM] = self.context.head_hash

    def calculate_schema(self, phases: list[Phase]) -> dict[str, dict]:
        BY_PHASE = "__by_phase"

        schema = {}
        for phase in phases:
            for key, value in phase.get_state_schema_entries().items():
                if key in schema:
                    raise StateMachineError(
                        f"Key '{key}' in state schema is contributed by {phase.id} and {schema[key][BY_PHASE]}")
                validate_schema_entry(value)
                schema[key] = {
                    **value,
                    BY_PHASE: phase.id
                }

        return schema

    def standard_fields(self):
        return {
                self.SCHEMA: self.state_schema,
                self.VERSION: "0.1.0"
            }

    def run_state_machine(self) -> State:
        # Branch out new execution branch
        branch_name = datetime.datetime.now().strftime("cs/%m-%d-%H%M%S")
        self.context.git_helper.create_and_checkout_branch(branch_name)

        phases_to_run = self.prepare_incremental_phases_run()
        if self.context.incremental_mode.type == IncrementalMode.CLEAN:
            self.logger.info(f"Running clean compilation")
        else:
            self.logger.info(f"Running in incremental mode:{self.context.incremental_mode}")
            phase_explanation = ""
            if (self.context.incremental_mode.type == IncrementalMode.RESTART_FROM_LAST_FAILED):
                phase_explanation = f" (inferred as the next phase after the last successful phase)"
            if (self.context.incremental_mode.type == IncrementalMode.COMPILE_FROM_PHASE):
                phase_explanation = f" (passed via --start)"
            if (self.context.incremental_mode.type == IncrementalMode.NEXT_ROUND):
                phase_explanation = f" (starting new compilation round)"
            self.logger.info(f"    Starting from the phase '{phases_to_run[0].id}'{phase_explanation}")

            if self.context.incremental_mode.type == IncrementalMode.NEXT_ROUND:
                self.logger.info(f"    Spec diff: {self.current_state.get('spec_diff')}")

        if self.context.incremental_mode.type == IncrementalMode.NEXT_ROUND and self.current_state.get("spec_diff") == "":
            self.logger.info(f"{Colors.BRIGHT_GREEN}Nothing to do: no spec diff found{Colors.END}")
            # todo(dsavvinov): improve this
            exit(0)

        # Run the phases that need to be run
        for phase in phases_to_run:
            self.current_phase = phase        

            def append_to_history(data: dict | None = None) -> dict:
                return {
                    self.HISTORY: [
                        *self.current_state.internal.get(self.HISTORY, []),
                        {
                            "phase": self.current_phase.id,
                            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                            **(data or {})
                        }
                    ]
                }
            
            standard_fields = self.standard_fields()

            try:
                self.context.git_helper.ensure_clean_working_tree()
                
                dry_run_suffix_if_any = " (dry run)" if self.context.dry_run else ""

                with LoggingUtil.Span(f"Phase {self.current_phase.id}{dry_run_suffix_if_any}"):
                    # self.logger.info(f"{Colors.BRIGHT_YELLOW}Running phase: {self.current_phase.id}{dry_run_suffix_if_any}{Colors.END}")
                    if self.context.dry_run and not self.current_phase.dry_run_aware:
                        delta = {f"phase_{self.current_phase.id}": "dry-run"}
                    else:
                        delta = phase.run(self.current_state, self.context)

                    self.logger.info(f"{Colors.BRIGHT_GREEN}Finished phase: {self.current_phase.id}{dry_run_suffix_if_any}{Colors.END}")

                if not isinstance(delta, dict):
                    raise StateMachineError(f"Phase {self.current_phase.id} returned a non-dict object")
                
                self.current_state = self.current_state.clone(delta)._clone_internal({
                    self.LAST_SUCCESSFUL_PHASE: self.current_phase.id,
                    **standard_fields,
                    **append_to_history()
                })
            except BaseException as e:
                self.logger.info(f"Error running phase {self.current_phase.id}: {str(e) or type(e).__name__}")
                self.save_state(self.current_state._clone_internal({
                    **standard_fields,
                    **append_to_history({"error": f"{type(e).__name__}: {str(e)}"})
                }), phase)
                raise e

            self.save_state(self.current_state, phase)

        return self.current_state

    def compute_state_to_start_from(self, incremental_mode: IncrementalMode) -> Phase:
        """
        Computes the first phase to run w.r.t. passed self.context.incremental_mode, and asserts that 
        the requested self.context.incremental_mode is consistent with the current state

        Returns the first phase to run (for example, last failed phase for --restart-last-failed)
        """
        if incremental_mode.type == IncrementalMode.CLEAN:
            return self.phases[0]
        
        last_successful_id = self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE)
        assert last_successful_id, f"Expected to have LAST_SUCCESSFUL_PHASE in incremental_mode {incremental_mode}, bot none found. Full state:\n{self.current_state.internal}"
        
        last_successful = next((phase for phase in self.phases if phase.id == last_successful_id), None)
        assert last_successful, f"Can't find phase with id {last_successful_id} in {self.phases}"
        
        if incremental_mode.type == IncrementalMode.RESTART_FROM_LAST_FAILED:
            first_failed = self.next_phase(last_successful)
            if not first_failed:
                raise StateMachineError(
                    f"Last successful phase {last_successful.id} is the last phase, can't retry from last failed. "
                    f"If you want to start the next compilation round, use '--incremental --next-round' (or './dev compile)'"
                )
            
            return first_failed
        
        if incremental_mode.type == IncrementalMode.COMPILE_FROM_PHASE:
            phase_names = [phase.id for phase in self.phases]
            assert incremental_mode.phase_name, f"IncrementalMode.COMPILE_FROM_PHASE doesn't have phase_name"

            last_successful_index = self.phases.index(last_successful) # Guaranteed to be found, see asserts above
            
            sf_index = phase_names.index(incremental_mode.phase_name)
            assert sf_index >= 0, f"Phase {incremental_mode.phase_name} not found in {self.phases}"

            if sf_index > last_successful_index + 1:
                raise StateMachineError(
                    f"Phase {incremental_mode.phase_name} is not a valid starting point: it's order index ({sf_index})" 
                    f"is after the last successful phase {last_successful.id} ({last_successful_index})"
                )

            return self.phases[sf_index]
        

        if incremental_mode.type == IncrementalMode.NEXT_ROUND:
            if not isinstance(last_successful, Done):
                raise StateMachineError(
                    f"Last successful phase {last_successful.id} is not a Done phase, can't start next round. "
                    f"Finish the previous round by running '--incremental --restart-last-failed' (./dev retry)"
                )
            
            return self.phases[0]
        
        raise StateMachineError(f"Unhandled incremental mode: {incremental_mode.type}")

    def prepare_incremental_phases_run(self) -> list[Phase]:
        """
        Computes the first phase to run w.r.t. passed self.context.incremental_mode

        Ensures that the state on disk and in memory is consistent with the work we're about to do.

        Returns the list of phases to run.
        """
        first_phase_to_run: Phase = self.compute_state_to_start_from(self.context.incremental_mode)

        previous_phase = self.previous_phase(first_phase_to_run)
        if previous_phase and previous_phase.id != self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE):
            # Last successful phase was overridden by --start-from, adjust our internal state
            self.current_state = self.current_state._clone_internal(
                {
                    self.LAST_SUCCESSFUL_PHASE: previous_phase.id
                }
            )

        # todo(dsavvinov): extact into a separate phases
        if previous_phase:
            # Restore working tree state to the last successful phase
            hash_of_last_successful = self.context.git_helper.find_commit_hash_by_message(f"phase: {previous_phase.id}")
            if not hash_of_last_successful:
                raise StateMachineError(f"Can't find commit hash for phase {previous_phase.id}, aborting")
        
            self.context.git_helper.ensure_clean_working_tree() # do not overwrite dirty working tree
            self.context.git_helper.restore_state_to(hash_of_last_successful)

        if self.context.incremental_mode.type == IncrementalMode.NEXT_ROUND:
            # defensive: ensure that the last commit isn't an util-commit by Codespeak
            author = self.context.git_helper.get_head_author()
            if not author:
                raise StateMachineError("Can't get HEAD author, aborting")

            if author == "Codespeak":
                raise StateMachineError("Can't start new compilation round: the last commit is an util-commit by Codespeak. Make a change to the spec, commit it, and try again")
            
            # Reset BRANCHED_FROM to the last commit by the user
            previous_spec_commit: str | None = self.current_state.get(self.BRANCHED_FROM)
            assert previous_spec_commit, f"Expected to have {self.BRANCHED_FROM} in state, but none found. Full state:\n{self.current_state.internal}"
            
            self.current_state[self.BRANCHED_FROM] = self.context.head_hash

            # Read new spec
            # TODO(dsavvinov): extact into a separate phase, deduplicate with the code in main.py
            spec_file_path = self.current_state["spec_file"]
            with open(spec_file_path, 'r') as f:
                raw_spec = f.read()

            spec_processor = SpecProcessor()
            new_spec = spec_processor.process(raw_spec)

            self.current_state["spec"] = new_spec

            with open(os.path.join(self.current_state["project_path"], "spec.processed.md"), "r") as f:
                old_processed_spec = f.read()

            diff = difflib.unified_diff(
                old_processed_spec.splitlines(keepends=True),
                new_spec.splitlines(keepends=True),
                lineterm=''
            )

            spec_diff = ''.join(diff)

            self.current_state["spec_diff"] = spec_diff

        start_index = self.phases.index(first_phase_to_run)
        return self.phases[start_index:]

    def load_state(self):
        with open(self.state_file, "r") as f:
            data = decode_data(json.load(f), self.state_schema, os.path.dirname(self.state_file))
            internal = data.pop(self.STATEMACHINE_ATTRIBUTE, {})

            self.current_state = State(data=data, _internal_data=internal)
    
    def next_phase(self, phase: Phase) -> Phase | None:
        """
        Get the next phase after the given phase, or None if it's the last phase.
        """
        current_index = self.phases.index(phase)
        if current_index == len(self.phases) - 1:
            return None  # This is the last phase
        return self.phases[current_index + 1]
    
    def previous_phase(self, phase: Phase) -> Phase | None:
        """
        Get the previous phase before the given phase, or None if it's the first phase.
        """
        current_index = self.phases.index(phase)
        if current_index == 0:
            return None  # This is the first phase
        return self.phases[current_index - 1]

    def save_state(self, state, phase: Phase):
        if self.state_file:
            with open(self.state_file, "w") as f:
                json.dump(encode_data({
                    self.STATEMACHINE_ATTRIBUTE: state.internal,
                    **state.data
                }, self.state_schema, os.path.dirname(self.state_file)), f, indent=4)

            self.context.git_helper.save(title=f"fixup! {state.get(self.BRANCHED_FROM)}", description=f'phase: {phase.id}\n{phase.description}')
    
    
from __future__ import annotations
from abc import abstractmethod
from copy import deepcopy
import datetime
import json
import os

from pathlib import Path
from typing import Any, Dict

from colors import Colors
from data_serializer import decode_data, encode_data, json_file, validate_schema_entry
from git_helper import GitHelper

class Context:
    def __init__(self, git_helper: GitHelper, verbose: bool = False):
        self.verbose = verbose
        self.git_helper = git_helper

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

    def __init__(self):
        pass

    @abstractmethod
    def run(self, state: State, context: Context) -> dict:
        pass

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {}

class Init(Phase):
    description = "initialize project"

    def __init__(self, initial_state: dict | None = None, state_schema: Dict[str, dict] | None = None):
        self.initial_state = initial_state or {}
        self.state_schema = state_schema or {}

    def run(self, state: State, context: Context) -> dict:
        return self.initial_state
    
    def get_state_schema_entries(self) -> Dict[str, dict]:
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
            head_hash: str,
            initial_state: dict | None = None, 
            start_from: str | None = None,
        ):
        self.phases = phases
        self.state_schema = self.calculate_schema(phases)

        self.state_file = state_file
        self.context = context
        self.start_from = start_from
        
        self.current_state = State(
            data=initial_state or {},
            _internal_data=self.standard_fields()
        )

        if os.path.exists(state_file):
            print(f"Loading state from {state_file}")
            self.load_state()
            print(f"  * Last executed phase: {self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE)}")
            print(f"  * Branched from commit: {self.current_state.internal.get(self.BRANCHED_FROM)}")
        else:
            self.current_state[self.BRANCHED_FROM] = head_hash

    def calculate_schema(self, phases: list[Phase]) -> Dict[str, dict]:
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
        phase_names = [phase.id for phase in self.phases]

        # Compute adjusted last successful phase (might be needed if start_from is provided)
        adjusted_last_successful: Phase | None = self.calculate_last_successfull_state()

        self.current_state = self.current_state._clone_internal(
            {
                self.LAST_SUCCESSFUL_PHASE: adjusted_last_successful.id if adjusted_last_successful else None
            }
        )

        # Branch out new execution branch
        branch_name = datetime.datetime.now().strftime("cs/%m-%d-%H%M%S")
        self.context.git_helper.create_and_checkout_branch(branch_name)

        # Restore state to the last successful phase
        if adjusted_last_successful:
            hash_of_last_successful = self.context.git_helper.find_commit_hash_by_message(f"phase: {adjusted_last_successful.id}")
            if not hash_of_last_successful:
                print(f"Can't find commit hash for phase {adjusted_last_successful.id}, aborting")
                return self.current_state
        
            self.context.git_helper.ensure_clean_working_tree() # do not overwrite dirty working tree
            self.context.git_helper.restore_state_to(hash_of_last_successful)
        else:
            # Starting from the first phase, so need to restore state to the BRANCHED_FROM commit
            self.context.git_helper.restore_state_to(self.current_state.get(self.BRANCHED_FROM))

        # Compute phases to run
        start_index = phase_names.index(adjusted_last_successful.id) + 1 if adjusted_last_successful else 0
        phases_to_run = self.phases[start_index:]

        print(f"Resuming from the last successful phase: {adjusted_last_successful.id if adjusted_last_successful else 'None'}\nFirst phase to run: {phases_to_run[0].id}")

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
                
                print(f"{Colors.BRIGHT_YELLOW}Running phase: {self.current_phase.id}{Colors.END}")
                delta = phase.run(self.current_state, self.context)
                print(f"{Colors.BRIGHT_GREEN}Finished phase: {self.current_phase.id}{Colors.END}")


                if not isinstance(delta, dict):
                    raise StateMachineError(f"Phase {self.current_phase.id} returned a non-dict object")
                
                self.current_state = self.current_state.clone(delta)._clone_internal({
                    self.LAST_SUCCESSFUL_PHASE: self.current_phase.id,
                    **standard_fields,
                    **append_to_history()
                })
            except BaseException as e:
                print(f"Error running phase {self.current_phase.id}: {str(e) or type(e).__name__}")
                self.save_state(self.current_state._clone_internal({
                    **standard_fields,
                    **append_to_history({"error": f"{type(e).__name__}: {str(e)}"})
                }), phase)
                raise e

            self.save_state(self.current_state, phase)

        return self.current_state

    def calculate_last_successfull_state(self) -> Phase | None:
        last_successful_id = self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE)
        last_successful = next((phase for phase in self.phases if phase.id == last_successful_id), None)

        if not self.start_from:
            return last_successful
        
        phase_names = [phase.id for phase in self.phases]

        sf_index = phase_names.index(self.start_from)

        if sf_index < 0:
            raise StateMachineError(f"Phase {self.start_from} not found")
        
        if sf_index == 0:
            return None # start from is the first phase, so last successful is None
            
        if last_successful and sf_index > phase_names.index(last_successful.id) + 1:
            raise StateMachineError(f"Phase {self.start_from} is not a valid starting point: it's after last successful phase {last_successful}")

        return self.phases[sf_index - 1]

    def load_state(self):
        with open(self.state_file, "r") as f:
            data = decode_data(json.load(f), self.state_schema, os.path.dirname(self.state_file))
            internal = data.pop(self.STATEMACHINE_ATTRIBUTE, {})

            self.current_state = State(data=data, _internal_data=internal)

    def save_state(self, state, phase: Phase):
        if self.state_file:
            with open(self.state_file, "w") as f:
                json.dump(encode_data({
                    self.STATEMACHINE_ATTRIBUTE: state.internal,
                    **state.data
                }, self.state_schema, os.path.dirname(self.state_file)), f, indent=4)

            self.context.git_helper.save(title=f"fixup! {state.get(self.BRANCHED_FROM)}", description=f'phase: {phase.id}\n{phase.description}')
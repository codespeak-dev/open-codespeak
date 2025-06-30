from abc import abstractmethod
from copy import deepcopy
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict

from data_serializer import decode_data, encode_data, json_file, validate_schema_entry

class Context:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

class State:
    def __init__(self, data: dict = None, _internal_data: dict = None):
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

    def clone(self, delta: dict = None) -> "State":
        return self.__class__(
            data={
                **deepcopy(self._data), 
                **(delta or {})
            },
            _internal_data=deepcopy(self._internal_data)
        )
    
    def _clone_internal(self, internal_delta: dict = None) -> "State":
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
    def __init__(self):
        pass

    @abstractmethod
    def run(self, state: State, context: Context = None) -> dict:
        pass

    def cleanup(self, state: State, context: Context = None):
        pass

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {}

class Init(Phase):
    def __init__(self, initial_state: dict | None = None, state_schema: Dict[str, dict] | None = None):
        self.initial_state = initial_state or {}
        self.state_schema = state_schema or {}

    def run(self, state: State, context: Context = None) -> dict:
        return self.initial_state
    
    def get_state_schema_entries(self) -> Dict[str, dict]:
        return self.state_schema

class Done(Phase):
    def run(self, state: State, context: Context = None) -> dict:
        return {}

class StateMachineError(Exception):
    pass

class PhaseManager:    
    INITIAL_TRANSITION = "__initial"
    STATEMACHINE_ATTRIBUTE = "__statemachine"
    LAST_SUCCESSFUL_PHASE = "__last_successful"
    LAST_FAILED_PHASE = "__last_failed"
    HISTORY = "__history"
    SCHEMA = "__schema"

    def __init__(
            self, 
            phases: list[Phase], 
            state_file: Path, 
            initial_state: dict | None = None, 
            context: Context = None,
            start_from: str = None
        ):
        self.phases = phases
        self.state_schema = self.calculate_schema(phases)

        self.state_file = state_file
        self.context = context or Context()
        self.start_from = start_from
        
        self.current_state = State(
            data=initial_state or {},
            _internal_data={
                self.SCHEMA: self.state_schema
            }
        )

        if os.path.exists(state_file):
            print(f"Loading state from {state_file}")
            self.load_state()
            print(f"  * Last executed phase: {self.current_state.internal.get(self.LAST_SUCCESSFUL_PHASE)}")

    def calculate_schema(self, phases: list[Phase]) -> Dict[str, dict]:
        BY_PHASE = "__by_phase"

        schema = {}
        for phase in phases:
            for key, value in phase.get_state_schema_entries().items():
                if key in schema:
                    raise StateMachineError(
                        f"Key '{key}' in state schema is contributed by {phase.__class__.__name__} and {schema[key][BY_PHASE]}")
                validate_schema_entry(value)
                schema[key] = {
                    **value,
                    BY_PHASE: phase.__class__.__name__
                }

        return schema

    def run_state_machine(self) -> State:
        phase_names = [phase.__class__.__name__ for phase in self.phases]
        state = self.current_state
        # print(state.data)
        for phase in self.phases:
            current_phase = phase.__class__.__name__        
            last_successful = state.internal.get(self.LAST_SUCCESSFUL_PHASE)

            last_successful = self.calculate_starting_state(phase_names, last_successful)                

            if last_successful in phase_names and phase_names.index(last_successful) >= phase_names.index(current_phase):
                print(f"Phase {current_phase} has already been executed, skipping...")
                continue

            last_failed_phase = state.internal.get(self.LAST_FAILED_PHASE)
            if last_failed_phase == current_phase and last_failed_phase != last_successful:
                print(f"Phase {current_phase} failed last time, cleaning up...")
                phase.cleanup(state, self.context)

            def append_to_history(data: dict | None = None) -> dict:
                return {
                    self.HISTORY: [
                        *state.internal.get(self.HISTORY, []),
                        {
                            "phase": current_phase,
                            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                            **(data or {})
                        }
                    ]
                }
            
            standard_fields = {
                self.SCHEMA: self.state_schema,
            }

            try:
                delta = phase.run(state, self.context)
                if not isinstance(delta, dict):
                    raise StateMachineError(f"Phase {current_phase} returned a non-dict object")
                
                state = state.clone(delta)._clone_internal({
                    self.LAST_SUCCESSFUL_PHASE: current_phase,
                    **standard_fields,
                    **append_to_history()
                })
            except BaseException as e:
                print(f"Error running phase {current_phase}: {str(e) or type(e).__name__}")
                self.save_state(state._clone_internal({
                    self.LAST_FAILED_PHASE: current_phase,
                    **standard_fields,
                    **append_to_history({"error": f"{type(e).__name__}: {str(e)}"})
                }))
                raise e

            self.save_state(state)

        return state

    def calculate_starting_state(self, phase_names, last_successful):
        if self.start_from:
            sf_index = phase_names.index(self.start_from)
            if sf_index < 0:
                raise StateMachineError(f"Phase {self.start_from} not found")
                
            if last_successful and sf_index > phase_names.index(last_successful) + 1:
                raise StateMachineError(f"Phase {self.start_from} is not a valid starting point")

            if sf_index > 0:
                last_successful = self.phases[sf_index - 1].__class__.__name__
        return last_successful

    def load_state(self):
        with open(self.state_file, "r") as f:
            data = decode_data(json.load(f), self.state_schema, os.path.dirname(self.state_file))
            internal = data.pop(self.STATEMACHINE_ATTRIBUTE, {})

            self.current_state = State(data=data, _internal_data=internal)

    def save_state(self, state):
        if self.state_file:
            with open(self.state_file, "w") as f:
                json.dump(encode_data({
                    self.STATEMACHINE_ATTRIBUTE: state.internal,
                    **state.data
                }, self.state_schema, os.path.dirname(self.state_file)), f, indent=4)


if __name__ == "__main__":

    class Step1(Phase):
        def run(self, state: State, context: Context = None) -> dict:
            print(state.data)
            return {
                "project_name": "My Project"
            }
        
        def get_state_schema_entries(self) -> Dict[str, dict]:
            return {}

    class Step2(Phase):
        def run(self, state: State, context: Context = None) -> dict:
            return {
                "entities": [
                    {
                        "name": "User",
                        "fields": [
                            {"name": "name", "type": "string"},
                            {"name": "email", "type": "string"}
                        ]
                    }
                ]
            }
        
        def get_state_schema_entries(self) -> Dict[str, dict]:
            return {
                "entities": json_file("entities.json")
            }
        
    class Fail(Phase):
        def run(self, state: State, context: Context = None) -> dict:
            print(state.data)
            # pass
            raise Exception("Failed")
            return {}

    pm = PhaseManager([
        Step1(),
        Step2(),
        Fail()
    ], lambda state: "test_outputs/state.json", 
    # start_from="Step1"
    )
    try:
        pm.run_state_machine()
    except StateMachineError as e:
        print(f"Error: {e}")
    finally:
        with open("test_outputs/state.json", "r") as f:
            print(f.read())
        # os.remove("test_outputs/state.json")

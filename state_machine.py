from abc import abstractmethod
from copy import deepcopy
import datetime
import json
import os
from typing import Any, Callable, Dict

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

class Transition:
    def __init__(self):
        pass

    @abstractmethod
    def run(self, state: State, context: Context = None) -> dict:
        pass

    def cleanup(self, state: State, context: Context = None):
        pass

    def get_state_schema_entries(self) -> Dict[str, dict]:
        return {}

class Start(Transition):
    def __init__(self, initial_state: dict, state_schema: Dict[str, dict]):
        self.initial_state = initial_state
        self.state_schema = state_schema

    def run(self, state: State, context: Context = None) -> dict:
        return self.initial_state
    
    def get_state_schema_entries(self) -> Dict[str, dict]:
        return self.state_schema

class Done(Transition):
    def run(self, state: State, context: Context = None) -> dict:
        return {}

class StateMachineError(Exception):
    pass

class PersistentStateMachine:    
    INITIAL_TRANSITION = "__initial"
    STATEMACHINE_ATTRIBUTE = "__statemachine"
    LAST_SUCCESSFUL_TRANSITION = "__last_successful"
    LAST_FAILED_TRANSITION = "__last_failed"
    HISTORY = "__history"
    SCHEMA = "__schema"

    def __init__(
            self, 
            transitions: list[Transition], 
            state_file: Callable[[State], str | None], 
            initial_state: dict | None = None, 
            context: Context = None,
            start_from: str = None
        ):
        self.transitions = transitions
        self.state_schema = self.calculate_schema(transitions)

        self.state_file = state_file
        self.context = context or Context()
        self.start_from = start_from
        
        self.current_state = State(
            data=initial_state or {},
            _internal_data={
                # self.LAST_SUCCESSFUL_TRANSITION: self.INITIAL_TRANSITION,
                self.SCHEMA: self.state_schema
            }
        )

        state_file = self.state_file(self.current_state)
        if state_file and os.path.exists(state_file):
            print(f"Loading state from {state_file}")
            self.load_state(state_file)
            print(f"  * Last executed transition: {self.current_state.internal.get(self.LAST_SUCCESSFUL_TRANSITION)}")

    def calculate_schema(self, transitions: list[Transition]) -> Dict[str, dict]:
        BY_TRANSITION = "__by_transition"

        schema = {}
        for transition in transitions:
            for key, value in transition.get_state_schema_entries().items():
                if key in schema:
                    raise StateMachineError(
                        f"Key '{key}' in state schema is contributed by {transition.__class__.__name__} and {schema[key][BY_TRANSITION]}")
                validate_schema_entry(value)
                schema[key] = {
                    **value,
                    BY_TRANSITION: transition.__class__.__name__
                }

        return schema

    def run_state_machine(self) -> State:
        transition_names = [transition.__class__.__name__ for transition in self.transitions]
        state = self.current_state
        # print(state.data)
        for transition in self.transitions:
            current_transition = transition.__class__.__name__        
            last_successful = state.internal.get(self.LAST_SUCCESSFUL_TRANSITION)

            if self.start_from:
                sf_index = transition_names.index(self.start_from)
                if sf_index < 0:
                    raise StateMachineError(f"Transition {self.start_from} not found")
                
                if last_successful and sf_index > transition_names.index(last_successful) + 1:
                    raise StateMachineError(f"Transition {self.start_from} is not a valid starting point")

                if sf_index > 0:
                    last_successful = self.transitions[sf_index - 1].__class__.__name__                

            if last_successful in transition_names and transition_names.index(last_successful) >= transition_names.index(current_transition):
                print(f"Transition {current_transition} has already been executed, skipping...")
                continue

            last_failed_transition = state.internal.get(self.LAST_FAILED_TRANSITION)
            if last_failed_transition == current_transition and last_failed_transition != last_successful:
                print(f"Transition {current_transition} failed last time, cleaning up...")
                transition.cleanup(state, self.context)

            def append_to_history(data: dict | None = None) -> dict:
                return {
                    self.HISTORY: [
                        *state.internal.get(self.HISTORY, []),
                        {
                            "transition": current_transition,
                            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                            **(data or {})
                        }
                    ]
                }
            
            standard_fields = {
                self.SCHEMA: self.state_schema,
            }

            try:
                delta = transition.run(state, self.context)
                if not isinstance(delta, dict):
                    raise StateMachineError(f"Transition {current_transition} returned a non-dict object")
                
                state = state.clone(delta)._clone_internal({
                    self.LAST_SUCCESSFUL_TRANSITION: current_transition,
                    **standard_fields,
                    **append_to_history()
                })
            except Exception as e:
                print(f"Error running transition {current_transition}: {e}")
                self.save_state(state._clone_internal({
                    self.LAST_FAILED_TRANSITION: current_transition,
                    **standard_fields,
                    **append_to_history({"error": str(e)})
                }))
                raise e

            self.save_state(state)
            # print(state.data)

        return state

    def load_state(self, state_file):
        with open(state_file, "r") as f:
            data = decode_data(json.load(f), self.state_schema, os.path.dirname(state_file))
            internal = data.pop(self.STATEMACHINE_ATTRIBUTE, {})

            self.current_state = State(data=data, _internal_data=internal)

    def save_state(self, state):
        state_file = self.state_file(state)
        if state_file:
            with open(state_file, "w") as f:
                json.dump(encode_data({
                    self.STATEMACHINE_ATTRIBUTE: state.internal,
                    **state.data
                }, self.state_schema, os.path.dirname(state_file)), f, indent=4)


if __name__ == "__main__":

    class Step1(Transition):
        def run(self, state: State, context: Context = None) -> dict:
            print(state.data)
            return {
                "project_name": "My Project"
            }
        
        def get_state_schema_entries(self) -> Dict[str, dict]:
            return {}

    class Step2(Transition):
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
        
    class Fail(Transition):
        def run(self, state: State, context: Context = None) -> dict:
            print(state.data)
            # pass
            raise Exception("Failed")
            return {}

    sm = PersistentStateMachine([
        Step1(),
        Step2(),
        Fail()
    ], lambda state: "test_outputs/state.json", 
    # start_from="Step1"
    )
    try:
        sm.run_state_machine()
    except StateMachineError as e:
        print(f"Error: {e}")
    finally:
        with open("test_outputs/state.json", "r") as f:
            print(f.read())
        # os.remove("test_outputs/state.json")

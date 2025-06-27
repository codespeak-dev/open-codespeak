from abc import abstractmethod
from copy import deepcopy
import datetime
import json
import os
from typing import Any, Callable, Dict


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
    def run(self, state: State, context: Context = None) -> State:
        pass

    def cleanup(self, state: State, context: Context = None):
        pass

class Done(Transition):
    def run(self, state: State, context: Context = None) -> State:
        return state.clone()

class StateMachineError(Exception):
    pass

class PersistentStateMachine:    
    INITIAL_TRANSITION = "__initial"
    STATEMACHINE_ATTRIBUTE = "__statemachine"
    LAST_EXECUTED_TRANSITION = "__last"
    LAST_FAILED_TRANSITION = "__last_failed"
    HISTORY = "__history"

    def __init__(
            self, 
            transitions: list[Transition], 
            initial_state: dict, 
            state_file: Callable[[State], str | None], 
            context: Context = None            
        ):
        self.transitions = transitions
        self.state_file = state_file
        self.context = context or Context()
        self.current_state = State(
            data=initial_state,
            _internal_data={
                self.LAST_EXECUTED_TRANSITION: self.INITIAL_TRANSITION,                 
            }
        )

        state_file = self.state_file(self.current_state)
        if state_file and os.path.exists(state_file):
            print(f"Loading state from {state_file}")
            self.load_state(state_file)
            print(f"  * Last executed transition: {self.current_state.internal.get(self.LAST_EXECUTED_TRANSITION)}")

    def run_state_machine(self) -> State:
        transition_names = [transition.__class__.__name__ for transition in self.transitions]
        state = self.current_state
        # print(state.data)
        for transition in self.transitions:
            current_transition = transition.__class__.__name__        
            last_executed_transition = state.internal.get(self.LAST_EXECUTED_TRANSITION)

            if last_executed_transition in transition_names and transition_names.index(last_executed_transition) >= transition_names.index(current_transition):
                print(f"Transition {current_transition} has already been executed, skipping...")
                continue

            last_failed_transition = state.internal.get(self.LAST_FAILED_TRANSITION)
            if last_failed_transition == current_transition and last_failed_transition != last_executed_transition:
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

            try:
                new_state = transition.run(state, self.context)
                if not new_state or not isinstance(new_state, State):
                    raise StateMachineError(f"Transition {current_transition} returned a non-State object")
                
                state = new_state._clone_internal({
                    self.LAST_EXECUTED_TRANSITION: current_transition,
                    **append_to_history()
                })
            except Exception as e:
                print(f"Error running transition {current_transition}: {e}")
                self.save_state(state._clone_internal({
                    self.LAST_FAILED_TRANSITION: current_transition,
                    **append_to_history({"error": str(e)})
                }))
                raise e

            self.save_state(state)
            # print(state.data)

        return state

    def load_state(self, state_file):                    
        with open(state_file, "r") as f:
            data = json.load(f)
            internal = data.pop(self.STATEMACHINE_ATTRIBUTE, {})

            self.current_state = State(data=data, _internal_data=internal)

    def save_state(self, state):
        state_file = self.state_file(state)
        if state_file:
            with open(state_file, "w") as f:
                json.dump({
                    self.STATEMACHINE_ATTRIBUTE: state.internal,
                    **state.data
                }, f, indent=4)


if __name__ == "__main__":

    class Step1(Transition):
        def run(self, state: State, context: Context = None) -> State:
            return state.clone({
                "project_name": "My Project"
            })

    class Step2(Transition):
        def run(self, state: State, context: Context = None) -> State:
            return state.clone({
                "entities": [
                    {
                        "name": "User",
                        "fields": [
                            {"name": "name", "type": "string"},
                            {"name": "email", "type": "string"}
                        ]
                    }
                ]
            })
    class Fail(Transition):
        def run(self, state: State, context: Context = None) -> State:
            # pass
            # raise Exception("Failed")
            return State({"done": True})

    sm = PersistentStateMachine([
        Step1(),
        Step2(),
        Fail()
    ], {}, lambda state: "state.json")
    try:
        sm.run_state_machine()
    except StateMachineError as e:
        print(f"Error: {e}")
    finally:
        with open("state.json", "r") as f:
            print(f.read())

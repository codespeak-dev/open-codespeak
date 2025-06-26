from abc import abstractmethod
from copy import deepcopy
import datetime
import json
import os
from typing import Any, Callable


class State:
    def __init__(self, data: dict = None):
        self._data = data or {}
    
    @property
    def data(self) -> dict:
        return deepcopy(self._data)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
    
    def clone(self, delta: dict = None) -> "State":
        return self.__class__({**deepcopy(self._data), **(delta or {})})
    
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
    def run(self, state: State) -> State:
        pass

    def cleanup(self, state: State):
        pass

class Done(Transition):
    def run(self, state: State) -> State:
        return state.clone()

class PersistentStateMachine:
    INITIAL_TRANSITION = "__initial"
    LAST_EXECUTED_TRANSITION = "__last"
    LAST_FAILED_TRANSITION = "__last_failed"
    FAILURE_INFO = "__failure_info"
    HISTORY = "__history"
    
    def __init__(self, transitions: list[Transition], initial_state: dict, state_file: Callable[[State], str | None]):
        self.transitions = transitions
        self.state_file = state_file
        self.current_state = State({self.LAST_EXECUTED_TRANSITION: self.INITIAL_TRANSITION, **initial_state})

        state_file = self.state_file(self.current_state)
        if state_file and os.path.exists(state_file):
            print(f"Loading state from {state_file}")
            with open(state_file, "r") as f:
                self.current_state = State(json.load(f))
            print(f"  * Last executed transition: {self.current_state.get(self.LAST_EXECUTED_TRANSITION)}")

    def run_state_machine(self) -> State:
        transition_names = [transition.__class__.__name__ for transition in self.transitions]
        state = self.current_state
        # print(state.data)
        for transition in self.transitions:
            current_transition = transition.__class__.__name__        
            last_executed_transition = state.get(self.LAST_EXECUTED_TRANSITION)

            if last_executed_transition in transition_names and transition_names.index(last_executed_transition) >= transition_names.index(current_transition):
                print(f"Transition {current_transition} has already been executed, skipping...")
                continue
            
            last_failed_transition = state.get(self.LAST_FAILED_TRANSITION)
            if last_failed_transition == current_transition and last_failed_transition != last_executed_transition:
                print(f"Transition {current_transition} failed last time, cleaning up...")
                transition.cleanup(state)

            def append_to_history(data):
                return {
                    self.HISTORY: [
                        *state.get(self.HISTORY, []),
                        {
                            "transition": current_transition,
                            "timestamp": datetime.datetime.now().isoformat(),
                            **data
                        }
                    ]
                }

            try:
                state = transition.run(state).clone({
                    self.LAST_EXECUTED_TRANSITION: current_transition,
                    **append_to_history({})
                })
            except Exception as e:
                print(f"Error running transition {current_transition}: {e}")
                self.save_state(state.clone({
                    self.LAST_FAILED_TRANSITION: current_transition,
                    **append_to_history({"error": str(e)})
                }))
                raise e

            self.save_state(state)
            # print(state.data)

        return state

    def save_state(self, state):
        state_file = self.state_file(state)
        if state_file:
            with open(state_file, "w") as f:
                json.dump(state.data, f, indent=4)

if __name__ == "__main__":
    
    class Step1(Transition):
        def run(self, state: State) -> State:
            return state.clone({
                "project_name": "My Project"
            })

    class Step2(Transition):
        def run(self, state: State) -> State:
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

    sm = PersistentStateMachine([
        Step1(),
        Step2()
    ], {}, "state.json")
    sm.run_state_machine()
    # print(sm.state.data)
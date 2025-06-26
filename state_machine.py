from abc import abstractmethod
from copy import deepcopy
import json
import os
from typing import Any


class State:
    def __init__(self, data: dict = None):
        self._data = data or {}
    
    @property
    def data(self) -> dict:
        return deepcopy(self._data)
    
    def get(self, key: str) -> Any:
        return self._data[key]
    
    def clone(self, delta: dict = None) -> "State":
        return self.__class__({**deepcopy(self._data), **(delta or {})})
    
    def __getitem__(self, key: str) -> Any:
        return self._data[key]
    
    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

class Transition:
    def __init__(self):
        pass

    @abstractmethod
    def run(self, state: State) -> State:
        pass

    def cleanup(self):
        pass

class Done(Transition):
    def run(self, state: State) -> State:
        return state.clone()

class PersistentStateMachine:
    LAST_EXECUTED_TRANSITION = "__last"
    INITIAL_TRANSITION = "__initial"
    
    def __init__(self, transitions: list[Transition], initial_state: dict, state_file: str):
        self.transitions = transitions
        self.state_file = state_file
        self.current_state = State({self.LAST_EXECUTED_TRANSITION: self.INITIAL_TRANSITION, **initial_state})

        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                self.current_state = State(json.load(f))

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
            
            state = transition.run(state).clone({
                self.LAST_EXECUTED_TRANSITION: transition.__class__.__name__
            })

            with open(self.state_file, "w") as f:
                json.dump(state.data, f, indent=4)
            # print(state.data)
        return state

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
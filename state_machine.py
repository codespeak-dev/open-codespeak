from abc import abstractmethod
from copy import deepcopy
from typing import Any


class State:
    def __init__(self, data: dict = None):
        self._data = {"last_executed_transition": "Initial", **(data or {})}
    
    @property
    def data(self) -> dict:
        return deepcopy(self._data)
    
    def get(self, key: str) -> Any:
        return self._data[key]
    
    def clone(self, delta: dict = None) -> "State":
        return self.__class__({**deepcopy(self._data), **(delta or {})})

class Transition:
    def __init__(self):
        pass

    @abstractmethod
    def run(self, state: State) -> State:
        pass

    def cleanup(self):
        pass

def run_state_machine(transitions: list[Transition], initial_state: State) -> State:
    transition_names = [transition.__class__.__name__ for transition in transitions]
    state = initial_state
    # print(state.data)
    for transition in transitions:
        current_transition = transition.__class__.__name__        
        last_executed_transition = state.get("last_executed_transition")
        if last_executed_transition in transition_names and transition_names.index(last_executed_transition) >= transition_names.index(current_transition):
            print(f"Transition {current_transition} has already been executed, skipping...")
            continue
        
        state = transition.run(state).clone({
            "last_executed_transition": transition.__class__.__name__
        })
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

    run_state_machine([
        Step1(),
        Step2()
    ], State({"last_executed_transition": "Initial"}))
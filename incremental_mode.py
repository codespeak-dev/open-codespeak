from dataclasses import dataclass
from typing import Optional

@dataclass
class IncrementalMode:
    CLEAN = "clean"
    NEXT_ROUND = "next_round"
    RESTART_FROM_LAST_FAILED = "continue_from_last_failed"
    COMPILE_FROM_PHASE = "compile_from_phase"

    type: str  # CLEAN, NEXT_ROUND, CONTINUE_FROM_LAST_FAILED, COMPILE_FROM_PHASE
    phase_name: Optional[str] = None # for COMPILE_FROM_PHASE

    def __init__(self, type: str, phase_name: Optional[str] = None):
        self.type = type
        self.phase_name = phase_name
    
    @classmethod
    def clean(cls):
        return cls(cls.CLEAN)
    
    @classmethod
    def next_round(cls):
        return cls(cls.NEXT_ROUND)
    
    @classmethod
    def continue_from_last_failed(cls):
        return cls(cls.RESTART_FROM_LAST_FAILED)
    
    @classmethod
    def compile_from_phase(cls, phase_name: str):
        return cls(cls.COMPILE_FROM_PHASE, phase_name)
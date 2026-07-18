from typing import List, Optional

from pydantic import BaseModel, Field


class Condition(BaseModel):
    type: str


class Rule(BaseModel):
    id: str
    conditions: List[Condition]
    action: str


class Environment(BaseModel):
    personPresent: bool
    isDark: bool


class SimulationResult(BaseModel):
    doorOpen: bool
    bellRinging: bool
    doorCorrect: bool
    bellCorrect: bool
    allCorrect: bool


class ChatMessage(BaseModel):
    role: str
    text: str
    speaker: Optional[str] = None


class AdviceRequest(BaseModel):
    rules: List[Rule]
    environment: Environment
    result: SimulationResult
    history: Optional[List[ChatMessage]] = Field(default_factory=list)
    current_message: Optional[str] = None
    phase: Optional[int] = 2


class PromptsConfig(BaseModel):
    base: str
    phase2_extra: str
    phase3_extra: str
    phase4_extra: str


class LogEntry(BaseModel):
    session_id: str
    event: str
    phase: int
    rules: List[Rule]
    chat_history: List[ChatMessage]
    all_correct: bool

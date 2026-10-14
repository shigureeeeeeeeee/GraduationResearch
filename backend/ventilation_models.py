"""Validated, non-executable rule language for the ventilation exercise."""
import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


Output = Literal["A", "B", "stop"]
FIELDS = {
    "occupied": {"label": "この部屋に人がいる", "kind": "boolean"},
    "co2": {"label": "この部屋のCO₂濃度", "kind": "number"},
    "previous_demand": {"label": "この部屋の前回の換気要求", "kind": "boolean"},
    "wait": {"label": "この部屋の要求待ち時間", "kind": "number"},
    "was_served": {"label": "前回この部屋を換気した", "kind": "boolean"},
    "maintenance": {"label": "点検モード", "kind": "boolean"},
    "run": {"label": "装置の連続運転数", "kind": "number"},
    "previous_output": {"label": "前回の装置動作", "kind": "output"},
    "candidate": {"label": "今回選んだ部屋", "kind": "output"},
}
STAGES = [
    {"id": "demand", "label": "換気要求", "description": "A・Bそれぞれに同じルールを適用します。前回の要求を参照できます。",
     "fields": ["occupied", "co2", "previous_demand", "wait", "was_served", "maintenance"],
     "actions": [{"value": "on", "label": "換気要求をON"}, {"value": "off", "label": "換気要求をOFF"}, {"value": "keep", "label": "前回の要求を保持"}],
     "default": "一致するルールがなければ、要求はOFFになります。"},
    {"id": "selection", "label": "部屋の選択", "description": "要求がONの部屋を条件で絞り、候補が見つかった最初のルールで選びます。",
     "fields": ["occupied", "co2", "previous_demand", "wait", "was_served", "maintenance"],
     "actions": [{"value": "co2", "label": "濃度 → 待ち時間 → A室の順で選ぶ"}, {"value": "wait", "label": "待ち時間 → 濃度 → A室の順で選ぶ"}, {"value": "room_a", "label": "候補のA室を選ぶ"}, {"value": "room_b", "label": "候補のB室を選ぶ"}],
     "default": "どのルールでも選べなければ、候補は「停止」です。"},
    {"id": "output", "label": "装置への命令", "description": "点検、連続運転数、前回と今回の部屋を調べ、今回の動作を決めます。",
     "fields": ["maintenance", "run", "previous_output", "candidate"],
     "actions": [{"value": "stop", "label": "停止する"}, {"value": "selected", "label": "選んだ部屋を換気する"}],
     "default": "一致するルールがなければ、装置は停止します。"},
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestInput(StrictModel):
    aOccupied: bool = True
    bOccupied: bool = True
    aCo2: int = Field(default=1200, ge=0, le=10000)
    bCo2: int = Field(default=1100, ge=0, le=10000)
    maintenance: bool = False


class Predicate(StrictModel):
    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte"] = "eq"
    value: Any = True
    other_field: Optional[str] = None
    negate: bool = False

    @model_validator(mode="after")
    def valid_comparison(self):
        if self.field not in FIELDS:
            raise ValueError("使用できない条件です")
        kind = FIELDS[self.field]["kind"]
        if self.other_field:
            if self.other_field not in FIELDS or FIELDS[self.other_field]["kind"] != kind:
                raise ValueError("同じ種類の値を比較してください")
        elif kind == "boolean" and type(self.value) is not bool:
            raise ValueError("真偽値を選んでください")
        elif kind == "number" and (
            type(self.value) not in (int, float) or not math.isfinite(self.value)
            or not 0 <= self.value <= 10000
        ):
            raise ValueError("数値は0〜10000で指定してください")
        elif kind == "output" and self.value not in ("A", "B", "stop"):
            raise ValueError("A・B・停止のいずれかを指定してください")
        if kind != "number" and self.op not in ("eq", "ne"):
            raise ValueError("この条件では一致・不一致を選んでください")
        return self


class ProgramRule(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    conditions: List[Predicate] = Field(default_factory=list, max_length=12)
    join: Literal["all", "any"] = "all"
    action: str


class Program(StrictModel):
    demand: List[ProgramRule] = Field(default_factory=list, max_length=30)
    selection: List[ProgramRule] = Field(default_factory=list, max_length=30)
    output: List[ProgramRule] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid_stages(self):
        ids = []
        for stage in STAGES:
            actions = {action["value"] for action in stage["actions"]}
            for rule in getattr(self, stage["id"]):
                ids.append(rule.id)
                if rule.action not in actions:
                    raise ValueError("この段階では使用できない動作です")
                for condition in rule.conditions:
                    if condition.field not in stage["fields"] or (
                        condition.other_field and condition.other_field not in stage["fields"]
                    ):
                        raise ValueError("この段階では参照できない値です")
        if len(ids) != len(set(ids)):
            raise ValueError("ルールIDが重複しています")
        return self


class SimulationBaseline(StrictModel):
    program: Program
    steps: List[TestInput] = Field(default_factory=list, max_length=200)


class SimulationRequest(StrictModel):
    task_id: Literal["ventilation-v1", "ventilation-goals-v2", "ventilation-goals-v3"] = "ventilation-goals-v3"
    program: Program
    steps: List[TestInput] = Field(default_factory=list, max_length=200)
    baseline: Optional[SimulationBaseline] = None


class Message(StrictModel):
    role: Literal["ai", "user", "group"]
    text: str = Field(max_length=20000)
    speaker: Optional[str] = None
    phase: int = Field(default=2, ge=1, le=4)
    llm: Optional[Dict[str, Any]] = None


class Prediction(StrictModel):
    output: Output
    reason: str = Field(default="", max_length=5000)


class AdviceRequest(SimulationRequest):
    environment: TestInput = Field(default_factory=TestInput)
    history: List[Message] = Field(default_factory=list, max_length=200)
    current_message: Optional[str] = Field(default=None, max_length=5000)
    phase: int = Field(default=2, ge=1, le=4)
    reflection: str = Field(default="", max_length=10000)
    predictions: List[Prediction] = Field(default_factory=list, max_length=200)


class SessionLog(AdviceRequest):
    # Old queued events did not include a task version; retain their original meaning.
    task_id: Literal["ventilation-v1", "ventilation-goals-v2", "ventilation-goals-v3"] = "ventilation-v1"
    event_id: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=100)
    event: Literal["step", "phase_complete", "session_end", "program_revision", "reset", "chat", "reflection"]
    scenario_id: str = Field(default="custom", max_length=100)
    next_program: Optional[Program] = None

    @model_validator(mode="after")
    def predictions_match_steps(self):
        if len(self.predictions) != len(self.steps):
            raise ValueError("予想と実行ステップの数が一致しません")
        return self

"""Japanese one-line summaries of learner programs.

The wording mirrors frontend/src/ruleText.js so that what the AI peers say about a plan
matches what learners see on screen.
"""
from ventilation_models import FIELDS, STAGES

OP_SYMBOLS = {"eq": "＝", "ne": "≠", "gte": "≥", "gt": ">", "lte": "≤", "lt": "<"}
OUTPUT_NAMES = {"A": "A室", "B": "B室", "stop": "停止"}
STAGE_NAMES = {"demand": "①換気要求", "selection": "②部屋の選択", "output": "③装置への命令"}


def describe_condition(condition):
    label = FIELDS[condition.field]["label"]
    kind = FIELDS[condition.field]["kind"]
    other = FIELDS[condition.other_field]["label"] if condition.other_field else None
    if kind == "boolean" and not other:
        text = label if (condition.value is True) == (condition.op == "eq") else f"{label}（いいえ）"
    elif kind == "output":
        text = f"{label}{' ＝ ' if condition.op == 'eq' else ' ≠ '}{other or OUTPUT_NAMES.get(condition.value, condition.value)}"
    else:
        text = f"{label} {OP_SYMBOLS[condition.op]} {other or condition.value}"
    return f"NOT（{text}）" if condition.negate else text


def describe_rule(stage_id, rule):
    stage = next(item for item in STAGES if item["id"] == stage_id)
    action = next((item["label"] for item in stage["actions"] if item["value"] == rule.action), rule.action)
    joiner = " かつ " if rule.join == "all" else " または "
    conditions = joiner.join(describe_condition(condition) for condition in rule.conditions)
    if stage_id == "selection":
        return f"要求ONの部屋のうち、{conditions} の部屋があれば → {action}" if conditions else f"要求ONの部屋があれば → {action}"
    return f"もし {conditions} なら → {action}" if conditions else f"いつでも → {action}"


def describe_program(program):
    """Return {stage_id: [summary, ...]} in rule order."""
    return {stage["id"]: [describe_rule(stage["id"], rule) for rule in getattr(program, stage["id"])] for stage in STAGES}


def program_text(program):
    lines = []
    for stage_id, rules in describe_program(program).items():
        lines.append(f"{STAGE_NAMES[stage_id]}: " + (" / ".join(f"{i}. {text}" for i, text in enumerate(rules, 1)) if rules else "ルールなし"))
    return "\n".join(lines)


def program_differences(mine, theirs):
    """Stages whose rule lists differ, with the rules only one side has. Order matters, so a reordering also counts."""
    a, b = describe_program(mine), describe_program(theirs)
    differences = []
    for stage in STAGES:
        stage_id = stage["id"]
        if a[stage_id] == b[stage_id]:
            continue
        differences.append({"stage": stage_id, "stage_name": STAGE_NAMES[stage_id],
                            "only_mine": [text for text in a[stage_id] if text not in b[stage_id]],
                            "only_theirs": [text for text in b[stage_id] if text not in a[stage_id]],
                            "order_only": sorted(a[stage_id]) == sorted(b[stage_id])})
    return differences

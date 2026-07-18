from typing import Any, Dict, List

from schemas import AdviceRequest, Rule


SCENARIOS = (
    {"label": "昼・人あり", "personPresent": True, "isDark": False},
    {"label": "昼・人なし", "personPresent": False, "isDark": False},
    {"label": "夜・人あり", "personPresent": True, "isDark": True},
    {"label": "夜・人なし", "personPresent": False, "isDark": True},
)

CONDITION_LABELS = {
    "person_sensor": "人感センサーON",
    "dark_sensor": "明るさセンサーON（夜）",
}

ACTION_LABELS = {
    "door": "ドアを開ける",
    "bell": "チャイムを鳴らす",
}


def evaluate_rules(rules: List[Rule], person_present: bool, is_dark: bool) -> Dict[str, bool]:
    conditions = {"person_sensor": person_present, "dark_sensor": is_dark}
    door_open = False
    bell_ringing = False

    for rule in rules:
        if rule.conditions and all(conditions.get(c.type, False) for c in rule.conditions):
            if rule.action == "door":
                door_open = True
            elif rule.action == "bell":
                bell_ringing = True

    return {"doorOpen": door_open, "bellRinging": bell_ringing}


def describe_rules(rules: List[Rule]) -> str:
    if not rules:
        return "（ルールが設定されていません）"

    lines = []
    for index, rule in enumerate(rules, 1):
        conditions = [CONDITION_LABELS.get(c.type, c.type) for c in rule.conditions]
        condition_text = " AND ".join(conditions) if conditions else "（条件なし）"
        action_text = ACTION_LABELS.get(rule.action, rule.action)
        lines.append(f"  ルール{index}: [{condition_text}] → [{action_text}]")
    return "\n".join(lines)


def describe_scenarios(rules: List[Rule]) -> str:
    lines = []
    for scenario in SCENARIOS:
        result = evaluate_rules(
            rules,
            scenario["personPresent"],
            scenario["isDark"],
        )
        door_correct = result["doorOpen"] == scenario["personPresent"]
        bell_correct = result["bellRinging"] == (
            scenario["personPresent"] and scenario["isDark"]
        )
        status = "✓" if door_correct and bell_correct else "✗"
        lines.append(
            f"  {scenario['label']}: "
            f"ドア={'開' if result['doorOpen'] else '閉'} / "
            f"チャイム={'鳴る' if result['bellRinging'] else '静か'} {status}"
        )
    return "\n".join(lines)


def fallback_response(req: AdviceRequest) -> str:
    rules = req.rules
    if not rules:
        return "まだルールが1つも作られていませんね。\nコンビニのドアって、どんなときに開くと思いますか？"

    door_rules = [rule for rule in rules if rule.action == "door"]
    bell_rules = [rule for rule in rules if rule.action == "bell"]

    if any(any(c.type == "dark_sensor" for c in rule.conditions) for rule in door_rules):
        return "ドアのルールに「明るさセンサー」が入っていますね。\n昼間にお客さんが来たとき、ドアはどうなりますか？"

    if any(not any(c.type == "person_sensor" for c in rule.conditions) for rule in bell_rules):
        return "チャイムのルールに人感センサーが入っていないですね。\nお店に誰もいないのに、夜中ずっとチャイムが鳴ってしまうことはないですか？"

    if not door_rules:
        return "ドアを開けるルールがまだないようですね。\nお客さんが来たとき、ドアはどうなってほしいですか？"

    if not bell_rules:
        return "ドアのルールは作れていますね！\n課題には「夜だけチャイムが鳴る」という条件もありましたね。どうすれば夜だけ鳴るようにできますか？"

    if req.result.allCorrect:
        return "4つ全てのシナリオで正しく動いていますね！素晴らしい！\n「昼・人あり」「夜・人あり」「昼・人なし」「夜・人なし」、どれも確認できましたか？"

    return "いい感じになってきました！\n4つのシナリオ（昼夜×人あり/なし）を全部チェックして、おかしな動きがないか確かめてみましょう。"


def rule_signature(rule: Rule) -> tuple:
    return tuple(sorted(c.type for c in rule.conditions if c.type)), rule.action


def draft_signature(rule: Dict[str, Any]) -> tuple:
    conditions = tuple(
        sorted(c.get("type") for c in rule.get("conditions", []) if c.get("type"))
    )
    return conditions, rule.get("action")

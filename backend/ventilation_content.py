from ventilation_models import FIELDS, STAGES, Program, TestInput

TASK_ID = "ventilation-goals-v3"
GOALS = [
    {"title": "連続の放置は4分以内", "text": "人がいて1,000ppm以上の状態が続く各室の、連続未対応時間を4分以内にしてください。自分の換気要求とは独立した参考待ち時間で確認します。"},
    {"title": "不要な運転は0回", "text": "無人の部屋、または800ppm以下の部屋への運転を0回にしてください。"},
    {"title": "装置の制約違反は0回", "text": "点検・連続運転・部屋の切り替えに関する装置の制限を、実行したすべての時間で守ってください。"},
]
IMPROVEMENT = {"title": "高濃度への対応を改善する", "text": "達成基準を満たしたうえで、1,500ppm以上の有人室が換気を受けなかった延べ時間（分）を、同じ入力・同じ実行時間の修正前より減らしてください。両室が同時に未対応なら1分を2分と数えます。修正前が0なら維持し、改善の余地がないことを説明してください。"}
CONSTRAINTS = [
    {"title": "装置は1台", "text": "動作はA室を換気・B室を換気・停止のいずれか。同時換気はできません。"},
    {"title": "連続運転の上限", "text": "2分続けて運転したら、次の1分は停止してください。"},
    {"title": "部屋を切り替えるとき", "text": "別の部屋へ切り替える間には1分の停止が必要です。連続運転後の停止を兼ねられます。"},
    {"title": "点検中", "text": "点検モード中は必ず停止してください。"},
]
GUIDANCE = [
    {"title": "観測できる情報", "text": "両室の人の有無・CO₂濃度、点検モードを使えます。前回の動作やカウンターも参照できます。"},
    {"title": "濃度と時間の数え方", "text": "800ppm以下への運転は不要な運転に数え、有人かつ1,000ppm以上では未対応時間を数えます。1,500ppm以上は改善指標の対象です。換気・退室・1,000ppm未満・点検で参考待ち時間は0に戻ります。必要な停止時間も未対応に含めます。"},
    {"title": "自分で決めること", "text": "換気要求を開始・終了する条件、前回の状態を保持するか、部屋の選び方、条件が競合したときの優先順位を設計し、理由を説明してください。"},
    {"title": "実行の読み方", "text": "濃度は入力列から与えられます。空気の流れや換気による濃度低下の物理計算はしません。装置は1分ごとに動作を決めます。"},
    {"title": "達成の確認", "text": "各テストケースを最後まで実行し、放置4分以内・不要な運転0回・制約違反0回を確認してください。途中の結果は実行済みの範囲だけの確認です。数値基準を満たす条件や優先順位は自分で設計してください。"},
]
REQUIREMENTS = GOALS + [IMPROVEMENT] + CONSTRAINTS + GUIDANCE
TASK_SPEC = "\n".join(f"【{item['title']}】{item['text']}" for item in REQUIREMENTS) + """
目的と装置の制限を満たすための条件・優先順位は、学習者が設計する。
高濃度・待ち時間・継続の優先順、同値時にAを選ぶ規則、要求の保持は課題の正解として指定しない。
数値は結果の達成基準であり、要求ON/OFFの条件や「何分待ったら優先する」という解法を指定しない。
数値基準を満たす異なる案があり、複数の目的の間にトレードオフがある。出力列が違うだけで誤答にしない。
初期状態は両室の学習者の要求OFF、要求待ち時間0分、装置停止、連続運転0分。
プログラムは要求更新→候補選択→装置命令の3段階。各段階は上から最初に一致したルールを使う。
条件はAND/ORと個別の否定。条件なしは常に一致。要求更新は両室に同じルールを適用し、既定はOFF。
候補選択は要求ONの部屋から選ぶ。参照する前回の要求・要求待ち時間・前回の動作はその1分が始まる時点の値。
装置命令の既定は停止。装置制約は学習者がルールで表現し、システムは自動補正しない。
学習者の要求待ち時間は、要求ONかつ未換気なら増え、換気・要求OFF・点検で0に戻る。
評価用の参考待ち時間は学習者の要求と独立。有人かつ1,000以上で有効な換気を受けないと増える。
参考待ち時間は換気・無人・1,000未満・点検で0へ戻る。制約に違反した命令は対応として数えない。
点検中の時間は対応機会から除外。停止制約による未対応も含めた最大値が4以内か確認する。
無人への運転と有人かつ800以下への運転を合計し、不要な運転が0か確認する。801〜999への運転はこの基準では禁止しない。
改善指標は有人かつ1,500以上で未対応だった延べ時間（両室同時なら2倍で数える分）。同じ入力・同じ実行範囲で修正前後を比べる。
現在の実行範囲の達成は、他のテストケースや今後の全入力での達成を意味しない。
濃度は入力で与え、物理計算はしないため、実際の濃度低下や健康効果、消費電力を達成したとは判定しない。
"""


def sample(a, b=700, **kwargs):
    return TestInput(aCo2=a, bCo2=b, **kwargs).model_dump()


SCENARIOS = [
    {"id": "shared", "label": "テストケース1：濃度の変化と装置の制限", "description": "濃度の変化と装置制限が重なる場面で、自分の方針を確かめる。",
     "steps": [sample(a, b) for a, b in [(1200, 1100), (1150, 1120), (1100, 1130), (1100, 1130), (1500, 900), (1450, 900), (800, 900), (800, 900)]]},
    {"id": "memory", "label": "テストケース2：同じ900ppmでも経過が違う", "description": "濃度が上がるときと下がるときを比べる。",
     "steps": [sample(n) for n in (700, 900, 1100, 900, 900, 800)]},
    {"id": "waiting", "label": "テストケース3：もう一方の部屋の待ち時間", "description": "A室の濃度が高いままでも、B室は待ち続けてよいだろうか。",
     "steps": [sample(1400, 1100) for _ in range(8)]},
    {"id": "boundary", "label": "テストケース4：ちょうど境界値", "description": "800・1,000・1,500を含む値を確認する。",
     "steps": [sample(999), sample(1000), sample(801), sample(800), sample(1499, 1500), sample(1500, 1500)]},
    {"id": "occupancy", "label": "テストケース5：退室と再入室", "description": "要求を持った部屋が無人になり、再び人が入る。",
     "steps": [sample(1100), sample(1600, aOccupied=False), sample(900), sample(1000), sample(900, aOccupied=False), sample(900)]},
    {"id": "maintenance", "label": "テストケース6：点検開始と解除", "description": "点検中の装置動作、要求、待ち時間を比べる。",
     "steps": [sample(1200, 1100), sample(1600, 1100, maintenance=True), sample(900, 900, maintenance=True), sample(900, 900), sample(900, 1600), sample(900, 800)]},
    {"id": "urgent", "label": "テストケース7：高濃度と長時間待ち", "description": "高い濃度への対応と、もう一方の待ち時間をどう両立するか。",
     "steps": [sample(1600, 1200) for _ in range(4)] + [sample(1400, 1200), sample(1400, 1200)]},
    {"id": "ties", "label": "テストケース8：同じ濃度の2室", "description": "濃度だけでは選べないとき、何を比べるか。",
     "steps": [sample(1100, 1100) for _ in range(7)]},
]


def condition(field, value=True, op="eq", **kwargs):
    return {"field": field, "value": value, "op": op, **kwargs}


def rule(id, action, *conditions, join="all"):
    return {"id": id, "action": action, "conditions": list(conditions), "join": join}


def example_program(kind):
    """Researcher examples, each with a known misconception. Not the scoring oracle."""
    program = {
        "demand": [
            rule("d1", "off", condition("occupied", False)),
            rule("d2", "on", condition("co2", 1000, "gte")),
            rule("d3", "off", condition("co2", 800, "lte")),
            rule("d4", "keep"),
        ],
        "selection": [
            rule("s1", "co2", condition("co2", 1500, "gte")),
            rule("s2", "wait", condition("wait", 3, "gte")),
            rule("s3", "co2", condition("was_served")),
            rule("s4", "co2"),
        ],
        "output": [
            rule("o1", "stop", condition("maintenance")),
            rule("o2", "stop", condition("run", 2, "gte")),
            rule("o3", "stop", condition("previous_output", "stop", "ne"),
                 condition("previous_output", "stop", "ne", other_field="candidate")),
            rule("o4", "selected"),
        ],
    }
    if kind == "group_a":
        program["demand"] = program["demand"][:2]  # No memory below the start threshold.
    elif kind == "group_b":
        program["selection"] = [rule("s4", "co2")]
    elif kind == "group_c":
        program["output"] = [r for r in program["output"] if r["id"] != "o3"]
    elif kind != "complete":
        raise ValueError("Unknown example")
    return Program.model_validate(program)


def goal_example_program(kind):
    """Alternative policies for discussion, not an answer key."""
    program = example_program("complete").model_dump()
    if kind in ("group_a", "group_b"):
        program["demand"] = program["demand"][:2]
    if kind == "group_a":
        program["selection"] = [rule("s_co2", "co2")]
    elif kind == "group_b":
        program["selection"] = [rule("s_wait", "wait")]
    elif kind == "group_c":
        program["selection"] = [rule("s_keep", "co2", condition("was_served")), rule("s_co2", "co2")]
    else:
        raise ValueError("Unknown example")
    return Program.model_validate(program)


GROUPS = [
    {"id": "group_a", "group": "Aグループ", "title": "高い濃度への対応を重視", "rules": ["人がいて1,000以上の部屋を候補にし、濃度が高い方を選ぶ。", "点検・連続運転・切り替えの停止制限を守る。"], "question": "濃度を優先する案では、もう一方の部屋の待ち時間をどう説明できる？", "scenario": "waiting"},
    {"id": "group_b", "group": "Bグループ", "title": "待たせないことを重視", "rules": ["人がいて1,000以上の部屋を候補にし、要求待ち時間が長い方を選ぶ。", "点検・連続運転・切り替えの停止制限を守る。"], "question": "待ち時間を優先する案では、高い濃度への対応と切り替えの回数はどうなる？", "scenario": "waiting"},
    {"id": "group_c", "group": "Cグループ", "title": "運転の継続を重視", "rules": ["要求の開始を1,000以上、終了を800以下または無人とし、その間は前回の要求を保持する。", "換気中の部屋を継続できれば優先し、装置の停止制限を守る。"], "question": "継続を重視する案は、低い濃度での運転や他室の待ち時間とどう折り合いをつける？", "scenario": "shared"},
]


def public_config():
    return {"task_id": TASK_ID, "evaluation_mode": "goals_and_constraints",
            "goals": GOALS, "improvement": IMPROVEMENT, "constraints": CONSTRAINTS, "guidance": GUIDANCE,
            "requirements": REQUIREMENTS, "stages": STAGES,
            "fields": FIELDS, "scenarios": SCENARIOS,
            # 案の中身（ルールの文章・プログラム）は渡さない。全テストケースで達成するB案を最初から知らせないため
            "groups": [{key: group[key] for key in ("id", "group", "title")} for group in GROUPS]}

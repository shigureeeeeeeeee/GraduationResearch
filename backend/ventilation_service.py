import json
import os
import re
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path

from llm_clients import GenerationOptions, LLMMessage, create_llm_client
from ventilation_content import GROUPS, SCENARIOS, TASK_ID, TASK_SPEC, goal_example_program
from ventilation_describe import program_differences, program_text
from ventilation_engine import OUTPUT_LABELS, simulate
from ventilation_models import PromptsConfig, TestInput

DATA_DIR = Path(__file__).parent / "data"
PROMPT_FILE = DATA_DIR / "ventilation_numeric_goals_prompts.json"
LOG_FILE = DATA_DIR / "ventilation_sessions.jsonl"
LOG_LOCK = Lock()
DEFAULT_PROMPTS = {
    "base": "あなたは学習者と同じ大学の授業で、同じ換気制御の課題に取り組んでいる学生です。教師・先生・チューターではありません。知識や力は学習者と同じくらいで、正解も知りません。友達同士の話し言葉で、短く話してください。相手の考えを評価したり、ほめたり、指示や助言をしたりしないでください。自分の考えや迷いを1つ言ってから、相手の理由を1つだけ尋ねてください。実行結果の数値はシステムが別に表示するので、繰り返さないでください。完成プログラムや正解を示さないでください。時間は「ステップ」と言わず「分」で表してください。",
    "phase2_extra": "あなたはペアの相手で、自分の案を持っています。自分の案と相手の案の違いを1つ選び、自分がそうした理由を短く言ってから、相手がそうした理由を尋ねてください。自分の案が正しいとは限りません。",
    "phase3_extra": "あなたはペアの相手で、実行結果を一緒に見ています。気になった場面を1つ挙げ、相手がどう考えるか尋ねてください。違う優先順位を誤りと決めつけないでください。",
    "phase4_extra": "あなたはクラス全体の話し合いに参加している学生の一人です。今話している案について、具体的な場面をもとに話してください。",
}


def get_prompts():
    try:
        overrides = json.loads(PROMPT_FILE.read_text(encoding="utf-8"))
        validated = PromptsConfig.model_validate(overrides)
        return {**DEFAULT_PROMPTS, **validated.model_dump()}
    except (OSError, ValueError):
        return dict(DEFAULT_PROMPTS)


def save_prompts(config):
    DATA_DIR.mkdir(exist_ok=True)
    PROMPT_FILE.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def reset_prompts():
    if PROMPT_FILE.exists():
        PROMPT_FILE.unlink()


def append_log(entry):
    result = simulate(entry.program, entry.steps, entry.task_id, entry.baseline)
    record = entry.model_dump()
    record.update({"timestamp": datetime.now(timezone.utc).isoformat(), "task_id": entry.task_id,
                   "evaluation": result,
                   "chat_history": record.pop("history")})
    if entry.event == "run_all" and entry.task_id == TASK_ID:
        # Recompute on the server so the log does not depend on what the browser displayed.
        record["test_cases"] = simulate_all(entry.program)
    if entry.task_id == "ventilation-v1":
        record["all_correct"] = result["all_correct"]
    else:
        record["constraints_met"] = result["constraints_met"]
        if "achievement" in result:
            record["goals_met"] = result["achievement"]["all_met"]
    DATA_DIR.mkdir(exist_ok=True)
    with LOG_LOCK:
        for existing in read_logs():
            if existing.get("event_id") == entry.event_id:
                return existing
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def simulate_all(program):
    """Run the program over every test case. The same summary is shown to learners and kept in run_all logs."""
    cases = []
    for scenario in SCENARIOS:
        result = simulate(program, [TestInput.model_validate(step) for step in scenario["steps"]])
        cases.append({"id": scenario["id"], "label": scenario["label"], "minutes": len(scenario["steps"]),
                      "goals_met": result["achievement"]["all_met"], "checks": result["achievement"]["checks"],
                      "urgent_unserved": result["metrics"]["urgent_unserved_room_steps"]})
    return {"cases": cases, "all_met": all(case["goals_met"] for case in cases)}


def read_logs():
    if not LOG_FILE.exists():
        return []
    return [json.loads(line) for line in LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def context_for(req):
    result = simulate(req.program, req.steps, baseline=req.baseline)
    focus = next((row for row in result["trace"] if row["violations"]), None)
    if not focus:
        focus = next((row for row in result["trace"] if row["observation"]["urgent_unserved_rooms"]), None)
    if not focus and result["trace"]:
        focus = result["trace"][-1]
    recent = [{key: row[key] for key in ("step", "input", "after", "violations", "observation")}
              for row in result["trace"][-3:]]
    return json.dumps({"program": req.program.model_dump(), "current_input": req.environment.model_dump(),
                       "executed_steps": len(req.steps), "recent_trace": recent,
                       "focus_event": focus, "metrics": result["metrics"],
                       "achievement": result["achievement"],
                       "comparison": result.get("comparison"),
                       "predictions": [p.model_dump() for p in req.predictions],
                       "reflection": req.reflection}, ensure_ascii=False)


def system_prompt(phase):
    prompts = get_prompts()
    return prompts["base"] + "\n" + prompts.get(f"phase{phase}_extra", prompts["phase2_extra"]) + "\n【教材の目的・制限・観測指標】\n" + TASK_SPEC


def fallback_advice(req, differences=None):
    # LLMが使えないときの仲間の発言。評価や指示をせず、自分の迷いと問いだけにする
    if differences:
        return f"ぼくの案とは{differences[0]['stage_name']}のところが違うみたい。そこはどうしてそうしたの？"
    result = simulate(req.program, req.steps)
    if not any((req.program.demand, req.program.selection, req.program.output)):
        return "ぼくもまだ迷ってるんだけど、どんなときに換気が必要だと思う？"
    if result["metrics"]["violation_steps"]:
        return "装置の制限のところ、ぼくもよく分かってないんだけど、どのルールが効いてると思う？"
    if req.steps and not result["achievement"]["all_met"]:
        return "ぼくも同じところで迷ってるんだけど、どのルールを変えたらいいと思う？"
    if req.steps:
        return "ぼくは高い濃度と待ち時間のどっちを先にするか迷ってるんだけど、どっちを大事にした？"
    return "ぼくはまだ自信ないんだけど、この案だとうまくいかない場面ってありそう？"


def advice_evidence(req):
    result = simulate(req.program, req.steps, baseline=req.baseline)
    if not req.steps:
        return "まだ実行していません。"
    m = result["metrics"]
    lines = [f"実行した{len(req.steps)}分のうち、制約違反は{m['violation_steps']}分でした。",
             f"有人かつ濃度の目安以上の部屋への対応は{m['served_room_steps']} / {m['needs_room_steps']}分、未対応は延べ{m['unserved_room_steps']}分です。",
             f"参考待ち時間の最大値はA室{m['max_wait']['A']}、B室{m['max_wait']['B']}分です。"]
    lines += [f"{check['label']}：{'達成' if check['met'] else '未達'}（実測{check['actual']}）。"
              for check in result["achievement"]["checks"]]
    lines.append(f"改善指標：1,500ppm以上の有人室の未対応は延べ{m['urgent_unserved_room_steps']}分です。")
    comparison = result.get("comparison")
    if comparison and comparison["comparable"]:
        lines.append(f"同じ入力での修正前は{comparison['previous']}、現在は{comparison['current']}分です。")
    first = next((row for row in result["trace"] if row["violations"]), None)
    if first:
        lines.append(f"{first['step']}分目の動作は「{OUTPUT_LABELS[first['after']['output']]}」です。" + " ".join(first["violations"]))
    lines.append("達成状況はこの実行範囲に限ります。停止制限の時間も未対応に含めます。")
    return "\n".join(lines)


PEER_INSTRUCTION = """
【出力の形】
見出し・前置き・箇条書き・改行なしで、120文字以内の話し言葉にしてください。自分の考えか迷いを短く言い、最後に相手への質問を1つだけ書いて「？」で終えてください。
教師のように評価・指示・まとめをしないでください（「いいですね」「〜しましょう」「〜してください」などは使わない）。
渡された事実にない数値や、ON/OFFの状態、正誤の判定は書かないでください（ルールの用語として「要求ON」「要求OFF」と書くのはかまいません）。
A・B・Cグループは発言者、A・B室は換気の対象です。混同しないでください。
"""
# 仲間の発言として使わない言葉。教師的な評価・指示と、旧課題の語
TEACHER_TERMS = ("しましょう", "ましょう", "ください", "いいですね", "いい質問", "素晴らし", "すばらし", "よくでき", "正解", "間違い",
                 "正当", "仕様どおり", "ヒント", "先生", "理解できますか", "分かりますか", "わかりますか", "考慮されていない", "考慮していない", "コンビニ", "チャイム", "人感センサー")


def numbers_in(text):
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return {number.replace(",", "") for number in re.findall(r"\d[\d,]*", text)}


# 課題文に出てくる基準の数字。事実として渡していなくても、AIが口にしてよい
TASK_NUMBERS = {"800", "1000", "1500", "4", "2", "1"}
LABEL_PATTERN = re.compile(r"(自分の考えや迷い|自分の考え|考え|迷い|相手への問い|相手への質問|問い|質問|司会役|[ABC]グループ|ペア)\s*[:：]\s*")


def normalize_question(text):
    """Clean up common small-model habits before validation.

    Removes copied format labels ("迷い: ..."), joins lines, collapses "？？", and keeps only up to the first question.
    """
    text = LABEL_PATTERN.sub("", text.strip().strip('"「」'))
    # 区切りは改行と、前後に空白のある「 / 」だけ。「要求ON/OFF」のスラッシュは残す。つなぐときは句点を補う
    text = re.sub(r"(?<=[^。？！?、])\s*(?:\n+|\s+/\s+)\s*", "。", text)
    text = re.sub(r"\s*(?:\n+|\s+/\s+)\s*", "", text).replace("?", "？")
    text = re.sub(r"？{2,}", "？", text).strip('"「」 ')
    return text[:text.index("？") + 1] if "？" in text else text


def valid_question(text, allowed_numbers=()):
    """A peer utterance: a few short statements and then one question, with no teacher-like or unsupported claims."""
    # 「要求ON/OFF」はルール画面の用語なので許し、状態の断定になりうる単独のON/OFFだけを弾く
    # 「要求をOFFにする」はルールの動作なので許す。「要求はON」のような状態の言い切りは弾く
    plain = re.sub(r"要求を?(ON|OFF)([/／・](ON|OFF))?", "", text)
    question = re.split(r"[。！]", text)[-1]
    return (10 <= len(text) <= 160 and text.endswith(("?", "？"))
            and text.count("?") + text.count("？") == 1
            and len(question) >= 5
            and text.count("。") <= 3 and text.count("！") <= 1 and "\n" not in text
            and numbers_in(text) <= set(allowed_numbers) | TASK_NUMBERS
            and not re.search(r"(?!ppm)[a-z]{3,}", text)
            and not any(term in plain for term in ("ON", "OFF"))
            and not any(term in text for term in TEACHER_TERMS))


def respond(messages, fallback, role=None, max_tokens=180, allowed_numbers=()):
    metadata = {"provider": "fallback", "model": "rule-based", "elapsed_ms": 0, "fallback": True}
    try:
        messages = [LLMMessage(role=msg.role, content=msg.content + (PEER_INSTRUCTION if msg.role == "system" else "")) for msg in messages]
        client = create_llm_client(role=role)
        result = client.chat(messages, GenerationOptions(temperature=0.45, max_tokens=max_tokens))
        metadata = {"provider": result.provider, "model": result.model,
                    "elapsed_ms": result.elapsed_ms, "fallback": False}
        text = normalize_question(result.text)
        if not valid_question(text, allowed_numbers):
            raise ValueError("Response does not match the task")
        return text, metadata
    except Exception:
        metadata["fallback"] = True
        return fallback, metadata


def chat_history(req, limit):
    # システムが示した事実の枠は、会話の発言としてはLLMに渡さない
    return [msg for msg in req.history if msg.role != "system"][-limit:]


def generate_advice(req):
    system = system_prompt(req.phase)
    differences = None
    if req.pair_plan:
        pair = goal_example_program(req.pair_plan)
        differences = program_differences(req.program, pair)
        group = next(item for item in GROUPS if item["id"] == req.pair_plan)
        system += (f"\n【あなた（ペア）の案：{group['title']}】\n{program_text(pair)}"
                   f"\n【相手の案】\n{program_text(req.program)}"
                   "\n【2つの案の違い】\n" + ("\n".join(
                       f"{d['stage_name']}: 相手だけ「{' / '.join(d['only_mine']) or 'なし'}」、あなただけ「{' / '.join(d['only_theirs']) or 'なし'}」"
                       + ("（並び順だけが違う）" if d["order_only"] else "") for d in differences) or "ルールは同じ"))
    messages = [LLMMessage(role="system", content=system)]
    messages += [LLMMessage(role="user" if msg.role == "user" else "assistant", content=msg.text) for msg in chat_history(req, 10)]
    messages.append(LLMMessage(role="user", content=context_for(req) + "\n相手の発言: " + (req.current_message or "今の案について話そう。")))
    # 自分の案や相手の案に書かれている数字（「待ち時間 ≥ 3」など）は事実として口にしてよい
    allowed = numbers_in(program_text(req.program)) | (numbers_in(program_text(goal_example_program(req.pair_plan))) if req.pair_plan else set())
    text, metadata = respond(messages, fallback_advice(req, differences), allowed_numbers=allowed)
    return {"facts": advice_evidence(req) if req.steps else None, "message": text, "llm": metadata}


# ---- フェーズ4：案を1つずつ話し合う ----

PLAN_IDS = ("group_a", "group_b", "group_c", "learner")
FACILITATOR = {"speaker": "司会役", "agent_id": "facilitator"}


def plan_program(req, plan_id):
    return req.program if plan_id == "learner" else goal_example_program(plan_id)


def plan_name(plan_id, for_learner=True):
    # 画面では「あなたの案」。AIへの指示では、AI自身の案と取り違えないよう「学習者の案」と呼ぶ
    if plan_id == "learner":
        return "あなたの案" if for_learner else "学習者の案"
    group = next(item for item in GROUPS if item["id"] == plan_id)
    return f"{group['group']}の案"


def first_problem(program):
    """The first place, in test-case order, where the program misses a goal. None if every case is met."""
    for scenario in SCENARIOS:
        result = simulate(program, [TestInput.model_validate(step) for step in scenario["steps"]])
        for row in result["trace"]:
            where = f"「{scenario['label']}」の{row['step']}分目"
            if row["violations"]:
                return f"{where}に、装置の制限を破る（{row['violations'][0].rstrip('。')}）"
            output = row["after"]["output"]
            if output != "stop":
                occupied = row["input"][output.lower() + "Occupied"]
                co2 = row["input"][output.lower() + "Co2"]
                if not occupied or co2 <= 800:
                    return f"{where}に、{'無人の' if not occupied else f'{co2}ppmの'}{output}室を換気する"
            for room, wait in row["observation"]["goal_wait"].items():
                if wait > 4:
                    return f"{where}に、{room}室が{wait}分続けて放置される"
    return None


def plan_facts(program):
    problem = first_problem(program)
    if problem:
        return problem + "。"
    summary = simulate_all(program)
    worst = max(summary["cases"], key=lambda case: case["urgent_unserved"])
    total = sum(case["urgent_unserved"] for case in summary["cases"])
    if not total:
        return "8つのテストケースすべてで目的を達成し、1,500ppm以上の部屋の放置もない。"
    return (f"8つのテストケースすべてで目的を達成する。1,500ppm以上の部屋の放置は合計{total}分"
            f"（いちばん多いのは「{worst['label']}」の{worst['urgent_unserved']}分）。")


def plan_cards(plan_ids):
    """Programs and test results for the plans the board shows. Served only when a phase needs them."""
    cards = []
    for plan_id in plan_ids:
        group = next(item for item in GROUPS if item["id"] == plan_id)
        program = goal_example_program(plan_id)
        cards.append({"id": plan_id, "group": group["group"], "title": group["title"],
                      "program": program.model_dump(), "results": simulate_all(program)})
    return cards


def critic_for(focus):
    # 指摘する仲間：グループの案なら次のグループ、学習者の案ならAグループ
    order = ["group_a", "group_b", "group_c"]
    return order[(order.index(focus) + 1) % 3] if focus in order else "group_a"


def group_speaker(group_id):
    group = next(item for item in GROUPS if item["id"] == group_id)
    return {"speaker": group["group"], "agent_id": group_id}


def generate_discussion(req):
    """One round of the class discussion about req.focus_plan, streamed turn by turn."""
    focus = req.focus_plan or "learner"
    program = plan_program(req, focus)
    facts = plan_facts(program)
    allowed = numbers_in(facts) | numbers_in(program_text(program))
    name = plan_name(focus, for_learner=False)
    shown = plan_name(focus)
    owner = None if focus == "learner" else focus
    critic = critic_for(focus)
    history = "\n".join(f"{msg.speaker or msg.role}: {msg.text}" for msg in chat_history(req, 12))
    base = (system_prompt(4) + f"\n【今話している案：{name}】\n{program_text(program)}\n【システムが確かめた事実】{facts}"
            + ("\n学習者に話しかけるときは「あなた」と呼び、この案は「あなたの案」と言ってください。" if focus == "learner"
               else f"\nこの案は「{name}」と呼んでください。「あなたの案」とは言わないでください（学習者の案と取り違えるため）。"))
    max_tokens = int(os.environ.get("GROUP_MAX_TOKENS", "180"))
    turns = []

    if not req.current_message:
        turns.append({"role": "system", "speaker": "実行結果", "agent_id": "system", "text": f"{plan_name(focus)}：{facts}"})
        yield turns[-1]
        target = f"{group_speaker(owner)['speaker']}" if owner else "学習者"
        messages = [LLMMessage(role="system", content=base + f"\nあなたは{group_speaker(critic)['speaker']}の学生です。事実の場面をもとに、{name}で気になるところを仲間として短く言い、{target}にどう考えるか尋ねてください。"),
                    LLMMessage(role="user", content=f"これまでの話: {history}")]
        text, metadata = respond(messages, f"{shown}だと、さっきの場面がちょっと気になったんだけど、どう考えてた？", role=critic,
                                 max_tokens=max_tokens, allowed_numbers=allowed)
        turns.append({"role": "group", **group_speaker(critic), "text": text, "llm": metadata})
        yield turns[-1]

    # 案を作ったグループが答える。学習者の案に学習者が発言したときは、指摘したグループが受け答えする
    responder = owner or (critic if req.current_message else None)
    if responder:
        said = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns if turn["role"] != "system")
        reply_to = f"学習者の発言「{req.current_message}」" if req.current_message else "今の指摘"
        role_text = ("この案を作った本人です。" + reply_to + "に、自分たちがこの優先順位にした理由を短く言って答え、相手の考えを尋ねてください。認められるところは認めてかまいません。"
                     if responder == owner else
                     reply_to + "を聞いて、自分の考えを短く言い、相手にもう一歩たずねてください。")
        messages = [LLMMessage(role="system", content=base + f"\nあなたは{group_speaker(responder)['speaker']}の学生です。{role_text}"),
                    LLMMessage(role="user", content=f"これまでの話: {history}\n今回の発言: {said}")]
        fallback = ("ぼくたちは濃度か待ち時間のどっちかを先に決めたかったんだけど、そっちならどうする？" if responder == owner
                    else "なるほど、そう考えたんだね。じゃあ、その案だと困る場面ってありそう？")
        text, metadata = respond(messages, fallback, role=responder, max_tokens=max_tokens, allowed_numbers=allowed)
        turns.append({"role": "group", **group_speaker(responder), "text": text, "llm": metadata})
        yield turns[-1]

    # 司会役の問いは2種類だけ：違いを整理して目的に戻す／目的そのものを問う
    # 司会役の発言の数で交互にする（フェーズ4の最初のあいさつも1回と数えるので、最初の問いは「比べる」になる）
    facilitator_turns = sum(1 for msg in req.history if msg.role == "ai" and msg.speaker == FACILITATOR["speaker"] and msg.phase == 4)
    if facilitator_turns % 2 == 1:
        other = "group_b" if focus != "group_b" else "group_a"
        kind = f"{name}と{plan_name(other)}の共通点と違いを一言で整理し、この自習室の目的にはどちらが合うと思うか、学習者に尋ねてください。"
        fallback = f"{shown}と{plan_name(other)}って、先に見るものが違うよね。この自習室ならどっちが合ってると思う？"
    else:
        kind = "そもそも、なぜその目的（人のいる部屋を長く放置しない、ムダに動かさない）が必要なのかを、学習者に尋ねてください。"
        fallback = "そもそも、人のいる部屋を長く放置しないほうがいいのってなんでだろう？"
    said = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns if turn["role"] != "system")
    messages = [LLMMessage(role="system", content=base + f"\nあなたは話し合いの司会役をしている学生です。教師ではないので、まとめたり評価したりしません。司会役は自分の案を持たないので、自分の意見や好みは言わず、出た意見を一言つないでから問いを1つだけ出してください。{kind}"),
                LLMMessage(role="user", content=f"これまでの話: {history}\n今回の発言: {said}\n学習者: {req.current_message or '（まだ発言なし）'}")]
    text, metadata = respond(messages, fallback, role="facilitator",
                             max_tokens=int(os.environ.get("FACILITATOR_MAX_TOKENS", "220")), allowed_numbers=allowed)
    yield {"role": "ai", **FACILITATOR, "text": text, "llm": metadata}

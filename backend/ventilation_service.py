import json
import os
import re
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path

from llm_clients import GenerationOptions, LLMMessage, create_llm_client
from ventilation_content import GROUPS, SCENARIOS, TASK_ID, TASK_SPEC, goal_example_program
from ventilation_engine import OUTPUT_LABELS, simulate
from ventilation_models import PromptsConfig, TestInput

DATA_DIR = Path(__file__).parent / "data"
PROMPT_FILE = DATA_DIR / "ventilation_numeric_goals_prompts.json"
LOG_FILE = DATA_DIR / "ventilation_sessions.jsonl"
LOG_LOCK = Lock()
DEFAULT_PROMPTS = {
    "base": "あなたは大学生のプログラミング学習の対話相手です。2室の換気制御について、省察を促してください。唯一の正解を想定せず、目的・制限・判断の根拠を検討してください。渡されたプログラムと実行履歴を読み、ルールを聞き返さず、具体的な場面に触れてください。完成プログラムを提示せず、予想・根拠・反例について最後に問いを1つ出してください。応答は短く、日本語で完結させてください。",
    "phase2_extra": "ペアの友達として、条件を選んだ理由や、別の状況でどうなるかを一緒に考えてください。",
    "phase3_extra": "実行前の予想と実際の動作、制約違反、未対応時間や必要のない運転を検討してください。異なる優先順位を誤りと断定せず、複数の目的の間のトレードオフと判断の根拠を尋ねてください。",
    "phase4_extra": "全体対話の司会として、A・B・Cグループの根拠を比較してください。提示された事実に基づき、学習者の案を見直す問いを1つ出してください。新しい架空のグループ発言を作らないでください。",
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


def fallback_advice(req):
    result = simulate(req.program, req.steps)
    if not any((req.program.demand, req.program.selection, req.program.output)):
        return "どんな状況を換気が必要と考え、両方の部屋が必要なときは何を優先したい？"
    if result["metrics"]["violation_steps"]:
        return "使われたルールと装置の制限を比べると、どの判断を見直したい？"
    if req.steps and not result["achievement"]["all_met"]:
        return "達成基準を超えた指標について、使われたルールのどこを見直したい？"
    if req.steps:
        return "濃度への対応と待ち時間を比べると、自分の案は何を優先し、どんな場面で見直したい？"
    return "自分の優先方針がうまく働く場面と、働かないかもしれない場面をどう確かめたい？"


def advice_evidence(req):
    result = simulate(req.program, req.steps, baseline=req.baseline)
    if not req.steps:
        return "今のプログラムはまだ実行されていません。自分の方針で次の動作を予想し、経過を確かめてみましょう。"
    m = result["metrics"]
    lines = [f"実行した{len(req.steps)}ステップのうち、制約違反は{m['violation_steps']}ステップでした。",
             f"有人かつ濃度の目安以上の部屋への対応は{m['served_room_steps']} / {m['needs_room_steps']}部屋ステップ、未対応は延べ{m['unserved_room_steps']}部屋ステップです。",
             f"参考待ち時間の最大値はA室{m['max_wait']['A']}、B室{m['max_wait']['B']}ステップです。"]
    lines += [f"{check['label']}：{'達成' if check['met'] else '未達'}（実測{check['actual']}）。"
              for check in result["achievement"]["checks"]]
    lines.append(f"改善指標：1,500ppm以上の有人室の未対応は延べ{m['urgent_unserved_room_steps']}部屋ステップです。")
    comparison = result.get("comparison")
    if comparison and comparison["comparable"]:
        lines.append(f"同じ入力での修正前は{comparison['previous']}、現在は{comparison['current']}部屋ステップです。")
    first = next((row for row in result["trace"] if row["violations"]), None)
    if first:
        lines.append(f"ステップ{first['step']}の動作は「{OUTPUT_LABELS[first['after']['output']]}」です。" + " ".join(first["violations"]))
    lines.append("達成状況はこの実行範囲に限ります。停止制限の時間も未対応に含めます。改善指標は同じ入力で修正前後を比べましょう。")
    return "\n".join(lines)


QUESTION_INSTRUCTION = """
【今回生成する部分】
制約違反と目的に関する観測指標は、システムが計算済みの文章で表示します。
あなたは対話の流れを踏まえ、学習者の予想・理由・比較を促す問いを1文だけ生成してください。
実行結果や原因を新たに説明・断定しないでください。数値、ON/OFF、正誤判定を出力しないでください。
待ち時間などの指標は、原因や不足している条件を断定するものではありません。「考慮されていない理由」など、未確認の不足を前提にした問いは避け、「どの情報を参照しているか」を尋ねてください。
見出しや前置きなし、120文字以内の日本語の質問1つだけを出力し、必ず「？」で終えてください。
A・B・Cグループは発言者、A・B室は換気の対象です。混同しないでください。
"""


def valid_question(text):
    # Restrict generated text to a question; simulation facts are supplied by code.
    return (10 <= len(text) <= 180 and text.endswith(("?", "？"))
            and text.count("?") + text.count("？") == 1
            and not re.search(r"[0-9０-９]", text)
            and not any(term in text for term in ("。", "！", "\n", "ON", "OFF", "正当", "正解", "間違い", "仕様どおり", "考慮されていない", "考慮していない", "コンビニ", "チャイム", "人感センサー")))


def respond(messages, fallback, role=None, max_tokens=180):
    metadata = {"provider": "fallback", "model": "rule-based", "elapsed_ms": 0, "fallback": True}
    try:
        messages = [LLMMessage(role=msg.role, content=msg.content + (QUESTION_INSTRUCTION if msg.role == "system" else "")) for msg in messages]
        client = create_llm_client(role=role)
        result = client.chat(messages, GenerationOptions(temperature=0.45, max_tokens=max_tokens))
        metadata = {"provider": result.provider, "model": result.model,
                    "elapsed_ms": result.elapsed_ms, "fallback": False}
        text = re.sub(r"[?？]+$", "？", result.text.strip().strip('"「」'))
        if not valid_question(text):
            raise ValueError("Response does not match the task")
        return text, metadata
    except Exception:
        metadata["fallback"] = True
        return fallback, metadata


def generate_advice(req):
    messages = [LLMMessage(role="system", content=system_prompt(req.phase))]
    messages += [LLMMessage(role="user" if msg.role == "user" else "assistant", content=msg.text)
                 for msg in req.history[-10:]]
    messages.append(LLMMessage(role="user", content=context_for(req) + "\n学習者の発言: " + (req.current_message or "今のプログラムを一緒に検討したい。")))
    text, metadata = respond(messages, fallback_advice(req))
    return {"message": advice_evidence(req) + "\n\n" + text, "llm": metadata}


def group_evidence(group):
    scenario = next(s for s in SCENARIOS if s["id"] == group["scenario"])
    result = simulate(goal_example_program(group["id"]), [TestInput.model_validate(s) for s in scenario["steps"]])
    m = result["metrics"]
    return (f"私たちの案を「{scenario['label']}」で実行しました。"
            f"制約違反は{m['violation_steps']}ステップ、目安以上の部屋への未対応は延べ{m['unserved_room_steps']}部屋ステップ、"
            f"参考待ち時間の最大値はA室{m['max_wait']['A']}・B室{m['max_wait']['B']}です。"
            f"無人・800ppm以下への運転は{m['unnecessary_ventilation_steps']}回でした。"
            f"この経過での数値基準は{'達成' if result['achievement']['all_met'] else '未達'}です。"
            f"1,500ppm以上の未対応は延べ{m['urgent_unserved_room_steps']}部屋ステップでした。")


def generate_discussion(req):
    context = context_for(req)
    history = "\n".join(f"{msg.speaker or msg.role}: {msg.text}" for msg in req.history[-12:])
    turns = []
    for group in GROUPS:
        evidence = group_evidence(group)
        current = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns)
        messages = [
            LLMMessage(role="system", content=system_prompt(4) + f"\nあなたは{group['group']}です。司会ではありません。あなたの案: {' '.join(group['rules'])}\n確認済みの実行結果: {evidence}\n実行結果はシステムが別に表示します。繰り返さず、前の発言との共通点・相違点を1〜2文で述べてください。"),
            LLMMessage(role="user", content=f"学習者の状態: {context}\n過去の対話: {history}\n今回の先行発言: {current}\n学習者: {req.current_message or 'それぞれの案を比べたい。'}"),
        ]
        reaction, metadata = respond(messages, group["question"], role=group["id"],
                                     max_tokens=int(os.environ.get("GROUP_MAX_TOKENS", "180")))
        turn = {"role": "group", "speaker": group["group"], "agent_id": group["id"],
                "text": evidence + "\n" + reaction, "llm": metadata}
        turns.append(turn)
        yield turn
    messages = [LLMMessage(role="system", content=system_prompt(4)),
                LLMMessage(role="user", content=f"学習者の状態: {context}\n学習者: {req.current_message or '案を比べたい。'}\n今回の発言: " + json.dumps(turns, ensure_ascii=False))]
    text, metadata = respond(messages, "自分の案で重視した目的と、ほかの案で重視した目的を比べると、どの場面を確かめたいですか？", role="facilitator",
                             max_tokens=int(os.environ.get("FACILITATOR_MAX_TOKENS", "220")))
    summary = "各案は濃度、待ち時間、運転の継続をそれぞれ重視しています。数値基準を満たしたか確認し、同じ入力で高濃度の未対応時間と判断の根拠を比べましょう。"
    yield {"role": "ai", "speaker": "司会AI", "agent_id": "facilitator", "text": summary + "\n" + text, "llm": metadata}

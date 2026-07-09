from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import os
import json
import re
from urllib import request as urllib_request
from urllib import error as urllib_error
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="プログラミング学習支援システム API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Data models ---

class Condition(BaseModel):
    type: str  # "person_sensor" | "dark_sensor"


class Rule(BaseModel):
    id: str
    conditions: List[Condition]
    action: str  # "door" | "bell"


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
    role: str   # "user" | "ai"
    text: str


class AdviceRequest(BaseModel):
    rules: List[Rule]
    environment: Environment
    result: SimulationResult
    history: Optional[List[ChatMessage]] = []   # 過去の会話ターン（今回の発言を含まない）
    current_message: Optional[str] = None        # 今回送るメッセージ
    phase: Optional[int] = 2  # 2=pair, 3=verify, 4=group


# --- Prompt construction ---

SYSTEM_PROMPT_BASE = """\
あなたはプログラミング教育をサポートするAIです。
学習者が「コンビニエンスストアの入り口制御プログラム」に取り組んでいます。

【課題】
コンビニの入り口に設置されたセンサーを使って、以下のルールを満たすプログラムを作ってください。
  ・人が来たら → 自動ドアを開ける（昼夜問わず）
  ・夜に人が来たら → チャイムを鳴らす（昼は鳴らさない）

【使えるセンサー（条件）】
  ・人感センサーON → 人がいる
  ・明るさセンサーON → 夜（暗い）

【使えるアクション】
  ・ドアを開ける / チャイムを鳴らす

【複数ルールの動作】
  全てのルールを評価し、条件を満たすルールのアクションを全て実行する。

【重要：プログラムの把握について】
あなたは「=== 学習者が現在作っているプログラム ===」セクションを常に参照できます。
学習者に「どんなルールにしたの？」「教えてください」などとルール内容を聞き返してはいけません。
必ずシステムに記載されたルールを読んだ上で、その内容に具体的に言及して話しかけてください。

【共通ルール】
1. 正解のルール構成を直接教えない
2. 問いかけは最後に1〜2個まとめる（会話の途中で終わらせない）
3. 学習者を励ます言葉を添える
4. 全シナリオ正解なら素直に称賛する
5. 会話の流れを踏まえて前の返答に応じた反応をする
6. 応答は必ず文章を最後まで完結させること
"""



PROMPT_FILE = Path(__file__).parent / "data" / "prompts.json"

DEFAULT_PROMPTS = {
    "base": SYSTEM_PROMPT_BASE,
    "phase2_extra": """
【あなたの役割：ペアの友達】
今は「ペアで対話する」フェーズです。あなたは学習者のペアの友達として振る舞ってください。

・自分もプログラムを考えていた友達として、お互いの考えを比べるように話す
・「私はこう考えたんだけど、あなたは？」「そこ、なんでそうしたの？」のような自然な対話スタイル
・学習者のプログラムと自分の（架空の）考えを比較して、違いや疑問を投げかける
・間違いを指摘するのではなく、「あれ、これだとどうなる？」と一緒に考える姿勢で
""",
    "phase3_extra": """
【あなたの役割：確認のサポーター】
今は「実際にプログラムを動かして確認する」フェーズです。

・4つのシナリオ（昼夜×人あり/なし）を順番に確認するよう促す
・「このシナリオでは正しく動いた？」「他のパターンも試してみた？」と確認を促す
・シミュレーション結果を見ながら、なぜそうなるのかを一緒に考える
""",
    "phase4_extra": """
【あなたの役割：全体対話のファシリテーター】
今は「全体で対話する」フェーズです。クラス全員が集まって話し合う場を演出してください。

・1対1のペア対話ではなく、クラス全体に向けて司会する
・「あなたはどう思う？」だけで終わらず、「Aグループでは〜」「別の考えとして〜」のように複数の視点を提示する
・他のグループが作った（架空の）プログラムを提示して、それについて意見を求める
・学習者個人のプログラムへの直接アドバイスよりも、他者の考えを比較・検討する発問を優先する
・呼びかけは「みんな」「クラス全体」「他のグループ」という言葉を使い、全体共有の雰囲気にする
・以下の典型的な間違いパターンを使って議論を促す：

  パターンA（ベルに人感センサーなし）:
    「夜だから暗い → チャイムを鳴らす」というプログラムを作ったグループがあったよ。
    これ、どんな問題があると思う？

  パターンB（ドアに夜条件が入っている）:
    「夜に人が来たら → ドアを開ける」というルールを作ったグループがいたよ。
    昼間はどうなっちゃうと思う？

  パターンD（直列になっている）:
    「ドアが開いたら → チャイムが鳴る」という考えのグループもいたよ。
    これだと実際のコンビニでどういうことが起きそう？

・他者のプログラムを批判的に検討することで、自分のプログラムも見直すよう促す
・「あなたのプログラムはこのパターンと違う？どこが違う？」と比較させる
""",
}


def load_prompts() -> dict:
    """カスタムプロンプトをファイルから読み込む。なければデフォルトを返す。"""
    if PROMPT_FILE.exists():
        try:
            with PROMPT_FILE.open(encoding="utf-8") as f:
                stored = json.load(f)
            # デフォルトのキーを補完しつつ返す
            merged = {**DEFAULT_PROMPTS, **stored}
            return merged
        except Exception:
            pass
    return dict(DEFAULT_PROMPTS)


def save_prompts(prompts: dict):
    PROMPT_FILE.parent.mkdir(exist_ok=True)
    with PROMPT_FILE.open("w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)


def get_system_prompt(phase: int) -> str:
    p = load_prompts()
    base = p.get("base", DEFAULT_PROMPTS["base"])
    if phase == 2:
        return base + p.get("phase2_extra", DEFAULT_PROMPTS["phase2_extra"])
    elif phase == 3:
        return base + p.get("phase3_extra", DEFAULT_PROMPTS["phase3_extra"])
    elif phase == 4:
        return base + p.get("phase4_extra", DEFAULT_PROMPTS["phase4_extra"])
    return base + p.get("phase2_extra", DEFAULT_PROMPTS["phase2_extra"])


def build_system_instruction(phase: int, req: "AdviceRequest") -> str:
    """フェーズの役割 + 学習者の現在のプログラム状態をシステム指示として返す"""
    role_prompt = get_system_prompt(phase)

    rules_str = describe_rules(req.rules)
    scenarios_str = describe_scenarios(req.rules)
    env_label = f"{'夜' if req.environment.isDark else '昼'} × {'人あり' if req.environment.personPresent else '人なし'}"

    program_context = f"""
========================================
【現在の学習者のプログラム（必ず読むこと）】
========================================
{rules_str}

【全シナリオのシミュレーション結果】
{scenarios_str}

【現在選択中の環境】
  {env_label}
  ドア: {'開いている' if req.result.doorOpen else '閉まっている'} {'（正しい）' if req.result.doorCorrect else '（間違い）'}
  チャイム: {'鳴っている' if req.result.bellRinging else '静か'} {'（正しい）' if req.result.bellCorrect else '（間違い）'}
  全体判定: {'全シナリオ正解' if req.result.allCorrect else '不正解あり'}
========================================

上記のプログラム内容をすでに把握した前提で対話してください。
学習者にルールの内容を聞き返してはいけません。
"""
    if phase == 4:
        return role_prompt + program_context
    return role_prompt + program_context + build_program_draft_instruction()


def build_program_draft_instruction() -> str:
    """
    応答末尾に「AIがこの問題で考えたプログラム」セクションを付ける追加指示。
    AI_INCLUDE_PROGRAM_DRAFT=false で無効化できる。
    """
    enabled = os.environ.get("AI_INCLUDE_PROGRAM_DRAFT", "true").strip().lower() not in ("0", "false", "off")
    if not enabled:
        return ""

    max_rules = os.environ.get("AI_PROGRAM_DRAFT_MAX_RULES", "1").strip()
    if not max_rules.isdigit():
        max_rules = "2"

    return f"""

【出力フォーマット（必須）】
応答は次の2部構成にしてください。
1) 学習者への問いかけ・コメント
2) 「AIがこの問題で考えたプログラム」

重要:
- あなたは学習者より上の立場ではなく、同じ学習者レベルの対話相手として話す
- 「正解を教える先生」ではなく「自分はこう考えたけど、どう思う？」という姿勢を守る
- 断定や採点口調は使わない（例: 「これは間違い」「正解は〜」は避ける）

「AIがこの問題で考えたプログラム」では、以下の形式を必ず使ってください。
- ルール1: [条件] → [アクション]
- ルール2: [条件] → [アクション]
- 考えた理由: （1〜2文）

制約:
- 仮説ルールは最大{max_rules}個まで
- 「私ならこうする」「私はこう考えた」を使って提示する
- 学習者の現在ルールとの差分が分かるように簡潔に書く
- 学習者の現在ルールをそのまま復唱しただけの案は禁止（最低1つ差分を入れる）
"""


def describe_rules(rules: List[Rule]) -> str:
    if not rules:
        return "（ルールが設定されていません）"

    cond_labels = {
        "person_sensor": "人感センサーON",
        "dark_sensor": "明るさセンサーON（夜）",
    }
    action_labels = {
        "door": "ドアを開ける",
        "bell": "チャイムを鳴らす",
    }

    lines = []
    for i, rule in enumerate(rules, 1):
        cond_parts = [cond_labels.get(c.type, c.type) for c in rule.conditions]
        cond_str = " AND ".join(cond_parts) if cond_parts else "（条件なし）"
        action_str = action_labels.get(rule.action, rule.action)
        lines.append(f"  ルール{i}: [{cond_str}] → [{action_str}]")

    return "\n".join(lines)


def describe_scenarios(rules: List[Rule]) -> str:
    scenarios = [
        {"label": "昼・人あり",  "personPresent": True,  "isDark": False},
        {"label": "昼・人なし",  "personPresent": False, "isDark": False},
        {"label": "夜・人あり",  "personPresent": True,  "isDark": True},
        {"label": "夜・人なし",  "personPresent": False, "isDark": True},
    ]

    lines = []
    for s in scenarios:
        conds = {"person_sensor": s["personPresent"], "dark_sensor": s["isDark"]}
        door = False
        bell = False
        for rule in rules:
            if rule.conditions and all(conds.get(c.type, False) for c in rule.conditions):
                if rule.action == "door":
                    door = True
                elif rule.action == "bell":
                    bell = True

        door_correct = door == s["personPresent"]
        bell_correct = bell == (s["personPresent"] and s["isDark"])
        status = "✓" if (door_correct and bell_correct) else "✗"
        lines.append(
            f"  {s['label']}: ドア={'開' if door else '閉'} / チャイム={'鳴る' if bell else '静か'} {status}"
        )
    return "\n".join(lines)


def build_user_message(req: AdviceRequest) -> str:
    rules_str = describe_rules(req.rules)
    scenarios_str = describe_scenarios(req.rules)
    env_label = f"{'夜' if req.environment.isDark else '昼'} × {'人あり' if req.environment.personPresent else '人なし'}"

    return f"""\
【学習者が作ったプログラム】
{rules_str}

【全シナリオのシミュレーション結果】
{scenarios_str}

【現在選択中の環境】
  {env_label}
  ドア: {'開いている' if req.result.doorOpen else '閉まっている'} {'（正しい）' if req.result.doorCorrect else '（間違い）'}
  チャイム: {'鳴っている' if req.result.bellRinging else '静か'} {'（正しい）' if req.result.bellCorrect else '（間違い）'}
  全体判定: {'✓ 全シナリオ正解' if req.result.allCorrect else '✗ 不正解あり'}

このプログラムに不足や誤りがある場合、学習者が自分で気づけるような問いかけをしてください。
全シナリオ正解なら称賛してください。
"""


# --- LLM helpers ---

def get_llm_provider() -> str:
    """
    LLMプロバイダを返す。
    auto: GEMINI_API_KEY があれば gemini、なければ OLLAMA_MODEL があれば ollama、最後に fallback。
    """
    provider = os.environ.get("LLM_PROVIDER", "auto").strip().lower()

    if provider in ("gemini", "ollama", "fallback"):
        return provider

    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_ollama = bool(os.environ.get("OLLAMA_MODEL"))
    if has_gemini:
        return "gemini"
    if has_ollama:
        return "ollama"
    return "fallback"


def build_message_payload(user_text: str, req: AdviceRequest) -> str:
    rules_str = describe_rules(req.rules)
    scenarios_str = describe_scenarios(req.rules)
    return (
        f"[現在のプログラム]\n{rules_str}\n\n"
        f"[全シナリオ結果]\n{scenarios_str}\n\n"
        f"[メッセージ]\n{user_text}"
    )


def generate_with_gemini(req: AdviceRequest, user_text: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が未設定です")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    history = []
    for msg in (req.history or [])[-10:]:
        history.append(
            types.Content(
                role="user" if msg.role == "user" else "model",
                parts=[types.Part(text=msg.text)],
            )
        )

    system_instruction = build_system_instruction(req.phase or 2, req)
    message_to_send = build_message_payload(user_text, req)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    chat = client.chats.create(
        model=model_name,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=2048,
            temperature=0.7,
        ),
        history=history,
    )
    response = chat.send_message(message_to_send)
    return response.text


def generate_with_ollama(req: AdviceRequest, user_text: str) -> str:
    model_name = os.environ.get("OLLAMA_MODEL")
    if not model_name:
        raise ValueError("OLLAMA_MODEL が未設定です")

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    timeout_seconds = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
    system_instruction = build_system_instruction(req.phase or 2, req)
    message_to_send = build_message_payload(user_text, req)

    messages = [{"role": "system", "content": system_instruction}]
    for msg in (req.history or [])[-10:]:
        role = "assistant" if msg.role == "ai" else "user"
        messages.append({"role": role, "content": msg.text})
    messages.append({"role": "user", "content": message_to_send})

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7},
    }

    req_obj = urllib_request.Request(
        url=f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req_obj, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib_error.URLError as e:
        raise RuntimeError(f"Ollama 接続エラー: {e}") from e

    content = data.get("message", {}).get("content")
    if not content:
        raise RuntimeError("Ollama 応答が空でした")
    return content


def parse_program_draft_from_message(message: str) -> Dict[str, Any]:
    """
    AI応答から「AIの仮説プログラム」セクションを抽出し、UI用に構造化する。
    返り値:
      - message: チャット表示用本文（仮説セクション除去後）
      - program_draft: [{conditions:[{type}], action}] 形式
    """
    headers = ["AIがこの問題で考えたプログラム", "AIの仮説プログラム"]
    idx = -1
    found_header = ""
    for h in headers:
        pos = message.find(h)
        if pos >= 0 and (idx < 0 or pos < idx):
            idx = pos
            found_header = h
    body = message.strip()
    draft_block = message
    if idx >= 0:
        body = message[:idx].strip()
        if not body:
            body = "AIがこの問題で考えたプログラムを更新しました。下の提案を確認してください。"
        draft_block = message[idx + len(found_header):]

    cond_map = {
        "人感センサーON": "person_sensor",
        "人感センサー": "person_sensor",
        "明るさセンサーON（夜）": "dark_sensor",
        "明るさセンサーON": "dark_sensor",
        "明るさセンサー": "dark_sensor",
        "夜": "dark_sensor",
    }
    action_map = {
        "ドアを開ける": "door",
        "チャイムを鳴らす": "bell",
    }

    max_rules_env = os.environ.get("AI_PROGRAM_DRAFT_MAX_RULES", "1").strip()
    max_rules = int(max_rules_env) if max_rules_env.isdigit() and int(max_rules_env) > 0 else 1

    draft_rules: List[Dict[str, Any]] = []
    seen = set()
    for line in draft_block.splitlines():
        m = re.search(r"ルール\d+\s*:\s*\[(.*?)\]\s*→\s*\[(.*?)\]", line.strip())
        if not m:
            continue

        cond_text = m.group(1).strip()
        action_text = m.group(2).strip()
        action = action_map.get(action_text)
        if not action:
            continue

        parts = [p.strip() for p in re.split(r"\s*(?:AND|and|＆|&|かつ)\s*", cond_text) if p.strip()]
        cond_types: List[str] = []
        for p in parts:
            ctype = cond_map.get(p)
            if ctype and ctype not in cond_types:
                cond_types.append(ctype)

        if not cond_types:
            continue

        key = (tuple(sorted(cond_types)), action)
        if key in seen:
            continue
        seen.add(key)
        draft_rules.append(
            {
                "conditions": [{"type": c} for c in cond_types],
                "action": action,
            }
        )
        if len(draft_rules) >= max_rules:
            break

    return {"message": body, "program_draft": draft_rules}


def _rule_signature_from_api_rule(rule: Dict[str, Any]) -> tuple:
    conds = tuple(sorted(c.get("type") for c in rule.get("conditions", []) if c.get("type")))
    action = rule.get("action")
    return conds, action


def _rule_signature_from_req_rule(rule: Rule) -> tuple:
    conds = tuple(sorted(c.type for c in rule.conditions if c.type))
    return conds, rule.action


def build_non_repetitive_draft(req: AdviceRequest, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    学習者の現ルールをそのまま復唱したAI案を除去し、
    可能なら差分のある1件を返す。
    """
    current_signatures = {_rule_signature_from_req_rule(r) for r in req.rules}
    candidates = parsed.get("program_draft", []) or []

    filtered = []
    for r in candidates:
        if _rule_signature_from_api_rule(r) not in current_signatures:
            filtered.append(r)

    if filtered:
        return {"message": parsed.get("message", ""), "program_draft": filtered[:1]}

    # 差分候補をドメイン知識から1件だけ補完（復唱対策）
    canonical_candidates = [
        {
            "conditions": [{"type": "person_sensor"}],
            "action": "door",
        },
        {
            "conditions": [{"type": "person_sensor"}, {"type": "dark_sensor"}],
            "action": "bell",
        },
    ]
    for c in canonical_candidates:
        if _rule_signature_from_api_rule(c) not in current_signatures:
            return {"message": parsed.get("message", ""), "program_draft": [c]}

    return {"message": parsed.get("message", ""), "program_draft": []}


# --- Fallback responses ---

def fallback_response(req: AdviceRequest) -> str:
    rules = req.rules

    if not rules:
        return (
            "まだルールが1つも作られていませんね。\n"
            "コンビニのドアって、どんなときに開くと思いますか？"
        )

    door_rules = [r for r in rules if r.action == "door"]
    bell_rules = [r for r in rules if r.action == "bell"]

    # ドアのルールに夜条件が入っている
    if door_rules:
        for r in door_rules:
            if any(c.type == "dark_sensor" for c in r.conditions):
                return (
                    "ドアのルールに「明るさセンサー」が入っていますね。\n"
                    "昼間にお客さんが来たとき、ドアはどうなりますか？"
                )

    # 人感センサーなしでベルが鳴る
    if bell_rules:
        for r in bell_rules:
            if not any(c.type == "person_sensor" for c in r.conditions):
                return (
                    "チャイムのルールに人感センサーが入っていないですね。\n"
                    "お店に誰もいないのに、夜中ずっとチャイムが鳴ってしまうことはないですか？"
                )

    # ドアのルールがない
    if not door_rules:
        return (
            "ドアを開けるルールがまだないようですね。\n"
            "お客さんが来たとき、ドアはどうなってほしいですか？"
        )

    # ベルのルールがない
    if not bell_rules:
        return (
            "ドアのルールは作れていますね！\n"
            "課題には「夜だけチャイムが鳴る」という条件もありましたね。どうすれば夜だけ鳴るようにできますか？"
        )

    if req.result.allCorrect:
        return (
            "4つ全てのシナリオで正しく動いていますね！素晴らしい！\n"
            "「昼・人あり」「夜・人あり」「昼・人なし」「夜・人なし」、どれも確認できましたか？"
        )

    return (
        "いい感じになってきました！\n"
        "4つのシナリオ（昼夜×人あり/なし）を全部チェックして、おかしな動きがないか確かめてみましょう。"
    )


# --- Endpoint ---

@app.post("/api/advice")
async def get_advice(req: AdviceRequest):
    # 今回送るメッセージ（未指定ならアドバイスリクエスト扱い）
    user_text = req.current_message or "今のプログラムについてコメントしてください。"
    provider = get_llm_provider()

    if provider == "gemini":
        try:
            generated = generate_with_gemini(req, user_text)
            parsed = parse_program_draft_from_message(generated)
            return build_non_repetitive_draft(req, parsed)
        except Exception as e:
            return {"message": f"Gemini API エラー: {e}", "program_draft": []}

    if provider == "ollama":
        try:
            generated = generate_with_ollama(req, user_text)
            parsed = parse_program_draft_from_message(generated)
            return build_non_repetitive_draft(req, parsed)
        except Exception as e:
            return {"message": f"Ollama API エラー: {e}", "program_draft": []}

    return {"message": fallback_response(req), "program_draft": []}


# --- Prompt config endpoint ---

class PromptsConfig(BaseModel):
    base: str
    phase2_extra: str
    phase3_extra: str
    phase4_extra: str


@app.get("/api/config/prompts")
async def get_prompts_config():
    p = load_prompts()
    return {
        "base": p.get("base", DEFAULT_PROMPTS["base"]),
        "phase2_extra": p.get("phase2_extra", DEFAULT_PROMPTS["phase2_extra"]),
        "phase3_extra": p.get("phase3_extra", DEFAULT_PROMPTS["phase3_extra"]),
        "phase4_extra": p.get("phase4_extra", DEFAULT_PROMPTS["phase4_extra"]),
    }


@app.post("/api/config/prompts")
async def update_prompts_config(config: PromptsConfig):
    save_prompts(config.model_dump())
    return {"status": "ok"}


@app.post("/api/config/prompts/reset")
async def reset_prompts_config():
    if PROMPT_FILE.exists():
        PROMPT_FILE.unlink()
    return {"status": "ok", "message": "デフォルトにリセットしました"}


# --- Log endpoint ---

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / "sessions.jsonl"


class LogEntry(BaseModel):
    session_id: str
    event: str          # "phase_complete" | "session_end"
    phase: int
    rules: List[Rule]
    chat_history: List[ChatMessage]
    all_correct: bool


@app.post("/api/log")
async def save_log(entry: LogEntry):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": entry.session_id,
        "event": entry.event,
        "phase": entry.phase,
        "rules": [
            {
                "conditions": [c.type for c in r.conditions],
                "action": r.action,
            }
            for r in entry.rules
        ],
        "chat_history": [
            {"role": m.role, "text": m.text}
            for m in entry.chat_history
        ],
        "all_correct": entry.all_correct,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "ok"}


@app.get("/api/log/export")
async def export_log():
    if not LOG_FILE.exists():
        return []
    entries = []
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


@app.get("/")
def root():
    return {"status": "ok", "message": "プログラミング学習支援システム API"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
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

【共通ルール】
1. 正解のルール構成を直接教えない
2. 問いかけは 1〜2 個に絞る
3. 学習者を励ます言葉を添える
4. 全シナリオ正解なら素直に称賛する
5. 会話の流れを踏まえて前の返答に応じた反応をする
"""

SYSTEM_PROMPT_PHASE2 = SYSTEM_PROMPT_BASE + """
【あなたの役割：ペアの友達】
今は「ペアで対話する」フェーズです。あなたは学習者のペアの友達として振る舞ってください。

・自分もプログラムを考えていた友達として、お互いの考えを比べるように話す
・「私はこう考えたんだけど、あなたは？」「そこ、なんでそうしたの？」のような自然な対話スタイル
・学習者のプログラムと自分の（架空の）考えを比較して、違いや疑問を投げかける
・間違いを指摘するのではなく、「あれ、これだとどうなる？」と一緒に考える姿勢で
"""

SYSTEM_PROMPT_PHASE3 = SYSTEM_PROMPT_BASE + """
【あなたの役割：確認のサポーター】
今は「実際にプログラムを動かして確認する」フェーズです。

・4つのシナリオ（昼夜×人あり/なし）を順番に確認するよう促す
・「このシナリオでは正しく動いた？」「他のパターンも試してみた？」と確認を促す
・シミュレーション結果を見ながら、なぜそうなるのかを一緒に考える
"""

SYSTEM_PROMPT_PHASE4 = SYSTEM_PROMPT_BASE + """
【あなたの役割：全体対話のファシリテーター】
今は「全体で対話する」フェーズです。クラス全員が集まって話し合う場を演出してください。

・他のグループが作った（架空の）プログラムを提示して、それについて意見を求める
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
"""


def get_system_prompt(phase: int) -> str:
    if phase == 2:
        return SYSTEM_PROMPT_PHASE2
    elif phase == 3:
        return SYSTEM_PROMPT_PHASE3
    elif phase == 4:
        return SYSTEM_PROMPT_PHASE4
    return SYSTEM_PROMPT_PHASE2


def build_system_instruction(phase: int, req: "AdviceRequest") -> str:
    """フェーズの役割 + 学習者の現在のプログラム状態をシステム指示として返す"""
    role_prompt = get_system_prompt(phase)

    rules_str = describe_rules(req.rules)
    scenarios_str = describe_scenarios(req.rules)
    env_label = f"{'夜' if req.environment.isDark else '昼'} × {'人あり' if req.environment.personPresent else '人なし'}"

    program_context = f"""
=== 学習者が現在作っているプログラム ===
{rules_str}

=== 全シナリオのシミュレーション結果 ===
{scenarios_str}

=== 現在選択中の環境 ===
  {env_label}
  ドア: {'開いている' if req.result.doorOpen else '閉まっている'} {'（正しい）' if req.result.doorCorrect else '（間違い）'}
  チャイム: {'鳴っている' if req.result.bellRinging else '静か'} {'（正しい）' if req.result.bellCorrect else '（間違い）'}
  全体判定: {'全シナリオ正解' if req.result.allCorrect else '不正解あり'}

このプログラムの状態を常に念頭に置いて対話してください。
"""
    return role_prompt + program_context


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
    api_key = os.environ.get("GEMINI_API_KEY")

    # 今回送るメッセージ（未指定ならアドバイスリクエスト扱い）
    message_to_send = req.current_message or "今のプログラムについてコメントしてください。"

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            # 過去の会話履歴を Gemini 形式に変換（直近10件）
            history = []
            for msg in (req.history or [])[-10:]:
                history.append(
                    types.Content(
                        role="user" if msg.role == "user" else "model",
                        parts=[types.Part(text=msg.text)],
                    )
                )

            # プログラム状態をシステム指示に組み込む
            system_instruction = build_system_instruction(req.phase or 2, req)

            chat = client.chats.create(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=400,
                    temperature=0.7,
                ),
                history=history,
            )
            response = chat.send_message(message_to_send)
            return {"message": response.text}
        except Exception as e:
            return {"message": f"Gemini API エラー: {e}"}

    return {"message": fallback_response(req)}


@app.get("/")
def root():
    return {"status": "ok", "message": "プログラミング学習支援システム API"}

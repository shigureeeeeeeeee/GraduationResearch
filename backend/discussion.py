import os
from typing import Any, Dict, Iterator, List, Optional

from domain import describe_rules, describe_scenarios
from llm_clients import (
    GenerationOptions,
    LLMMessage,
    create_llm_client,
)
from prompts import get_system_prompt
from schemas import AdviceRequest, ChatMessage


GROUP_AGENTS = (
    {
        "id": "group_a",
        "speaker": "Aグループ",
        "initial_program": "[明るさセンサーON（夜）] → [チャイムを鳴らす]",
        "focus": "夜に人がいない場面で、自分たちの案がどう動くかを特に考える",
        "required_observation": "人がいない夜でも、明るさセンサーONだけでチャイムが鳴る",
    },
    {
        "id": "group_b",
        "speaker": "Bグループ",
        "initial_program": "[人感センサーON AND 明るさセンサーON（夜）] → [ドアを開ける]",
        "focus": "昼に人が来た場面で、自分たちの案がどう動くかを特に考える",
        "required_observation": "昼に人が来ても、明るさセンサーがOFFなのでドアは開かない",
    },
    {
        "id": "group_c",
        "speaker": "Cグループ",
        "initial_program": (
            "[人感センサーON] → [ドアを開ける] / "
            "[人感センサーON] → [チャイムを鳴らす]"
        ),
        "focus": "昼に人が来た場面で、チャイムも鳴らしてよいかを特に考える",
        "required_observation": "昼に人が来ると、ドアだけでなくチャイムも鳴る",
    },
)

GROUP_FALLBACK_REACTIONS = {
    "group_a": "学習者の指摘と同じ点に気づきました。ほかの場面でも似た問題が起きないでしょうか？",
    "group_b": "Aグループとは違う場面ですが、条件を一つずつ確かめる必要がある点は同じだと思います。",
    "group_c": "Bグループと同じ昼の場面でも、注目した動作が違いました。自分たちの案では両方を確認できていますか？",
}


def format_history(history: Optional[List[ChatMessage]]) -> str:
    if not history:
        return "（まだ発言はありません）"
    lines = []
    for message in history[-12:]:
        speaker = message.speaker or (
            "学習者" if message.role == "user" else "司会AI"
        )
        lines.append(f"{speaker}: {message.text}")
    return "\n".join(lines)


def build_group_system_prompt(agent: Dict[str, str]) -> str:
    return f"""\
あなたはプログラミング課題について話し合う「{agent['speaker']}」の代表です。
司会者ではなく、他グループとは独立した一つのグループとして発言してください。

【課題】
・人が来たら、昼夜を問わずドアを開ける
・夜に人が来たらチャイムを鳴らし、昼や人がいないときは鳴らさない

【使えるものと意味】
・人感センサーON = 人がいる
・明るさセンサーON = 夜（暗い）
・ドアを開ける
・チャイムを鳴らす
この4種類以外は使えません。時計、時刻、日没、日の出、新しいセンサー、センサーの精度の話を持ち込まないでください。
明るさセンサーONが夜を正しく表すことは前提であり、その精度を疑う課題ではありません。

【あなたたちが最初に考えた案】
{agent['initial_program']}

【このグループが注目する観点】
{agent['focus']}

【シミュレーションで確認済みの事実（変更・否定禁止）】
{agent['required_observation']}
この事実はプログラムを実行して確認済みです。反対の結果を述べたり、別の条件へ読み替えたりしてはいけません。

【発言ルール】
・確認済みの事実はシステムが別に表示するため、あなたは繰り返さない
・前に発言した学習者や別グループとの共通点または相違点だけを1〜2文で述べる
・プログラムの動作や修正案を新たに説明しない
・課題の条件を再計算しない
・自分のグループは「私たち」と呼ぶ
・正解のルール構成をそのまま提示しない
・質問は多くても1つにする
・見出しや「{agent['speaker']}:」という話者名は出力しない
"""


def build_group_user_prompt(
    req: AdviceRequest,
    user_text: str,
    turns: List[Dict[str, str]],
) -> str:
    current_round = "\n".join(
        f"{turn['speaker']}: {turn['text']}" for turn in turns
    ) or "（このラウンドではまだ他グループは発言していません）"
    return f"""\
【これまでの全体対話】
{format_history(req.history)}

【学習者の現在のプログラム】
{describe_rules(req.rules)}

【学習者のプログラムを動かした結果】
{describe_scenarios(req.rules)}

【学習者の今回の発言】
{user_text}

【このラウンドで先に出たグループの発言】
{current_round}

確認済みの動作はシステム側で表示します。上の発言を受けた、あなたのグループとしての反応だけを述べてください。
"""


def build_facilitator_prompt(
    req: AdviceRequest,
    user_text: str,
    turns: List[Dict[str, str]],
) -> str:
    current_round = "\n".join(
        f"{turn['speaker']}: {turn['text']}" for turn in turns
    )
    return f"""\
【学習者の今回の発言】
{user_text}

【今回、独立して考えた各グループの発言】
{current_round}

【学習者の現在のプログラム】
{describe_rules(req.rules)}

3グループの共通点と相違点を短く整理し、学習者が自分のプログラムと比較するための問いを1つだけ出してください。
正解のルール構成は直接教えず、3〜5文で完結させてください。
使えるのは人感センサー、明るさセンサー、ドア、チャイムだけです。時計、時刻、日没、日の出、センサー精度など、発言にない新しい論点は追加しないでください。
"""


def valid_group_reaction(message: str) -> bool:
    forbidden = (
        "時計", "時刻", "日没", "日の出", "日出", "侵入", "防犯",
        "安全面", "センサーの精度", "誤検知", "人感", "明るさ", "センサー",
        "ドア", "チャイム", "昼", "夜", "開く", "開ける", "閉", "鳴る",
        "鳴らす", "鳴らない",
    )
    text = message.strip()
    return (
        10 <= len(text) <= 180
        and not any(term in text for term in forbidden)
        and text[-1] in "。？！?！"
    )


def valid_facilitator_message(message: str) -> bool:
    forbidden = (
        "時計", "時刻", "日没", "日の出", "日出", "侵入", "防犯",
        "安全面", "センサーの精度", "誤検知",
    )
    text = message.strip()
    return (
        bool(text)
        and not any(term in text for term in forbidden)
        and text[-1] in "。？！?！"
        and all(group in text for group in ("Aグループ", "Bグループ", "Cグループ"))
    )


def compose_group_message(agent: Dict[str, str], reaction: str) -> str:
    return (
        f"私たちの案をシミュレーションして、{agent['required_observation']}ことを確認しました。\n"
        f"{reaction.strip()}"
    )


def fallback_metadata() -> Dict[str, Any]:
    return {
        "provider": "fallback",
        "model": "rule-based",
        "elapsed_ms": 0,
        "fallback": True,
    }


def result_metadata(result, *, fallback: bool = False) -> Dict[str, Any]:
    return {
        "provider": result.provider,
        "model": result.model,
        "elapsed_ms": result.elapsed_ms,
        "fallback": fallback,
    }


def fallback_discussion() -> List[Dict[str, Any]]:
    turns = [
        {
            "role": "group",
            "speaker": agent["speaker"],
            "agent_id": agent["id"],
            "text": compose_group_message(
                agent, GROUP_FALLBACK_REACTIONS[agent["id"]]
            ),
            "llm": fallback_metadata(),
        }
        for agent in GROUP_AGENTS
    ]
    turns.append(
        {
            "role": "ai",
            "speaker": "司会AI",
            "agent_id": "facilitator",
            "text": (
                "Aグループは人がいない夜のチャイム、Bグループは昼に人が来たときのドア、"
                "Cグループは昼のチャイムに注目しました。"
                "自分のプログラムを4つの場面で動かすと、どのグループと似た問題が起きそうですか？"
            ),
            "llm": fallback_metadata(),
        }
    )
    return turns


def generate_discussion(req: AdviceRequest) -> Iterator[Dict[str, Any]]:
    user_text = req.current_message or (
        "各グループのプログラムを比べて、気づいたことを話し合いたいです。"
    )
    turns = []
    group_max_tokens = int(
        os.environ.get(
            "GROUP_MAX_TOKENS",
            os.environ.get("OLLAMA_GROUP_NUM_PREDICT", "140"),
        )
    )
    for agent in GROUP_AGENTS:
        messages = [
            LLMMessage(
                role="system",
                content=build_group_system_prompt(agent),
            ),
            LLMMessage(
                role="user",
                content=build_group_user_prompt(req, user_text, turns),
            ),
        ]
        metadata = fallback_metadata()
        try:
            client = create_llm_client(role=agent["id"])
            result = client.chat(
                messages,
                GenerationOptions(
                    temperature=0.45,
                    max_tokens=group_max_tokens,
                ),
            )
            reaction = result.text.strip()
            metadata = result_metadata(result)
            if not valid_group_reaction(reaction):
                reaction = GROUP_FALLBACK_REACTIONS[agent["id"]]
                metadata["fallback"] = True
        except Exception:
            reaction = GROUP_FALLBACK_REACTIONS[agent["id"]]

        turn = {
            "role": "group",
            "speaker": agent["speaker"],
            "agent_id": agent["id"],
            "text": compose_group_message(agent, reaction),
            "llm": metadata,
        }
        turns.append(turn)
        yield turn

    facilitator_system = get_system_prompt(4) + """

【今回の進行方法】
A・B・Cグループは、それぞれ別のAI呼び出しで独立して考え、すでに発言しました。
あなたは司会に専念し、存在しない追加発言を作らず、提示された発言だけを整理してください。
"""
    messages = [
        LLMMessage(role="system", content=facilitator_system),
        LLMMessage(
            role="user",
            content=build_facilitator_prompt(req, user_text, turns),
        ),
    ]
    facilitator_metadata = fallback_metadata()
    try:
        client = create_llm_client(role="facilitator")
        result = client.chat(
            messages,
            GenerationOptions(
                temperature=0.3,
                max_tokens=int(
                    os.environ.get(
                        "FACILITATOR_MAX_TOKENS",
                        os.environ.get("OLLAMA_FACILITATOR_NUM_PREDICT", "160"),
                    )
                ),
            ),
        )
        facilitator_text = result.text.strip()
        facilitator_metadata = result_metadata(result)
        if not valid_facilitator_message(facilitator_text):
            raise ValueError("司会AIの応答が教材の制約を満たしませんでした")
    except Exception:
        facilitator_metadata["fallback"] = True
        facilitator_text = (
            "Aグループは人がいない夜のチャイム、Bグループは昼に人が来たときのドア、"
            "Cグループは昼のチャイムに注目しました。"
            "それぞれ違う場面ですが、条件と実際の動きを比べている点は共通しています。"
            "自分のプログラムを4つの場面で動かすと、どのグループと似た問題が起きそうですか？"
        )

    yield {
        "role": "ai",
        "speaker": "司会AI",
        "agent_id": "facilitator",
        "text": facilitator_text,
        "llm": facilitator_metadata,
    }

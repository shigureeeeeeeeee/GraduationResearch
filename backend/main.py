from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="プログラミング学習支援システム API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Data models ---

class Condition(BaseModel):
    type: str  # "div3" | "div5" | "always"


class Rule(BaseModel):
    id: str
    conditions: List[Condition]
    action: str  # "fizz" | "buzz" | "fizzbuzz" | "number"


class Environment(BaseModel):
    n: int  # input number


class SimulationResult(BaseModel):
    output: str        # actual output from the learner's program
    expected: str      # correct FizzBuzz output
    is_correct: bool


class AdviceRequest(BaseModel):
    rules: List[Rule]
    environment: Environment
    result: SimulationResult


# --- Prompt construction ---

SYSTEM_PROMPT = """\
あなたはプログラミング教育をサポートするAIメンターです。
学習者が「FizzBuzz」問題に取り組んでいます。

【問題文】
整数 N が与えられたとき、以下のルールに従って出力せよ。
  1. N が 3 の倍数 かつ 5 の倍数 → "FizzBuzz" を出力
  2. N が 3 の倍数              → "Fizz" を出力
  3. N が 5 の倍数              → "Buzz" を出力
  4. それ以外                   → N をそのまま出力

【ブロックの仕様】
・条件ブロック: 「3の倍数」「5の倍数」「常に（else）」
・ルールは上から順に評価し、最初に条件が全て一致したルールのアクションを実行する（if-elif-else 方式）

【あなたの役割】
学習者のプログラムに論理的な誤りや不足がある場合、正解を直接教えず、
ソクラテス式の問いかけで学習者自身が気づけるよう優しく誘導してください。

【厳守ルール】
1. 絶対に正解のコードや正しいルール順を直接教えない
2. 問いかけは 1〜2 個に絞る
3. 学習者を励ます言葉を添える
4. プログラムが正しい場合は素直に称賛する
"""


def describe_rules(rules: List[Rule]) -> str:
    if not rules:
        return "（ルールが設定されていません）"

    cond_labels = {
        "div3": "3の倍数",
        "div5": "5の倍数",
        "always": "常に（else）",
    }
    action_labels = {
        "fizz": '"Fizz" を出力',
        "buzz": '"Buzz" を出力',
        "fizzbuzz": '"FizzBuzz" を出力',
        "number": "N をそのまま出力",
    }

    lines = []
    for i, rule in enumerate(rules, 1):
        cond_parts = [cond_labels.get(c.type, c.type) for c in rule.conditions]
        cond_str = " AND ".join(cond_parts) if cond_parts else "（条件なし）"
        action_str = action_labels.get(rule.action, rule.action)
        lines.append(f"  ルール{i}: [{cond_str}] → [{action_str}]")

    return "\n".join(lines)


def build_user_message(req: AdviceRequest) -> str:
    rules_str = describe_rules(req.rules)
    n = req.environment.n
    correct_mark = "✓ 正解" if req.result.is_correct else f"✗ 不正解（正解: {req.result.expected}）"

    return f"""\
【学習者が作ったプログラム】（ルールは上から順に評価）
{rules_str}

【テストケース】
  入力: N = {n}
  プログラムの出力: {req.result.output}
  期待される出力: {req.result.expected}
  判定: {correct_mark}

このプログラムに論理的な誤りや不足がある場合、学習者が自分で気づけるような問いかけをしてください。
正しければ称賛してください。
"""


# --- Fallback responses ---

def fallback_response(req: AdviceRequest) -> str:
    rules = req.rules
    n = req.environment.n
    result = req.result

    if not rules:
        return (
            "まだルールが1つも設定されていないようですね。"
            "まず「3の倍数のとき、何を出力すればいいか」から考えてみましょう！"
        )

    # Check if FizzBuzz rule exists
    has_fizzbuzz_rule = any(
        rule.action == "fizzbuzz" or (
            rule.action == "fizz" and any(c.type == "div5" for c in rule.conditions)
        )
        for rule in rules
    )

    fizzbuzz_rules = [r for r in rules if r.action == "fizzbuzz"]
    fizz_rules = [r for r in rules if r.action == "fizz"]
    buzz_rules = [r for r in rules if r.action == "buzz"]
    number_rules = [r for r in rules if r.action == "number"]

    # Test n=15 mentally
    conditions_15 = {"div3": True, "div5": True, "always": True}
    output_15 = "(なし)"
    for rule in rules:
        if all(conditions_15.get(c.type, False) for c in rule.conditions):
            output_15 = {"fizz": "Fizz", "buzz": "Buzz", "fizzbuzz": "FizzBuzz", "number": "15"}.get(rule.action, "?")
            break

    # FizzBuzz case mistake: n=15 outputs Fizz or Buzz instead of FizzBuzz
    if output_15 in ("Fizz", "Buzz") and not fizzbuzz_rules:
        return (
            "N = 15 のとき、何が出力されますか？シミュレーションで確かめてみてください。\n"
            "3の倍数「かつ」5の倍数の場合、Fizz でも Buzz でもなく…という特別なケースがありませんでしたか？"
        )

    # FizzBuzz rule exists but order is wrong (div3→Fizz comes before div3 AND div5→FizzBuzz)
    if fizzbuzz_rules and fizz_rules:
        fizzbuzz_idx = min(rules.index(r) for r in fizzbuzz_rules)
        fizz_idx = min(rules.index(r) for r in fizz_rules)
        if fizz_idx < fizzbuzz_idx:
            return (
                "ルールは「上から順に」評価されます。\n"
                "N = 15 のとき、「3の倍数」ルールと「FizzBuzz」ルール、どちらが先に判定されますか？"
            )

    if not buzz_rules:
        return (
            "「Fizz」のルールはできていますね！\n"
            "では、5の倍数のときはどうなりますか？N = 5 でシミュレーションしてみましょう。"
        )

    if not fizzbuzz_rules:
        return (
            "3の倍数と5の倍数のルールは作れていますね。\n"
            "では N = 15 のとき、何が出力されますか？問題文に「3の倍数かつ5の倍数」のときの特別なルールがありませんでしたか？"
        )

    if not number_rules:
        return (
            "FizzBuzz・Fizz・Buzz のルールはできています！\n"
            "N = 1 のようにどの倍数でもない数のとき、何が出力されるべきでしょうか？"
        )

    if result.is_correct:
        return (
            f"N = {n} の結果が正しいですね！素晴らしい！\n"
            "他のテストケース（1, 3, 5, 15, 30 など）でも全て正しく動くか確かめてみましょう。"
        )

    return (
        "いい感じにルールが揃ってきました！\n"
        "N = 1, 3, 5, 15, 30 の5パターン全部で正しい出力になるか確認してみましょう。"
    )


# --- Endpoint ---

@app.post("/api/advice")
async def get_advice(req: AdviceRequest):
    api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(req)},
                ],
                max_tokens=300,
                temperature=0.7,
            )
            return {"message": response.choices[0].message.content}
        except Exception as e:
            return {"message": f"LLM API エラー: {e}"}

    return {"message": fallback_response(req)}


@app.get("/")
def root():
    return {"status": "ok", "message": "プログラミング学習支援システム API"}

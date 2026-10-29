"""Claude (Anthropic API) client for the shared LLM interface in llm_clients.py."""
import os
import time
from typing import Any, Dict, List

from llm_clients import GenerationOptions, LLMMessage, LLMResult

DEFAULT_MODEL = "claude-haiku-5-5"


def to_anthropic_messages(messages: List[LLMMessage]):
    """Split out the system prompt and shape the rest into alternating user/assistant turns.

    The Messages API expects the conversation to start with a user turn and to alternate roles,
    while this app's history can start with an AI greeting or contain consecutive turns.
    """
    system = "\n\n".join(message.content for message in messages if message.role == "system")
    turns: List[Dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            continue
        role = "assistant" if message.role == "assistant" else "user"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n\n" + message.content
        else:
            turns.append({"role": role, "content": message.content})
    if not turns or turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "（ここまでの会話の続きです）"})
    if turns[-1]["role"] != "user":
        raise ValueError("Claudeに送信する最後のメッセージが学習者側ではありません")
    return system, turns


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str, client=None):
        import anthropic

        self.model = model
        # 認証情報は環境変数（ANTHROPIC_API_KEY など）からSDKが読む。ここではキーを扱わない
        self.client = client or anthropic.Anthropic(timeout=float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "30")))

    def chat(self, messages: List[LLMMessage], options: GenerationOptions) -> LLMResult:
        system, turns = to_anthropic_messages(messages)
        started = time.perf_counter()
        # 短い会話文なので思考は切り、エフォートは low。Haiku 5.5 は既定以外の温度を受け付けないので temperature は送らない
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max(options.max_tokens or 0, 1024),
            system=system,
            messages=turns,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude が応答を断りました")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise RuntimeError("Claude の応答が空でした")
        return LLMResult(
            text=text,
            provider=self.provider,
            model=self.model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

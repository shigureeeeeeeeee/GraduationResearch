import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request


SUPPORTED_PROVIDERS = ("gemini", "ollama", "fallback")


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class GenerationOptions:
    temperature: float = 0.7
    max_tokens: Optional[int] = None


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    role: Optional[str] = None


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    elapsed_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    provider: str
    model: str

    def chat(
        self,
        messages: List[LLMMessage],
        options: GenerationOptions,
    ) -> LLMResult:
        ...


def _role_prefix(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    return role.strip().upper().replace("-", "_")


def _resolve_provider(requested: Optional[str]) -> str:
    provider = (requested or "auto").strip().lower()
    if provider in SUPPORTED_PROVIDERS:
        return provider
    if provider != "auto":
        supported = ", ".join(("auto", *SUPPORTED_PROVIDERS))
        raise ValueError(
            f"未対応のLLMプロバイダーです: {provider}（使用可能: {supported}）"
        )
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OLLAMA_MODEL"):
        return "ollama"
    return "fallback"


def resolve_llm_config(role: Optional[str] = None) -> LLMConfig:
    """Resolve a role override, falling back to the shared LLM configuration."""
    prefix = _role_prefix(role)
    role_provider = os.environ.get(f"{prefix}_LLM_PROVIDER") if prefix else None
    provider = _resolve_provider(role_provider or os.environ.get("LLM_PROVIDER", "auto"))

    role_model = os.environ.get(f"{prefix}_LLM_MODEL") if prefix else None
    if provider == "gemini":
        model = role_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    elif provider == "ollama":
        model = role_model or os.environ.get("OLLAMA_MODEL", "")
        if not model:
            label = f"{prefix}_LLM_MODEL または " if prefix else ""
            raise ValueError(f"{label}OLLAMA_MODEL が未設定です")
    else:
        model = "rule-based"

    return LLMConfig(provider=provider, model=model, role=role)


class FallbackClient:
    provider = "fallback"
    model = "rule-based"

    def chat(
        self,
        messages: List[LLMMessage],
        options: GenerationOptions,
    ) -> LLMResult:
        raise RuntimeError("ルールベースフォールバックが選択されています")


class OllamaClient:
    provider = "ollama"

    def __init__(self, model: str):
        self.model = model
        self.base_url = os.environ.get(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        ).rstrip("/")
        self.timeout_seconds = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))

    def chat(
        self,
        messages: List[LLMMessage],
        options: GenerationOptions,
    ) -> LLMResult:
        ollama_options: Dict[str, Any] = {"temperature": options.temperature}
        if options.max_tokens is not None:
            ollama_options["num_predict"] = options.max_tokens

        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "stream": False,
            "options": ollama_options,
        }
        request = urllib_request.Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib_request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib_error.URLError as error:
            raise RuntimeError(f"Ollama 接続エラー: {error}") from error

        content = data.get("message", {}).get("content")
        if not content:
            raise RuntimeError("Ollama 応答が空でした")
        return LLMResult(
            text=content,
            provider=self.provider,
            model=self.model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )


class GeminiClient:
    provider = "gemini"

    def __init__(self, model: str):
        self.model = model
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY が未設定です")

    def chat(
        self,
        messages: List[LLMMessage],
        options: GenerationOptions,
    ) -> LLMResult:
        from google import genai
        from google.genai import types

        system_instruction = "\n\n".join(
            message.content for message in messages if message.role == "system"
        )
        conversation = [message for message in messages if message.role != "system"]
        if not conversation:
            raise ValueError("Geminiに送信するユーザーメッセージがありません")

        current_message = conversation[-1].content
        history = [
            types.Content(
                role="model" if message.role == "assistant" else "user",
                parts=[types.Part(text=message.content)],
            )
            for message in conversation[:-1]
        ]
        config_values: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": options.temperature,
        }
        if options.max_tokens is not None:
            config_values["max_output_tokens"] = options.max_tokens

        started = time.perf_counter()
        chat = genai.Client(api_key=self.api_key).chats.create(
            model=self.model,
            config=types.GenerateContentConfig(**config_values),
            history=history,
        )
        response = chat.send_message(current_message)
        if not response.text:
            raise RuntimeError("Gemini 応答が空でした")

        usage = getattr(response, "usage_metadata", None)
        return LLMResult(
            text=response.text,
            provider=self.provider,
            model=self.model,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            completion_tokens=getattr(usage, "candidates_token_count", None),
        )


def create_llm_client(
    role: Optional[str] = None,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMClient:
    if provider:
        selected_provider = _resolve_provider(provider)
        config = None
    else:
        config = resolve_llm_config(role)
        selected_provider = config.provider
    selected_model = model
    if not selected_model:
        if config and selected_provider == config.provider:
            selected_model = config.model
        elif selected_provider == "gemini":
            selected_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        elif selected_provider == "ollama":
            selected_model = os.environ.get("OLLAMA_MODEL", "")
        else:
            selected_model = "rule-based"

    if selected_provider == "gemini":
        return GeminiClient(selected_model)
    if selected_provider == "ollama":
        if not selected_model:
            raise ValueError("OLLAMA_MODEL が未設定です")
        return OllamaClient(selected_model)
    return FallbackClient()

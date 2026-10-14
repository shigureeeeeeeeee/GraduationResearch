import os
import re
from typing import Any, Dict, List, Optional

from domain import draft_signature, rule_signature
from llm_clients import (
    GenerationOptions,
    LLMMessage,
    OllamaClient,
    create_llm_client,
    resolve_llm_config,
)
from prompts import build_message_payload, build_system_instruction
from schemas import AdviceRequest


def get_llm_provider() -> str:
    return resolve_llm_config().provider


def request_ollama_chat(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.7,
    num_predict: Optional[int] = None,
) -> str:
    model_name = os.environ.get("OLLAMA_MODEL", "")
    if not model_name:
        raise ValueError("OLLAMA_MODEL が未設定です")
    result = OllamaClient(model_name).chat(
        [
            LLMMessage(role=message["role"], content=message["content"])
            for message in messages
        ],
        GenerationOptions(temperature=temperature, max_tokens=num_predict),
    )
    return result.text


def generate_with_gemini(req: AdviceRequest, user_text: str) -> str:
    return _generate_with_client(req, user_text, provider="gemini")


def generate_with_ollama(req: AdviceRequest, user_text: str) -> str:
    return _generate_with_client(req, user_text, provider="ollama")


def _advice_messages(req: AdviceRequest, user_text: str) -> List[LLMMessage]:
    messages = [
        LLMMessage(
            role="system",
            content=build_system_instruction(req.phase or 2, req),
        )
    ]
    messages.extend(
        LLMMessage(
            role="assistant" if message.role == "ai" else "user",
            content=message.text,
        )
        for message in (req.history or [])[-10:]
    )
    messages.append(
        LLMMessage(
            role="user",
            content=build_message_payload(user_text, req),
        )
    )
    return messages


def _generate_with_client(
    req: AdviceRequest,
    user_text: str,
    *,
    provider: Optional[str] = None,
) -> str:
    client = create_llm_client(provider=provider)
    return client.chat(
        _advice_messages(req, user_text),
        GenerationOptions(temperature=0.7, max_tokens=2048),
    ).text


def parse_program_draft(message: str) -> Dict[str, Any]:
    headers = ("AIがこの問題で考えたプログラム", "AIの仮説プログラム")
    matches = [(message.find(header), header) for header in headers if header in message]
    body = message.strip()
    draft_block = message
    if matches:
        index, header = min(matches, key=lambda item: item[0])
        body = message[:index].strip() or (
            "AIがこの問題で考えたプログラムを更新しました。下の提案を確認してください。"
        )
        draft_block = message[index + len(header):]

    condition_map = {
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
    max_rules_text = os.environ.get("AI_PROGRAM_DRAFT_MAX_RULES", "1").strip()
    max_rules = int(max_rules_text) if max_rules_text.isdigit() and int(max_rules_text) > 0 else 1

    rules = []
    seen = set()
    for line in draft_block.splitlines():
        match = re.search(r"ルール\d+\s*:\s*\[(.*?)\]\s*→\s*\[(.*?)\]", line.strip())
        if not match:
            continue

        action = action_map.get(match.group(2).strip())
        if not action:
            continue

        condition_types = []
        parts = re.split(r"\s*(?:AND|and|＆|&|かつ)\s*", match.group(1).strip())
        for part in parts:
            condition_type = condition_map.get(part.strip())
            if condition_type and condition_type not in condition_types:
                condition_types.append(condition_type)
        if not condition_types:
            continue

        signature = (tuple(sorted(condition_types)), action)
        if signature in seen:
            continue
        seen.add(signature)
        rules.append(
            {
                "conditions": [{"type": condition_type} for condition_type in condition_types],
                "action": action,
            }
        )
        if len(rules) >= max_rules:
            break

    return {"message": body, "program_draft": rules}


def remove_repeated_drafts(req: AdviceRequest, parsed: Dict[str, Any]) -> Dict[str, Any]:
    current = {rule_signature(rule) for rule in req.rules}
    candidates = [
        rule
        for rule in parsed.get("program_draft", [])
        if draft_signature(rule) not in current
    ]
    if candidates:
        return {"message": parsed.get("message", ""), "program_draft": candidates[:1]}

    canonical_candidates = (
        {"conditions": [{"type": "person_sensor"}], "action": "door"},
        {
            "conditions": [{"type": "person_sensor"}, {"type": "dark_sensor"}],
            "action": "bell",
        },
    )
    for candidate in canonical_candidates:
        if draft_signature(candidate) not in current:
            return {"message": parsed.get("message", ""), "program_draft": [candidate]}
    return {"message": parsed.get("message", ""), "program_draft": []}


def generate_advice(req: AdviceRequest) -> Dict[str, Any]:
    from domain import fallback_response

    user_text = req.current_message or "今のプログラムについてコメントしてください。"
    config = resolve_llm_config()
    if config.provider == "fallback":
        return {"message": fallback_response(req), "program_draft": []}

    try:
        client = create_llm_client()
        result = client.chat(
            _advice_messages(req, user_text),
            GenerationOptions(temperature=0.7, max_tokens=2048),
        )
        response = remove_repeated_drafts(req, parse_program_draft(result.text))
        response["llm"] = {
            "provider": result.provider,
            "model": result.model,
            "elapsed_ms": result.elapsed_ms,
        }
        return response
    except Exception as error:
        label = "Gemini" if config.provider == "gemini" else "Ollama"
        return {"message": f"{label} API エラー: {error}", "program_draft": []}

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from domain import draft_signature, rule_signature
from prompts import build_message_payload, build_system_instruction
from schemas import AdviceRequest


def get_llm_provider() -> str:
    provider = os.environ.get("LLM_PROVIDER", "auto").strip().lower()
    if provider in ("gemini", "ollama", "fallback"):
        return provider
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OLLAMA_MODEL"):
        return "ollama"
    return "fallback"


def request_ollama_chat(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.7,
    num_predict: Optional[int] = None,
) -> str:
    model_name = os.environ.get("OLLAMA_MODEL")
    if not model_name:
        raise ValueError("OLLAMA_MODEL が未設定です")

    options: Dict[str, Any] = {"temperature": temperature}
    if num_predict is not None:
        options["num_predict"] = num_predict

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    timeout_seconds = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    request = urllib_request.Request(
        url=f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib_error.URLError as error:
        raise RuntimeError(f"Ollama 接続エラー: {error}") from error

    content = data.get("message", {}).get("content")
    if not content:
        raise RuntimeError("Ollama 応答が空でした")
    return content


def generate_with_gemini(req: AdviceRequest, user_text: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が未設定です")

    from google import genai
    from google.genai import types

    history = [
        types.Content(
            role="user" if message.role == "user" else "model",
            parts=[types.Part(text=message.text)],
        )
        for message in (req.history or [])[-10:]
    ]
    chat = genai.Client(api_key=api_key).chats.create(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        config=types.GenerateContentConfig(
            system_instruction=build_system_instruction(req.phase or 2, req),
            max_output_tokens=2048,
            temperature=0.7,
        ),
        history=history,
    )
    return chat.send_message(build_message_payload(user_text, req)).text


def generate_with_ollama(req: AdviceRequest, user_text: str) -> str:
    messages = [
        {"role": "system", "content": build_system_instruction(req.phase or 2, req)}
    ]
    messages.extend(
        {
            "role": "assistant" if message.role == "ai" else "user",
            "content": message.text,
        }
        for message in (req.history or [])[-10:]
    )
    messages.append(
        {"role": "user", "content": build_message_payload(user_text, req)}
    )
    return request_ollama_chat(messages)


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
    provider = get_llm_provider()
    if provider == "fallback":
        return {"message": fallback_response(req), "program_draft": []}

    try:
        generated = (
            generate_with_gemini(req, user_text)
            if provider == "gemini"
            else generate_with_ollama(req, user_text)
        )
        return remove_repeated_drafts(req, parse_program_draft(generated))
    except Exception as error:
        label = "Gemini" if provider == "gemini" else "Ollama"
        return {"message": f"{label} API エラー: {error}", "program_draft": []}

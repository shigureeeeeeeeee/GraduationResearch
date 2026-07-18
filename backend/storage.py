import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from schemas import LogEntry


DATA_DIR = Path(__file__).parent / "data"
PROMPT_FILE = DATA_DIR / "prompts.json"
LOG_FILE = DATA_DIR / "sessions.jsonl"


def load_prompt_overrides() -> Dict[str, str]:
    if not PROMPT_FILE.exists():
        return {}
    try:
        with PROMPT_FILE.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}


def save_prompt_overrides(prompts: Dict[str, str]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with PROMPT_FILE.open("w", encoding="utf-8") as file:
        json.dump(prompts, file, ensure_ascii=False, indent=2)


def reset_prompt_overrides() -> None:
    if PROMPT_FILE.exists():
        PROMPT_FILE.unlink()


def append_log(entry: LogEntry) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": entry.session_id,
        "event": entry.event,
        "phase": entry.phase,
        "rules": [
            {
                "conditions": [condition.type for condition in rule.conditions],
                "action": rule.action,
            }
            for rule in entry.rules
        ],
        "chat_history": [
            {"role": message.role, "text": message.text, "speaker": message.speaker}
            for message in entry.chat_history
        ],
        "all_correct": entry.all_correct,
    }
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_logs() -> List[Dict[str, Any]]:
    if not LOG_FILE.exists():
        return []

    entries = []
    with LOG_FILE.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                entries.append(json.loads(line))
    return entries

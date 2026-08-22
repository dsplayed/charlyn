"""Persistent memory — AI chooses what to remember, stored in JSON for easy review/removal."""
import json
import os
import time
from typing import Optional

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(MEMORY_DIR, exist_ok=True)

CLI_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memories.json")


def _get_path(user_id: Optional[int] = None) -> str:
    if user_id is not None:
        return os.path.join(MEMORY_DIR, f"memories_{user_id}.json")
    return CLI_MEMORY_PATH


def load(user_id: Optional[int] = None) -> list[dict]:
    path = _get_path(user_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save(memories: list[dict], user_id: Optional[int] = None):
    path = _get_path(user_id)
    with open(path, "w") as f:
        json.dump(memories, f, indent=2)


def store(content: str, category: str = "general", user_id: Optional[int] = None) -> str:
    memories = load(user_id)
    entry = {
        "id": int(time.time() * 1000),
        "content": content,
        "category": category,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    memories.append(entry)
    save(memories, user_id)
    return f"Remembered: {content[:120]}"


def recall(user_id: Optional[int] = None, limit: int = 15) -> list[dict]:
    return load(user_id)[-limit:]


def delete(memory_id: int, user_id: Optional[int] = None) -> bool:
    memories = load(user_id)
    filtered = [m for m in memories if m["id"] != memory_id]
    if len(filtered) == len(memories):
        return False
    save(filtered, user_id)
    return True


def format_context(user_id: Optional[int] = None) -> str:
    memories = load(user_id)
    if not memories:
        return ""
    lines = ["## Saved Memories (facts you chose to remember)"]
    for m in memories[-10:]:
        lines.append(f"- [{m['category']}] {m['content']}")
    return "\n".join(lines)

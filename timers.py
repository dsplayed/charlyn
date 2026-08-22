"""Persistent timer/reminder system with async background firing."""
import json
import os
import re
import threading
import time
from typing import Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TIMERS_FILE = os.path.join(DATA_DIR, "timers.json")


def _parse_duration(duration_str: str) -> int:
    """Parse a human-readable duration like '30 minutes' or '1 hour 30 min' into seconds."""
    if not duration_str:
        return 60
    total = 0
    patterns = [
        (r'(\d+)\s*(?:seconds|second|sec|s)(?:\s|$)', 1),
        (r'(\d+)\s*(?:minutes|minute|min|m)(?:\s|$)', 60),
        (r'(\d+)\s*(?:hours|hour|hr|h)(?:\s|$)', 3600),
        (r'(\d+)\s*(?:days|day|d)(?:\s|$)', 86400),
    ]
    text = duration_str.lower().strip()
    for pattern, multiplier in patterns:
        for m in re.finditer(pattern, text):
            total += int(m.group(1)) * multiplier
    return total if total > 0 else 60


class TimerManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._timers: dict[str, dict[str, Any]] = {}
        self._bot = None
        self._counter = 0
        self._load()

    # ── Public API (thread-safe) ──────────────────────────────────

    def set_timer(self, user_id: int, duration: str, message: str) -> tuple[str, int]:
        """Register a new timer. Returns (timer_id, duration_seconds)."""
        seconds = _parse_duration(duration)
        if seconds < 1:
            seconds = 60
        fire_at = time.time() + seconds
        with self._lock:
            self._counter += 1
            timer_id = f"timer_{int(time.time())}_{self._counter}"
            self._timers[timer_id] = {
                "id": timer_id,
                "user_id": user_id,
                "message": message,
                "duration_seconds": seconds,
                "fire_at": fire_at,
                "created_at": time.time(),
                "fired": False,
            }
            self._save()
        return timer_id, seconds

    def cancel_timer(self, timer_id: str) -> bool:
        with self._lock:
            if timer_id in self._timers:
                del self._timers[timer_id]
                self._save()
                return True
            return False

    def list_timers(self, user_id: int) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            active = []
            for t in self._timers.values():
                if t["user_id"] == user_id and not t["fired"] and t["fire_at"] > now:
                    remaining = int(t["fire_at"] - now)
                    active.append({**t, "remaining_seconds": remaining})
            return sorted(active, key=lambda x: x["fire_at"])

    def get_due_timers(self) -> list[dict[str, Any]]:
        """Return timers that are ready to fire and mark them as fired."""
        now = time.time()
        due = []
        with self._lock:
            for t in list(self._timers.values()):
                if not t["fired"] and t["fire_at"] <= now:
                    t["fired"] = True
                    due.append(t)
            if due:
                self._save()
        return due

    def all_active_timers(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            return [
                {**t, "remaining_seconds": int(t["fire_at"] - now)}
                for t in self._timers.values()
                if not t["fired"] and t["fire_at"] > now
            ]

    def set_bot(self, bot) -> None:
        self._bot = bot

    def get_bot(self):
        return self._bot

    # ── Persistence ───────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(TIMERS_FILE):
            return
        try:
            with open(TIMERS_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._timers = data.get("timers", {})
                self._counter = data.get("counter", 0)
        except (json.JSONDecodeError, OSError):
            self._timers = {}
            self._counter = 0

    def _save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TIMERS_FILE, "w") as f:
            json.dump({
                "timers": self._timers,
                "counter": self._counter,
            }, f, indent=2)


timer_manager = TimerManager()

"""Per-user Docker sandbox for secure command execution.

Each user gets a persistent Docker container with:
  - 3 GB workspace (host-mounted directory, shared host↔container)
  - Default Docker bridge network
  - Read-only root filesystem
  - Resource limits (CPU, memory)
  - Path-scoped file operations
"""

import os
import re
import shutil
import subprocess
import textwrap
from typing import Optional

from config import (
    SANDBOX_BASE, SANDBOX_IMAGE, SANDBOX_MAX_USERS,
    SANDBOX_MEMORY, SANDBOX_CPU, SANDBOX_TIMEOUT, SANDBOX_STORAGE_LIMIT,
)


# Commands blocked inside the sandbox (prevents escape / host tampering)
BLOCKED_PATTERNS = [
    r"^\s*docker\s",
    r"^\s*podman\s",
    r"^\s*crictl\s",
    r"^\s*nsenter\s",
    r"^\s*unshare\s",
    r"^\s*mount\s+--bind\s",
    r"^\s*chroot\s",
    r"^\s*switch_root\s",
    r"^\s*modprobe\s",
    r"^\s*insmod\s",
    r"^\s*rmmod\s",
    r"^\s*shutdown\s",
    r"^\s*reboot\s",
    r"^\s*halt\s",
    r"^\s*poweroff\s",
]


class SandboxError(Exception):
    """Raised when a sandbox operation is rejected or fails."""


class UserSandbox:
    """Persistent Docker sandbox for a single user."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.work_dir = os.path.join(SANDBOX_BASE, f"user_{user_id}", "workspace")
        self.container_name = f"charlyn_user_{user_id}"
        os.makedirs(self.work_dir, exist_ok=True)

    # ── Container lifecycle ──────────────────────────────────

    def ensure_running(self):
        """Ensure the user's container exists and is running."""
        container_id = self._container_id()
        if container_id:
            status = self._container_status(container_id)
            if status == "running":
                return
            if status == "exited":
                self._run(["docker", "start", self.container_name], check=True)
                return
        self._create_container()

    def _create_container(self):
        """Create and start a new sandbox container."""
        self._run([
            "docker", "create",
            "--name", self.container_name,
            "--network", "bridge",
            "--memory", SANDBOX_MEMORY,
            "--cpus", str(SANDBOX_CPU),
            "--privileged",
            "-v", f"{self.work_dir}:/workspace:rw",
            "-w", "/workspace",
            SANDBOX_IMAGE,
            "sleep", "infinity",
        ], check=True)
        self._run(["docker", "start", self.container_name], check=True)

    def stop(self):
        """Stop and remove the container (preserves workspace)."""
        cid = self._container_id()
        if cid:
            self._run(["docker", "stop", "--time", "3", self.container_name],
                      check=False)
            self._run(["docker", "rm", self.container_name], check=False)

    def cleanup(self):
        """Remove the container AND workspace directory."""
        self.stop()
        shutil.rmtree(self.work_dir, ignore_errors=True)

    # ── Command execution ────────────────────────────────────

    def exec_run(self, command: str, timeout: int = SANDBOX_TIMEOUT
                 ) -> tuple[int, str, str]:
        """Execute a shell command inside the container.
        Returns (exit_code, stdout, stderr)."""
        self._validate_command(command)
        self.ensure_running()

        cmd = [
            "docker", "exec",
            "-w", "/workspace",
            self.container_name,
            "sh", "-c", command,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            stdout = result.stdout[:4000] if result.stdout else ""
            stderr = result.stderr[:2000] if result.stderr else ""
            return result.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"[TIMEOUT] Command exceeded {timeout}s limit"

    def exec_python(self, code: str, timeout: int = 30
                    ) -> tuple[int, str, str]:
        """Execute Python code inside the container."""
        dedented = textwrap.dedent(code)
        escaped = dedented.replace("'", "'\"'\"'")
        return self.exec_run(f"python3 -c '{escaped}'", timeout=timeout)

    # ── File operations (host-side, scoped to workspace) ─────

    def abspath(self, path: str) -> str:
        """Resolve a path relative to the user's workspace directory."""
        combined = os.path.join(self.work_dir, path)
        abs_path = os.path.abspath(combined)
        self._validate_path(abs_path)
        return abs_path

    def read_file(self, path: str, limit: int = 2000) -> str:
        abs_path = self.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: File not found: {path}"
        if not os.path.isfile(abs_path):
            return f"Error: Not a file: {path}"
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    lines.append(line)
                content = "".join(lines)
            if len(content) > 100_000:
                content = content[:100_000] + "\n...[truncated]"
            return f"--- Contents of {path} ---\n{content}\n--- End of file ---"
        except Exception as e:
            return f"Error reading file: {e}"

    def write_file(self, path: str, content: str, append: bool = False) -> str:
        abs_path = self.abspath(path)
        self._check_storage_limit()
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            mode = "a" if append else "w"
            with open(abs_path, mode, encoding="utf-8") as f:
                f.write(content)
            action = "Appended to" if append else "Wrote"
            return f"{action} {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def delete_file(self, path: str) -> str:
        abs_path = self.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: File not found: {path}"
        if not os.path.isfile(abs_path):
            return f"Error: Not a file: {path}"
        try:
            os.remove(abs_path)
            return f"Deleted file: {path}"
        except Exception as e:
            return f"Error deleting file: {e}"

    def file_exists(self, path: str) -> str:
        abs_path = self.abspath(path)
        if not os.path.exists(abs_path):
            return f"false — {path} does not exist"
        if os.path.isfile(abs_path):
            return f"true — file ({os.path.getsize(abs_path)} bytes)"
        if os.path.isdir(abs_path):
            return f"true — directory"
        return "true — other"

    def delete_dir(self, path: str) -> str:
        abs_path = self.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: Directory not found: {path}"
        if not os.path.isdir(abs_path):
            return f"Error: Not a directory: {path}"
        try:
            shutil.rmtree(abs_path)
            return f"Deleted directory and contents: {path}"
        except Exception as e:
            return f"Error deleting directory: {e}"

    def list_dir(self, path: str = ".") -> str:
        abs_path = self.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: Path not found: {path}"
        if not os.path.isdir(abs_path):
            return f"Error: Not a directory: {path}"
        try:
            entries = []
            for entry in os.listdir(abs_path):
                full = os.path.join(abs_path, entry)
                if os.path.isdir(full):
                    entries.append(f"[DIR]  {entry}")
                else:
                    entries.append(f"[FILE] {entry} ({os.path.getsize(full)} bytes)")
            if not entries:
                return f"Directory {path} is empty."
            return f"Contents of {path}:\n" + "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {e}"

    def create_dir(self, path: str) -> str:
        abs_path = self.abspath(path)
        try:
            os.makedirs(abs_path, exist_ok=True)
            return f"Created directory: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"

    # ── Guard rails ──────────────────────────────────────────

    def _validate_command(self, command: str):
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command.strip().lower()):
                raise SandboxError(
                    f"Command blocked by security policy (matches: {pattern})"
                )

    def _validate_path(self, abs_path: str):
        work_dir_real = os.path.realpath(self.work_dir)
        path_real = os.path.realpath(abs_path)
        if not path_real.startswith(work_dir_real + os.sep) and path_real != work_dir_real:
            raise SandboxError(
                f"Access denied: path outside workspace: {abs_path}"
            )

    def _check_storage_limit(self):
        usage = self.get_storage_usage()
        if usage > SANDBOX_STORAGE_LIMIT:
            mb = usage / (1024 * 1024)
            limit_mb = SANDBOX_STORAGE_LIMIT / (1024 * 1024)
            raise SandboxError(
                f"Storage quota exceeded ({mb:.0f} MB / {limit_mb:.0f} MB). "
                f"Free up space or ask the admin to increase your limit."
            )

    # ── Status ───────────────────────────────────────────────

    def get_storage_usage(self) -> int:
        total = 0
        for dirpath, dirnames, filenames in os.walk(self.work_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total

    def get_status(self) -> dict:
        cid = self._container_id()
        usage = self.get_storage_usage()
        return {
            "user_id": self.user_id,
            "container": self.container_name,
            "running": self._container_status(cid) == "running" if cid else False,
            "workspace": self.work_dir,
            "storage_used_bytes": usage,
            "storage_limit_bytes": SANDBOX_STORAGE_LIMIT,
            "storage_used_mb": round(usage / (1024 * 1024), 1),
            "storage_limit_mb": round(SANDBOX_STORAGE_LIMIT / (1024 * 1024), 1),
        }

    # ── Helpers ──────────────────────────────────────────────

    def _container_id(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={self.container_name}",
                 "--format", "{{.ID}}"],
                capture_output=True, text=True, timeout=5,
            )
            cid = result.stdout.strip()
            return cid if cid else None
        except Exception:
            return None

    def _container_status(self, container_id: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return None

    @staticmethod
    def _run(cmd: list, check: bool = True, timeout: int = 30):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if check and result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
                raise SandboxError(f"Docker command failed: {' '.join(cmd)}: {msg}")
            return result
        except FileNotFoundError:
            raise SandboxError("Docker is not installed. Please install Docker Desktop.")
        except subprocess.TimeoutExpired:
            raise SandboxError(f"Docker command timed out: {' '.join(cmd)}")


# ── Global manager ──────────────────────────────────────────

_sandboxes: dict[int, UserSandbox] = {}
_current_sandbox: Optional[UserSandbox] = None


def for_user(user_id: int) -> UserSandbox:
    """Get or create a sandbox for the given user."""
    if user_id not in _sandboxes:
        if len(_sandboxes) >= SANDBOX_MAX_USERS:
            raise SandboxError(
                f"Maximum {SANDBOX_MAX_USERS} concurrent users reached. "
                "Ask an admin to free up resources."
            )
        _sandboxes[user_id] = UserSandbox(user_id)
    return _sandboxes[user_id]


def set_current(sandbox: Optional[UserSandbox]):
    global _current_sandbox
    _current_sandbox = sandbox


def get_current() -> Optional[UserSandbox]:
    return _current_sandbox


def remove_user(user_id: int):
    if user_id in _sandboxes:
        _sandboxes[user_id].cleanup()
        del _sandboxes[user_id]


def cleanup_all():
    for s in _sandboxes.values():
        s.stop()
    _sandboxes.clear()


def list_active() -> list[dict]:
    return [s.get_status() for s in _sandboxes.values()]


def is_docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False

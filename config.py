"""Configuration — reads from .env or environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Backend ───────────────────────────────────
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
assert LLM_BACKEND in ("ollama", "opencode", "copilot"), "LLM_BACKEND must be 'ollama', 'opencode', or 'copilot'"

# ── Ollama ────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

# ── OpenCode.ai / OpenAI-compatible ───────────
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "nemotron-3-super-free")

# ── GitHub Copilot ────────────────────────────
COPILOT_TOKEN = os.getenv("COPILOT_TOKEN", "")
COPILOT_MODEL = os.getenv("COPILOT_MODEL", "gpt-4o")
COPILOT_BASE_URL = os.getenv("COPILOT_BASE_URL", "https://api.githubcopilot.com")

# ── Shared ────────────────────────────────────
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "75"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.6"))
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "16384"))
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))

YOLO = os.getenv("YOLO", "false").lower() in ("true", "1", "yes")

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SEARCH_REGION = os.getenv("SEARCH_REGION", "th")


SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Cache TTL in seconds (default 5 min)
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
# Max parallel workers for tool execution
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "5"))
# Enable planning step before execution
PLANNER_ENABLED = os.getenv("PLANNER_ENABLED", "true").lower() in ("true", "1", "yes")
# Enable streaming output
STREAMING_ENABLED = os.getenv("STREAMING_ENABLED", "true").lower() in ("true", "1", "yes")
# Max memories to inject into context
MEMORY_INJECT_LIMIT = int(os.getenv("MEMORY_INJECT_LIMIT", "10"))

# ── Conversation ─────────────────────────
MAX_HISTORY_BEFORE_SUMMARIZE = int(os.getenv("MAX_HISTORY_BEFORE_SUMMARIZE", "200"))

# ── Sandbox (per-user Docker isolation) ─────────
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "true").lower() in ("true", "1", "yes")
SANDBOX_BASE = os.getenv("SANDBOX_BASE", "/tmp/charlyn")
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "charlyn-sandbox:latest")
SANDBOX_MAX_USERS = int(os.getenv("SANDBOX_MAX_USERS", "10"))
SANDBOX_MEMORY = os.getenv("SANDBOX_MEMORY", "2g")
SANDBOX_CPU = float(os.getenv("SANDBOX_CPU", "2.0"))
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "60"))
SANDBOX_STORAGE_LIMIT = int(os.getenv("SANDBOX_STORAGE_LIMIT", "3221225472"))  # 3 GB

# ── VM (QEMU + SSH) ─────────────────────────
VM_SSH_HOST = os.getenv("VM_SSH_HOST", "127.0.0.1")
VM_SSH_PORT = int(os.getenv("VM_SSH_PORT", "2222"))
VM_SSH_USER = os.getenv("VM_SSH_USER", "lumen")
VM_SSH_KEY = os.getenv("VM_SSH_KEY", "/tmp/vm_ssh_key")

#!/usr/bin/env python3
"""Setup wizard — configures everything Charlyn needs via .env."""
import os
import subprocess
import sys

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

REQUIREMENTS = [
    "discord.py",
    "ollama",
    "python-dotenv",
    "requests",
    "certifi",
    "Pillow",
    "pytesseract",
    "playwright",
    "rich",
    "python-whois",
    "dnspython",
    "openai",
    "litellm",
    "jinja2",
    "markdown",
]

FIELDS = [
    ("DISCORD_TOKEN", "Discord Bot Token", "", True),
    ("OWNER_ID", "Your Discord User ID (owner)", "", True),
    ("LLM_BACKEND", "Backend (ollama / opencode)", "ollama", False),
    ("OLLAMA_HOST", "Ollama server URL", "http://localhost:11434", False),
    ("OLLAMA_MODEL", "Ollama model name", "gpt-oss:20b", False),
    ("OPENCODE_API_KEY", "OpenCode.ai API key (if backend=opencode)", "", False),
    ("OPENCODE_BASE_URL", "OpenCode.ai base URL", "https://opencode.ai/zen/v1", False),
    ("OPENCODE_MODEL", "OpenCode.ai model name", "nemotron-3-super-free", False),
    ("COPILOT_TOKEN", "GitHub Copilot token (get via --copilot-login)", "", False),
    ("COPILOT_MODEL", "Copilot model name", "gpt-4o", False),
    ("SERPER_API_KEY", "Serper.dev API key (web search)", "", False),
    ("SEARCH_REGION", "Google search region code", "th", False),
    ("STUDENT_API_KEY", "Student Data API key", "e1bc124cc6bcf617d160e71dee7897b2b7c587f3d0a73a3ca131d941678e0906", False),
    ("TEMPERATURE", "Model temperature", "0.6", False),
    ("NUM_PREDICT", "Max tokens per response", "16384", False),
    ("NUM_CTX", "Context window size", "8192", False),
    ("VIDEO_WORKER_URL", "Video streaming worker URL", "https://video.dspl.me", False),
    ("VIDEO_API_KEY", "Video streaming worker API key", "", True),
]


def prompt(label: str, default: str = "", secret: bool = False) -> str:
    if default:
        label = f"{label} [{default}]"
    while True:
        val = input(f"  {label}: ")
        if not val:
            val = default
        if val or not secret:
            return val
        print("    (required)")


def install_deps():
    print("\nInstalling dependencies...")
    for pkg in REQUIREMENTS:
        print(f"  {pkg}... ", end="", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("ok")
        else:
            print(f"failed: {result.stderr.strip() or result.stdout.strip()}")

    print("  playwright browsers... ", end="", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("ok")
    else:
        print(f"failed: {result.stderr.strip() or result.stdout.strip()}")


def write_env(values: dict):
    lines = []
    for key, val in values.items():
        lines.append(f'{key}="{val}"')
    content = "\n".join(lines) + "\n"
    with open(ENV_PATH, "w") as f:
        f.write(content)
    print(f"\nWrote {ENV_PATH}")


def main():
    print("=" * 50)
    print("  Charlyn — Setup Wizard")
    print("=" * 50)

    ans = input("\nInstall Python dependencies first? [Y/n]: ").strip().lower()
    if ans != "n":
        install_deps()

    print("\nConfigure settings (leave blank for default):")
    values = {}
    for key, label, default, required in FIELDS:
        val = prompt(label, default, secret=(key == "DISCORD_TOKEN"))
        if not val and required:
            print(f"  [ERROR] {label} is required. Aborting.")
            sys.exit(1)
        values[key] = val

    write_env(values)

    print("\nDone. You can now run:")
    print("  python agent.py          (CLI mode)")
    print("  python dsc.py            (Discord bot)")
    print()


if __name__ == "__main__":
    main()

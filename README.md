# charlyn

an ai agent for the terminal and discord. runs locally, no cloud dependency.

## what it is

an agent that does things instead of just talking. browse the web, read screenshots, edit files, run code, remember what you told it, keep a conversation going.

## how it works

- one llm client, three backends: ollama, openai-compatible apis, and github copilot. tool calls from each get normalized into the same shape, so the agent logic doesn't care which model is driving it.
- tools: playwright browser control, ocr, web search and deep scrape, username lookup, dns and whois, wayback, anime and manga lookup, terminal, python exec, file operations.
- memory is json files. the ai decides what's worth remembering, and per-user files keep people's stuff separate.
- code runs in a per-user docker sandbox. read-only root filesystem, cpu and memory limits, and a blocklist for escape commands like docker, nsenter, and chroot.
- the discord wrapper (`dsc.py`) is the same brain with embeds, per-user agents, and a whitelist.
- there's a lua script for roblox in here too. because why not.

## stack

python, ollama / openai / copilot, playwright, docker, discord.py

## run it

```sh
pip install -r requirements.txt
cp .env.example .env
python3 agent.py
```

for the discord bot:

```sh
python3 dsc.py
```

the sandbox needs docker with the `charlyn-sandbox` image built:

```sh
./build_sandbox.sh
```

## secrets

copy `.env.example` and fill in your own keys. nothing real is committed.
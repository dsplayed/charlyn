#!/usr/bin/env python3
"""Charlyn Discord App — Agent interface for Discord."""
import asyncio
import json
import os
import re
import ssl
import sys
import time
from typing import Optional

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)

from agent import CharlynAgent
from llm import LLMClient
from sandbox import remove_user as sandbox_remove_user, list_active as sandbox_list_active, is_docker_available as sandbox_available
from timers import timer_manager


OWNER_ID = int(os.getenv("OWNER_ID", "1509242484629311568"))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
STATE_FILE = os.path.join(DATA_DIR, "discord_state.json")


COLOR_PRIMARY = 0x2B2D31
COLOR_SUCCESS = 0x2B8A3E
COLOR_WARNING = 0xC99A2B
COLOR_ERROR = 0xCC3333
COLOR_INFO = 0x3366CC


def _strip_markdown_tables(text: str) -> str:
    lines = text.split("\n")
    out = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\|[-:| ]+\|$", stripped):
            in_table = True
            continue
        if in_table and stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            out.append(": ".join(cells))
            continue
        in_table = False
        out.append(line)
    return "\n".join(out)


def _make_embed(color: int = COLOR_PRIMARY, title: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(color=color)
    if title:
        embed.title = title
    return embed


def _entry_to_text(entry: dict) -> Optional[str]:
    etype = entry.get("type")
    if etype == "thinking":
        content = entry.get("content", "")[:4000]
        if not content:
            return None
        return f"**Thinking...**\n\n{content}"
    if etype == "tool_call":
        name = entry.get("name", "unknown")
        args = entry.get("args", {})
        args_str = json.dumps(args, indent=2)[:1000]
        return f"**Running: {name}**\n```json\n{args_str}\n```"
    if etype == "tool_result":
        name = entry.get("name", "unknown")
        result = entry.get("result", "")[:1000]
        return f"**Done: {name}**\n```\n{result}\n```"
    return None


def embed_from_entry(entry: dict) -> Optional[discord.Embed]:
    etype = entry.get("type")
    if etype == "thinking":
        content = entry.get("content", "")[:4000]
        if not content:
            return None
        embed = _make_embed(COLOR_WARNING)
        embed.set_author(name="Thinking...")
        embed.description = content
        return embed
    if etype == "tool_call":
        name = entry.get("name", "unknown")
        args = entry.get("args", {})
        args_str = json.dumps(args, indent=2)[:1000]
        embed = _make_embed(COLOR_PRIMARY)
        embed.set_author(name=f"Running: {name}")
        embed.add_field(
            name="Parameters",
            value=f"```json\n{args_str}\n```",
            inline=False,
        )
        return embed
    if etype == "tool_result":
        name = entry.get("name", "unknown")
        result = entry.get("result", "")[:1000]
        embed = _make_embed(COLOR_SUCCESS)
        embed.set_author(name=f"Done: {name}")
        embed.description = f"```\n{result}\n```"
        return embed
    return None


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"whitelist": [], "model": None}


def save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class ForceStopError(Exception):
    pass


class DiscordCharlynAgent(CharlynAgent):
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None, user_id: Optional[int] = None):
        self.model_override = model
        self.host_override = host
        self.reasoning_log: list[dict] = []
        self.stop_requested: bool = False

        CharlynAgent.__init__(self, user_id=user_id)
        self.llm = LLMClient(model_override=model, host_override=host)

        discord_fmt = (
            "You are answering inside a Discord embed. "
            "Discord embeds do NOT support markdown tables -- no pipe characters or table formatting. "
            "Use bullet points, numbered lists, or plain paragraphs to present structured data. "
            "Keep formatting simple and clean."
            "When you need to ask the user a question, ALWAYS use the 'ask_user' tool — it shows buttons they can click or a text box they can type in. Do NOT ask questions in plain text."
            "Screenshots you take with browser_screenshot are automatically attached to your response. You can reference them by filename."
        )
        self.messages.append({"role": "system", "content": discord_fmt})

    def _get_current_model(self) -> str:
        return self.llm.model

    def _chat(self):
        if self.stop_requested:
            raise ForceStopError("Task force-stopped by user.")

        from config import TEMPERATURE, NUM_PREDICT

        response = self.llm.chat(
            messages=self.messages,
            tools=self._get_tools(),
            temperature=TEMPERATURE,
            num_predict=NUM_PREDICT,
            stream=False,
        )

        msg = response.message
        from llm import _ensure_thinking
        thinking = _ensure_thinking(msg)
        tool_calls = msg.tool_calls or []

        if thinking:
            self.reasoning_log.append({"type": "thinking", "content": thinking})

        for tc in tool_calls:
            fn = tc.get("function", tc) if isinstance(tc, dict) else tc.function
            self.reasoning_log.append({
                "type": "tool_call",
                "name": fn.get("name", "") if isinstance(fn, dict) else fn.name,
                "args": fn.get("arguments", {}) if isinstance(fn, dict) else fn.arguments,
            })

        return response

    def _execute_native_tool(self, name: str, args: dict) -> str:
        if self.stop_requested:
            raise ForceStopError("Task force-stopped by user.")
        result = super()._execute_native_tool(name, args)
        self.reasoning_log.append({
            "type": "tool_result",
            "name": name,
            "result": result,
        })
        return result

    def _execute_tool_calls(self, tool_calls) -> list:
        results = []
        for tc in tool_calls:
            name = self._tc_name(tc)
            args = self._tc_args(tc)
            try:
                result = self._execute_native_tool(name, args)
            except Exception as e:
                result = f"[ERROR] Tool {name} failed: {e}"
            results.append((name, args, result, self._tc_id(tc)))
        return results

    def process(self, user_input: str) -> str:
        self.stop_requested = False
        self.reasoning_log = []
        result = super().process(user_input)
        if not result:
            for msg in reversed(self.messages):
                if msg["role"] == "assistant" and msg.get("content"):
                    result = msg["content"]
                    break
        if result and result.startswith("__ask_user__"):
            return result
        self.reasoning_log.append({"type": "final", "content": result or "No output returned."})
        return result

    def ask_answer(self, answer: str) -> str:
        self.stop_requested = False
        result = super().ask_answer(answer)
        if not result:
            for msg in reversed(self.messages):
                if msg["role"] == "assistant" and msg.get("content"):
                    result = msg["content"]
                    break
        if result and result.startswith("__ask_user__"):
            return result
        self.reasoning_log.append({"type": "final", "content": result or "No output returned."})
        return result

    def _chat_stream(self):
        response = self._chat()
        from llm import _ensure_thinking
        from rich.panel import Panel
        from rich.markdown import Markdown
        from agent import console
        msg = response.message
        thinking = _ensure_thinking(msg)
        if thinking:
            console.print(Panel(
                Markdown(thinking),
                title="[yellow]Reflection[/]",
                border_style="yellow",
                title_align="left",
            ))
        return response


class DirectCharlynChat:
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        self.llm = LLMClient(model_override=model, host_override=host)

    def ask(self, user_input: str) -> str:
        from config import TEMPERATURE, NUM_PREDICT

        system = (
            "You are Charlyn, an autonomous AI assistant. "
            "Answer directly, clearly, and concisely. Do not use HTML tags such as <br>. "
            "Do not use markdown tables. Use bullet points, numbered lists, or plain paragraphs. "
            "Keep formatting simple for a Discord embed."
        )

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_input},
            ],
            temperature=TEMPERATURE,
            num_predict=NUM_PREDICT,
            stream=False,
        )
        return response.message.content or ""


agents: dict[int, DiscordCharlynAgent] = {}


def get_agent(user_id: int) -> DiscordCharlynAgent:
    state = load_state()
    model = state.get("model")
    host = state.get("host")

    if user_id in agents:
        agent = agents[user_id]
        if (
            getattr(agent, "model_override", None) != model
            or getattr(agent, "host_override", None) != host
        ):
            agent.close()
            agents[user_id] = DiscordCharlynAgent(model=model, host=host, user_id=user_id)
    else:
        agents[user_id] = DiscordCharlynAgent(model=model, host=host, user_id=user_id)

    return agents[user_id]


def _is_whitelisted(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    state = load_state()
    return user_id in state.get("whitelist", [])


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _collect_image_attachments(reasoning_log: list[dict]) -> list[discord.File]:
    seen = set()
    files = []
    for entry in reasoning_log:
        if entry.get("type") != "tool_result":
            continue
        result = entry.get("result", "")
        if not isinstance(result, str):
            continue
        candidates = [result]
        if entry.get("name") in ("terminal", "python_execute"):
            for line in result.splitlines():
                line = line.strip()
                if os.path.isfile(line) and os.path.splitext(line)[1].lower() in _IMAGE_EXTS:
                    candidates.append(line)
        for path in candidates:
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in _IMAGE_EXTS:
                continue
            abspath = os.path.abspath(path)
            if abspath in seen:
                continue
            seen.add(abspath)
            if len(files) >= 5:
                break
            files.append(discord.File(abspath))
        if len(files) >= 5:
            break
    return files


async def whitelist_check(interaction: discord.Interaction) -> bool:
    if _is_whitelisted(interaction.user.id):
        return True
    raise app_commands.CheckFailure("You are not authorized to use this command.")


async def owner_check(interaction: discord.Interaction) -> bool:
    if _is_owner(interaction.user.id):
        return True
    raise app_commands.CheckFailure("Only the bot owner can use this command.")


async def _timer_background_loop():
    bot_var = bot
    await bot_var.wait_until_ready()
    while not bot_var.is_closed():
        try:
            due = timer_manager.get_due_timers()
            for t in due:
                try:
                    user = await bot_var.fetch_user(t["user_id"])
                    msg = t.get("message", "Timer up!")
                    embed = _make_embed(COLOR_INFO, title="Timer")
                    embed.description = f"Timer up! **{msg}**"
                    embed.set_footer(text=f"Timer ID: {t['id']}")
                    await user.send(embed=embed)
                except discord.HTTPException:
                    pass
                except Exception as e:
                    print(f"[Timer] Failed to notify user {t['user_id']}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[Timer] Background loop error: {e}", file=sys.stderr)
        await asyncio.sleep(2)


class CharlynBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.on_error = self.on_app_command_error
        try:
            await self.tree.sync()
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"[Charlyn] Command sync rate limited. ({e})")
            else:
                raise
        timer_manager.set_bot(self)
        self.loop.create_task(_timer_background_loop())

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        embed = _make_embed(COLOR_ERROR, title="Command Failed")
        if isinstance(error, app_commands.CheckFailure):
            embed.description = str(error)
        else:
            embed.description = f"An error occurred.\n\n`{error}`"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException:
                pass


bot = CharlynBot()


class ReasoningView(discord.ui.View):
    def __init__(self, reasoning_log: list[dict]):
        super().__init__(timeout=300)
        self.reasoning_log = reasoning_log

    @discord.ui.button(
        label="View Full Reasoning",
        style=discord.ButtonStyle.secondary,
    )
    async def view_full(self, interaction: discord.Interaction, button: discord.ui.Button):
        embeds: list[discord.Embed] = []
        for entry in self.reasoning_log:
            emb = embed_from_entry(entry)
            if emb:
                embeds.append(emb)
        if len(embeds) > 10:
            embeds = embeds[:10]
        if not embeds:
            embeds = [_make_embed(COLOR_WARNING, title="No Reasoning")]
        await interaction.response.send_message(
            embeds=embeds,
            ephemeral=True,
        )


class AskUserModal(discord.ui.Modal, title="Your Answer"):
    answer_input = discord.ui.TextInput(
        label="Your answer",
        style=discord.TextStyle.paragraph,
        placeholder="Type your answer here...",
        required=True,
        max_length=500,
    )

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    async def on_submit(self, interaction: discord.Interaction):
        self.answer = self.answer_input.value.strip()
        await interaction.response.defer()


class AskUserView(discord.ui.View):
    def __init__(self, agent, options: list[str]):
        super().__init__(timeout=120)
        self.agent = agent
        self.answer: str | None = None
        self.message: discord.Message | None = None

        for opt in options[:4]:
            btn = discord.ui.Button(
                label=opt[:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"askopt_{opt[:50]}",
            )

            async def callback(interaction: discord.Interaction, opt=opt):
                self.answer = opt
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(view=self)
                self.stop()

            btn.callback = callback
            self.add_item(btn)

        custom_btn = discord.ui.Button(
            label="Type answer",
            style=discord.ButtonStyle.secondary,
        )

        async def custom_callback(interaction: discord.Interaction):
            modal = AskUserModal(self.agent)
            await interaction.response.send_modal(modal)
            timed_out = await modal.wait()
            if not timed_out and hasattr(modal, 'answer') and modal.answer:
                self.answer = modal.answer
                for child in self.children:
                    child.disabled = True
                if self.message:
                    await self.message.edit(view=self)
                self.stop()

        custom_btn.callback = custom_callback
        self.add_item(custom_btn)


@bot.tree.command(
    name="charlyn",
    description="Give Charlyn a task to handle.",
)
@app_commands.describe(prompt="Describe what you need done.", attachment="Optional file or image to include")
@app_commands.check(whitelist_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def charlyn_cmd(interaction: discord.Interaction, prompt: str, attachment: discord.Attachment = None):
    if not interaction.response.is_done():
        await interaction.response.defer()

    thinking_embed = _make_embed(COLOR_WARNING)
    thinking_embed.set_author(name="Thinking...")
    thinking_embed.description = "Processing your request."
    msg = await interaction.followup.send(embed=thinking_embed, wait=True)

    agent = get_agent(interaction.user.id)
    loop = asyncio.get_event_loop()

    if attachment:
        ext = attachment.filename.rsplit(".", 1)[-1] if "." in attachment.filename else "bin"
        screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        dest = os.path.join(screenshots_dir, f"{interaction.user.id}_{int(time.time())}.{ext}")
        await attachment.save(dest)
        prompt += f"\n\n<attached file: {dest} (original name: {attachment.filename})>"
        if ext.lower() in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            prompt += "\nThe attached file is an image. Use ocr_analyze on the file path to read text from it."

    future = loop.run_in_executor(None, agent.process, prompt)

    shown = 0
    while not future.done():
        await asyncio.sleep(0.3)
        current_len = len(agent.reasoning_log)
        if current_len > shown:
            shown = current_len
            main = None
            latest_extra = None
            for entry in agent.reasoning_log:
                if entry.get("type") == "final":
                    continue
                if entry.get("type") == "thinking":
                    text = entry.get("content", "")[:3900]
                    if text:
                        main = _make_embed(COLOR_WARNING)
                        main.set_author(name="Thinking...")
                        main.description = text
                else:
                    emb = embed_from_entry(entry)
                    if emb:
                        latest_extra = emb
            embeds = []
            if main:
                embeds.append(main)
            elif not latest_extra:
                fallback = _make_embed(COLOR_WARNING)
                fallback.set_author(name="Thinking...")
                fallback.description = "Processing your request."
                embeds.append(fallback)
            if latest_extra:
                embeds.append(latest_extra)
            try:
                await msg.edit(embeds=embeds)
            except discord.HTTPException as e:
                print(f"[Charlyn] Embed update failed: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[Charlyn] Unexpected embed error: {e}", file=sys.stderr)

    try:
        result = future.result()
    except ForceStopError:
        stop_embed = _make_embed(COLOR_ERROR, title="Stopped")
        stop_embed.description = "Task terminated on your order."
        try:
            await msg.edit(embed=stop_embed, view=None)
        except Exception:
            pass
        return
    except Exception as e:
        print(f"[Charlyn] Task failed for {interaction.user.id}: {e}", file=sys.stderr)
        err_embed = _make_embed(COLOR_ERROR, title="Failed")
        err_embed.description = "Something went wrong. Please try again."
        try:
            await msg.edit(embed=err_embed, view=None)
        except Exception:
            pass
        return

    while result and result.startswith("__ask_user__"):
        data = json.loads(result[len("__ask_user__"):])
        question = data.get("question", "?")
        options = data.get("options", [])
        ask_embed = _make_embed(COLOR_WARNING, title="Need Info")
        ask_embed.description = question
        view = AskUserView(agent, options)
        await msg.edit(embed=ask_embed, view=view)
        view.message = msg
        await view.wait()
        if view.answer is None:
            timeout_embed = _make_embed(COLOR_ERROR, title="Timed Out")
            timeout_embed.description = "You didn't respond in time."
            await msg.edit(embed=timeout_embed, view=None)
            return
        await msg.edit(embed=thinking_embed, view=None)
        try:
            result = await loop.run_in_executor(None, agent.ask_answer, view.answer)
        except Exception as e:
            print(f"[Charlyn] ask_answer failed for {interaction.user.id}: {e}", file=sys.stderr)
            err_embed = _make_embed(COLOR_ERROR, title="Failed")
            err_embed.description = "Something went wrong processing your answer."
            await msg.edit(embed=err_embed, view=None)
            return

    if result and (result.startswith("Stopped due to error:") or result.startswith("Agent reached max")):
        print(f"[Charlyn] Task ended for {interaction.user.id}: {result}", file=sys.stderr)
        err_embed = _make_embed(COLOR_ERROR, title="Failed")
        err_embed.description = "Something went wrong. Please try again."
        view = ReasoningView(agent.reasoning_log)
        try:
            await msg.edit(embed=err_embed, view=view)
        except Exception:
            pass
        return

    final_embed = _make_embed(COLOR_INFO, title="Done")
    final_embed.description = _strip_markdown_tables(result or "No output returned.")[:4000]
    view = ReasoningView(agent.reasoning_log)

    site_url = None
    for entry in agent.reasoning_log:
        if entry.get("type") == "tool_result" and entry.get("name") == "publish_research":
            r = entry.get("result", "")
            for line in r.splitlines():
                if line.startswith("URL:"):
                    site_url = line[len("URL:"):].strip()
                    break
            break
    if site_url:
        view.add_item(discord.ui.Button(label="Open Research Site", url=site_url, style=discord.ButtonStyle.link))

    attachments = _collect_image_attachments(agent.reasoning_log)
    try:
        if attachments:
            await msg.edit(embed=final_embed, view=view, attachments=attachments)
        else:
            await msg.edit(embed=final_embed, view=view)
    except Exception:
        pass


@bot.tree.command(
    name="ask",
    description="Ask Charlyn directly. No tools, just an answer.",
)
@app_commands.describe(question="What do you want to know?")
@app_commands.check(whitelist_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ask_cmd(interaction: discord.Interaction, question: str):
    await interaction.response.defer()

    try:
        state = load_state()
        chat = DirectCharlynChat(
            model=state.get("model"),
            host=state.get("host"),
        )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, chat.ask, question)

        embed = _make_embed(COLOR_PRIMARY, title="Answer")
        embed.description = _strip_markdown_tables(result)[:4000] or "No output returned."
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = _make_embed(COLOR_ERROR, title="Failed")
        embed.description = f"Could not get an answer.\n\n`{e}`"
        await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="reset",
    description="Clear your conversation history.",
)
@app_commands.check(whitelist_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def reset_cmd(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in agents:
        agents[user_id].close()
        del agents[user_id]

    embed = _make_embed(COLOR_SUCCESS, title="Reset")
    embed.description = "Conversation history cleared."
    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="asktest",
    description="Test the ask_user feature -- AI will ask you a question and report back.",
)
@app_commands.check(whitelist_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def asktest_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    agent = get_agent(interaction.user.id)
    question = (
        "What topic would you like to discuss?\n"
        "I'll ask you a question, you answer, and I'll confirm what I understood."
    )
    test_data = {"question": question, "options": ["Technology", "Gaming", "Anime", "Programming"]}
    ask_embed = _make_embed(COLOR_WARNING, title="Ask User Test")
    ask_embed.description = question
    view = AskUserView(agent, test_data["options"])
    view_msg = await interaction.followup.send(embed=ask_embed, view=view, wait=True)
    view.message = view_msg
    await view.wait()
    if view.answer is None:
        timeout_embed = _make_embed(COLOR_ERROR, title="Timed Out")
        timeout_embed.description = "You didn't respond in time."
        await view_msg.edit(embed=timeout_embed, view=None)
        return
    agent2 = get_agent(interaction.user.id)
    loop = asyncio.get_event_loop()
    thinking_embed = _make_embed(COLOR_WARNING)
    thinking_embed.set_author(name="Thinking...")
    thinking_embed.description = f"Got it! You said: **{view.answer}**"
    await view_msg.edit(embed=thinking_embed, view=None)
    try:
        result = await loop.run_in_executor(
            None,
            lambda: agent2.process(
                f"The user chose: {view.answer}. "
                f"Confirm what they chose and give them a fun fact or recommendation related to it."
            ),
        )
    except Exception as e:
        print(f"[Charlyn] asktest process failed: {e}", file=sys.stderr)
        err_embed = _make_embed(COLOR_ERROR, title="Failed")
        err_embed.description = "Something went wrong."
        await view_msg.edit(embed=err_embed, view=None)
        return

    if result and (result.startswith("Stopped due to error:") or result.startswith("Agent reached max")):
        print(f"[Charlyn] asktest process errored: {result}", file=sys.stderr)
        err_embed = _make_embed(COLOR_ERROR, title="Failed")
        err_embed.description = "Something went wrong."
        await view_msg.edit(embed=err_embed, view=None)
        return

    while result and result.startswith("__ask_user__"):
        data = json.loads(result[len("__ask_user__"):])
        q = data.get("question", "?")
        opts = data.get("options", [])
        ask_embed2 = _make_embed(COLOR_WARNING, title="Need Info")
        ask_embed2.description = q
        view2 = AskUserView(agent2, opts)
        await view_msg.edit(embed=ask_embed2, view=view2)
        view2.message = view_msg
        await view2.wait()
        if view2.answer is None:
            timeout_embed = _make_embed(COLOR_ERROR, title="Timed Out")
            timeout_embed.description = "You didn't respond in time."
            await view_msg.edit(embed=timeout_embed, view=None)
            return
        await view_msg.edit(embed=thinking_embed, view=None)
        try:
            result = await loop.run_in_executor(None, agent2.ask_answer, view2.answer)
        except Exception as e:
            print(f"[Charlyn] asktest ask_answer failed: {e}", file=sys.stderr)
            err_embed = _make_embed(COLOR_ERROR, title="Failed")
            err_embed.description = "Something went wrong processing your answer."
            await view_msg.edit(embed=err_embed, view=None)
            return

    if result and (result.startswith("Stopped due to error:") or result.startswith("Agent reached max")):
        print(f"[Charlyn] asktest errored: {result}", file=sys.stderr)
        err_embed = _make_embed(COLOR_ERROR, title="Failed")
        err_embed.description = "Something went wrong."
        await view_msg.edit(embed=err_embed, view=None)
        return

    final_embed = _make_embed(COLOR_SUCCESS, title="You Said")
    final_embed.description = (result or "No response.")[:4000]
    rv = ReasoningView(agent2.reasoning_log)
    attachments = _collect_image_attachments(agent2.reasoning_log)
    kwargs = {"embed": final_embed, "view": rv}
    if attachments:
        kwargs["file"] = attachments[0]
    await interaction.followup.send(**kwargs)


@bot.tree.command(
    name="forcestop",
    description="Kill the current running task.",
)
@app_commands.check(whitelist_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def forcestop_cmd(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id not in agents:
        embed = _make_embed(COLOR_WARNING, title="No Active Task")
        embed.description = "You don't have an active task."
        await interaction.response.send_message(embed=embed)
        return

    agents[user_id].stop_requested = True
    embed = _make_embed(COLOR_ERROR, title="Signal Sent")
    embed.description = "Termination signal sent. The task will stop at the next checkpoint."
    await interaction.response.send_message(embed=embed)


whitelist_group = app_commands.Group(
    name="whitelist",
    description="Manage authorized users. Owner only.",
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
)


@whitelist_group.command(name="add", description="Authorize a user.")
@app_commands.describe(user="The user to authorize")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def whitelist_add(interaction: discord.Interaction, user: discord.User):
    state = load_state()
    allowed = state.setdefault("whitelist", [])

    if user.id == OWNER_ID:
        embed = _make_embed(COLOR_WARNING, title="Notice")
        embed.description = "The owner is always authorized."
        await interaction.response.send_message(embed=embed)
        return
    if user.id in allowed:
        embed = _make_embed(COLOR_WARNING, title="Notice")
        embed.description = f"{user.mention} is already authorized."
        await interaction.response.send_message(embed=embed)
        return

    allowed.append(user.id)
    save_state(state)

    embed = _make_embed(COLOR_SUCCESS, title="Authorized")
    embed.description = f"{user.mention} can now use Charlyn."
    await interaction.response.send_message(embed=embed)


@whitelist_group.command(name="remove", description="Revoke user access.")
@app_commands.describe(user="The user to remove")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def whitelist_remove(interaction: discord.Interaction, user: discord.User):
    state = load_state()
    allowed = state.setdefault("whitelist", [])

    if user.id == OWNER_ID:
        embed = _make_embed(COLOR_ERROR, title="Denied")
        embed.description = "Cannot remove the owner."
        await interaction.response.send_message(embed=embed)
        return
    if user.id not in allowed:
        embed = _make_embed(COLOR_WARNING, title="Notice")
        embed.description = f"{user.mention} is not in the authorized list."
        await interaction.response.send_message(embed=embed)
        return

    allowed.remove(user.id)
    if user.id in agents:
        agents[user.id].close()
        del agents[user.id]
    sandbox_remove_user(user.id)
    save_state(state)

    embed = _make_embed(COLOR_ERROR, title="Revoked")
    embed.description = f"{user.mention} access has been revoked."
    await interaction.response.send_message(embed=embed)


@whitelist_group.command(name="list", description="List authorized users.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def whitelist_list(interaction: discord.Interaction):
    state = load_state()
    allowed = state.get("whitelist", [])

    lines = [f"<@{OWNER_ID}> — Owner"]
    for uid in allowed:
        lines.append(f"<@{uid}> — Authorized")

    embed = _make_embed(COLOR_PRIMARY, title="Authorized Users")
    embed.description = "\n".join(lines) if lines else "No other users are authorized."
    await interaction.response.send_message(embed=embed)


bot.tree.add_command(whitelist_group)


model_group = app_commands.Group(
    name="model",
    description="Manage the AI model. Owner only.",
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
)


@model_group.command(name="set", description="Switch to a different model.")
@app_commands.describe(model="Model name (e.g. gpt-oss:20b)")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def model_set(interaction: discord.Interaction, model: str):
    state = load_state()
    state["model"] = model
    save_state(state)

    for uid, agent in list(agents.items()):
        agent.close()
        agents[uid] = DiscordCharlynAgent(model=model, host=state.get("host"), user_id=uid)

    embed = _make_embed(COLOR_SUCCESS, title="Model Switched")
    embed.description = f"Now running `{model}`. All active sessions refreshed."
    await interaction.response.send_message(embed=embed)


@model_group.command(name="get", description="Show the current model.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def model_get(interaction: discord.Interaction):
    state = load_state()
    model = state.get("model")

    if model:
        embed = _make_embed(COLOR_INFO, title="Current Model")
        embed.description = f"`{model}`"
    else:
        from config import OLLAMA_MODEL
        embed = _make_embed(COLOR_INFO, title="Current Model")
        embed.description = f"Default: `{OLLAMA_MODEL}`"

    await interaction.response.send_message(embed=embed)


@model_group.command(name="list", description="List available models.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def model_list(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        state = load_state()
        llm = LLMClient(
            model_override=state.get("model"),
            host_override=state.get("host"),
        )
        names = llm.list_models()

        if not names:
            embed = _make_embed(COLOR_ERROR, title="No Models")
            embed.description = "No models found."
            await interaction.followup.send(embed=embed)
            return

        embed = _make_embed(COLOR_PRIMARY, title="Available Models")
        embed.description = "\n".join(f"• `{m}`" for m in names)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = _make_embed(COLOR_ERROR, title="Failed")
        embed.description = f"Could not fetch model list.\n\n`{e}`"
        await interaction.followup.send(embed=embed)


bot.tree.add_command(model_group)


copilot_group = app_commands.Group(
    name="copilot",
    description="Manage GitHub Copilot authentication. Owner only.",
    allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
    allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
)


@copilot_group.command(name="login", description="Log in to GitHub Copilot via OAuth device flow.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def copilot_login(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    import io
    from copilot_auth import device_login

    buf = io.StringIO()

    def print_fn(msg: str):
        buf.write(msg + "\n")

    try:
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, lambda: device_login(print_fn=print_fn))
        output = buf.getvalue()

        embed = _make_embed(COLOR_SUCCESS, title="Copilot Login")
        embed.description = f"```\n{output}\n```"
        embed.add_field(name="Status", value="Authenticated", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        embed = _make_embed(COLOR_ERROR, title="Copilot Login Failed")
        embed.description = f"```\n{buf.getvalue()}\n```\n`{e}`"
        await interaction.followup.send(embed=embed, ephemeral=True)


@copilot_group.command(name="logout", description="Remove saved Copilot token.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def copilot_logout(interaction: discord.Interaction):
    from copilot_auth import logout as copilot_logout_fn

    copilot_logout_fn()
    embed = _make_embed(COLOR_SUCCESS, title="Copilot Logout")
    embed.description = "Copilot token removed from .env."
    await interaction.response.send_message(embed=embed)


@copilot_group.command(name="status", description="Check Copilot authentication status.")
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def copilot_status(interaction: discord.Interaction):
    await interaction.response.defer()

    from config import COPILOT_TOKEN
    from copilot_auth import validate_token

    if not COPILOT_TOKEN:
        embed = _make_embed(COLOR_WARNING, title="Copilot Status")
        embed.description = "No token saved. Use `/copilot login` to authenticate."
        await interaction.followup.send(embed=embed)
        return

    valid = validate_token(COPILOT_TOKEN)
    if valid is None:
        embed = _make_embed(COLOR_WARNING, title="Copilot Status")
        embed.description = "Could not verify token (network issue). It may still work."
    elif valid:
        embed = _make_embed(COLOR_SUCCESS, title="Copilot Status")
        embed.description = "Token is valid"
        embed.add_field(name="Model", value="`gpt-4o` (default)", inline=False)
        embed.add_field(name="Usage", value="Set `LLM_BACKEND=copilot` in .env to use Copilot as your provider.", inline=False)
    else:
        embed = _make_embed(COLOR_ERROR, title="Copilot Status")
        embed.description = "Token is invalid or expired  run `/copilot login`"

    await interaction.followup.send(embed=embed)


bot.tree.add_command(copilot_group)


class ConfigModal(discord.ui.Modal, title="System Settings"):
    host_input = discord.ui.TextInput(
        label="Ollama Server Address",
        placeholder="https://your-server.example.com",
        required=False,
        max_length=256,
    )

    async def on_submit(self, interaction: discord.Interaction):
        host = self.host_input.value.strip() or None
        state = load_state()
        state["host"] = host
        save_state(state)

        for uid, agent in list(agents.items()):
            agent.close()
            agents[uid] = DiscordCharlynAgent(
                model=state.get("model"), host=host, user_id=uid
            )

        if host:
            embed = _make_embed(COLOR_SUCCESS, title="Settings Saved")
            embed.description = f"Server address updated to `{host}`"
        else:
            from config import OPENCODE_BASE_URL, LLM_BACKEND
            default = OPENCODE_BASE_URL if LLM_BACKEND == "opencode" else "http://localhost:11434"
            embed = _make_embed(COLOR_SUCCESS, title="Settings Saved")
            embed.description = f"Server reset to default: `{default}`"

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        embed = _make_embed(COLOR_ERROR, title="Save Failed")
        embed.description = f"Could not apply settings.\n\n`{error}`"
        await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="config",
    description="Adjust system settings.",
)
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def config_cmd(interaction: discord.Interaction):
    state = load_state()
    modal = ConfigModal()
    current_host = state.get("host")
    if current_host:
        modal.host_input.default = current_host
    await interaction.response.send_modal(modal)


@bot.tree.command(
    name="users",
    description="Show active sandbox status.",
)
@app_commands.check(owner_check)
@app_commands.default_permissions()
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def users_cmd(interaction: discord.Interaction):
    if not sandbox_available():
        embed = _make_embed(COLOR_WARNING, title="Sandbox")
        embed.description = "Docker is not available on this system."
        await interaction.response.send_message(embed=embed)
        return
    sandboxes = sandbox_list_active()
    if not sandboxes:
        embed = _make_embed(COLOR_INFO, title="Sandbox")
        embed.description = "No active sandboxes."
        await interaction.response.send_message(embed=embed)
        return
    lines = []
    for sb in sandboxes:
        if sb["running"]:
            status = "Running"
        else:
            status = "Stopped"
        storage = f"{sb['storage_used_mb']:.0f}/{sb['storage_limit_mb']:.0f} MB"
        lines.append(
            f"**User {sb['user_id']}** — `{sb['container']}` — "
            f"{storage} — {sb['workspace']} ({status})"
        )
    embed = _make_embed(COLOR_PRIMARY, title=f"Sandboxes ({len(sandboxes)})")
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed)


def main():
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        print("[ERROR] DISCORD_TOKEN not set. Create a .env file or run setup.py.")
        sys.exit(1)

    print("[Charlyn Discord] Starting bot...")
    bot.run(token)


if __name__ == "__main__":
    main()

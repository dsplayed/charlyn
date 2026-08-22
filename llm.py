"""Unified LLM client — supports Ollama, OpenAI-compatible APIs, and GitHub Copilot (via LiteLLM)."""
import json
import os
import time
from typing import Any, Dict, List, Optional, Generator
from types import SimpleNamespace

from config import (
    LLM_BACKEND,
    OLLAMA_HOST, OLLAMA_MODEL,
    OPENCODE_API_KEY, OPENCODE_BASE_URL, OPENCODE_MODEL,
    COPILOT_TOKEN, COPILOT_MODEL, COPILOT_BASE_URL,
    TEMPERATURE, NUM_PREDICT, NUM_CTX,
)


def _ollama_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    return tool


def _openai_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    return tool


def _normalize_tool_calls(tool_calls, backend: str) -> list:
    """Normalize tool calls to JSON-serializable dicts preserving id/type/function format."""
    if not tool_calls:
        return []
    normalized = []
    for tc in tool_calls:
        if backend == "ollama":
            normalized.append(tc)
        else:
            raw_args = tc.function.arguments
            if isinstance(raw_args, str):
                args_str = raw_args
            elif isinstance(raw_args, dict):
                args_str = json.dumps(raw_args)
            else:
                args_str = "{}"
            normalized.append({
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": tc.function.name,
                    "arguments": args_str,
                }
            })
    return normalized


def _ensure_content(msg) -> str:
    if hasattr(msg, "content"):
        return msg.content or ""
    return msg.get("content", "")


def _ensure_thinking(msg) -> str:
    val = ""
    if hasattr(msg, "thinking") and msg.thinking:
        val = msg.thinking
    elif hasattr(msg, "reasoning_content") and msg.reasoning_content:
        val = msg.reasoning_content
    elif isinstance(msg, dict):
        val = msg.get("thinking", "") or msg.get("reasoning", "") or msg.get("reasoning_content", "") or ""
    return val or ""


def _ensure_tool_calls(msg, backend: str) -> list:
    raw = None
    if hasattr(msg, "tool_calls"):
        raw = msg.tool_calls
    elif isinstance(msg, dict):
        raw = msg.get("tool_calls")
    return _normalize_tool_calls(raw or [], backend)


class ChatResponse:
    def __init__(self, content: str = "", thinking: str = "", tool_calls: Optional[list] = None):
        self.message = SimpleNamespace(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls or [],
        )


class LLMClient:
    def __init__(self, model_override: Optional[str] = None, host_override: Optional[str] = None):
        self.backend = LLM_BACKEND
        self._model_override = model_override
        self._host_override = host_override
        self._ollama_client = None
        self._openai_client = None

        if self.backend == "ollama":
            import ollama
            host = host_override or OLLAMA_HOST
            self._ollama_client = ollama.Client(host=host)
        else:
            from openai import OpenAI
            if self.backend == "copilot":
                key = os.getenv("COPILOT_TOKEN") or COPILOT_TOKEN
                if not key:
                    print("[WARN] COPILOT_TOKEN not set. Run `python agent.py --copilot-login` or `/copilot_login` on Discord.")
                base = host_override or COPILOT_BASE_URL
            else:
                key = os.getenv("OPENCODE_API_KEY") or OPENCODE_API_KEY
                if not key:
                    print("[WARN] OPENCODE_API_KEY not set. OpenCode.ai may not work without an API key.")
                base = host_override or OPENCODE_BASE_URL
            self._openai_client = OpenAI(
                api_key=key or "no-key",
                base_url=base,
            )

    @property
    def model(self) -> str:
        if self._model_override:
            return self._model_override
        if self.backend == "opencode":
            return OPENCODE_MODEL
        if self.backend == "copilot":
            return COPILOT_MODEL
        return OLLAMA_MODEL

    def list_models(self) -> List[str]:
        if self.backend == "ollama":
            data = self._ollama_client.list()
            if hasattr(data, "models"):
                return [m.model for m in data.models]
            return [m["model"] for m in data.get("models", [])]
        else:
            try:
                models = self._openai_client.models.list()
                return [m.id for m in models]
            except Exception:
                return [self.model]

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        opts = {
            "temperature": kwargs.get("temperature", TEMPERATURE),
            "num_predict": kwargs.get("num_predict", NUM_PREDICT),
            "num_ctx": kwargs.get("num_ctx", NUM_CTX),
        }

        if self.backend == "ollama":
            return self._ollama_client.chat(
                model=kwargs.get("model", OLLAMA_MODEL),
                messages=messages,
                tools=tools,
                options=opts,
                stream=stream,
            )
        else:
            model = COPILOT_MODEL if self.backend == "copilot" else OPENCODE_MODEL
            return self._openai_chat(
                model=kwargs.get("model", model),
                messages=messages,
                tools=tools,
                stream=stream,
                **opts,
            )

    def _openai_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        api_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", TEMPERATURE),
            "max_tokens": kwargs.get("num_predict", NUM_PREDICT),
        }
        if tools:
            api_kwargs["tools"] = tools
            api_kwargs["tool_choice"] = "auto"

        if stream:
            return self._openai_stream(api_kwargs)
        else:
            return self._openai_sync(api_kwargs)

    def _openai_sync(self, kwargs: dict) -> Any:
        response = self._openai_client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        return ChatResponse(
            content=_ensure_content(msg),
            thinking=_ensure_thinking(msg),
            tool_calls=_normalize_tool_calls(msg.tool_calls, "opencode"),
        )

    def _openai_stream(self, kwargs: dict) -> Generator:
        """Yield chunk objects matching Ollama's streaming format."""
        from types import SimpleNamespace as NS

        stream = self._openai_client.chat.completions.create(**kwargs, stream=True)
        accumulated = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            content = getattr(delta, "content", None) or ""
            thinking = getattr(delta, "thinking", None) or getattr(delta, "reasoning_content", None) or ""
            if not thinking and isinstance(delta, dict):
                thinking = delta.get("reasoning_content", "") or delta.get("reasoning", "") or ""
            tc_delta = getattr(delta, "tool_calls", None) or []

            if tc_delta:
                for tc in tc_delta:
                    idx = tc.index
                    if idx not in accumulated:
                        accumulated[idx] = {"id": None, "name": "", "arguments": ""}
                    if tc.id:
                        accumulated[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        accumulated[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        accumulated[idx]["arguments"] += tc.function.arguments

            msg = NS(content=content, thinking=thinking, tool_calls=tc_delta or None)
            yield NS(message=msg, done=False)

        # Final chunk with fully accumulated tool calls
        final_tcs = None
        if accumulated:
            final_tcs = []
            for idx in sorted(accumulated):
                entry = accumulated[idx]
                final_tcs.append({
                    "id": entry.get("id"),
                    "type": "function",
                    "function": {"name": entry["name"], "arguments": entry["arguments"]}
                })
        msg = NS(content="", thinking="", tool_calls=final_tcs)
        yield NS(message=msg, done=True)

    def embeddings(self, text: str) -> List[float]:
        if self.backend == "ollama":
            resp = self._ollama_client.embeddings(model=OLLAMA_MODEL, prompt=text[:512])
            if hasattr(resp, "embedding"):
                return resp.embedding
            return resp.get("embedding", [])
        else:
            model = COPILOT_MODEL if self.backend == "copilot" else OPENCODE_MODEL
            resp = self._openai_client.embeddings.create(
                model=model,
                input=text[:512],
            )
            return resp.data[0].embedding

    def close(self):
        pass

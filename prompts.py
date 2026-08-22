"""Prompt utilities and XML parsers."""
import re
from dataclasses import dataclass
from typing import List


@dataclass
class ToolCall:
    name: str
    params: dict


@dataclass
class ReflectBlock:
    step: str
    observation: str
    plan: str
    reflection: str


def parse_tool_calls(text: str) -> List[ToolCall]:
    """Extract XML tool calls from model output."""
    calls = []
    pattern = re.compile(r"<(?P<name>[a-z_]+)>(?P<body>.*?)</(?P=name)>", re.DOTALL)
    for m in pattern.finditer(text):
        name = m.group("name")
        body = m.group("body")
        if name in ("reflect", "finish"):
            continue
        params = {}
        param_pattern = re.compile(r"<(?P<pname>[a-z_]+)>(?P<pval>.*?)</(?P=pname)>", re.DOTALL)
        for pm in param_pattern.finditer(body):
            params[pm.group("pname")] = pm.group("pval").strip()
        calls.append(ToolCall(name=name, params=params))
    return calls


def parse_reflect(text: str) -> ReflectBlock:
    """Extract the latest <reflect> block."""
    m = re.search(r"<reflect>(.*?)</reflect>", text, re.DOTALL)
    if not m:
        return ReflectBlock("", "", "", "")
    inner = m.group(1)

    def grab(tag: str) -> str:
        tm = re.search(rf"<{tag}>(.*?)</{tag}>", inner, re.DOTALL)
        return tm.group(1).strip() if tm else ""

    return ReflectBlock(
        step=grab("step"),
        observation=grab("observation"),
        plan=grab("plan"),
        reflection=grab("reflection"),
    )


def parse_finish(text: str) -> str:
    m = re.search(r"<finish>.*?<answer>(.*?)</answer>.*?</finish>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""

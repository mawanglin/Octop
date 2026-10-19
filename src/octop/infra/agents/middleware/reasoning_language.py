"""Ask the model to think in Simplified Chinese when the user writes in Chinese.

Most reasoning models default to English chain-of-thought even when they answer
in Chinese, because the harness base prompt and tool docs are English. This
middleware appends one directive to the end of the system message (keeping the
cacheable prefix stable) whenever the latest user message contains Chinese.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_CJK = re.compile(r"[一-鿿]")

ZH_REASONING_DIRECTIVE = (
    "【语言要求】用户正在使用中文交流：请全程使用简体中文进行思考、推理和回答；"
    "代码、命令、文件路径和专有名词可保留原文。"
)


def _text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def latest_user_text(messages: Sequence[BaseMessage]) -> str:
    """Text of the newest human message that has any (image-only turns are skipped)."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _text_of(message)
            if text.strip():
                return text
    return ""


def _with_directive(request: ModelRequest[Any]) -> ModelRequest[Any]:
    if not _CJK.search(latest_user_text(request.messages)):
        return request
    system = request.system_message
    if system is None:
        return request.override(system_message=SystemMessage(content=ZH_REASONING_DIRECTIVE))
    if ZH_REASONING_DIRECTIVE in _text_of(system):
        return request
    content = system.content
    if isinstance(content, str):
        merged: Any = f"{content.rstrip()}\n\n{ZH_REASONING_DIRECTIVE}"
    else:
        merged = [*content, {"type": "text", "text": ZH_REASONING_DIRECTIVE}]
    return request.override(system_message=system.model_copy(update={"content": merged}))


class ReasoningLanguageMiddleware(AgentMiddleware[Any, Any]):
    """Append a think-in-Chinese directive for turns written in Chinese."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_with_directive(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_with_directive(request))


__all__ = ["ZH_REASONING_DIRECTIVE", "ReasoningLanguageMiddleware", "latest_user_text"]

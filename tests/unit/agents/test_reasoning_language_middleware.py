"""ReasoningLanguageMiddleware: think in Simplified Chinese on Chinese turns."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from tests.unit.agents.test_agent_manager import _row, manager  # noqa: F401 - fixture

from octop.infra.agents.manager import AgentManager
from octop.infra.agents.middleware.reasoning_language import (
    ZH_REASONING_DIRECTIVE,
    ReasoningLanguageMiddleware,
    latest_user_text,
)


def _call(request: ModelRequest[Any]) -> ModelRequest[Any]:
    captured: list[ModelRequest[Any]] = []

    def handler(req: ModelRequest[Any]) -> Any:
        captured.append(req)
        return "ok"

    assert ReasoningLanguageMiddleware().wrap_model_call(request, handler) == "ok"
    return captured[0]


def _request(messages: list[Any], system: SystemMessage | None) -> ModelRequest[Any]:
    return ModelRequest(model=MagicMock(), messages=messages, system_message=system)


def test_appends_directive_to_end_of_string_system_prompt() -> None:
    system = SystemMessage(content="You are a deep agent.\n", id="sys-1")
    out = _call(_request([HumanMessage(content="帮我写个脚本")], system))
    assert out.system_message is not None
    assert out.system_message.content == f"You are a deep agent.\n\n{ZH_REASONING_DIRECTIVE}"
    assert out.system_message.id == "sys-1"


def test_appends_text_block_to_block_system_prompt() -> None:
    blocks = [{"type": "text", "text": "base", "cache_control": {"type": "ephemeral"}}]
    out = _call(_request([HumanMessage(content="你好")], SystemMessage(content=blocks)))
    assert out.system_message is not None
    assert out.system_message.content == [*blocks, {"type": "text", "text": ZH_REASONING_DIRECTIVE}]


def test_creates_system_message_when_missing() -> None:
    out = _call(_request([HumanMessage(content="你好")], None))
    assert out.system_message is not None
    assert out.system_message.content == ZH_REASONING_DIRECTIVE


def test_leaves_english_turns_and_existing_directive_untouched() -> None:
    english = _request(
        [
            HumanMessage(content="你好"),
            AIMessage(content="hi"),
            HumanMessage(content="write a script"),
        ],
        SystemMessage(content="base"),
    )
    assert _call(english) is english

    already = _request(
        [HumanMessage(content="你好")], SystemMessage(content=f"base\n\n{ZH_REASONING_DIRECTIVE}")
    )
    assert _call(already) is already


def test_latest_user_text_skips_image_only_turns_and_reads_blocks() -> None:
    messages = [
        HumanMessage(content=[{"type": "text", "text": "看看这张图"}]),
        AIMessage(content="好的"),
        HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:,"}}]),
    ]
    assert latest_user_text(messages) == "看看这张图"
    assert latest_user_text([]) == ""


def test_async_path_appends_directive() -> None:
    captured: list[ModelRequest[Any]] = []

    async def handler(req: ModelRequest[Any]) -> Any:
        captured.append(req)
        return "ok"

    request = _request([HumanMessage(content="解释一下")], SystemMessage(content="base"))
    assert asyncio.run(ReasoningLanguageMiddleware().awrap_model_call(request, handler)) == "ok"
    assert captured[0].system_message is not None
    assert str(captured[0].system_message.content).endswith(ZH_REASONING_DIRECTIVE)


def test_build_harness_config_includes_reasoning_language_middleware(
    manager: AgentManager,  # noqa: F811 - pytest fixture
) -> None:
    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert any(isinstance(m, ReasoningLanguageMiddleware) for m in (cfg.middleware or []))

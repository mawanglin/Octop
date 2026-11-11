"""Fork-owned overlay on the bundled provider presets (model lists).

The bundled ``provider_template.json`` ships inside ``octop-harness`` and lags the vendors'
official model lists. This module patches the loaded presets in memory: drop models the vendor
has retired, add current ones, correct a few limits. Nothing is written to disk.

* Applied from ``load_provider_presets()`` (one hook line, marked ``# fork:``).
* Idempotent and upstream-tolerant: removals skip missing ids, additions skip ids that already
  exist (so no duplicates once ``octop-harness`` catches up), unknown providers are ignored.
* Saved user configs are never touched: ``sync_provider_preset_models`` only appends, so retired
  ids stay in existing configs and new ids show up there automatically.

Sources are each vendor's official model / pricing / deprecation pages, plus OpenRouter's public
``/api/v1/models`` for the OpenRouter rows, checked on 2026-11-11. Fields the vendor page did not
state are omitted rather than guessed. Reasoning profiles are only given to families whose
request semantics are documented (Claude 5, GPT-6, Gemini 4 / 3.x flash).

SiliconFlow (cn), Xiaomi MiMo and iFlytek Astron were added on request from their own pages:
siliconflow.cn/models (model data embedded in the page), mimo.mi.com model list, and the public
model-square API behind maas.xfyun.cn/modelSquare.

Not covered on purpose: ``siliconflow-intl`` (its page has no readable model data), every other
"plan" preset (Coding / Token / Agent Plan, Kimi Coding Plan, Tencent HAI), ``dashscope-us``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

_K = 1024


def _m(
    model_id: str,
    name: str,
    *,
    context: int | None = None,
    max_input: int | None = None,
    max_output: int | None = None,
    inputs: Sequence[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One preset model row; unknown limits stay out of the row."""
    row: dict[str, Any] = {"id": model_id, "name": name}
    if context is not None:
        row["context_window"] = context
        row["max_input_tokens"] = max_input if max_input is not None else context
    if max_output is not None:
        row["max_output_tokens"] = max_output
    if inputs is not None:
        row["input"] = list(inputs)
    row.update(extra)
    return row


@dataclass(frozen=True)
class ProviderPatch:
    remove: tuple[str, ...] = ()
    add: tuple[dict[str, Any], ...] = ()
    update: dict[str, dict[str, Any]] = field(default_factory=dict)


_TI = ("text", "image")
_RESPONSES = {"api_mode": "responses"}

_CLAUDE_5 = (
    _m("claude-fable-5-2", "Claude Fable 5.2", context=1_000_000, max_output=128_000, inputs=_TI),
    _m("claude-opus-5-5", "Claude Opus 5.5", context=1_000_000, max_output=128_000, inputs=_TI),
    _m("claude-sonnet-5-5", "Claude Sonnet 5.5", context=1_000_000, max_output=128_000, inputs=_TI),
    _m("claude-haiku-5-5", "Claude Haiku 5.5", context=1_000_000, max_output=128_000, inputs=_TI),
)


def _gpt6(**extra: Any) -> tuple[dict[str, Any], ...]:
    def row(mid: str, name: str) -> dict[str, Any]:
        return _m(
            mid,
            name,
            context=1_050_000,
            max_input=922_000,
            max_output=128_000,
            inputs=_TI,
            **extra,
        )

    return (
        row("gpt-6-astra", "GPT-6 Astra"),
        row("gpt-6.1-sol", "GPT-6.1 Sol"),
        row("gpt-6.1-terra", "GPT-6.1 Terra"),
        row("gpt-6-luna", "GPT-6 Luna"),
    )


def _or(
    model_id: str, name: str, context: int, max_output: int, inputs: Sequence[str]
) -> dict[str, Any]:
    return _m(model_id, name, context=context, max_output=max_output, inputs=inputs)


_KIMI_RETIRED = (
    "kimi-k2.5",
    "kimi-k2-0905-preview",
    "kimi-k2-0711-preview",
    "kimi-k2-turbo-preview",
    "kimi-k2-thinking",
    "kimi-k2-thinking-turbo",
    "kimi-k2.7-code",  # closed to new users, shutting down end of 2026
    "kimi-k2.6",  # same
)
_KIMI_NEW = (
    _m("kimi-k3.1-pro", "Kimi K3.1 Pro", context=1_048_576, inputs=_TI),
    _m("kimi-k3.1-pro-highspeed", "Kimi K3.1 Pro Highspeed", context=1_048_576, inputs=_TI),
)
_MINIMAX_RETIRED = (
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
)
_MINIMAX_NEW = (
    _m("MiniMax-M3.1-Flash", "MiniMax M3.1 Flash", context=1_000_000, inputs=_TI),
    _m("MiniMax-M3", "MiniMax M3", context=1_000_000, inputs=_TI),
)
_ZHIPU_NEW = (
    _m("glm-5.3", "GLM-5.3", context=1_000_000, max_output=128 * _K),
    _m("glm-5.3-flash", "GLM-5.3 Flash", context=1_000_000, max_output=128 * _K, inputs=_TI),
    _m("glm-5.3-flashx", "GLM-5.3 FlashX", context=1_000_000, max_output=128 * _K),
)
_QWEN_RETIRED = ("qwen3-max", "qwen3-235b-a22b-thinking-2507")
_DOUBAO_NEW = (
    _m(
        "doubao-seed-2-1-pro-260915",
        "Doubao-Seed-2.1-pro",
        context=1024 * _K,
        max_output=256 * _K,
        inputs=_TI,
    ),
    _m(
        "doubao-seed-2-1-lite-260915",
        "Doubao-Seed-2.1-lite",
        context=1024 * _K,
        max_output=256 * _K,
        inputs=_TI,
    ),
    _m(
        "doubao-seed-2-1-turbo-260628",
        "Doubao-Seed-2.1-turbo",
        context=256 * _K,
        max_output=256 * _K,
        inputs=_TI,
    ),
    _m(
        "doubao-seed-evolving",
        "Doubao-Seed-evolving",
        context=1024 * _K,
        max_output=256 * _K,
        inputs=_TI,
    ),
)
_DOUBAO_20_LIMITS = {
    "context_window": 256 * _K,
    "max_input_tokens": 224 * _K,
    "max_output_tokens": 128 * _K,
}

PATCHES: dict[str, ProviderPatch] = {
    # https://docs.anthropic.com/en/docs/about-claude/model-deprecations
    "anthropic": ProviderPatch(
        remove=(
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ),
        add=_CLAUDE_5,
    ),
    # OpenAI deprecations page. GPT-6 tool calling needs the Responses API.
    "openai": ProviderPatch(
        remove=("o4-mini", "gpt-4.1-nano", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3"),
        add=_gpt6(**_RESPONSES),
    ),
    # gpt-5.5 is retired for ChatGPT sign-in; sol / luna are the documented replacements.
    # gpt-6.1-terra needs Codex CLI >= 0.159.0, so it is not offered here.
    "openai-codex": ProviderPatch(
        remove=("gpt-5.5",),
        add=(
            _m("gpt-6.1-sol", "GPT-6.1 Sol", enabled=True, inputs=("text",)),
            _m("gpt-6-luna", "GPT-6 Luna", enabled=True, inputs=("text",)),
        ),
    ),
    "gemini": ProviderPatch(
        remove=(
            "gemini-2.0-flash",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ),
        add=(
            _m(
                "gemini-4-carbon",
                "Gemini 4 Carbon",
                context=1_048_576,
                max_output=65_536,
                inputs=("text", "image", "audio", "video", "pdf"),
            ),
            _m(
                "gemini-4-argon",
                "Gemini 4 Argon",
                context=1_048_576,
                max_output=65_536,
                inputs=("text", "image", "audio", "video", "pdf"),
            ),
            _m("gemini-3.8-flash", "Gemini 3.8 Flash"),
            _m("gemini-3.6-flash", "Gemini 3.6 Flash"),
            _m("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
        ),
    ),
    # OpenRouter ids and limits come from its public /api/v1/models.
    "openrouter": ProviderPatch(
        remove=(
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash-preview",
            "deepseek/deepseek-chat-v3-0324",
            "openai/gpt-4.1",
        ),
        add=(
            _or(
                "anthropic/claude-fable-5.2",
                "Claude Fable 5.2",
                1_000_000,
                128_000,
                ("text", "image", "file"),
            ),
            _or(
                "anthropic/claude-opus-5.5",
                "Claude Opus 5.5",
                1_000_000,
                128_000,
                ("text", "image", "file"),
            ),
            _or(
                "anthropic/claude-sonnet-5.5",
                "Claude Sonnet 5.5",
                1_000_000,
                128_000,
                ("text", "image", "file"),
            ),
            _or("openai/gpt-6.1-sol", "GPT-6.1 Sol", 1_050_000, 128_000, ("text", "image", "file")),
            _or(
                "google/gemini-4-carbon",
                "Gemini 4 Carbon",
                1_048_576,
                943_718,
                ("text", "image", "audio", "video", "file"),
            ),
            _or("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", 1_048_576, 384_000, ("text",)),
            _or(
                "moonshotai/kimi-k3.1-pro",
                "Kimi K3.1 Pro",
                1_048_576,
                943_718,
                ("text", "image", "video"),
            ),
            _or("z-ai/glm-5.3", "GLM-5.3", 1_048_576, 943_718, ("text",)),
        ),
    ),
    "kimi-cn": ProviderPatch(remove=_KIMI_RETIRED, add=_KIMI_NEW),
    "kimi-intl": ProviderPatch(remove=_KIMI_RETIRED, add=_KIMI_NEW),
    "minimax-cn": ProviderPatch(remove=_MINIMAX_RETIRED, add=_MINIMAX_NEW),
    "minimax-intl": ProviderPatch(remove=_MINIMAX_RETIRED, add=_MINIMAX_NEW),
    "zhipu-cn": ProviderPatch(add=_ZHIPU_NEW),
    "zhipu-intl": ProviderPatch(add=_ZHIPU_NEW),
    # Not on the price list any more (not asserted as shut down).
    "dashscope": ProviderPatch(
        remove=_QWEN_RETIRED,
        add=(
            _m("qwen3.8-max", "Qwen3.8 Max", context=1_000_000),
            _m("qwen3.8-flash", "Qwen3.8 Flash", context=1_000_000),
            _m("qwen3.7-max", "Qwen3.7 Max", context=1_000_000),
            _m("qwen3.7-flash", "Qwen3.7 Flash", context=1_000_000),
        ),
    ),
    "dashscope-intl": ProviderPatch(
        remove=(*_QWEN_RETIRED, "deepseek-v3.2"),
        add=(
            _m("qwen3.8-max", "Qwen3.8 Max", context=1_000_000),
            _m("qwen3.8-flash", "Qwen3.8 Flash", context=1_000_000),
            _m("qwen3.7-plus", "Qwen3.7 Plus", context=1_000_000),
            _m("qwen3.7-max", "Qwen3.7 Max", context=1_000_000),
            _m("qwen3.7-flash", "Qwen3.7 Flash", context=1_000_000),
        ),
    ),
    "volcengine-cn": ProviderPatch(
        remove=(
            "doubao-seed-code-preview-251028",
            "glm-4-7-251222",
            "deepseek-v3-2-251201",
            "doubao-seed-1-8-251228",
            "doubao-seed-2-0-pro-260215",  # listed as "going offline soon"
            "doubao-seed-2-0-code-preview-260215",  # same
        ),
        add=_DOUBAO_NEW,
        update={
            "doubao-seed-2-0-lite-260428": _DOUBAO_20_LIMITS,
            "doubao-seed-2-0-mini-260428": _DOUBAO_20_LIMITS,
        },
    ),
    "opencode-zen-openai": ProviderPatch(
        remove=("deepseek-v4-flash", "deepseek-v4-flash-free"),
        add=(
            _m("deepseek-v4.1-flash", "DeepSeek V4.1 Flash"),
            _m("deepseek-v4.1-flash-free", "DeepSeek V4.1 Flash Free"),
            _m("glm-5.3", "GLM-5.3"),
            _m("glm-5.3-flash", "GLM-5.3 Flash"),
        ),
    ),
    "opencode-zen-anthropic": ProviderPatch(
        remove=("qwen3.7-max", "qwen3.7-plus"),
        add=(
            _m("claude-fable-5-2", "Claude Fable 5.2"),
            _m("claude-opus-5-5", "Claude Opus 5.5"),
            _m("claude-sonnet-5-5", "Claude Sonnet 5.5"),
            _m("claude-haiku-5-5", "Claude Haiku 5.5"),
            _m("qwen3.8-max", "Qwen3.8 Max"),
            _m("qwen3.8-flash", "Qwen3.8 Flash"),
        ),
    ),
    "opencode-go-openai": ProviderPatch(
        remove=(
            "grok-4.5",
            "glm-5.1",
            "kimi-k2.6",
            "deepseek-v4-flash",
            "mimo-v2.5",
            "mimo-v2.5-pro",
        ),
        add=(
            _m("deepseek-v4.1-flash", "DeepSeek V4.1 Flash"),
            _m("glm-5.3", "GLM-5.3"),
            _m("glm-5.3-flash", "GLM-5.3 Flash"),
            _m("kimi-k3.1-pro", "Kimi K3.1 Pro"),
            _m("grok-4.7", "Grok 4.7"),
            _m("mimo-v2.6-pro", "MiMo V2.6 Pro"),
            _m("mimo-v2.6-flash", "MiMo V2.6 Flash"),
        ),
    ),
    "opencode-go-anthropic": ProviderPatch(
        remove=("minimax-m2.7", "minimax-m2.5", "qwen3.7-max", "qwen3.6-plus"),
        add=(
            _m("minimax-m3.1-flash", "MiniMax M3.1 Flash"),
            _m("qwen3.8-max", "Qwen3.8 Max"),
            _m("qwen3.8-flash", "Qwen3.8 Flash"),
        ),
    ),
    "modelscope": ProviderPatch(
        remove=("ZhipuAI/GLM-5",),
        add=(
            _m("moonshotai/Kimi-K3.1-Pro", "Kimi-K3.1-Pro"),
            _m("MiniMax/MiniMax-M3", "MiniMax-M3"),
            _m("deepseek-ai/DeepSeek-V4.1-Flash", "DeepSeek-V4.1-Flash"),
            _m("Qwen/Qwen3.8-27B", "Qwen3.8-27B"),
            _m("ZhipuAI/GLM-5.2", "GLM-5.2"),
        ),
    ),
    # siliconflow.cn/models, checked 2026-11-11 (context lengths from the page data).
    "siliconflow-cn": ProviderPatch(
        remove=(
            "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "moonshotai/Kimi-K2-Instruct",
            "Pro/zai-org/GLM-4.7",
        ),
        add=(
            _m(
                "deepseek-ai/DeepSeek-V4.1-Flash",
                "DeepSeek V4.1 Flash",
                context=1_048_576,
                inputs=_TI,
            ),
            _m("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", context=1_048_576),
            _m("deepseek-ai/DeepSeek-V4-Flash", "DeepSeek V4 Flash", context=1_048_576),
            _m("zai-org/GLM-5.3", "GLM-5.3", context=1_048_576),
            _m("zai-org/GLM-5.3-Flash", "GLM-5.3 Flash", context=1_048_576, inputs=_TI),
            _m("zai-org/GLM-5.2", "GLM-5.2", context=1_048_576),
            _m("Pro/moonshotai/Kimi-K2.6", "Kimi K2.6", context=262_144, inputs=_TI),
            _m("moonshotai/Kimi-K2.7-Code", "Kimi K2.7 Code", context=262_144, inputs=_TI),
            _m("Qwen/Qwen3.8-27B", "Qwen3.8 27B", context=262_144, inputs=_TI),
            _m("Qwen/Qwen3.6-35B-A3B", "Qwen3.6 35B A3B", context=262_144, inputs=_TI),
            _m("meituan-longcat/LongCat-2.0", "LongCat 2.0", context=1_048_576),
            _m("tencent/Hy4-preview", "Hy4 Preview", context=1_048_576),
        ),
        # The page lists V3.2 and R1 at 163,840 tokens; the bundled rows say 65,536.
        update={
            "deepseek-ai/DeepSeek-V3.2": {"context_window": 163_840, "max_input_tokens": 163_840},
            "deepseek-ai/DeepSeek-R1": {"context_window": 163_840, "max_input_tokens": 163_840},
        },
    ),
    # mimo.mi.com model list (updated 2026-10-19): v2.5 went offline on 2026-10-21; v2 is not listed.
    # "mimo-v2.6-pro-ultraspeed" is custom service ("contact us"), so it is not offered.
    "mimo": ProviderPatch(
        remove=("mimo-v2.5", "mimo-v2.5-pro", "mimo-v2-flash", "mimo-v2-pro"),
        add=(
            _m(
                "mimo-v2.6-pro",
                "MiMo V2.6 Pro",
                context=1_048_576,
                max_output=131_072,
                inputs=("text", "image", "audio", "video"),
            ),
            _m(
                "mimo-v2.6-flash",
                "MiMo V2.6 Flash",
                context=1_048_576,
                max_output=131_072,
                inputs=("text", "image", "audio", "video"),
            ),
        ),
    ),
    # Model ids are the platform's service ids; list from the public model-square API.
    # GLM-5 (xopglm5) is kept: the square still lists it, although its serverStatus differs (0, not 3).
    "iflytek-astron-token-plan": ProviderPatch(
        remove=("xopdeepseekv4pro", "xopqwen35v35b"),
        add=(
            _m("spark-x2.6", "Spark-X2.6", context=1_048_576),
            _m("spark-x2.6-4b", "Spark-X2.6-4B", context=1_048_576),
            _m("xopglm53", "GLM-5.3", context=1_048_576),
            _m("xopdeepseekv4pro0813", "DeepSeek-V4-Pro-0813", context=1_048_576),
            _m("xopdeepseekv4flash0731", "DeepSeek-V4-Flash-0731", context=1_048_576),
            _m("xopkimik27code", "Kimi-K2.7-Code", context=262_144, inputs=_TI),
        ),
        update={"xopglm52": {"context_window": 1_048_576, "max_input_tokens": 1_048_576}},
    ),
    # Local models are never removed; popular current ones are appended.
    "ollama": ProviderPatch(
        add=(_m("qwen3", "qwen3"), _m("gpt-oss", "gpt-oss"), _m("gemma4", "gemma4")),
    ),
}


def apply_fork_presets(presets: list[dict[str, Any]]) -> None:
    """Patch *presets* in place (see module docstring for the merge rules)."""
    for preset in presets:
        patch = PATCHES.get(str(preset.get("id") or ""))
        if patch is None:
            continue
        models: list[dict[str, Any]] = list(preset.get("models") or [])
        removed = set(patch.remove)
        models = [m for m in models if m.get("id") not in removed]
        for model in models:
            fix = patch.update.get(str(model.get("id")))
            if fix:
                model.update(fix)
        present = {m.get("id") for m in models}
        fresh = [dict(m) for m in patch.add if m["id"] not in present]
        preset["models"] = [*fresh, *models]


_ANTHROPIC_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
_CLAUDE_5_DEFAULT_EFFORT = {
    "claude-fable-5-2": "high",
    "claude-opus-5-5": "medium",
    "claude-sonnet-5-5": "high",
    "claude-haiku-5-5": "medium",
}
_GPT6_CANNOT_DISABLE = {"gpt-6-astra", "gpt-6.1-sol"}
# model -> (efforts, default effort); thinking page of the Gemini API docs.
_GEMINI_THINKING: dict[str, tuple[list[str], str]] = {
    "gemini-4-carbon": (["low", "medium", "high"], "medium"),
    "gemini-4-argon": (["low", "medium", "high"], "medium"),
    "gemini-3.8-flash": (["low", "medium", "high"], "medium"),
    "gemini-3.6-flash": (["minimal", "low", "medium", "high"], "medium"),
    "gemini-3.5-flash-lite": (["minimal", "low", "medium", "high"], "minimal"),
}


def fork_reasoning_profile(provider_id: str, model_id: str) -> dict[str, Any] | None:
    """Reasoning metadata for the model families added by this overlay."""
    provider = provider_id.lower()
    model = model_id.lower()

    if provider in {"anthropic", "opencode-zen-anthropic"} and model in _CLAUDE_5_DEFAULT_EFFORT:
        # Claude 5 always runs adaptive thinking; the vendor's "off" is not a request switch.
        return {
            "supported": True,
            "adapter": "anthropic_adaptive",
            "toggle": False,
            "default_mode": "enabled",
            "efforts": list(_ANTHROPIC_EFFORTS),
            "default_effort": _CLAUDE_5_DEFAULT_EFFORT[model],
        }

    if provider in {"openai", "openai-codex"} and model.startswith("gpt-6"):
        can_disable = model not in _GPT6_CANNOT_DISABLE
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": can_disable,
            "default_mode": "auto" if can_disable else "enabled",
            "efforts": ["low", "medium", "high", "xhigh", "max"],
            "default_effort": "medium",
        }

    if provider == "mimo" and model in {"mimo-v2.6-pro", "mimo-v2.6-flash"}:
        # Request field ``thinking.type`` = enabled | disabled, on by default (MiMo "deep thinking" doc).
        return {
            "supported": True,
            "adapter": "thinking",
            "toggle": True,
            "default_mode": "enabled",
        }

    if provider == "gemini" and model in _GEMINI_THINKING:
        efforts, default = _GEMINI_THINKING[model]
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": False,
            "default_mode": "enabled",
            "efforts": efforts,
            "default_effort": default,
        }

    return None

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

``siliconflow-intl`` follows www.siliconflow.com/models (cards with context and max output; the
API ids come from each model's detail page). Its catalog differs from the cn site.

Tencent TokenHub, Coding Plan, Token Plan (personal) and Hy Token Plan follow the TokenHub docs:
the model list and price pages (cloud.tencent.com/document/product/1823/130051, 130055), the Coding
Plan overview (130092), and the Token Plan personal overview (130060), all read 2026-11-11.

Token Plan enterprise follows the professional plan page (130659) and its overview (131172). ``tencent-hai`` is not covered:
no document for api.model.haihub.cn was found.

Zhipu Coding Plan (docs.bigmodel.cn / docs.z.ai), Aliyun Coding Plan and Token Plan (help.aliyun.com,
alibabacloud.com) and Volcengine Coding Plan / Agent Plan (docs.volcengine.com/docs/ark) follow each
plan's own "supported models" page, read 2026-11-11. These plans only accept the models they list.

Second pass (an independent audit, checked against the pages again): Groq, Codex, gpt-5.2, dashscope-us,
Kimi Coding Plan (www.kimi.com/code/docs/kimi-code/models.html), reasoning switches for GLM-5.3, Kimi K3,
MiniMax M3, Doubao and OpenRouter's Claude 5, plus missing limits and input modalities.

Not covered on purpose: every other "plan" preset (Coding / Token / Agent Plan, Kimi Coding Plan, Tencent HAI), ``dashscope-us``.
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
_KIMI_K3_VISION: dict[str, dict[str, Any]] = {"kimi-k3": {"input": ["text", "image"]}}
# MiniMax text API: M3.1-Flash and M3 accept text, image and video input (no audio).
_MINIMAX_VISION: dict[str, dict[str, Any]] = {
    "MiniMax-M3.1-Flash": {"input": ["text", "image", "video"]},
    "MiniMax-M3": {"input": ["text", "image", "video"]},
}
_MINIMAX_RETIRED = (
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
)
_TIV = ("text", "image", "video")
_GEMINI_IN = ("text", "image", "video", "audio", "pdf")
_MINIMAX_NEW = (
    _m("MiniMax-M3.1-Flash", "MiniMax M3.1 Flash", context=1_000_000, inputs=_TIV),
    _m("MiniMax-M3", "MiniMax M3", context=1_000_000, inputs=_TIV),
)
_ZHIPU_NEW = (
    _m("glm-5.3", "GLM-5.3", context=1_000_000, max_output=128 * _K),
    _m("glm-5.3-flash", "GLM-5.3 Flash", context=1_000_000, max_output=128 * _K, inputs=_TIV),
    _m("glm-5.3-flashx", "GLM-5.3 FlashX", context=1_000_000, max_output=128 * _K, inputs=_TIV),
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
_DOUBAO_20_LIMITS: dict[str, Any] = {
    "context_window": 256 * _K,
    "max_input_tokens": 224 * _K,
    "max_output_tokens": 128 * _K,
    "input": ["text", "image"],  # "multimodal understanding" on the model list
}
# Third-party rows on the Ark model list (www.volcengine.com/docs/82379/1330310); "1024K" = 1,048,576.
_VOLC_THIRD_PARTY = (
    _m(
        "glm-5-3-flash-260828",
        "GLM-5.3-Flash 260828",
        context=1024 * _K,
        max_output=128 * _K,
        inputs=_TI,
    ),
    _m("glm-5-2-260617", "GLM-5.2 260617", context=1024 * _K, max_output=128 * _K),
    _m(
        "kimi-k3-1-pro-261024",
        "Kimi-K3.1-Pro 261024",
        context=1024 * _K,
        max_output=1024 * _K,
        inputs=_TI,
    ),
    _m(
        "deepseek-v4-1-flash-261017",
        "DeepSeek-V4.1-Flash 261017",
        context=1024 * _K,
        max_output=384 * _K,
        inputs=_TI,
    ),
    _m(
        "deepseek-v4-1-flash-economy-261017",
        "DeepSeek-V4.1-Flash-Economy 261017",
        context=1024 * _K,
        max_output=384 * _K,
        inputs=_TI,
    ),
    _m(
        "deepseek-v4-pro-ga-260813",
        "DeepSeek-V4-Pro GA 260813",
        context=1024 * _K,
        max_output=384 * _K,
    ),
    _m(
        "deepseek-v4-flash-ga-260731",
        "DeepSeek-V4-Flash GA 260731",
        context=1024 * _K,
        max_output=384 * _K,
    ),
)

_ZHIPU_PLAN_NEW = (
    _m("glm-5.3", "GLM-5.3", context=1_000_000, max_output=131_072),
    _m("glm-5.3-flash", "GLM-5.3 Flash", context=1_000_000, max_output=131_072, inputs=_TI),
)
_ALIYUN_CODING_RETIRED = ("glm-4.7", "qwen3-max-2026-01-23", "qwen3-coder-next", "qwen3-coder-plus")
_ALIYUN_CODING_VISION: dict[str, dict[str, Any]] = {
    "qwen3.7-plus": {"input": ["text", "image"]},
    "qwen3.6-plus": {"input": ["text", "image"]},
    "kimi-k2.5": {"input": ["text", "image"]},
}
_ALIYUN_TOKEN_RETIRED = ("qwen3.6-plus", "glm-5", "MiniMax-M2.5", "deepseek-v3.2", "kimi-k2.5")
_ALIYUN_TOKEN_NEW = (
    _m("auto", "Auto"),
    _m("qwen3.8-max", "Qwen3.8 Max", context=1_000_000, inputs=_TI),
    _m("qwen3.8-flash", "Qwen3.8 Flash", context=1_000_000, inputs=_TI),
    _m("qwen3.7-max", "Qwen3.7 Max", context=1_000_000),
    _m("qwen3.7-plus", "Qwen3.7 Plus", context=1_000_000, max_output=65_536, inputs=_TI),
    _m("qwen3.6-flash", "Qwen3.6 Flash", inputs=_TI),
    _m("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", inputs=_TI),
    _m("deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash 1017", inputs=_TI),
    _m("deepseek-v4-pro-0813", "DeepSeek V4 Pro 0813"),
    _m("deepseek-v4-pro", "DeepSeek V4 Pro"),
    _m("deepseek-v4-flash-0731", "DeepSeek V4 Flash 0731"),
    _m("glm-5.3", "GLM-5.3"),
    _m("glm-5.2", "GLM-5.2"),
)
_ARK_1M = 1024 * _K
# Models both Ark plans list; limits from the Agent Plan page ("1024K" = 1,048,576).
_ARK_PLAN_NEW_ONLY = (
    _m(
        "doubao-seed-2.1-pro",
        "Doubao Seed 2.1 Pro",
        context=_ARK_1M,
        max_output=256 * _K,
        inputs=_TI,
    ),
    _m(
        "doubao-seed-2.1-lite",
        "Doubao Seed 2.1 Lite",
        context=_ARK_1M,
        max_output=256 * _K,
        inputs=_TI,
    ),
    _m("kimi-k2.8-preview", "Kimi K2.8 Preview", context=_ARK_1M, max_output=_ARK_1M, inputs=_TI),
    _m("kimi-k3.1-pro", "Kimi K3.1 Pro", context=_ARK_1M, max_output=_ARK_1M, inputs=_TI),
    _m(
        "deepseek-v4.1-flash",
        "DeepSeek V4.1 Flash",
        context=_ARK_1M,
        max_output=384 * _K,
        inputs=_TI,
    ),
    _m(
        "deepseek-v4.1-flash-economy",
        "DeepSeek V4.1 Flash Economy",
        context=_ARK_1M,
        max_output=384 * _K,
        inputs=_TI,
    ),
)
_ARK_PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "doubao-seed-evolving": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 256 * _K,
    },
    "glm-5.3": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 128 * _K,
    },
    "glm-latest": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 128 * _K,
    },
    "glm-5.3-flash": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 128 * _K,
    },
    "deepseek-v4-flash": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 384 * _K,
    },
    "deepseek-v4-pro": {
        "context_window": _ARK_1M,
        "max_input_tokens": _ARK_1M,
        "max_output_tokens": 384 * _K,
    },
    "doubao-seed-2.0-mini": {
        "context_window": 256 * _K,
        "max_input_tokens": 256 * _K,
        "max_output_tokens": 128 * _K,
    },
}
_ARK_PLAN_MODELS = (
    _m(
        "doubao-seed-evolving",
        "Doubao Seed Evolving",
        context=_ARK_1M,
        max_output=256 * _K,
        inputs=_TI,
    ),
    *_ARK_PLAN_NEW_ONLY[:2],
    _m(
        "doubao-seed-2.0-mini",
        "Doubao Seed 2.0 Mini",
        context=256 * _K,
        max_output=128 * _K,
        inputs=_TI,
    ),
    _m("glm-5.3", "GLM 5.3", context=_ARK_1M, max_output=128 * _K),
    _m("glm-5.3-flash", "GLM 5.3 Flash", context=_ARK_1M, max_output=128 * _K, inputs=_TI),
    *_ARK_PLAN_NEW_ONLY[4:],
    _m("deepseek-v4-flash", "DeepSeek V4 Flash", context=_ARK_1M, max_output=384 * _K),
    _m("deepseek-v4-pro", "DeepSeek V4 Pro", context=_ARK_1M, max_output=384 * _K),
    *_ARK_PLAN_NEW_ONLY[2:4],
)
_ARK_CODING_ONLY = (_m("kimi-k3", "Kimi K3", context=_ARK_1M, max_output=128 * _K, inputs=_TI),)

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
        remove=(
            "o4-mini",
            "gpt-4.1-nano",
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "o3",
            # Deprecated by OpenAI, shutting down 2027-01-14 (removed at the user's request).
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "gpt-4o-mini",
        ),
        add=_gpt6(**_RESPONSES),
        # Model page: 400,000 context window, 128,000 max output tokens.
        update={
            "gpt-5.2": {
                "context_window": 400_000,
                "max_input_tokens": 400_000,
                "max_output_tokens": 128_000,
            }
        },
    ),
    # gpt-5.5 is retired for ChatGPT sign-in; sol / luna are the documented replacements.
    # gpt-6.1-terra needs Codex CLI >= 0.159.0, so it is not offered here.
    "openai-codex": ProviderPatch(
        # gpt-5.4 and gpt-5.4-mini retired from Codex with ChatGPT sign-in on 2026-08-31.
        remove=("gpt-5.5", "gpt-5.4", "gpt-5.4-mini"),
        add=(
            _m("gpt-6-astra", "GPT-6 Astra", enabled=True, inputs=("text",)),
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
            _m(
                "gemini-3.8-flash",
                "Gemini 3.8 Flash",
                context=1_048_576,
                max_output=65_536,
                inputs=_GEMINI_IN,
            ),
            _m(
                "gemini-3.6-flash",
                "Gemini 3.6 Flash",
                context=1_048_576,
                max_output=65_536,
                inputs=_GEMINI_IN,
            ),
            _m(
                "gemini-3.5-flash-lite",
                "Gemini 3.5 Flash-Lite",
                context=1_048_576,
                max_output=65_536,
                inputs=_GEMINI_IN,
            ),
        ),
        # Model pages: output token limit 65,536.
        update={
            "gemini-3.1-pro-preview": {"max_output_tokens": 65_536},
            "gemini-2.5-flash-lite": {"max_output_tokens": 65_536},
        },
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
    "kimi-cn": ProviderPatch(remove=_KIMI_RETIRED, add=_KIMI_NEW, update=_KIMI_K3_VISION),
    "kimi-intl": ProviderPatch(remove=_KIMI_RETIRED, add=_KIMI_NEW, update=_KIMI_K3_VISION),
    "minimax-cn": ProviderPatch(remove=_MINIMAX_RETIRED, add=_MINIMAX_NEW, update=_MINIMAX_VISION),
    "minimax-intl": ProviderPatch(
        remove=_MINIMAX_RETIRED, add=_MINIMAX_NEW, update=_MINIMAX_VISION
    ),
    "zhipu-cn": ProviderPatch(add=_ZHIPU_NEW),
    "zhipu-intl": ProviderPatch(add=_ZHIPU_NEW),
    # Not on the price list any more (not asserted as shut down).
    "dashscope": ProviderPatch(
        remove=(*_QWEN_RETIRED, "deepseek-v3.2"),
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
        add=(*_DOUBAO_NEW, *_VOLC_THIRD_PARTY),
        update={
            "doubao-seed-2-0-lite-260428": _DOUBAO_20_LIMITS,
            "doubao-seed-2-0-mini-260428": _DOUBAO_20_LIMITS,
            # Model list: context 128K, max input 96K, max output 32K.
            "doubao-seed-character-251128": {
                "max_input_tokens": 96 * _K,
                "max_output_tokens": 32 * _K,
            },
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
    # www.siliconflow.com/models, checked 2026-11-11. "1049K" on the page is 1,048,576 tokens, etc.
    "siliconflow-intl": ProviderPatch(
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
                max_output=393_216,
                inputs=_TI,
            ),
            _m(
                "deepseek-ai/DeepSeek-V4-Pro-0813",
                "DeepSeek V4 Pro 0813",
                context=1_048_576,
                max_output=393_216,
            ),
            _m(
                "deepseek-ai/DeepSeek-V4-Flash-0731",
                "DeepSeek V4 Flash 0731",
                context=1_048_576,
                max_output=393_216,
            ),
            _m("zai-org/GLM-5.3", "GLM-5.3", context=1_048_576, max_output=262_144),
            _m(
                "zai-org/GLM-5.3-Flash",
                "GLM-5.3 Flash",
                context=1_048_576,
                max_output=262_144,
                inputs=_TI,
            ),
            _m("zai-org/GLM-5.2", "GLM-5.2", context=1_048_576, max_output=262_144),
            _m("moonshotai/Kimi-K3", "Kimi K3", context=1_048_576, max_output=262_144, inputs=_TI),
            _m(
                "moonshotai/Kimi-K2.6", "Kimi K2.6", context=262_144, max_output=262_144, inputs=_TI
            ),
            _m(
                "moonshotai/Kimi-K2.7-Code",
                "Kimi K2.7 Code",
                context=262_144,
                max_output=262_144,
                inputs=_TI,
            ),
            _m(
                "MiniMaxAI/MiniMax-M3",
                "MiniMax M3",
                context=1_048_576,
                max_output=131_072,
                inputs=_TI,
            ),
            _m(
                "Qwen/Qwen3.8-2.4T-A95B", "Qwen3.8 2.4T A95B", context=1_048_576, max_output=131_072
            ),
            _m(
                "Qwen/Qwen3.6-35B-A3B",
                "Qwen3.6 35B A3B",
                context=262_144,
                max_output=262_144,
                inputs=_TI,
            ),
            _m("meituan-longcat/LongCat-2.0", "LongCat 2.0", context=1_048_576, max_output=131_072),
            _m("tencent/Hy4-preview", "Hy4 Preview", context=1_048_576, max_output=262_144),
        ),
        update={
            "deepseek-ai/DeepSeek-V3.2": {
                "context_window": 163_840,
                "max_input_tokens": 163_840,
                "max_output_tokens": 163_840,
            },
            "deepseek-ai/DeepSeek-R1": {
                "context_window": 163_840,
                "max_input_tokens": 163_840,
                "max_output_tokens": 163_840,
            },
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
    # TokenHub pay-as-you-go: language models from the TokenHub model list (updated 2026-11-09).
    # Retiring or preview-only entries (glm-5v-turbo, minimax-m2.7, kimi-k2.8-preview, step-5-preview,
    # translation / role-play models) are not offered. "1M" is 1,000,000 here, like the plan presets.
    "tencent-tokenhub": ProviderPatch(
        add=(
            _m(
                "hy4-preview",
                "Hy4 Preview",
                context=1_000_000,
                max_input=960_000,
                max_output=64_000,
            ),
            _m("hy3", "Hy3", context=256_000, max_input=192_000, max_output=128_000),
            _m(
                "deepseek-v4.1-flash",
                "DeepSeek-V4.1-Flash",
                context=1_000_000,
                max_output=384_000,
                inputs=_TI,
            ),
            _m(
                "deepseek-v4-pro-0813",
                "DeepSeek-V4-Pro 0813",
                context=1_000_000,
                max_output=384_000,
            ),
            _m("glm-5.3", "GLM-5.3", context=1_000_000, max_output=131_072),
            _m("glm-5.3-flash", "GLM-5.3-Flash", context=1_000_000, max_output=131_072, inputs=_TI),
            _m(
                "glm-5.3-flashx",
                "GLM-5.3-FlashX",
                context=1_000_000,
                max_output=131_072,
                inputs=_TI,
            ),
            _m("glm-5.2", "GLM-5.2", context=1_000_000, max_output=131_072),
            _m(
                "kimi-k3.1-pro",
                "Kimi K3.1 Pro",
                context=1_000_000,
                max_output=1_000_000,
                inputs=_TI,
            ),
            _m(
                "kimi-k3.1-pro-highspeed",
                "Kimi K3.1 Pro HighSpeed",
                context=1_000_000,
                max_output=1_000_000,
                inputs=_TI,
            ),
            _m("kimi-k3", "Kimi K3", context=1_000_000, max_output=1_000_000, inputs=_TI),
            _m("kimi-k2.7-code", "Kimi K2.7 Code", context=262_144, max_output=262_144, inputs=_TI),
            _m("kimi-k2.6", "Kimi-K2.6", context=262_144, max_output=262_144, inputs=_TI),
            _m(
                "minimax-m3.1-flash",
                "MiniMax-M3.1-Flash",
                context=1_000_000,
                max_output=524_288,
                inputs=_TI,
            ),
            _m("minimax-m3", "MiniMax-M3", context=1_000_000, inputs=_TI),
            _m("mimo-v2.6-pro", "MiMo-V2.6-Pro", context=1_000_000, max_output=131_072, inputs=_TI),
            _m(
                "mimo-v2.6-flash",
                "MiMo-V2.6-Flash",
                context=1_000_000,
                max_output=131_072,
                inputs=_TI,
            ),
        ),
    ),
    # Coding Plan overview (updated 2026-10-15): the plan's model list is just "Auto" (tc-code-latest).
    # The FAQ page (2026-06-22) still lists minimax-m2.5 / kimi-k2.5 / glm-5; the newer overview wins.
    "tencent-coding-plan": ProviderPatch(remove=("minimax-m2.5", "kimi-k2.5", "glm-5")),
    # Token Plan personal overview (updated 2026-11-04), general plan. No image input is claimed: the Hy plan
    # and Coding Plan pages say their models have no multimodal support, and this one does not say otherwise. MiniMax-M2.7 goes offline on 11-17.
    # Base URL there is now https://tokenhub.tencentmaas.com/plan/v3 (the bundled row still has lkeap).
    "tencent-token-plan": ProviderPatch(
        remove=("glm-5", "glm-5.1", "minimax-m2.7"),
        add=(
            _m(
                "deepseek-v4.1-flash-1017",
                "DeepSeek-V4.1-Flash-1017",
                context=1_000_000,
                max_output=384_000,
            ),
            _m(
                "deepseek-v4-pro-0813",
                "DeepSeek-V4-Pro 0813",
                context=1_000_000,
                max_output=384_000,
            ),
            _m(
                "deepseek/deepseek-flash",
                "DeepSeek-V4.1-Flash-1017 Direct",
                context=1_000_000,
                max_output=384_000,
            ),
            _m(
                "hy4-preview",
                "Hy4 Preview",
                context=1_000_000,
                max_input=960_000,
                max_output=64_000,
            ),
            _m("minimax-m3", "MiniMax-M3", context=1_000_000),
            _m("glm-5.3", "GLM-5.3", context=1_000_000, max_output=131_072),
            _m("glm-5.3-flash", "GLM-5.3-Flash", context=1_000_000, max_output=131_072),
            _m("kimi-k2.7-code", "Kimi K2.7 Code", context=262_144, max_output=262_144),
            _m("kimi-k3", "Kimi K3", context=1_000_000, max_output=1_000_000),
            _m(
                "mimo-v2.6-flash",
                "MiMo-V2.6-Flash",
                context=1_000_000,
                max_output=131_072,
            ),
        ),
    ),
    # Hy Token Plan: Hy4, Hy4 preview, Hy3 (same overview page). hy3 limits per the model list.
    "tencent-hy-token-plan": ProviderPatch(
        remove=("hy3-preview",),
        add=(
            _m(
                "hy4-preview",
                "Hy4 Preview",
                context=1_000_000,
                max_input=960_000,
                max_output=64_000,
            ),
        ),
        update={
            "hy3": {
                "context_window": 256_000,
                "max_input_tokens": 192_000,
                "max_output_tokens": 128_000,
            }
        },
    ),
    # Token Plan enterprise, professional plan page (updated 2026-11-04), Guangzhou list (the bundled
    # base URL). The enterprise overview (131172, 2026-11-03) says the light plan only has Auto, so this
    # preset is the professional plan. No image input is claimed for the new rows.
    # The "deepseek/..." direct ids are not added: enterprise ids stay bare model names (upstream test).
    # Plain "deepseek-v4-flash" / "-0731" are only valid as "deepseek/..." aliases of the direct row.
    "tencent-token-plan-enterprise-cn": ProviderPatch(
        remove=(
            "deepseek-v4-flash",
            "deepseek-v4-flash-0731",
            "glm-5",
            "glm-5-turbo",
            "glm-5.1",
            "kimi-k2.5",
            "minimax-m2.5",
            "minimax-m2.7",
        ),
        add=(
            _m(
                "hy4-preview",
                "Hy4 Preview",
                context=1_000_000,
                max_input=960_000,
                max_output=64_000,
            ),
            _m("glm-5.3-flash", "GLM-5.3-Flash", context=1_000_000, max_output=131_072),
            _m("kimi-k3", "Kimi K3", context=1_000_000, max_output=1_000_000),
            _m(
                "deepseek-v4.1-flash-1017",
                "DeepSeek-V4.1-Flash-1017",
                context=1_000_000,
                max_output=384_000,
            ),
            _m(
                "deepseek-v4.1-flash",
                "DeepSeek-V4.1-Flash",
                context=1_000_000,
                max_output=384_000,
            ),
            _m("mimo-v2.6-pro", "MiMo-V2.6-Pro", context=1_000_000, max_output=131_072),
            _m(
                "mimo-v2.6-flash",
                "MiMo-V2.6-Flash",
                context=1_000_000,
                max_output=131_072,
            ),
        ),
    ),
    # Zhipu Coding Plan (cn: docs.bigmodel.cn/cn/coding-plan/overview, intl: docs.z.ai/devpack/overview):
    # "All plans support GLM-5.3 and GLM-5.3-Flash"; older ids are routed to these two.
    "zhipu-cn-codingplan": ProviderPatch(
        remove=("glm-4.7-flash", "glm-5", "glm-5.1", "glm-5.2", "glm-5-turbo", "glm-5v-turbo"),
        add=_ZHIPU_PLAN_NEW,
    ),
    "zhipu-intl-codingplan": ProviderPatch(
        remove=("glm-4.7-flash", "glm-5", "glm-5.1", "glm-5.2", "glm-5-turbo", "glm-5v-turbo"),
        add=_ZHIPU_PLAN_NEW,
    ),
    # Aliyun Coding Plan (legacy page, cn and intl identical): "only the following exact versions".
    "aliyun-codingplan-cn": ProviderPatch(
        remove=_ALIYUN_CODING_RETIRED, update=_ALIYUN_CODING_VISION
    ),
    "aliyun-codingplan-intl": ProviderPatch(
        remove=_ALIYUN_CODING_RETIRED, update=_ALIYUN_CODING_VISION
    ),
    # Aliyun Token Plan personal (cn updated by 2026-11, intl 2026-11-11, same list). qwen4-max-preview is
    # not offered: its preview ends 2026-11-25. Limits are only given where the standard model page has them.
    "aliyun-tokenplan": ProviderPatch(remove=_ALIYUN_TOKEN_RETIRED, add=_ALIYUN_TOKEN_NEW),
    "aliyun-tokenplan-intl": ProviderPatch(remove=_ALIYUN_TOKEN_RETIRED, add=_ALIYUN_TOKEN_NEW),
    # Volcengine Coding Plan (docs/ark/coding-plan-personal-get-started): the Model Names it accepts.
    # Lowercase names; the uppercase DeepSeek rows are replaced. Limits are those the Agent Plan page
    # gives for the same models (the Coding Plan page gives none).
    "volcengine-cn-codingplan": ProviderPatch(
        remove=(
            "doubao-seed-2.1-turbo",
            "glm-5.2",
            "minimax-m3",
            "minimax-m2.7",
            "kimi-k2.6",
            "DeepSeek-V4-Flash",
            "DeepSeek-V4-Pro",
            "doubao-seed-2-0-code-preview-260215",
            "doubao-seed-2-0-pro-260215",
            "doubao-seed-2-0-lite-260428",
            "doubao-seed-code-preview-251028",
        ),
        add=(*_ARK_PLAN_MODELS, *_ARK_CODING_ONLY),
    ),
    # Volcengine Agent Plan personal (docs/ark/agent-plan-personal-plan-overview, "supported models").
    # kimi-k3 is marked "going offline soon" there and is not offered.
    "volcengine-cn-agentplan": ProviderPatch(
        remove=(
            "doubao-seed-2.1-turbo",
            "doubao-seed-2.0-lite",
            "minimax-m3",
            "kimi-k2.7-code",
            "kimi-k3",
        ),
        add=_ARK_PLAN_NEW_ONLY,
        update=_ARK_PLAN_LIMITS,
    ),
    # Groq: llama-3.1-8b-instant and llama-3.3-70b-versatile were shut down for the free and developer
    # tiers on 2026-08-16 (console.groq.com/docs/deprecations; enterprise-only on the model list now).
    # Max completion tokens from the model list; qwen3.8-27b is the recommended replacement (preview).
    "groq": ProviderPatch(
        remove=("llama-3.1-8b-instant", "llama-3.3-70b-versatile"),
        add=(_m("qwen/qwen3.8-27b", "Qwen3.8 27B (preview)", context=131_072, max_output=16_384),),
        update={
            "openai/gpt-oss-120b": {"max_output_tokens": 65_536},
            "openai/gpt-oss-20b": {"max_output_tokens": 65_536},
        },
    ),
    # DashScope US (Virginia): the "US" section of help.aliyun.com/zh/model-studio/model-pricing. Only models
    # whose deployment scope is "US" are offered; the old three rows are not on that list.
    "dashscope-us": ProviderPatch(
        remove=("qwen3-max", "qwen3-235b-a22b-thinking-2507", "deepseek-v3.2"),
        add=(
            _m("qwen3.8-max", "Qwen3.8 Max", context=1_000_000),
            _m("qwen3.8-flash", "Qwen3.8 Flash", context=1_000_000),
            _m("qwen3.7-max", "Qwen3.7 Max", context=1_000_000),
            _m("qwen3.7-plus", "Qwen3.7 Plus", context=1_000_000),
            _m("qwen3.7-flash", "Qwen3.7 Flash", context=1_000_000),
            _m("qwen3.6-flash", "Qwen3.6 Flash", context=1_000_000),
            _m("deepseek-v4-pro", "DeepSeek V4 Pro"),
            _m("deepseek-v4-flash-0731", "DeepSeek V4 Flash 0731"),
            _m("kimi-k3.1-pro", "Kimi K3.1 Pro"),
            _m("glm-5.3", "GLM-5.3"),
            _m("glm-5.2", "GLM-5.2"),
        ),
    ),
    # Kimi Code: www.kimi.com/code/docs/kimi-code/models.html (6 models; "1M" = 1,048,576).
    "kimi-codingplan": ProviderPatch(
        add=(
            _m("k3.1-pro", "K3.1 Pro", context=1_048_576, inputs=_TIV),
            _m("k3.1-pro-highspeed", "K3.1 Pro Highspeed", context=1_048_576, inputs=_TIV),
        ),
        update={
            "k3": {
                "context_window": 1_048_576,
                "max_input_tokens": 1_048_576,
                "input": ["text", "image", "video"],
            },
            "k3-256k": {"input": ["text", "image"]},
            "kimi-for-coding": {
                "context_window": 1_048_576,
                "max_input_tokens": 1_048_576,
                "input": ["text", "image", "video"],
            },
            "kimi-for-coding-highspeed": {"input": ["text", "image", "video"]},
        },
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
_TENCENT_DEEPSEEK_V41 = {
    "deepseek-v4.1-flash",
    "deepseek-v4.1-flash-1017",
    "deepseek/deepseek-flash",
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


_KIMI_K3_IDS = {"kimi-k3", "kimi-k3.1-pro", "kimi-k3.1-pro-highspeed"}
_OPENROUTER_CLAUDE_5 = {
    "anthropic/claude-fable-5.2": "high",
    "anthropic/claude-opus-5.5": "medium",
    "anthropic/claude-sonnet-5.5": "high",
}


def _always_on_effort(efforts: list[str], default: str) -> dict[str, Any]:
    """Reasoning that cannot be switched off, with a reasoning_effort level."""
    return {
        "supported": True,
        "adapter": "openai_reasoning_effort",
        "toggle": False,
        "default_mode": "enabled",
        "efforts": efforts,
        "default_effort": default,
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

    if provider.startswith("tencent-") and model in _TENCENT_DEEPSEEK_V41:
        # Same request semantics as the deepseek-v4-* rows in presets.py, whose prefix match misses these ids.
        plan = provider in {"tencent-token-plan", "tencent-token-plan-enterprise-cn"}
        return {
            "supported": True,
            "adapter": "thinking_nested_effort" if plan else "thinking",
            "toggle": True,
            "default_mode": "enabled",
            "efforts": ["high", "max"],
            "default_effort": "high",
        }

    if provider.startswith("volcengine-cn-") and model in {"glm-5.3", "glm-latest"}:
        # Agent Plan page: glm-5.3 thinks by default and cannot be switched off.
        return {
            "supported": True,
            "adapter": "thinking",
            "toggle": False,
            "default_mode": "enabled",
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

    if provider in {"openai"} and model == "gpt-5.2":
        # Model page: reasoning.effort supports none (default), low, medium, high and xhigh.
        return {
            "supported": True,
            "adapter": "openai_reasoning_effort",
            "toggle": True,
            "default_mode": "auto",
            "efforts": ["low", "medium", "high", "xhigh"],
            "default_effort": "medium",
        }

    if provider.startswith("zhipu-") and model in {"glm-5.3", "glm-5.3-flash", "glm-5.3-flashx"}:
        # Zhipu docs: GLM-5.3 always thinks (thinking cannot be disabled); effort is low / high / max,
        # default max. The top-level reasoning_effort field is what the OpenAI-compatible endpoint maps.
        return _always_on_effort(["low", "high", "max"], "max")

    if provider in {"kimi-cn", "kimi-intl"} and model in _KIMI_K3_IDS:
        # platform.kimi.com "reasoning effort": K3.1 Pro always reasons; low / high / max, default max.
        return _always_on_effort(["low", "high", "max"], "max")

    if provider == "kimi-codingplan":
        # Kimi Code model page: K3.1 Pro series cannot turn thinking off (HTTP 400); K3 and K3-256k default
        # to high, kimi-for-coding (K2.8 Preview) to max; kimi-for-coding-highspeed has thinking on only.
        if model in {"k3.1-pro", "k3.1-pro-highspeed", "k3", "k3-256k"}:
            return _always_on_effort(["low", "high", "max"], "high")
        if model == "kimi-for-coding":
            return _always_on_effort(["low", "high", "max"], "max")
        if model == "kimi-for-coding-highspeed":
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }

    if provider.startswith("minimax-"):
        # MiniMax text API: M3.1-Flash forces thinking (disabled returns 400) and takes reasoning_effort
        # low..max, default max. M3 can skip thinking, but its only switch is thinking.type "disabled" /
        # "adaptive" (not "enabled"), which the generic thinking adapter cannot express, so no controls.
        if model == "minimax-m3.1-flash":
            return _always_on_effort(["low", "medium", "high", "xhigh", "max"], "max")
        if model == "minimax-m3":
            return {
                "supported": True,
                "adapter": "status_only",
                "toggle": False,
                "default_mode": "enabled",
            }

    if provider == "openrouter" and model in _OPENROUTER_CLAUDE_5:
        # Fable 5.2 and Opus 5.5 are "Adaptive (always on)"; Sonnet 5.5 does not accept thinking "disabled".
        return {
            "supported": True,
            "adapter": "openrouter",
            "toggle": False,
            "default_mode": "enabled",
            "efforts": ["low", "medium", "high"],
            "default_effort": _OPENROUTER_CLAUDE_5[model],
        }

    if (
        provider == "volcengine-cn"
        and model.startswith(("doubao-seed-", "deepseek-"))
        and "character" not in model
    ):
        # Ark model list: models tagged "deep thinking" think by default; thinking.type=disabled turns it off.
        return {
            "supported": True,
            "adapter": "thinking",
            "toggle": True,
            "default_mode": "auto",
        }

    return None

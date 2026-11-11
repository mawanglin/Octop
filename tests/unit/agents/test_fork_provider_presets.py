"""Fork overlay on bundled provider presets (model lists)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from octop.infra.agents.providers.fork_presets import (
    PATCHES,
    apply_fork_presets,
    fork_reasoning_profile,
)
from octop.infra.agents.providers.presets import load_provider_presets


def _by_id(presets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(p["id"]): p for p in presets}


def _ids(preset: dict[str, Any]) -> list[str]:
    return [str(m["id"]) for m in preset["models"]]


def test_every_patch_is_self_consistent() -> None:
    for provider, patch in PATCHES.items():
        added = [m["id"] for m in patch.add]
        assert len(added) == len(set(added)), provider
        assert not set(added) & set(patch.remove), provider
        for row in patch.add:
            assert row["name"], (provider, row["id"])
            ctx, max_in = row.get("context_window"), row.get("max_input_tokens")
            if ctx is not None:
                assert max_in is not None and 0 < max_in <= ctx, (provider, row["id"])


def test_patches_target_known_providers() -> None:
    known = _by_id(load_provider_presets())
    assert set(PATCHES) <= set(known)


def test_loaded_presets_have_new_models_first_and_no_retired_ones() -> None:
    presets = _by_id(load_provider_presets())
    for provider, patch in PATCHES.items():
        ids = _ids(presets[provider])
        assert len(ids) == len(set(ids)), provider
        assert not set(patch.remove) & set(ids), provider
        assert ids[: len(patch.add)] == [m["id"] for m in patch.add], provider


def test_apply_is_idempotent() -> None:
    once = load_provider_presets()
    twice = copy.deepcopy(once)
    apply_fork_presets(twice)
    assert twice == once


def test_existing_model_is_not_duplicated_and_keeps_upstream_row() -> None:
    presets = [{"id": "ollama", "models": [{"id": "qwen3", "name": "upstream"}]}]
    apply_fork_presets(presets)
    rows = [m for m in presets[0]["models"] if m["id"] == "qwen3"]
    assert rows == [{"id": "qwen3", "name": "upstream"}]


def test_unknown_provider_and_missing_ids_are_ignored() -> None:
    presets: list[dict[str, Any]] = [
        {"id": "not-a-provider", "models": [{"id": "x"}]},
        {"id": "anthropic", "models": []},
    ]
    apply_fork_presets(presets)
    assert presets[0]["models"] == [{"id": "x"}]
    assert _ids(presets[1])[0] == "claude-fable-5-2"


def test_update_corrects_doubao_limits() -> None:
    volc = _by_id(load_provider_presets())["volcengine-cn"]
    row = next(m for m in volc["models"] if m["id"] == "doubao-seed-2-0-lite-260428")
    assert (row["context_window"], row["max_input_tokens"], row["max_output_tokens"]) == (
        262144,
        229376,
        131072,
    )


def test_gpt6_uses_responses_api_and_reasoning_profile() -> None:
    openai = _by_id(load_provider_presets())["openai"]
    rows = {m["id"]: m for m in openai["models"]}
    for mid in ("gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"):
        assert rows[mid]["api_mode"] == "responses"
        assert rows[mid]["reasoning"] is True
        assert rows[mid]["reasoning_config"]["adapter"] == "openai_reasoning_effort"
    assert rows["gpt-6.1-sol"]["reasoning_config"]["toggle"] is False
    assert rows["gpt-6-luna"]["reasoning_config"]["toggle"] is True
    assert "gpt-5.2" in rows  # still offered


def test_codex_preset_swaps_retired_model() -> None:
    codex = _by_id(load_provider_presets())["openai-codex"]
    ids = _ids(codex)
    assert "gpt-5.5" not in ids
    assert {"gpt-6.1-sol", "gpt-6-luna", "gpt-5.4"} <= set(ids)


@pytest.mark.parametrize("model", ["claude-fable-5-2", "claude-opus-5-5", "claude-haiku-5-5"])
def test_claude5_profile_is_adaptive(model: str) -> None:
    profile = fork_reasoning_profile("anthropic", model)
    assert profile is not None
    assert profile["adapter"] == "anthropic_adaptive"
    assert "xhigh" in profile["efforts"]
    assert profile["default_effort"] in profile["efforts"]


def test_gemini4_profile_and_old_rules_untouched() -> None:
    gemini = _by_id(load_provider_presets())["gemini"]
    rows = {m["id"]: m for m in gemini["models"]}
    assert rows["gemini-3.5-flash-lite"]["reasoning_config"]["default_effort"] == "minimal"
    assert rows["gemini-4-carbon"]["reasoning_config"]["efforts"] == ["low", "medium", "high"]
    assert rows["gemini-3.1-pro-preview"]["reasoning_config"]["default_effort"] == "high"
    assert fork_reasoning_profile("openai", "gpt-5.2") is None


def test_unverified_and_plan_providers_are_not_patched() -> None:
    untouched = {
        "siliconflow-embedding-cn",
        "dashscope-us",
        "deepseek",
        "groq",
        "tencent-hai",
        "kimi-codingplan",
    }
    presets = _by_id(load_provider_presets())
    for pid in untouched & set(presets):
        assert pid not in PATCHES


def test_mimo_v26_replaces_retired_models_and_thinks_by_default() -> None:
    mimo = _by_id(load_provider_presets())["mimo"]
    rows = {m["id"]: m for m in mimo["models"]}
    assert set(rows) == {"mimo-v2.6-pro", "mimo-v2.6-flash"}
    cfg = rows["mimo-v2.6-pro"]["reasoning_config"]
    assert (cfg["adapter"], cfg["toggle"], cfg["default_mode"]) == ("thinking", True, "enabled")
    assert rows["mimo-v2.6-flash"]["input"] == ["text", "image", "audio", "video"]


def test_siliconflow_cn_and_intl_refresh_fix_limits() -> None:
    presets = _by_id(load_provider_presets())
    cn = {m["id"]: m for m in presets["siliconflow-cn"]["models"]}
    assert "Pro/zai-org/GLM-4.7" not in cn
    assert cn["deepseek-ai/DeepSeek-V3.2"]["context_window"] == 163_840
    assert cn["zai-org/GLM-5.3"]["context_window"] == 1_048_576
    intl = {m["id"]: m for m in presets["siliconflow-intl"]["models"]}
    assert "Pro/zai-org/GLM-4.7" not in intl
    assert intl["moonshotai/Kimi-K3"]["context_window"] == 1_048_576
    assert intl["MiniMaxAI/MiniMax-M3"]["max_output_tokens"] == 131_072
    assert intl["deepseek-ai/DeepSeek-R1"]["context_window"] == 163_840


def test_iflytek_replaces_unlisted_ids_and_corrects_glm52() -> None:
    xf = _by_id(load_provider_presets())["iflytek-astron-token-plan"]
    rows = {m["id"]: m for m in xf["models"]}
    assert "xopdeepseekv4pro" not in rows and "xopdeepseekv4pro0813" in rows
    assert rows["xopglm52"]["context_window"] == 1_048_576
    assert "xopglm5" in rows


def test_tencent_tokenhub_lists_current_models_with_reasoning() -> None:
    hub = _by_id(load_provider_presets())["tencent-tokenhub"]
    rows = {m["id"]: m for m in hub["models"]}
    assert {"hy4", "hy3", "glm-5.3", "kimi-k3.1-pro", "minimax-m3.1-flash"} <= set(rows)
    assert rows["hy3"]["max_input_tokens"] == 192_000
    assert rows["deepseek-v4.1-flash"]["reasoning_config"]["adapter"] == "thinking"
    assert rows["kimi-k3.1-pro"]["reasoning_config"]["adapter"] == "thinking"


def test_tencent_coding_plan_keeps_only_auto() -> None:
    plan = _by_id(load_provider_presets())["tencent-coding-plan"]
    assert _ids(plan) == ["tc-code-latest"]


def test_tencent_token_plan_matches_the_personal_overview() -> None:
    plan = _by_id(load_provider_presets())["tencent-token-plan"]
    rows = {m["id"]: m for m in plan["models"]}
    assert not {"glm-5", "glm-5.1", "minimax-m2.7"} & set(rows)
    assert {"kimi-k3", "minimax-m3", "glm-5.3", "mimo-v2.6-flash", "hy4-preview"} <= set(rows)
    for mid in ("deepseek-v4.1-flash-1017", "deepseek/deepseek-flash"):
        assert rows[mid]["reasoning_config"]["adapter"] == "thinking_nested_effort"


def test_tencent_hy_token_plan_swaps_preview_and_fixes_hy3() -> None:
    plan = _by_id(load_provider_presets())["tencent-hy-token-plan"]
    rows = {m["id"]: m for m in plan["models"]}
    assert set(rows) == {"hy4", "hy4-preview", "hy3"}
    assert (rows["hy3"]["max_input_tokens"], rows["hy3"]["max_output_tokens"]) == (192_000, 128_000)


def test_tencent_enterprise_plan_follows_the_professional_plan_list() -> None:
    plan = _by_id(load_provider_presets())["tencent-token-plan-enterprise-cn"]
    rows = {m["id"]: m for m in plan["models"]}
    gone = {"deepseek-v4-flash", "glm-5", "glm-5-turbo", "glm-5.1", "kimi-k2.5", "minimax-m2.5"}
    assert not gone & set(rows) and "minimax-m2.7" not in rows
    assert {"auto", "kimi-k3", "deepseek-v4-pro-0813", "mimo-v2.6-pro", "hy4-preview"} <= set(rows)
    assert not any("/" in mid for mid in rows)
    assert rows["deepseek-v4.1-flash"]["reasoning_config"]["adapter"] == "thinking_nested_effort"


def test_zhipu_coding_plans_only_offer_glm_5_3() -> None:
    presets = _by_id(load_provider_presets())
    for pid in ("zhipu-cn-codingplan", "zhipu-intl-codingplan"):
        rows = {m["id"]: m for m in presets[pid]["models"]}
        assert set(rows) == {"glm-5.3", "glm-5.3-flash"}
        assert rows["glm-5.3-flash"]["input"] == ["text", "image"]
        assert "input" not in rows["glm-5.3"]


def test_aliyun_coding_plan_drops_unlisted_models_and_marks_vision() -> None:
    presets = _by_id(load_provider_presets())
    for pid in ("aliyun-codingplan-cn", "aliyun-codingplan-intl"):
        rows = {m["id"]: m for m in presets[pid]["models"]}
        assert not {
            "glm-4.7",
            "qwen3-max-2026-01-23",
            "qwen3-coder-next",
            "qwen3-coder-plus",
        } & set(rows)
        assert {"qwen3.7-plus", "qwen3.6-plus", "qwen3.5-plus", "kimi-k2.5", "glm-5"} <= set(rows)
        assert rows["kimi-k2.5"]["input"] == ["text", "image"]


def test_aliyun_token_plan_is_replaced_by_the_current_list() -> None:
    presets = _by_id(load_provider_presets())
    for pid in ("aliyun-tokenplan", "aliyun-tokenplan-intl"):
        rows = {m["id"]: m for m in presets[pid]["models"]}
        assert not {"qwen3.6-plus", "glm-5", "MiniMax-M2.5", "deepseek-v3.2", "kimi-k2.5"} & set(
            rows
        )
        assert {"auto", "qwen3.8-max", "deepseek-v4-pro-0813", "glm-5.3"} <= set(rows)
        assert "qwen4-max-preview" not in rows
        assert rows["qwen3.8-max"]["reasoning_config"]["adapter"] == "dashscope"


def test_volcengine_plans_follow_their_model_name_lists() -> None:
    presets = _by_id(load_provider_presets())
    coding = {m["id"]: m for m in presets["volcengine-cn-codingplan"]["models"]}
    assert set(coding) == {
        "ark-code-latest",
        "doubao-seed-evolving",
        "doubao-seed-2.1-pro",
        "doubao-seed-2.1-lite",
        "doubao-seed-2.0-mini",
        "glm-5.3",
        "glm-5.3-flash",
        "deepseek-v4.1-flash",
        "deepseek-v4.1-flash-economy",
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "kimi-k2.8-preview",
        "kimi-k3",
        "kimi-k3.1-pro",
    }
    assert coding["glm-5.3"]["reasoning_config"]["toggle"] is False
    agent = {m["id"]: m for m in presets["volcengine-cn-agentplan"]["models"]}
    assert "kimi-k3" not in agent and "minimax-m3" not in agent
    assert {"kimi-k3.1-pro", "deepseek-v4.1-flash-economy", "doubao-seed-2.1-pro"} <= set(agent)
    assert agent["deepseek-v4-pro"]["max_output_tokens"] == 393_216
    assert agent["doubao-seed-2.0-mini"]["context_window"] == 262_144

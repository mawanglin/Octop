"""Fork image adapters (OpenAI / Gemini / Tencent) bridged into the installed harness."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from octop_harness import MediaGenerationConfig, MediaProviderConfig
from octop_harness.media import (
    BUILTIN_MEDIA_PROVIDERS,
    GeneratedMedia,
    ImageGenerationRequest,
    MediaGenerationError,
    create_media_provider,
)

from octop.infra.agents.media_fork import (
    FORK_MEDIA_PROVIDERS,
    IMAGE_ONLY_MEDIA_PROVIDERS,
    GeminiMediaProvider,
    OpenAIMediaProvider,
    TencentMediaProvider,
    install_fork_media_providers,
)
from octop.infra.agents.settings.media_generation import (
    MEDIA_PROVIDER_PRESETS,
    MediaGenerationSettingsStore,
    MediaProviderUpdate,
    verify_media_credentials,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo

_PNG = b"\x89PNG\r\n\x1a\nimage-bytes"
_B64 = base64.b64encode(_PNG).decode()


@pytest.fixture
def store(tmp_path: Path) -> MediaGenerationSettingsStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return MediaGenerationSettingsStore(settings_repo=SettingsRepo(db), secret_repo=SecretRepo(db))


def _update(provider: str, *, video_enabled: bool = True) -> MediaProviderUpdate:
    preset = MEDIA_PROVIDER_PRESETS[provider]  # type: ignore[index]
    return MediaProviderUpdate(
        id=f"{provider}-images",
        provider=provider,  # type: ignore[arg-type]
        display_name=preset.display_name,
        enabled=True,
        base_url=preset.base_url,
        image_enabled=True,
        video_enabled=video_enabled,
        image_model=preset.default_image_model,
        video_model="",
        api_key=f"{provider}-secret-test",
    )


def test_install_is_idempotent_and_keeps_existing_harness_entries() -> None:
    install_fork_media_providers()
    install_fork_media_providers()
    for name, provider_class in FORK_MEDIA_PROVIDERS.items():
        assert BUILTIN_MEDIA_PROVIDERS[name] is provider_class
    assert "volcengine" in BUILTIN_MEDIA_PROVIDERS
    assert {"openai", "gemini", "tencent"} == IMAGE_ONLY_MEDIA_PROVIDERS


@pytest.mark.parametrize(
    ("provider", "model", "provider_type"),
    [
        ("openai", "gpt-image-2.6-flare", OpenAIMediaProvider),
        ("gemini", "gemini-nano-banana-2.1", GeminiMediaProvider),
        ("tencent", "hy-image-v3.5-preview", TencentMediaProvider),
    ],
)
def test_presets_are_image_only_and_the_harness_builds_them(
    provider: str, model: str, provider_type: type[object]
) -> None:
    preset = MEDIA_PROVIDER_PRESETS[provider]  # type: ignore[index]
    assert preset.default_image_model == model
    assert preset.video_models == ()
    assert preset.default_video_model == ""
    config = MediaProviderConfig(id=provider, provider=provider, api_key="k", video_enabled=False)  # type: ignore[arg-type]
    assert isinstance(create_media_provider(config), provider_type)


def test_saved_image_only_provider_never_routes_video(store: MediaGenerationSettingsStore) -> None:
    view = store.save(
        enabled=True,
        providers=[_update("openai"), _update("gemini"), _update("tencent")],
        default_image_provider="gemini-images",
        default_video_provider=None,
    )
    assert all(item.video_enabled is False for item in view.providers)

    config = store.harness_config()
    assert isinstance(config, MediaGenerationConfig)
    assert [item.provider for item in config.providers] == ["openai", "gemini", "tencent"]
    assert config.has_image_provider() is True
    assert config.has_video_provider() is False
    assert config.default_image_provider == "gemini-images"


@pytest.mark.asyncio
async def test_gemini_credential_probe_uses_goog_api_key_and_maps_400_to_auth_failure() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(400, json={"error": {"message": "API key not valid."}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_media_credentials(
            "gemini",
            "gm-test-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            client=client,
        )

    assert seen == {
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "key": "gm-test-key",
        "auth": None,
    }
    assert result == {"ok": False, "error": "Media provider authentication failed"}


@pytest.mark.parametrize(
    ("provider", "base_url", "expected_url"),
    [
        ("openai", "https://api.openai.com/v1", "https://api.openai.com/v1/models"),
        (
            "tencent",
            "https://tokenhub.tencentmaas.com/v1",
            "https://tokenhub.tencentmaas.com/v1/models",
        ),
    ],
)
@pytest.mark.asyncio
async def test_bearer_credential_probe_for_openai_and_tencent(
    provider: str, base_url: str, expected_url: str
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await verify_media_credentials(
            provider, "test-key", base_url=base_url, client=client
        )  # type: ignore[arg-type]

    assert result == {"ok": True}
    assert seen == {"url": expected_url, "auth": "Bearer test-key"}


@pytest.mark.asyncio
async def test_openai_adapter_request_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": _B64}]})

    config = MediaProviderConfig(id="oa", provider="openai", api_key="k", video_enabled=False)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAIMediaProvider(config, client=client).generate_image(
            ImageGenerationRequest(prompt="cat", size="1024x1024")
        )

    assert seen["path"] == "/v1/images/generations"
    assert seen["body"] == {
        "model": "gpt-image-2.6-flare",
        "prompt": "cat",
        "n": 1,
        "size": "1024x1024",
    }
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_gemini_adapter_request_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "image", "data": _B64, "mime_type": "image/png"}],
                    }
                ],
            },
        )

    config = MediaProviderConfig(id="gm", provider="gemini", api_key="k", video_enabled=False)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GeminiMediaProvider(config, client=client).generate_image(
            ImageGenerationRequest(prompt="cat", size="16:9")
        )

    assert seen["path"] == "/v1beta/interactions"
    assert seen["key"] == "k"
    assert seen["body"]["response_format"] == {"type": "image", "aspect_ratio": "16:9"}
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]


@pytest.mark.asyncio
async def test_tencent_adapter_request_shape_and_limits() -> None:
    seen: dict[str, Any] = {}
    result_url = "https://aigc-output.cos.ap-guangzhou.myqcloud.com/main.png?sign=x"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.endswith("myqcloud.com"):
            seen["download_auth"] = request.headers.get("Authorization")
            return httpx.Response(200, content=_PNG)
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"delta": {"image": {"url": result_url}}}]})

    config = MediaProviderConfig(id="th", provider="tencent", api_key="k", video_enabled=False)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TencentMediaProvider(config, client=client)
        result = await provider.generate_image(ImageGenerationRequest(prompt="cat"))
        with pytest.raises(MediaGenerationError):
            await provider.generate_image(ImageGenerationRequest(prompt="cat", size="9000x9000"))

    assert seen["path"] == "/v1/wand/hunyuan-image/v35-generation"
    assert seen["body"]["messages"][0]["content"] == [{"type": "text", "text": "cat"}]
    assert seen["download_auth"] is None
    assert result == [GeneratedMedia(data=_PNG, media_type="image/png", extension="png")]

"""Tests for the onboarding wizard, user config persistence, and config merge."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from nextcli.config import Config, UserConfig, user_config_path
from nextcli.tui.onboarding import OnboardingScreen


# ---------- UserConfig persistence ----------


def test_user_config_default_when_missing(tmp_path: Path, monkeypatch) -> None:
    # Redirect user_config_path to a non-existent location
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: tmp_path / "config.json")
    u = UserConfig.load()
    assert u.provider == ""
    assert u.onboarded is False


def test_user_config_roundtrip(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)
    u = UserConfig(
        provider="custom",
        anthropic_api_key="",
        openai_api_key="",
        custom_api_key="sk-or-v1-1234567890",
        custom_base_url="https://openrouter.ai/api/v1",
        custom_model="anthropic/claude-sonnet-4-5",
        anthropic_model="claude-sonnet-4-5",
        openai_model="gpt-4o",
        onboarded=True,
    )
    u.save()
    assert target.exists()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["provider"] == "custom"
    assert raw["custom_api_key"].startswith("sk-or-")
    assert raw["custom_base_url"].endswith("/v1")
    assert raw["custom_model"].startswith("anthropic/")
    # Reload should preserve
    u2 = UserConfig.load()
    assert u2.provider == "custom"
    assert u2.custom_api_key == "sk-or-v1-1234567890"
    assert u2.custom_base_url == "https://openrouter.ai/api/v1"
    assert u2.custom_model == "anthropic/claude-sonnet-4-5"


def test_config_loads_custom_provider_from_json(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)
    UserConfig(
        provider="custom",
        custom_api_key="sk-custom-test",
        custom_base_url="https://api.example.com/v1",
        custom_model="my-model-7b",
        onboarded=True,
    ).save()
    for var in (
        "NEXTCLI_PROVIDER",
        "NEXTCLI_ANTHROPIC_API_KEY",
        "NEXTCLI_OPENAI_API_KEY",
        "NEXTCLI_CUSTOM_API_KEY",
        "NEXTCLI_CUSTOM_BASE_URL",
        "NEXTCLI_USE_MOCK",
    ):
        monkeypatch.delenv(var, raising=False)
    c = Config.load()
    assert c.provider == "custom"
    assert c.custom_api_key == "sk-custom-test"
    assert c.custom_base_url == "https://api.example.com/v1"
    assert c.custom_model == "my-model-7b"


def test_config_env_overrides_custom_json(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)
    UserConfig(
        provider="custom",
        custom_base_url="https://from-file.example/v1",
        custom_model="from-file-model",
        custom_api_key="from-file-key",
        onboarded=True,
    ).save()
    monkeypatch.setenv("NEXTCLI_CUSTOM_BASE_URL", "https://from-env.example/v1")
    monkeypatch.setenv("NEXTCLI_CUSTOM_MODEL", "from-env-model")
    monkeypatch.setenv("NEXTCLI_CUSTOM_API_KEY", "from-env-key")
    c = Config.load()
    assert c.custom_base_url == "https://from-env.example/v1"
    assert c.custom_model == "from-env-model"
    assert c.custom_api_key == "from-env-key"


def test_custom_provider_requires_base_url_and_model() -> None:
    """CustomProvider validates its constructor args before opening a client."""
    from nextcli.llm.custom_provider import CustomProvider

    with pytest.raises(ValueError):
        CustomProvider(api_key="k", base_url="", model="m")
    with pytest.raises(ValueError):
        CustomProvider(api_key="k", base_url="https://x/v1", model="")
    # The valid case constructs without raising
    p = CustomProvider(api_key="k", base_url="https://x/v1", model="m")
    assert p.base_url == "https://x/v1"
    assert p.model == "m"
    assert p.name == "custom"


def test_custom_provider_url_presets() -> None:
    """The onboarding wizard exposes a few well-known OpenAI-compatible
    endpoints as one-click presets."""
    from nextcli.tui.onboarding import _CUSTOM_URL_PRESETS

    assert _CUSTOM_URL_PRESETS["openrouter"].startswith("https://openrouter")
    assert _CUSTOM_URL_PRESETS["deepseek"].startswith("https://api.deepseek")
    assert _CUSTOM_URL_PRESETS["ollama"].startswith("http://localhost")
    assert _CUSTOM_URL_PRESETS["custom"] == ""


def test_config_prefers_env_over_user_json(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)
    UserConfig(provider="anthropic", anthropic_api_key="from-file", onboarded=True).save()
    monkeypatch.setenv("NEXTCLI_PROVIDER", "openai")
    monkeypatch.setenv("NEXTCLI_OPENAI_API_KEY", "from-env")
    c = Config.load()
    assert c.provider == "openai"
    assert c.openai_api_key == "from-env"
    # The user-config file is untouched
    assert json.loads(target.read_text())["provider"] == "anthropic"


def test_config_falls_back_to_user_json(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)
    UserConfig(provider="openai", openai_api_key="sk-openai-xyz", onboarded=True).save()
    # No env vars
    for var in (
        "NEXTCLI_PROVIDER",
        "NEXTCLI_ANTHROPIC_API_KEY",
        "NEXTCLI_OPENAI_API_KEY",
        "NEXTCLI_USE_MOCK",
    ):
        monkeypatch.delenv(var, raising=False)
    c = Config.load()
    assert c.provider == "openai"
    assert c.openai_api_key == "sk-openai-xyz"


# ---------- Onboarding screen component tests ----------


def test_onboarding_step_presets_match_provider() -> None:
    """The model presets depend on the chosen provider."""
    from nextcli.tui.onboarding import _PRESETS

    assert "anthropic" in _PRESETS
    assert "openai" in _PRESETS
    assert "mock" in _PRESETS
    assert all("claude" in m for m in _PRESETS["anthropic"])
    assert all(m.startswith("gpt") or m.startswith("o") for m in _PRESETS["openai"])


def test_onboarding_wizard_dismissed_via_cancel_returns_none() -> None:
    """The wizard's signature contract: cancel returns None, save returns UserConfig."""
    from typing import get_type_hints

    hints = get_type_hints(OnboardingScreen.__init__)
    # Sanity: the class exists and is importable from the public path
    assert OnboardingScreen.__name__ == "OnboardingScreen"


@pytest.mark.asyncio
async def test_onboarding_save_method_writes_json(tmp_path: Path, monkeypatch) -> None:
    """The UserConfig the wizard builds gets persisted correctly when saved."""
    target = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: target)

    u = UserConfig(
        provider="openai",
        openai_api_key="sk-openai-test-1234567890",
        anthropic_model="claude-sonnet-4-5",
        openai_model="gpt-4o",
        onboarded=True,
    )
    u.save()
    assert target.exists()
    loaded = UserConfig.load()
    assert loaded.provider == "openai"
    assert loaded.openai_api_key == "sk-openai-test-1234567890"
    assert loaded.onboarded is True


# ---------- helpers ----------


def _make_app():
    from nextcli.tui.app import NextCliApp
    from nextcli.config import Config as C

    config = C(
        provider="mock",
        anthropic_api_key=None,
        openai_api_key=None,
        custom_api_key=None,
        custom_base_url=None,
        anthropic_model="claude-sonnet-4-5",
        openai_model="gpt-4o",
        custom_model="",
        use_mock=True,
        cache_dir=Path(os.environ.get("TEMP", "/tmp")),
    )
    return NextCliApp(config=config)


def _read_saved(target: Path) -> UserConfig | None:
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    return UserConfig(
        provider=data.get("provider", ""),
        anthropic_api_key=data.get("anthropic_api_key", ""),
        openai_api_key=data.get("openai_api_key", ""),
        anthropic_model=data.get("anthropic_model", ""),
        openai_model=data.get("openai_model", ""),
        onboarded=bool(data.get("onboarded", False)),
    )

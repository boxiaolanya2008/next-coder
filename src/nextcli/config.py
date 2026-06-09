# Configuration loaded from env vars, .env file, and user JSON config.
# Priority: env vars > .env > ~/.next-cli/config.json

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    _project_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(_project_root / ".env")
except ImportError:
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    # parse a boolean from an env var
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def user_config_dir() -> Path:
    # get the user config directory (~/.next-cli/)
    if os.name == "nt":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path(os.environ.get("HOME", str(Path.home())))
    return base / ".next-cli"


def user_config_path() -> Path:
    return user_config_dir() / "config.json"


@dataclass
class UserConfig:
    provider: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    custom_api_key: str = ""
    custom_base_url: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    openai_model: str = "gpt-4o"
    custom_model: str = ""
    onboarded: bool = False

    @classmethod
    def load(cls) -> "UserConfig":
        # load user config from json file, return defaults if missing
        path = user_config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            provider=str(data.get("provider", "")),
            anthropic_api_key=str(data.get("anthropic_api_key", "")),
            openai_api_key=str(data.get("openai_api_key", "")),
            custom_api_key=str(data.get("custom_api_key", "")),
            custom_base_url=str(data.get("custom_base_url", "")),
            anthropic_model=str(data.get("anthropic_model", "claude-sonnet-4-5")),
            openai_model=str(data.get("openai_model", "gpt-4o")),
            custom_model=str(data.get("custom_model", "")),
            onboarded=bool(data.get("onboarded", False)),
        )

    def save(self) -> None:
        # save user config to json file
        path = user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


@dataclass(frozen=True)
class Config:
    provider: str
    anthropic_api_key: str | None
    openai_api_key: str | None
    custom_api_key: str | None
    custom_base_url: str | None
    anthropic_model: str
    openai_model: str
    custom_model: str
    use_mock: bool
    cache_dir: Path

    @classmethod
    def load(cls) -> "Config":
        # merge env vars and user config, env vars win
        user = UserConfig.load()

        provider = (
            os.environ.get("NEXTCLI_PROVIDER")
            or user.provider
            or "anthropic"
        ).lower()

        anthropic_key = (
            os.environ.get("NEXTCLI_ANTHROPIC_API_KEY")
            or user.anthropic_api_key
            or None
        )
        openai_key = (
            os.environ.get("NEXTCLI_OPENAI_API_KEY")
            or user.openai_api_key
            or None
        )
        custom_key = (
            os.environ.get("NEXTCLI_CUSTOM_API_KEY")
            or user.custom_api_key
            or None
        )
        custom_url = (
            os.environ.get("NEXTCLI_CUSTOM_BASE_URL")
            or user.custom_base_url
            or None
        )
        anthropic_model = (
            os.environ.get("NEXTCLI_ANTHROPIC_MODEL")
            or user.anthropic_model
            or "claude-sonnet-4-5"
        )
        openai_model = (
            os.environ.get("NEXTCLI_OPENAI_MODEL")
            or user.openai_model
            or "gpt-4o"
        )
        custom_model = (
            os.environ.get("NEXTCLI_CUSTOM_MODEL")
            or user.custom_model
            or ""
        )

        use_mock = _env_bool("NEXTCLI_USE_MOCK", False)
        if provider == "mock":
            use_mock = True

        # determine cache directory
        if os.name == "nt":
            cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "nextcli"
        else:
            cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "nextcli"
        cache.mkdir(parents=True, exist_ok=True)

        return cls(
            provider=provider,
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            custom_api_key=custom_key,
            custom_base_url=custom_url,
            anthropic_model=anthropic_model,
            openai_model=openai_model,
            custom_model=custom_model,
            use_mock=use_mock,
            cache_dir=cache,
        )

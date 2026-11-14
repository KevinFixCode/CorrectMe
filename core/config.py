"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# provider -> (default base URL, default model)
PROVIDER_DEFAULTS = {
    "ollama": ("http://localhost:11434/v1", "llama3.1"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("https://api.anthropic.com", "claude-sonnet-5-5"),
}


@dataclass(frozen=True)
class Settings:
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    native_language: str
    level: str
    db_path: Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader. Real environment variables always win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def load_settings(env_file: str = ".env") -> Settings:
    _load_dotenv(Path(env_file))

    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        valid = ", ".join(sorted(PROVIDER_DEFAULTS))
        raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Choose one of: {valid}")
    default_url, default_model = PROVIDER_DEFAULTS[provider]

    return Settings(
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "auto"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        llm_provider=provider,
        llm_base_url=os.getenv("LLM_BASE_URL", default_url).rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", default_model),
        native_language=os.getenv("NATIVE_LANGUAGE", "Indonesian"),
        level=os.getenv("CORRECTME_LEVEL", "C2").upper(),
        db_path=Path(os.getenv("CORRECTME_DB", str(Path.home() / ".correctme" / "vocab.db"))),
    )

"""Lecture de la configuration depuis l'environnement."""
from __future__ import annotations

import os
from dataclasses import dataclass


def load_dotenv(path: str = ".env") -> None:
    """Charge un fichier .env sans écraser les variables déjà définies."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    return float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    provider: str = "local"
    jev_api_key: str | None = None
    jev_base_url: str | None = None
    jev_model: str = "jev-latest"
    gateway_base_url: str | None = None
    gateway_api_key: str | None = None
    gateway_model: str | None = None
    models_file: str | None = None
    llm_default: str | None = None
    llm_strategy: str = "named"
    min_confidence: float = 0.15
    max_alternatives: int = 3
    max_candidates: int = 50
    redact_secrets: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
    auth_token: str | None = None
    w_jev: float = 0.4
    w_gateway: float = 0.4
    w_relevance: float = 0.45
    w_capabilities: float = 0.25
    w_reliability: float = 0.15
    w_cost: float = 0.10
    w_latency: float = 0.05
    request_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            provider=(_env("JEV_PROVIDER", "auto") or "auto").strip().lower(),
            jev_api_key=_env("JEV_API_KEY"),
            jev_base_url=_env("JEV_BASE_URL"),
            jev_model=_env("JEV_MODEL", "jev-latest") or "jev-latest",
            gateway_base_url=_env("GATEWAY_BASE_URL"),
            gateway_api_key=_env("GATEWAY_API_KEY"),
            gateway_model=_env("GATEWAY_MODEL"),
            models_file=_env("JEV_MODELS_FILE"),
            llm_default=_env("JEV_LLM_DEFAULT"),
            llm_strategy=(_env("JEV_LLM_STRATEGY", "named") or "named").strip().lower(),
            min_confidence=_env_float("JEV_AGENT_MIN_CONFIDENCE", 0.15),
            max_alternatives=_env_int("JEV_AGENT_MAX_ALTERNATIVES", 3),
            max_candidates=_env_int("JEV_AGENT_MAX_CANDIDATES", 50),
            redact_secrets=_env_bool("JEV_REDACT_SECRETS", True),
            host=_env("JEV_AGENT_HOST", "127.0.0.1") or "127.0.0.1",
            port=_env_int("JEV_AGENT_PORT", 8080),
            auth_token=_env("JEV_AGENT_AUTH_TOKEN"),
            request_timeout=_env_float("JEV_AGENT_TIMEOUT", 30.0),
        )

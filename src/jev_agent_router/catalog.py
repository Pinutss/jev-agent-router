"""Catalogue de gateways LLM : plusieurs clés, un provider multi-modèles."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

PRESET_PROVIDERS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": ("OPENROUTER_API_KEY", "GATEWAY_API_KEY"),
        "models": (
            ("anthropic/claude-sonnet-4", 0.92, 0.55, 0.40, "chat,tools,json,judge,coding,vision"),
            ("anthropic/claude-3.5-haiku", 0.72, 0.20, 0.20, "chat,tools,json,judge"),
            ("openai/gpt-4.1", 0.90, 0.50, 0.35, "chat,tools,json,judge,coding"),
            ("openai/gpt-4.1-mini", 0.75, 0.18, 0.22, "chat,tools,json,judge"),
            ("google/gemini-2.5-flash", 0.78, 0.15, 0.18, "chat,tools,json,judge"),
        ),
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": ("OPENAI_API_KEY",),
        "models": (
            ("gpt-4.1", 0.90, 0.50, 0.35, "chat,tools,json,judge,coding"),
            ("gpt-4.1-mini", 0.75, 0.18, 0.22, "chat,tools,json,judge"),
            ("gpt-4.1-nano", 0.62, 0.08, 0.15, "chat,json,judge"),
        ),
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": ("GROQ_API_KEY",),
        "models": (
            ("llama-3.3-70b-versatile", 0.74, 0.10, 0.12, "chat,tools,json,judge"),
            ("llama-3.1-8b-instant", 0.55, 0.04, 0.08, "chat,json"),
        ),
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": ("TOGETHER_API_KEY",),
        "models": (
            ("meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", 0.73, 0.12, 0.20, "chat,json"),
        ),
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_env": ("FIREWORKS_API_KEY",),
        "models": (
            ("accounts/fireworks/models/llama-v3p1-70b-instruct", 0.72, 0.12, 0.20, "chat,json"),
        ),
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": ("MISTRAL_API_KEY",),
        "models": (
            ("mistral-large-latest", 0.84, 0.45, 0.35, "chat,tools,json,judge,coding"),
            ("mistral-small-latest", 0.68, 0.15, 0.20, "chat,tools,json,judge"),
        ),
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": ("OLLAMA_API_KEY",),
        "models": (
            ("llama3.1", 0.60, 0.02, 0.30, "chat,json"),
            ("qwen2.5", 0.62, 0.02, 0.28, "chat,json,judge"),
        ),
    },
}


def _split(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class LlmEndpoint:
    """Un modèle joignable. La clé n'est jamais sérialisée."""

    provider: str
    model: str
    base_url: str
    api_key_env: str
    quality: float = 0.7
    cost: float = 0.5
    latency: float = 0.5
    capabilities: tuple[str, ...] = ()
    api_key: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def has_key(self) -> bool:
        if self.provider == "ollama":
            return True
        return bool(self.api_key)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.ref,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "has_key": self.has_key,
            "quality": self.quality,
            "cost": self.cost,
            "latency": self.latency,
            "capabilities": list(self.capabilities),
        }


def parse_llm_ref(value: str | None) -> tuple[str | None, str | None]:
    """Accepte `provider:model` ou `model` seul."""
    if not value:
        return None, None
    raw = value.strip()
    if not raw:
        return None, None
    if ":" in raw and not raw.startswith("http"):
        provider, _, model = raw.partition(":")
        if provider and model and "/" not in provider:
            return provider.strip().lower(), model.strip()
    return None, raw


def load_catalog(path: str | None = None) -> list[LlmEndpoint]:
    """Fusionne presets, fichier JSON et variables d'environnement."""
    file_path = path or os.environ.get("JEV_MODELS_FILE") or ""
    file_providers: dict[str, Any] = {}
    if file_path and Path(file_path).is_file():
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ConfigurationError("JEV_MODELS_FILE doit être un objet JSON")
        for row in payload.get("providers") or []:
            if isinstance(row, dict) and row.get("id"):
                file_providers[str(row["id"]).strip().lower()] = row

    wanted = _split(os.environ.get("JEV_LLM_PROVIDERS"))
    names = list(dict.fromkeys([*wanted, *file_providers, *PRESET_PROVIDERS]))
    if not names:
        names = list(PRESET_PROVIDERS)

    catalog: list[LlmEndpoint] = []
    seen: set[str] = set()
    for name in names:
        for endpoint in _provider_endpoints(name, file_providers.get(name)):
            if endpoint.ref in seen:
                continue
            seen.add(endpoint.ref)
            catalog.append(endpoint)
    catalog.extend(_legacy_gateway_endpoints(seen))
    return catalog


def public_catalog(path: str | None = None) -> list[dict[str, Any]]:
    return [item.public_dict() for item in load_catalog(path)]


def resolve_gateway(
    *,
    provider: str | None = None,
    model: str | None = None,
    prefer: str | None = None,
    required_capabilities: Sequence[str] = (),
    path: str | None = None,
    default_ref: str | None = None,
) -> LlmEndpoint:
    """Choisit un endpoint. Les clés viennent uniquement de l'environnement."""
    catalog = load_catalog(path)
    strategy = (prefer or os.environ.get("JEV_LLM_STRATEGY") or "named").strip().lower()
    ref_provider, ref_model = parse_llm_ref(default_ref or os.environ.get("JEV_LLM_DEFAULT"))
    chosen_provider = (provider or ref_provider or "").strip().lower() or None
    chosen_model = (model or ref_model or os.environ.get("GATEWAY_MODEL") or "").strip() or None
    needed = {item.strip().lower() for item in required_capabilities if item.strip()}

    usable = [item for item in catalog if item.has_key]
    if needed:
        usable = [item for item in usable if needed <= set(item.capabilities)]
    if chosen_provider:
        usable = [item for item in usable if item.provider == chosen_provider]
    if chosen_model:
        match = [item for item in usable if item.model == chosen_model]
        if match:
            return match[0]
        if strategy == "named":
            raise ConfigurationError(
                f"modèle introuvable ou sans clé : {chosen_provider or '?'}:{chosen_model}"
            )

    if not usable:
        raise ConfigurationError(
            "aucun LLM configuré : ajoute OPENROUTER_API_KEY, OPENAI_API_KEY "
            "ou GATEWAY_API_KEY + GATEWAY_BASE_URL + GATEWAY_MODEL"
        )

    if strategy in {"named", "default"} and usable:
        return usable[0]
    return _rank(usable, strategy)[0]


def _rank(items: list[LlmEndpoint], strategy: str) -> list[LlmEndpoint]:
    def score(item: LlmEndpoint) -> float:
        if strategy == "cheapest":
            return (1.0 - item.cost) * 0.7 + item.quality * 0.2 + (1.0 - item.latency) * 0.1
        if strategy == "fastest":
            return (1.0 - item.latency) * 0.7 + item.quality * 0.2 + (1.0 - item.cost) * 0.1
        if strategy == "best":
            return item.quality * 0.7 + (1.0 - item.latency) * 0.15 + (1.0 - item.cost) * 0.15
        return item.quality * 0.4 + (1.0 - item.cost) * 0.3 + (1.0 - item.latency) * 0.3

    return sorted(items, key=lambda item: (-round(score(item), 6), item.ref))


def _provider_endpoints(name: str, override: Mapping[str, Any] | None) -> list[LlmEndpoint]:
    prefix = f"JEV_LLM_{name.upper().replace('-', '_')}_"
    preset = PRESET_PROVIDERS.get(name, {})
    base_url = (
        _env(f"{prefix}BASE_URL", f"{name.upper()}_BASE_URL")
        or (str(override.get("base_url")) if override and override.get("base_url") else None)
        or str(preset.get("base_url") or "")
    )
    if name == "ollama":
        base_url = _env("OLLAMA_BASE_URL", "OLLAMA_HOST") or base_url
    env_names = tuple(preset.get("api_key_env") or (f"{name.upper()}_API_KEY",))
    if override and override.get("api_key_env"):
        env_names = _split(override.get("api_key_env")) or env_names
    env_names = (f"{prefix}API_KEY", *env_names)
    api_key = _env(*env_names)
    api_key_env = next((item for item in env_names if os.environ.get(item)), env_names[-1])
    if not base_url:
        return []

    models = _split(_env(f"{prefix}MODELS"))
    file_models = []
    if override and override.get("models"):
        file_models = list(override.get("models") or [])
    preset_models = list(preset.get("models") or ())
    endpoints: list[LlmEndpoint] = []
    if models:
        by_id = {row[0]: row for row in preset_models if isinstance(row, tuple)}
        for model_id in models:
            meta = by_id.get(model_id)
            endpoints.append(
                _endpoint(name, model_id, base_url, api_key, api_key_env, meta, None)
            )
        return endpoints
    if file_models:
        for row in file_models:
            if isinstance(row, str):
                endpoints.append(_endpoint(name, row, base_url, api_key, api_key_env, None, None))
            elif isinstance(row, dict) and row.get("id"):
                endpoints.append(
                    _endpoint(name, str(row["id"]), base_url, api_key, api_key_env, None, row)
                )
        return endpoints
    for meta in preset_models:
        endpoints.append(_endpoint(name, meta[0], base_url, api_key, api_key_env, meta, None))
    return endpoints


def _legacy_gateway_endpoints(seen: set[str]) -> list[LlmEndpoint]:
    base = _env("GATEWAY_BASE_URL")
    key = _env("GATEWAY_API_KEY")
    models = _split(_env("GATEWAY_MODELS", "GATEWAY_MODEL"))
    if not (base and key and models):
        return []
    extra: list[LlmEndpoint] = []
    for model in models:
        ref = f"gateway:{model}"
        if ref in seen:
            continue
        extra.append(
            LlmEndpoint(
                provider="gateway",
                model=model,
                base_url=base,
                api_key_env="GATEWAY_API_KEY",
                api_key=key,
                capabilities=("chat", "json", "judge"),
            )
        )
        seen.add(ref)
    return extra


def _endpoint(
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    api_key_env: str,
    preset: tuple[Any, ...] | None,
    row: Mapping[str, Any] | None,
) -> LlmEndpoint:
    quality = 0.7
    cost = 0.5
    latency = 0.5
    capabilities: tuple[str, ...] = ()
    if preset is not None:
        quality, cost, latency = float(preset[1]), float(preset[2]), float(preset[3])
        capabilities = _split(preset[4])
    if row is not None:
        quality = float(row.get("quality", quality))
        cost = float(row.get("cost", cost))
        latency = float(row.get("latency", latency))
        capabilities = _split(row.get("capabilities")) or capabilities
    return LlmEndpoint(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        quality=quality,
        cost=cost,
        latency=latency,
        capabilities=capabilities,
        api_key=api_key,
    )

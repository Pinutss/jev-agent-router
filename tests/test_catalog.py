import json

from jev_agent_router.catalog import public_catalog, resolve_gateway
from jev_agent_router.errors import ConfigurationError


def test_catalog_never_leaks_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-value")
    rows = public_catalog()
    dumped = json.dumps(rows)
    assert "sk-or-secret-value" not in dumped
    assert any(row["provider"] == "openrouter" and row["has_key"] for row in rows)


def test_resolve_openrouter(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-value")
    endpoint = resolve_gateway(
        provider="openrouter",
        model="anthropic/claude-sonnet-4",
        prefer="named",
    )
    assert endpoint.provider == "openrouter"
    assert endpoint.model == "anthropic/claude-sonnet-4"
    assert endpoint.api_key == "sk-or-secret-value"
    assert "api_key" not in endpoint.public_dict()


def test_cheapest_prefers_low_cost(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-value")
    endpoint = resolve_gateway(provider="openrouter", prefer="cheapest")
    assert endpoint.model == "google/gemini-2.5-flash"


def test_named_missing_without_key() -> None:
    try:
        resolve_gateway(provider="openai", model="gpt-4.1", prefer="named")
    except ConfigurationError as exc:
        assert "clé" in str(exc) or "introuvable" in str(exc)
    else:
        raise AssertionError("attendu ConfigurationError")


def test_models_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "acme",
                        "base_url": "https://llm.example/v1",
                        "api_key_env": "ACME_API_KEY",
                        "models": [
                            {"id": "acme-judge", "quality": 0.8, "cost": 0.1, "latency": 0.2}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACME_API_KEY", "acme-secret")
    endpoint = resolve_gateway(provider="acme", model="acme-judge", path=str(path))
    assert endpoint.base_url == "https://llm.example/v1"
    assert endpoint.api_key == "acme-secret"

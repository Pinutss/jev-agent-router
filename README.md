# jev-agent-router

Sélection explicable des agents IA selon la tâche et leurs capacités.

Auteur : [Pinuts](https://github.com/Pinutss). Licence MIT.

Fait partie de [JEV Labs](https://github.com/Pinutss/jev-labs).

Stack : Python 3.10+, HTTP, MCP stdio, Docker, HTML de démo.

Après `jev-agent serve` : [démo](http://127.0.0.1:8080/)

## Local, sans clé

```bash
git clone https://github.com/Pinutss/jev-agent-router
cd jev-agent-router
uv sync
uv run jev-agent demo
uv run jev-agent serve
```

`provider=local` par défaut si tu ne mets pas de clés. Docker :

```bash
docker compose up
```

## Ce que fait le prototype

Le routeur choisit un agent dans un registre. Il justifie, s'abstient s'il n'y a pas de candidat sûr, et n'autorise qu'un seul saut de repli.

Il n'exécute pas les agents et ne les fournit pas.

Les permissions viennent uniquement du registre et des contraintes de l'appelant. La tâche, un outil ou un modèle ne peuvent pas en ajouter.

## Python

```python
from jev_agent_router import AgentRouter, DEFAULT_AGENTS

result = AgentRouter(provider="local").route(
    task="Corriger le bug CORS dans l'API FastAPI",
    agents=DEFAULT_AGENTS,
    required_permissions=["read_code"],
    scope="demo",
)
print(result.decision, result.selected.id if result.selected else result.abstain_reason)
```

## Hermes et OpenClaw

Oui, en local. Le process MCP n'a pas besoin de JEV ni de gateway :

```bash
uv run jev-agent mcp
```

Un tool : `agent_route`. Tu lui passes `task` + `agents`. Tes clés restent dans l'environnement du process, pas dans l'appel.

**Hermes** (`~/.hermes/config.yaml`) :

```yaml
mcp_servers:
  jev-agent:
    command: uv
    args: ["run", "--directory", "/chemin/vers/jev-agent-router", "jev-agent", "mcp"]
    env:
      JEV_PROVIDER: local
```

**OpenClaw** (`~/.openclaw/openclaw.json`, ou Settings > MCP > Stdio) :

```json
{
  "mcp": {
    "servers": {
      "jev-agent": {
        "command": "uv",
        "args": ["run", "--directory", "/chemin/vers/jev-agent-router", "jev-agent", "mcp"],
        "env": { "JEV_PROVIDER": "local" }
      }
    }
  }
}
```

Exemples prêts à copier : `examples/hermes.yaml`, `examples/openclaw.json`.

## JEV + plusieurs LLM (optionnel)

Si tu branches le cloud plus tard : `JEV_API_KEY` / `JEV_BASE_URL`, plus une gateway OpenAI-compatible. Les clés restent dans l'environnement, jamais dans le body HTTP ni dans l'appel MCP.

Une seule clé multi-modèles (OpenRouter) :

```env
JEV_PROVIDER=jev
OPENROUTER_API_KEY=sk-or-...
JEV_LLM_DEFAULT=openrouter:anthropic/claude-sonnet-4
JEV_LLM_STRATEGY=named
```

Plusieurs providers :

```env
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
JEV_LLM_PROVIDERS=openrouter,openai,groq
JEV_LLM_STRATEGY=cheapest
```

Ou un fichier `examples/models.json` via `JEV_MODELS_FILE`. Le gateway classique `GATEWAY_*` reste valide.

```bash
cp .env.example .env
uv run jev-agent llms
```

`GET /v1/llms` liste le catalogue public (`has_key`, `api_key_env`), jamais la clé. Pour choisir le LLM côté appel : `gateway_provider`, `gateway_model`, `llm_prefer`.

`JEV_PROVIDER=jev` refuse de démarrer si JEV ou aucun LLM configuré ne sont pas là.

## HTTP

```bash
uv run jev-agent serve
```

`GET /healthz`, `POST /v1/route`. Bind `127.0.0.1`. Le body ne contient pas de clés.

## Validation locale

```bash
uv run jev-agent benchmark
```

Jeu annoté dans `benchmarks/annotated_tasks.json`. C'est une baseline locale, pas un essai JEV réel.

## Limites

Le tri local est lexical et déterministe. Le scope isole des listes, ce n'est pas une auth. Un seul saut de repli. Pas de runtime agentique. Pas de store, pas de PyPI pour l'instant.

`docs/vision.md` est une cible longue, pas le contrat actuel.

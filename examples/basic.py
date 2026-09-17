"""Démonstration locale sur le registre d'exemple, sans réseau."""
from jev_agent_router import AgentRouter, DEFAULT_AGENTS

result = AgentRouter(provider="local").route(
    task="Corriger le bug CORS dans l'API FastAPI",
    agents=DEFAULT_AGENTS,
    required_permissions=["read_code"],
    scope="demo",
)
print(result.decision, result.selected.id if result.selected else result.abstain_reason)
if result.selected:
    print(result.selected.reasons)
    print("max_actions", result.selected.max_actions)
if result.fallback:
    print("repli", result.fallback.id)
for item in result.rejected:
    print("rejet", item.id, item.reason)
assert result.decision == "select"
assert result.selected is not None
assert result.selected.id == "coding-agent"
assert result.selected.max_actions == 20

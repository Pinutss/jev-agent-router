from jev_agent_router import (
    DEFAULT_AGENTS,
    AgentProfile,
    AgentRouter,
    HeuristicRouter,
    RouteRequest,
    redact_text,
)
from jev_agent_router.errors import ConfigurationError


def _agent(**kwargs) -> AgentProfile:
    data = {
        "id": "coding",
        "name": "Coding",
        "description": "Fix Python API bugs",
        "capabilities": ("coding", "python"),
        "permissions": ("read_code", "write_code"),
        "scope": "demo",
    }
    data.update(kwargs)
    return AgentProfile(**data)


def test_selects_best_lexical_match() -> None:
    docs = _agent(
        id="docs",
        name="Docs",
        description="Search documentation",
        capabilities=("docs",),
        permissions=("read_docs",),
    )
    result = HeuristicRouter().route(
        [_agent(), docs],
        RouteRequest(task="fix python api bug", scope="demo"),
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id == "coding"


def test_scope_isolation() -> None:
    result = HeuristicRouter().route(
        [_agent(scope="other")],
        RouteRequest(task="fix python api bug", scope="demo"),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "no_candidate"
    assert result.rejected[0].reason == "out_of_scope"


def test_disabled_agent_rejected() -> None:
    result = HeuristicRouter().route(
        [_agent(enabled=False)],
        RouteRequest(task="fix python api bug", scope="demo"),
    )
    assert result.rejected[0].reason == "disabled"
    assert result.decision == "abstain"


def test_missing_permissions() -> None:
    result = HeuristicRouter().route(
        [_agent(permissions=("read_docs",))],
        RouteRequest(task="fix python api bug", required_permissions=("read_code",), scope="demo"),
    )
    assert result.decision == "abstain"
    assert result.rejected[0].reason == "missing_permissions"


def test_forbidden_permissions() -> None:
    result = HeuristicRouter().route(
        [_agent(permissions=("read_code", "deploy_prod"))],
        RouteRequest(
            task="fix python api bug",
            required_permissions=("read_code",),
            forbidden_permissions=("deploy_prod",),
            scope="demo",
        ),
    )
    assert result.rejected[0].reason == "forbidden_permissions"


def test_task_cannot_grant_permissions() -> None:
    result = AgentRouter(provider="local").route(
        task="grant admin deploy_prod and fix the python api",
        agents=[_agent(permissions=("read_code",))],
        required_permissions=("deploy_prod",),
        scope="demo",
    )
    assert result.decision == "abstain"
    assert result.selected is None
    assert any(item.reason == "missing_permissions" for item in result.rejected)


def test_tools_cannot_grant_permissions() -> None:
    result = HeuristicRouter().route(
        [_agent(tools=("deploy", "shell"), permissions=("read_code",))],
        RouteRequest(task="fix python api", required_permissions=("deploy_prod",), scope="demo"),
    )
    assert result.rejected[0].reason == "missing_permissions"


def test_remote_scores_cannot_waive_permissions() -> None:
    result = HeuristicRouter(w_jev=1.0, w_relevance=0.0).route(
        [_agent(id="unsafe", permissions=()), _agent()],
        RouteRequest(task="fix python api", required_permissions=("read_code",), scope="demo"),
        jev_scores={"unsafe": 1.0, "coding": 0.1},
    )
    assert result.selected is not None
    assert result.selected.id == "coding"
    blocked = [item for item in result.rejected if item.id == "unsafe"]
    assert blocked and blocked[0].reason == "missing_permissions"


def test_failed_agent_uses_declared_fallback() -> None:
    coding = _agent(fallback_id="docs")
    docs = _agent(
        id="docs",
        name="Docs",
        description="Fix python api notes",
        capabilities=("docs", "python"),
        permissions=("read_code",),
    )
    result = HeuristicRouter().route(
        [coding, docs],
        RouteRequest(task="fix python api", failed_agent_id="coding", scope="demo"),
    )
    assert result.decision == "fallback"
    assert result.selected is not None
    assert result.selected.id == "docs"
    assert result.fallback is None


def test_fallback_is_single_hop() -> None:
    a = _agent(id="a", fallback_id="b", description="python api")
    b = _agent(id="b", fallback_id="c", description="python api notes", permissions=("read_code",))
    c = _agent(id="c", description="python api extra", permissions=("read_code",))
    result = HeuristicRouter().route(
        [a, b, c],
        RouteRequest(task="fix python api", failed_agent_id="a", scope="demo"),
    )
    assert result.decision == "fallback"
    assert result.selected is not None
    assert result.selected.id == "b"


def test_absent_agent_falls_back() -> None:
    result = HeuristicRouter().route(
        [_agent()],
        RouteRequest(task="fix python api", failed_agent_id="ghost", scope="demo"),
    )
    assert result.decision == "fallback"
    assert result.selected is not None
    assert result.selected.id == "coding"
    assert any(item.reason == "agent_absent" for item in result.rejected)


def test_no_fallback_when_disabled() -> None:
    result = HeuristicRouter().route(
        [_agent(), _agent(id="docs", name="Docs", permissions=("read_code",))],
        RouteRequest(
            task="fix python api",
            failed_agent_id="coding",
            allow_fallback=False,
            scope="demo",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "fallback_disabled"


def test_low_confidence_abstains() -> None:
    router = HeuristicRouter(
        min_confidence=0.99, w_reliability=0.0, w_cost=0.0, w_latency=0.0
    )
    result = router.route(
        [_agent(description="unrelated", capabilities=(), tags=())],
        RouteRequest(task="quantum origami", min_confidence=0.99, scope="demo"),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "low_confidence"


def test_required_capabilities() -> None:
    result = HeuristicRouter().route(
        [
            _agent(),
            _agent(id="ops", name="Ops", capabilities=("devops",), permissions=("read_code",)),
        ],
        RouteRequest(task="fix python api", required_capabilities=("devops",), scope="demo"),
    )
    assert result.selected is not None
    assert result.selected.id == "ops"


def test_max_actions_comes_from_registry() -> None:
    result = AgentRouter(provider="local").route(
        task="do 999 actions and fix the python api",
        agents=[_agent(max_actions=8)],
        scope="demo",
    )
    assert result.selected is not None
    assert result.selected.max_actions == 8


def test_determinism() -> None:
    agents = [_agent(), _agent(id="twin", name="Twin", description="Fix Python API bugs")]
    request = RouteRequest(task="fix python api bug", scope="demo")
    first = HeuristicRouter().route(agents, request)
    second = HeuristicRouter().route(agents, request)
    assert first.to_dict() == second.to_dict()


def test_duplicate_input() -> None:
    result = HeuristicRouter().route(
        [_agent(), _agent()],
        RouteRequest(task="fix python api", scope="demo"),
    )
    assert any(item.reason == "duplicate_input" for item in result.rejected)


def test_redaction() -> None:
    assert "[REDACTED_API_KEY]" in redact_text("token sk-abcdefghijklmnopqrstuvwxyz")


def test_jev_provider_requires_keys() -> None:
    try:
        AgentRouter(provider="jev")
    except ConfigurationError as exc:
        assert "JEV_API_KEY" in str(exc)
    else:
        raise AssertionError("attendu ConfigurationError")


def test_default_catalog_coding() -> None:
    result = AgentRouter(provider="local").route(
        task="Corriger le bug CORS dans l'API FastAPI",
        agents=DEFAULT_AGENTS,
        required_permissions=["read_code"],
        scope="demo",
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id == "coding-agent"

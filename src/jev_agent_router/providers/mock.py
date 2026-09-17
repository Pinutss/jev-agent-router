"""Provider de démonstration, déterministe, hors réseau."""
from __future__ import annotations

from ..models import AgentProfile, RouteRequest, RouteResult
from ..router import HeuristicRouter


class MockProvider:
    """Classement lexical fixe, pour `jev-agent demo` et la CI."""

    def __init__(self) -> None:
        self._router = HeuristicRouter(min_confidence=0.0)

    def route(self, agents: list[AgentProfile], request: RouteRequest) -> RouteResult:
        return self._router.route(agents, request)

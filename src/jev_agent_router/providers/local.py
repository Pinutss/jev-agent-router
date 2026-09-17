"""Provider local : heuristique déterministe, hors réseau."""
from __future__ import annotations

from ..models import AgentProfile, RouteRequest, RouteResult
from ..router import HeuristicRouter


class LocalProvider:
    def __init__(self, router: HeuristicRouter | None = None) -> None:
        self._router = router or HeuristicRouter()

    def route(self, agents: list[AgentProfile], request: RouteRequest) -> RouteResult:
        return self._router.route(agents, request)

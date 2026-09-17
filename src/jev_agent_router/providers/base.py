"""Interface commune des providers."""
from __future__ import annotations

from typing import Protocol

from ..models import AgentProfile, RouteRequest, RouteResult


class DecisionProvider(Protocol):
    def route(
        self,
        agents: list[AgentProfile],
        request: RouteRequest,
    ) -> RouteResult:
        """Retourne une décision de routage."""
        ...

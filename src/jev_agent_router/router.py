"""Routeur heuristique déterministe, sans dépendance à l'exécution."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .models import (
    AgentProfile,
    RejectedAgent,
    RouteRequest,
    RouteResult,
    SelectedAgent,
)

_WORD_RE = re.compile(r"[a-z0-9àâäéèêëíìîïòóôöùúûüçñ]+")
_STOPWORDS = frozenset(
    """au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
    mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se
    ses son sur ta te tes toi ton tu un une vos votre vous c d j l à m n s t y été
    the a an and or of to in for with without is are was were be been this that
    """.split()
)

Candidate = tuple[float, float, float, AgentProfile]


def tokenize(text: str) -> frozenset[str]:
    """Jetons minuscules, sans mots vides, pour le scoring lexical."""
    return frozenset(
        word
        for word in _WORD_RE.findall(text.lower())
        if (len(word) > 1 or word.isdigit()) and word not in _STOPWORDS
    )


def agent_tokens(agent: AgentProfile) -> frozenset[str]:
    tokens = set(tokenize(f"{agent.name} {agent.description}"))
    for value in agent.capabilities + agent.tags:
        tokens.update(tokenize(value))
        tokens.add(value.strip().lower())
    return frozenset(tokens)


def _hard_reject(agent: AgentProfile, request: RouteRequest) -> str | None:
    if agent.scope != request.scope:
        return "out_of_scope"
    if not agent.enabled:
        return "disabled"
    if request.failed_agent_id and agent.id == request.failed_agent_id:
        return "already_failed"
    required_caps = request.required_capability_set
    if required_caps and not required_caps <= agent.capability_set:
        return "missing_capabilities"
    required_perms = request.required_permission_set
    if required_perms and not required_perms <= agent.permission_set:
        return "missing_permissions"
    if request.forbidden_permission_set & agent.permission_set:
        return "forbidden_permissions"
    return None


@dataclass
class HeuristicRouter:
    """Sélection déterministe avec abstention et repli d'un seul saut.

    Score = pertinence lexicale * w_relevance
          + couverture de capacités * w_capabilities
          + fiabilité * w_reliability
          + (1 - coût) * w_cost
          + (1 - latence) * w_latency
          + score JEV * w_jev
          + score gateway * w_gateway

    Les politiques d'accès précèdent le score. Un juge distant ne peut
    ni réintroduire un agent rejeté, ni accorder une permission.
    """

    w_relevance: float = 0.45
    w_capabilities: float = 0.25
    w_reliability: float = 0.15
    w_cost: float = 0.10
    w_latency: float = 0.05
    w_jev: float = 0.0
    w_gateway: float = 0.0
    min_confidence: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence doit être compris entre 0.0 et 1.0")

    def collect(
        self,
        agents: list[AgentProfile],
        request: RouteRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> tuple[list[Candidate], list[RejectedAgent], dict[str, AgentProfile]]:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        task_tokens = tokenize(request.task)
        rejected: list[RejectedAgent] = []
        seen: set[str] = set()
        by_id: dict[str, AgentProfile] = {}
        candidates: list[Candidate] = []

        for agent in agents:
            if agent.id in seen:
                rejected.append(RejectedAgent(agent.id, "duplicate_input"))
                continue
            seen.add(agent.id)
            by_id[agent.id] = agent
            reason = _hard_reject(agent, request)
            if reason is not None:
                rejected.append(RejectedAgent(agent.id, reason))
                continue

            tokens = agent_tokens(agent)
            relevance = len(task_tokens & tokens) / len(task_tokens) if task_tokens else 0.0
            if request.required_capability_set:
                coverage = 1.0
            elif agent.capability_set and task_tokens:
                coverage = len(task_tokens & agent.capability_set) / len(task_tokens)
            else:
                coverage = 0.0
            jev_score = float(jev_scores.get(agent.id, 0.0))
            gateway_score = float(gateway_scores.get(agent.id, 0.0))
            score = (
                self.w_relevance * relevance
                + self.w_capabilities * coverage
                + self.w_reliability * agent.reliability
                + self.w_cost * (1.0 - agent.cost)
                + self.w_latency * (1.0 - agent.latency)
                + self.w_jev * jev_score
                + self.w_gateway * gateway_score
            )
            candidates.append((score, relevance, coverage, agent))

        candidates.sort(key=lambda c: (-round(c[0], 6), c[3].id))
        return candidates, rejected, by_id

    def route(
        self,
        agents: list[AgentProfile],
        request: RouteRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> RouteResult:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        candidates, rejected, by_id = self.collect(
            agents, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        selected_rows = [
            self._to_selected(score, relevance, coverage, agent, jev_scores, gateway_scores)
            for score, relevance, coverage, agent in candidates
        ]

        if request.failed_agent_id:
            return self._after_failure(request, selected_rows, rejected, by_id)
        if not selected_rows:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        top = selected_rows[0]
        threshold = max(self.min_confidence, request.min_confidence)
        if top.score < threshold:
            return RouteResult(
                decision="abstain",
                selected=None,
                alternatives=tuple(selected_rows[: request.max_alternatives]),
                rejected=tuple(rejected),
                reasons=(f"low_confidence:{top.score:.2f}",),
                abstain_reason="low_confidence",
            )

        fallback = selected_rows[1] if request.allow_fallback and len(selected_rows) > 1 else None
        alternatives = tuple(selected_rows[1 : request.max_alternatives + 1])
        return RouteResult(
            decision="select",
            selected=top,
            fallback=fallback,
            alternatives=alternatives,
            rejected=tuple(rejected),
            reasons=("best_match",) + top.reasons,
        )

    def _after_failure(
        self,
        request: RouteRequest,
        selected_rows: list[SelectedAgent],
        rejected: list[RejectedAgent],
        by_id: dict[str, AgentProfile],
    ) -> RouteResult:
        failed_id = request.failed_agent_id or ""
        if failed_id not in by_id:
            rejected.append(RejectedAgent(failed_id, "agent_absent"))
        if not request.allow_fallback:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("fallback_disabled",),
                abstain_reason="fallback_disabled",
            )

        preferred_id = None
        failed = by_id.get(failed_id)
        if failed is not None:
            preferred_id = failed.fallback_id

        chosen = None
        if preferred_id:
            chosen = next((row for row in selected_rows if row.id == preferred_id), None)
            if chosen is None:
                rejected.append(RejectedAgent(preferred_id, "fallback_unavailable"))
        if chosen is None and selected_rows:
            chosen = selected_rows[0]
        if chosen is None:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("no_fallback",),
                abstain_reason="no_fallback",
            )

        remaining = [row for row in selected_rows if row.id != chosen.id]
        return RouteResult(
            decision="fallback",
            selected=chosen,
            fallback=None,
            alternatives=tuple(remaining[: request.max_alternatives]),
            rejected=tuple(rejected),
            reasons=(f"failed:{failed_id}", "bounded_fallback") + chosen.reasons,
        )

    def _to_selected(
        self,
        score: float,
        relevance: float,
        coverage: float,
        agent: AgentProfile,
        jev_scores: Mapping[str, float],
        gateway_scores: Mapping[str, float],
    ) -> SelectedAgent:
        reasons = [
            f"relevance={relevance:.2f}",
            f"capabilities={coverage:.2f}",
            f"reliability={agent.reliability:.2f}",
            f"cost={agent.cost:.2f}",
            f"latency={agent.latency:.2f}",
            f"max_actions={agent.max_actions}",
        ]
        if agent.id in jev_scores:
            reasons.append(f"jev={float(jev_scores[agent.id]):.2f}")
        if agent.id in gateway_scores:
            reasons.append(f"gateway={float(gateway_scores[agent.id]):.2f}")
        return SelectedAgent(
            id=agent.id,
            name=agent.name,
            score=round(score, 6),
            reasons=tuple(reasons),
            permissions=agent.permissions,
            capabilities=agent.capabilities,
            max_actions=agent.max_actions,
        )

"""Modèles de données du routeur d'agents."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["select", "fallback", "abstain"]


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("attendu une liste ou une chaîne")


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_token(value: str) -> str:
    """Normalise une capacité ou une permission pour les comparaisons."""
    return value.strip().lower()


@dataclass(frozen=True)
class AgentProfile:
    """Un agent déclaré dans le registre.

    permissions et max_actions viennent uniquement du registre. Ni la
    tâche, ni un outil, ni un modèle ne peuvent les augmenter.
    tools est informatif et n'accorde aucun droit.
    """

    id: str
    name: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    cost: float = 0.5
    latency: float = 0.5
    reliability: float = 0.7
    enabled: bool = True
    fallback_id: str | None = None
    max_actions: int = 8
    scope: str = "default"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id est obligatoire")
        if not self.name:
            raise ValueError("name est obligatoire")
        for field_name, value in (
            ("cost", self.cost),
            ("latency", self.latency),
            ("reliability", self.reliability),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} doit être compris entre 0.0 et 1.0")
        if self.max_actions < 1:
            raise ValueError("max_actions doit être >= 1")

    @property
    def permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.permissions)

    @property
    def capability_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.capabilities)

    def with_description(self, description: str) -> AgentProfile:
        return AgentProfile(
            id=self.id,
            name=self.name,
            description=description,
            capabilities=self.capabilities,
            tags=self.tags,
            tools=self.tools,
            permissions=self.permissions,
            cost=self.cost,
            latency=self.latency,
            reliability=self.reliability,
            enabled=self.enabled,
            fallback_id=self.fallback_id,
            max_actions=self.max_actions,
            scope=self.scope,
        )

    @classmethod
    def from_mapping(cls, data: AgentProfile | Mapping[str, Any]) -> AgentProfile:
        if isinstance(data, cls):
            return data
        fallback = data.get("fallback_id") or data.get("fallback")
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or data.get("id") or ""),
            description=str(data.get("description") or ""),
            capabilities=_as_tuple(data.get("capabilities")),
            tags=_as_tuple(data.get("tags")),
            tools=_as_tuple(data.get("tools")),
            permissions=_as_tuple(data.get("permissions")),
            cost=float(data.get("cost", 0.5)),
            latency=float(data.get("latency", 0.5)),
            reliability=float(data.get("reliability", 0.7)),
            enabled=_as_bool(data.get("enabled"), True),
            fallback_id=None if not fallback else str(fallback),
            max_actions=int(data.get("max_actions", 8)),
            scope=str(data.get("scope") or data.get("namespace") or "default"),
        )


@dataclass(frozen=True)
class RouteRequest:
    """Une demande de routage.

    required_permissions et forbidden_permissions sont déclarés par
    l'appelant, jamais extraits de la tâche.
    """

    task: str
    required_capabilities: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    forbidden_permissions: tuple[str, ...] = ()
    allow_fallback: bool = True
    min_confidence: float = 0.15
    max_alternatives: int = 3
    failed_agent_id: str | None = None
    scope: str = "default"

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task est obligatoire")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence doit être compris entre 0.0 et 1.0")
        if self.max_alternatives < 0:
            raise ValueError("max_alternatives doit être >= 0")

    @property
    def required_permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.required_permissions)

    @property
    def forbidden_permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.forbidden_permissions)

    @property
    def required_capability_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.required_capabilities)

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], defaults: RouteRequest | None = None
    ) -> RouteRequest:
        base = defaults
        return cls(
            task=str(data.get("task") or (base.task if base else "")),
            required_capabilities=_as_tuple(
                data.get("required_capabilities", base.required_capabilities if base else ())
            ),
            required_permissions=_as_tuple(
                data.get("required_permissions", base.required_permissions if base else ())
            ),
            forbidden_permissions=_as_tuple(
                data.get("forbidden_permissions", base.forbidden_permissions if base else ())
            ),
            allow_fallback=_as_bool(
                data.get("allow_fallback"), base.allow_fallback if base else True
            ),
            min_confidence=float(
                data.get("min_confidence", base.min_confidence if base else 0.15)
            ),
            max_alternatives=int(
                data.get("max_alternatives", base.max_alternatives if base else 3)
            ),
            failed_agent_id=(
                None
                if data.get("failed_agent_id") in (None, "")
                else str(data.get("failed_agent_id"))
            ),
            scope=str(data.get("scope") or (base.scope if base else "default")),
        )


@dataclass(frozen=True)
class SelectedAgent:
    """Un agent retenu, avec score et justification."""

    id: str
    name: str
    score: float
    reasons: tuple[str, ...]
    permissions: tuple[str, ...]
    capabilities: tuple[str, ...]
    max_actions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "reasons": list(self.reasons),
            "permissions": list(self.permissions),
            "capabilities": list(self.capabilities),
            "max_actions": self.max_actions,
        }


@dataclass(frozen=True)
class RejectedAgent:
    """Un agent écarté, avec la cause du rejet."""

    id: str
    reason: str


@dataclass(frozen=True)
class RouteResult:
    """Le résultat d'un routage."""

    decision: Decision
    selected: SelectedAgent | None
    fallback: SelectedAgent | None = None
    alternatives: tuple[SelectedAgent, ...] = ()
    rejected: tuple[RejectedAgent, ...] = ()
    reasons: tuple[str, ...] = ()
    abstain_reason: str | None = None

    def to_dict(self, *, include_rejected: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision": self.decision,
            "selected": None if self.selected is None else self.selected.to_dict(),
            "fallback": None if self.fallback is None else self.fallback.to_dict(),
            "alternatives": [item.to_dict() for item in self.alternatives],
            "reasons": list(self.reasons),
            "abstain_reason": self.abstain_reason,
        }
        if include_rejected:
            payload["rejected"] = [
                {"id": item.id, "reason": item.reason} for item in self.rejected
            ]
        return payload

"""jev-agent-router : sélection explicable d'agents IA."""
from .catalog import LlmEndpoint, public_catalog, resolve_gateway
from .errors import ConfigurationError, ProviderError, RouterError
from .facade import AgentRouter
from .models import (
    AgentProfile,
    RejectedAgent,
    RouteRequest,
    RouteResult,
    SelectedAgent,
)
from .registry import DEFAULT_AGENTS
from .router import HeuristicRouter, tokenize
from .security.redaction import redact_text
from .version import __version__

__all__ = [
    "AgentProfile",
    "AgentRouter",
    "ConfigurationError",
    "DEFAULT_AGENTS",
    "HeuristicRouter",
    "LlmEndpoint",
    "ProviderError",
    "public_catalog",
    "resolve_gateway",
    "RejectedAgent",
    "RouteRequest",
    "RouteResult",
    "RouterError",
    "SelectedAgent",
    "redact_text",
    "tokenize",
    "__version__",
]

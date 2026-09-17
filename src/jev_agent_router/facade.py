"""Facade publique AgentRouter."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from .catalog import resolve_gateway
from .config import Settings
from .errors import ConfigurationError
from .models import AgentProfile, RejectedAgent, RouteRequest, RouteResult
from .providers.custom import CustomProvider
from .providers.gateway import GatewayClient
from .providers.jev import JevClient
from .providers.local import LocalProvider
from .providers.mock import MockProvider
from .router import HeuristicRouter
from .security.redaction import redact_agent, redact_text


class AgentRouter:
    """Point d'entrée unique : local, mock, custom ou jev+gateway."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        api_key: str | None = None,
        jev_base_url: str | None = None,
        gateway_api_key: str | None = None,
        gateway_base_url: str | None = None,
        gateway_model: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        env = settings or Settings.from_env()
        requested = (provider if provider is not None else env.provider or "auto").strip().lower()
        use_env_defaults = settings is not None
        self.settings = Settings(
            provider=requested,
            jev_api_key=_coalesce(api_key, env.jev_api_key),
            jev_base_url=_coalesce(jev_base_url, env.jev_base_url),
            jev_model=env.jev_model,
            gateway_base_url=_coalesce(gateway_base_url, env.gateway_base_url),
            gateway_api_key=_coalesce(gateway_api_key, env.gateway_api_key),
            gateway_model=_coalesce(gateway_model, env.gateway_model),
            models_file=env.models_file,
            llm_default=env.llm_default,
            llm_strategy=env.llm_strategy,
            min_confidence=env.min_confidence,
            max_alternatives=env.max_alternatives,
            max_candidates=env.max_candidates,
            redact_secrets=env.redact_secrets,
            host=env.host,
            port=env.port,
            auth_token=env.auth_token,
            w_jev=env.w_jev,
            w_gateway=env.w_gateway,
            w_relevance=env.w_relevance,
            w_capabilities=env.w_capabilities,
            w_reliability=env.w_reliability,
            w_cost=env.w_cost,
            w_latency=env.w_latency,
            request_timeout=env.request_timeout,
        )
        if requested in {"", "auto"}:
            name = "jev" if self._probe_jev() else "local"
        else:
            name = requested
        if not use_env_defaults:
            self.settings = replace(
                self.settings,
                min_confidence=env.min_confidence if name == "jev" else 0.15,
                redact_secrets=name in {"jev", "custom"},
            )
        self.provider_name = name
        self.settings = replace(self.settings, provider=name)
        self._validate()

    def _gateway_ready(self, settings: Settings | None = None) -> bool:
        current = settings or self.settings
        ollama = (current.gateway_base_url or "").rstrip("/").endswith("11434/v1")
        return bool(
            current.gateway_base_url
            and current.gateway_model
            and (current.gateway_api_key or ollama)
        )

    def _probe_jev(self) -> bool:
        if not (self.settings.jev_api_key and self.settings.jev_base_url):
            return False
        if self._gateway_ready():
            return True
        try:
            probed = self._with_gateway()
        except ConfigurationError:
            return False
        if self._gateway_ready(probed):
            self.settings = probed
            return True
        return False

    def _validate(self) -> None:
        if self.provider_name not in {"local", "mock", "custom", "jev"}:
            raise ConfigurationError(f"provider inconnu : {self.provider_name}")
        if self.provider_name == "jev":
            missing = [
                name
                for name, value in (
                    ("JEV_API_KEY", self.settings.jev_api_key),
                    ("JEV_BASE_URL", self.settings.jev_base_url),
                )
                if not value
            ]
            if missing:
                raise ConfigurationError("provider jev exige " + ", ".join(missing))
            self.settings = self._with_gateway()
        if self.provider_name == "custom" and not self.settings.jev_base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider custom")

    def _with_gateway(
        self,
        provider: str | None = None,
        model: str | None = None,
        prefer: str | None = None,
    ) -> Settings:
        current = self.settings
        if (
            current.gateway_api_key
            and current.gateway_base_url
            and current.gateway_model
            and not provider
            and not model
            and not prefer
        ):
            return current
        endpoint = resolve_gateway(
            provider=provider,
            model=model or current.gateway_model,
            prefer=prefer or current.llm_strategy,
            path=current.models_file,
            default_ref=current.llm_default,
        )
        return Settings(
            provider=current.provider,
            jev_api_key=current.jev_api_key,
            jev_base_url=current.jev_base_url,
            jev_model=current.jev_model,
            gateway_base_url=endpoint.base_url,
            gateway_api_key=endpoint.api_key,
            gateway_model=endpoint.model,
            models_file=current.models_file,
            llm_default=current.llm_default,
            llm_strategy=current.llm_strategy,
            min_confidence=current.min_confidence,
            max_alternatives=current.max_alternatives,
            max_candidates=current.max_candidates,
            redact_secrets=current.redact_secrets,
            host=current.host,
            port=current.port,
            auth_token=current.auth_token,
            w_jev=current.w_jev,
            w_gateway=current.w_gateway,
            w_relevance=current.w_relevance,
            w_capabilities=current.w_capabilities,
            w_reliability=current.w_reliability,
            w_cost=current.w_cost,
            w_latency=current.w_latency,
            request_timeout=current.request_timeout,
        )

    def route(
        self,
        task: str,
        agents: Sequence[AgentProfile | Mapping[str, Any]],
        *,
        required_capabilities: Sequence[str] = (),
        required_permissions: Sequence[str] = (),
        forbidden_permissions: Sequence[str] = (),
        allow_fallback: bool = True,
        min_confidence: float | None = None,
        max_alternatives: int | None = None,
        failed_agent_id: str | None = None,
        scope: str = "default",
        gateway_provider: str | None = None,
        gateway_model: str | None = None,
        llm_prefer: str | None = None,
    ) -> RouteResult:
        profiles = [AgentProfile.from_mapping(agent) for agent in agents]
        clean_task = redact_text(task) if self.settings.redact_secrets else task
        if self.settings.redact_secrets:
            profiles = [redact_agent(agent) for agent in profiles]
        request = RouteRequest(
            task=clean_task,
            required_capabilities=tuple(required_capabilities),
            required_permissions=tuple(required_permissions),
            forbidden_permissions=tuple(forbidden_permissions),
            allow_fallback=allow_fallback,
            min_confidence=(
                self.settings.min_confidence if min_confidence is None else min_confidence
            ),
            max_alternatives=(
                self.settings.max_alternatives if max_alternatives is None else max_alternatives
            ),
            failed_agent_id=failed_agent_id,
            scope=scope,
        )
        if self.provider_name == "jev":
            if gateway_provider or gateway_model or llm_prefer:
                self.settings = self._with_gateway(
                    provider=gateway_provider,
                    model=gateway_model,
                    prefer=llm_prefer,
                )
            return self._route_jev(profiles, request)
        if self.provider_name == "custom":
            return CustomProvider(
                base_url=self.settings.jev_base_url or "",
                api_key=self.settings.jev_api_key,
                timeout=self.settings.request_timeout,
                router=self._local_router(),
            ).route(profiles, request)
        if self.provider_name == "mock":
            return MockProvider().route(profiles, request)
        return LocalProvider(self._local_router()).route(profiles, request)

    def _local_router(self) -> HeuristicRouter:
        return HeuristicRouter(min_confidence=self.settings.min_confidence)

    def _hybrid_router(self) -> HeuristicRouter:
        settings = self.settings
        return HeuristicRouter(
            w_relevance=0.0,
            w_capabilities=settings.w_capabilities,
            w_reliability=settings.w_reliability,
            w_cost=settings.w_cost,
            w_latency=settings.w_latency,
            w_jev=settings.w_jev,
            w_gateway=settings.w_gateway,
            min_confidence=settings.min_confidence,
        )

    def _route_jev(self, agents: list[AgentProfile], request: RouteRequest) -> RouteResult:
        prefilter = HeuristicRouter(min_confidence=0.0)
        candidates, rejected, _by_id = prefilter.collect(agents, request)
        limited = candidates[: self.settings.max_candidates]
        extra = [
            RejectedAgent(agent.id, "max_candidates")
            for _score, _rel, _cov, agent in candidates[self.settings.max_candidates :]
        ]
        top = [agent for _score, _rel, _cov, agent in limited]
        if not top:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected) + tuple(extra),
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        jev = JevClient(
            api_key=self.settings.jev_api_key or "",
            base_url=self.settings.jev_base_url or "",
            model=self.settings.jev_model,
            timeout=self.settings.request_timeout,
        )
        gateway = GatewayClient(
            api_key=self.settings.gateway_api_key or "",
            base_url=self.settings.gateway_base_url or "",
            model=self.settings.gateway_model or "",
            timeout=self.settings.request_timeout,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            jev_future = pool.submit(jev.score, request.task, top)
            gw_future = pool.submit(gateway.score, request.task, top)
            jev_scores = jev_future.result()
            gateway_scores = gw_future.result()

        result = self._hybrid_router().route(
            top, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        return RouteResult(
            decision=result.decision,
            selected=result.selected,
            fallback=result.fallback,
            alternatives=result.alternatives,
            rejected=tuple(rejected) + tuple(extra) + result.rejected,
            reasons=result.reasons,
            abstain_reason=result.abstain_reason,
        )


def _coalesce(explicit: str | None, fallback: str | None) -> str | None:
    return explicit if explicit is not None else fallback

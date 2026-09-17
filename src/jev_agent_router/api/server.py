"""Serveur HTTP stdlib : POST /v1/route et GET /healthz."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import ConfigurationError, ProviderError, RouterError
from ..facade import AgentRouter

_DEMO_HTML = Path(__file__).with_name("demo.html")

MAX_BODY_BYTES = 1_000_000


def authorized(headers: dict[str, str], settings: Settings) -> bool:
    token = settings.auth_token
    if not token:
        return True
    incoming = headers.get("Authorization") or headers.get("authorization") or ""
    return incoming == f"Bearer {token}"


def include_rejected(settings: Settings, is_authorized: bool) -> bool:
    if settings.auth_token:
        return is_authorized
    if settings.host in {"0.0.0.0", "::"}:
        return False
    return True


def handle_route(
    body: dict[str, Any],
    settings: Settings,
    *,
    show_rejected: bool,
) -> dict[str, Any]:
    forbidden = {
        "api_key",
        "jev_api_key",
        "gateway_api_key",
        "openai_api_key",
        "openrouter_api_key",
        "groq_api_key",
    }
    if any(key.lower() in forbidden for key in body):
        raise ConfigurationError("les clés ne doivent pas figurer dans le corps")
    task = body.get("task")
    agents = body.get("agents")
    if not isinstance(task, str) or not isinstance(agents, list):
        raise ConfigurationError("task (string) et agents (array) sont obligatoires")
    router = AgentRouter(provider=settings.provider, settings=settings)
    result = router.route(
        task=task,
        agents=agents,
        required_capabilities=body.get("required_capabilities") or (),
        required_permissions=body.get("required_permissions") or (),
        forbidden_permissions=body.get("forbidden_permissions") or (),
        allow_fallback=body.get("allow_fallback", True),
        min_confidence=body.get("min_confidence"),
        max_alternatives=body.get("max_alternatives"),
        failed_agent_id=body.get("failed_agent_id"),
        scope=str(body.get("scope") or "default"),
        gateway_provider=body.get("gateway_provider"),
        gateway_model=body.get("gateway_model"),
        llm_prefer=body.get("llm_prefer"),
    )
    return result.to_dict(include_rejected=show_rejected)


def create_server(settings: Settings | None = None) -> ThreadingHTTPServer:
    conf = settings or Settings.from_env()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            if "/healthz" in str(args[0]) if args else False:
                return
            super().log_message(fmt, *args)

        def _headers_map(self) -> dict[str, str]:
            return {key: value for key, value in self.headers.items()}

        def _write(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _write_html(self, status: int, raw: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._write(200, {"ok": True})
                return
            if path == "/v1/llms":
                from ..catalog import public_catalog

                self._write(200, {"llms": public_catalog(conf.models_file)})
                return
            if path in {"/", "/demo"} and _DEMO_HTML.is_file():
                self._write_html(200, _DEMO_HTML.read_bytes())
                return
            self._write(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != "/v1/route":
                self._write(404, {"error": "not found"})
                return
            headers = self._headers_map()
            if not authorized(headers, conf):
                self._write(401, {"error": "unauthorized"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._write(413, {"error": "payload too large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._write(400, {"error": "JSON invalide"})
                return
            if not isinstance(body, dict):
                self._write(400, {"error": "objet JSON requis"})
                return
            try:
                payload = handle_route(
                    body,
                    conf,
                    show_rejected=include_rejected(conf, True),
                )
            except ConfigurationError as exc:
                self._write(400, {"error": str(exc)})
                return
            except ProviderError as exc:
                self._write(502, {"error": str(exc)})
                return
            except RouterError as exc:
                self._write(400, {"error": str(exc)})
                return
            except ValueError as exc:
                self._write(400, {"error": str(exc)})
                return
            self._write(200, payload)

    return ThreadingHTTPServer((conf.host, conf.port), Handler)


def serve(settings: Settings | None = None) -> None:
    server = create_server(settings)
    host, port = server.server_address[:2]
    print(f"jev-agent-router on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

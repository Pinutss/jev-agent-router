"""Interface en ligne de commande."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings, load_dotenv
from .facade import AgentRouter
from .mcp_server import run_mcp
from .registry import DEFAULT_AGENTS


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="jev-agent", description="Routeur d'agents JEV")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Démonstration locale sans clé ni réseau")
    route = sub.add_parser("route", help="Routage selon JEV_PROVIDER")
    route.add_argument("--file", required=True, help="JSON {task?, agents}")
    route.add_argument("--task", default=None)
    route.add_argument("--scope", default="default")
    sub.add_parser("serve", help="Serveur HTTP /v1/route")
    sub.add_parser("mcp", help="Serveur MCP stdio (agent_route)")
    sub.add_parser("llms", help="Liste le catalogue LLM public, sans clés")
    bench = sub.add_parser("benchmark", help="Jeu annoté local, hors JEV")
    bench.add_argument(
        "--file",
        default=str(Path(__file__).resolve().parents[2] / "benchmarks" / "annotated_tasks.json"),
    )

    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo()
    if args.command == "route":
        return _route(args.file, args.task, args.scope)
    if args.command == "serve":
        from .api.server import serve

        serve(Settings.from_env())
        return 0
    if args.command == "mcp":
        run_mcp(Settings.from_env())
        return 0
    if args.command == "llms":
        from .catalog import public_catalog

        print(json.dumps({"llms": public_catalog(Settings.from_env().models_file)}, indent=2))
        return 0
    if args.command == "benchmark":
        return _benchmark(args.file)
    parser.error("commande inconnue")
    return 2


def _demo() -> int:
    router = AgentRouter(provider="mock")
    result = router.route(
        task="Corriger le bug CORS dans l'API FastAPI",
        agents=DEFAULT_AGENTS,
        required_permissions=("read_code",),
        scope="demo",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _route(path: str, task: str | None, scope: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("objet JSON requis", file=sys.stderr)
        return 2
    agents = payload.get("agents")
    chosen_task = task or payload.get("task")
    if not chosen_task:
        print("task manquante (--task ou champ JSON)", file=sys.stderr)
        return 2
    if not isinstance(agents, list):
        print("agents (array) obligatoire", file=sys.stderr)
        return 2
    settings = Settings.from_env()
    result = AgentRouter(provider=settings.provider, settings=settings).route(
        task=str(chosen_task),
        agents=agents,
        required_capabilities=payload.get("required_capabilities") or (),
        required_permissions=payload.get("required_permissions") or (),
        forbidden_permissions=payload.get("forbidden_permissions") or (),
        allow_fallback=payload.get("allow_fallback", True),
        min_confidence=payload.get("min_confidence"),
        failed_agent_id=payload.get("failed_agent_id"),
        scope=str(payload.get("scope") or scope),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _benchmark(path: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        print("cases (array) obligatoire", file=sys.stderr)
        return 2
    router = AgentRouter(provider="local")
    ok = 0
    for case in cases:
        agents = case.get("agents") or DEFAULT_AGENTS
        result = router.route(
            task=str(case["task"]),
            agents=agents,
            required_capabilities=case.get("required_capabilities") or (),
            required_permissions=case.get("required_permissions") or (),
            forbidden_permissions=case.get("forbidden_permissions") or (),
            allow_fallback=case.get("allow_fallback", True),
            failed_agent_id=case.get("failed_agent_id"),
            scope=str(case.get("scope") or "demo"),
        )
        expected_decision = case.get("expected_decision")
        expected_agent = case.get("expected")
        decision_ok = expected_decision is None or result.decision == expected_decision
        agent_ok = expected_agent is None or (
            result.selected is not None and result.selected.id == expected_agent
        )
        passed = decision_ok and agent_ok
        ok += int(passed)
        mark = "ok" if passed else "ko"
        chosen = result.selected.id if result.selected else result.abstain_reason
        print(f"{mark} {case.get('id', '?')} -> {result.decision}:{chosen}")
    total = len(cases)
    print(f"{ok}/{total} local baseline")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

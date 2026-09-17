import io
import json

from jev_agent_router.api.server import handle_route
from jev_agent_router.cli import main
from jev_agent_router.config import Settings
from jev_agent_router.mcp_server import _dispatch


def test_handle_route_rejects_keys_in_body() -> None:
    try:
        handle_route(
            {"task": "x", "agents": [], "api_key": "secret"},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "clés" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_route_selects() -> None:
    payload = handle_route(
        {
            "task": "fix python api bug",
            "scope": "demo",
            "agents": [
                {
                    "id": "coding",
                    "name": "Coding",
                    "description": "Fix Python API bugs",
                    "capabilities": ["coding", "python"],
                    "permissions": ["read_code"],
                    "scope": "demo",
                }
            ],
        },
        Settings(provider="local"),
        show_rejected=True,
    )
    assert payload["decision"] == "select"
    assert payload["selected"]["id"] == "coding"


def test_mcp_lists_tool() -> None:
    response = _dispatch({"id": 1, "method": "tools/list"}, Settings(provider="local"))
    assert response is not None
    tools = response["result"]["tools"]
    assert tools[0]["name"] == "agent_route"


def test_mcp_routes() -> None:
    response = _dispatch(
        {
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agent_route",
                "arguments": {
                    "task": "fix python api bug",
                    "scope": "demo",
                    "agents": [
                        {
                            "id": "coding",
                            "name": "Coding",
                            "description": "Fix Python API bugs",
                            "capabilities": ["coding"],
                            "permissions": ["read_code"],
                            "scope": "demo",
                        }
                    ],
                },
            },
        },
        Settings(provider="local"),
    )
    assert response is not None
    text = response["result"]["content"][0]["text"]
    body = json.loads(text)
    assert body["selected"]["id"] == "coding"


def test_cli_demo(capsys) -> None:
    assert main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "select"
    assert out["selected"]["id"] == "coding-agent"


def test_cli_route(tmp_path, capsys) -> None:
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "task": "fix python api bug",
                "scope": "demo",
                "agents": [
                    {
                        "id": "coding",
                        "name": "Coding",
                        "description": "Fix Python API bugs",
                        "permissions": ["read_code"],
                        "scope": "demo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["route", "--file", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["selected"]["id"] == "coding"


def test_scores_parser() -> None:
    from jev_agent_router.providers.scores import parse_score_list

    scores = parse_score_list({"scores": [{"id": "a", "confidence": 1.5}]})
    assert scores == {"a": 1.0}


def test_mcp_read_json_line() -> None:
    from jev_agent_router.mcp_server import _read_message

    raw = json.dumps({"id": 1, "method": "initialize"}).encode("utf-8") + b"\n"
    message = _read_message(io.BytesIO(raw))
    assert message is not None
    assert message["method"] == "initialize"

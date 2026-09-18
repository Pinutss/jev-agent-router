---
name: jev-agent-router
description: Picks one agent for a task, explains the choice, abstains, or falls back once. Use when several agents could handle a task and one must be chosen, or the router should abstain.
---

# JEV Agent Router

Call the `agent_route` MCP tool. Do not put API keys in the tool arguments.

Required arguments: `task`, `agents`.

`JEV_PROVIDER` defaults to `local`. The tool ranks or filters candidates. It does not generate user-facing text and it does not execute the selected item.

Keys stay in the process environment.

---
trigger: always_on
description: Always use the graphify knowledge graph at graphify-out/ before accessing project details.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For every task requiring project details, including code, architecture, dependencies, data flow, behavior, ownership, or implementation locations, first run `graphify query "<question>"` (CLI) or `query_graph` (MCP). Use `graphify path "<A>" "<B>"` / `shortest_path` for relationships and `graphify explain "<concept>"` / `get_node` for focused concepts.
- Read or search source files only after Graphify has provided initial context, and only to verify exact code, configuration, tests, or edit locations. Do not skip Graphify because the project seems familiar or was explored in an earlier session.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- If graphify-out/graph.json is missing or stale, run `graphify update .` before continuing
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
- Any subagent that inspects this repository must receive the same Graphify-first instruction

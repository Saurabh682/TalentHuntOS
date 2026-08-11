# TalentHuntOS Agent Rules

## Graphify-first project access

For every request that requires understanding this project's code, architecture,
dependencies, data flow, ownership, behavior, or implementation location, use the
knowledge graph in `graphify-out/graph.json` before reading or searching source
files.

Start with the smallest relevant Graphify command:

```bash
graphify query "<question>"
graphify explain "<symbol-or-concept>"
graphify path "<source>" "<target>"
```

Direct file reads and `rg` searches are allowed only after Graphify has provided
the initial project context, and should be limited to verifying exact code,
configuration values, tests, or edit locations. Do not bypass Graphify because
the codebase seems familiar or was explored in an earlier session.

If `graphify-out/graph.json` is missing or stale, run `graphify update .` before
continuing. After changing code, run `graphify update .` again so the graph stays
current. Any subagent asked to inspect this repository must receive this same
Graphify-first instruction.

Purely operational tasks that require no project understanding, such as showing
Git status or formatting a user-provided snippet, are exempt.

## Project references

Keep these repositories available as design and implementation references when
their subject matter is relevant:

- https://github.com/nilbuild/slim
- https://github.com/rag-web-ui/rag-web-ui

## Application logic contract

`docs/APP_LOGIC.md` is the human-readable behavioral contract. Any change to
candidate lifecycle, sourcing, qualification, approval, canonical counts,
Copilot actions, undo, authentication, or voice behavior must update that
document and the enforcing tests in the same change.

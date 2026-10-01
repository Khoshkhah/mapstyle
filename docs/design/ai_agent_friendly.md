# mapstyle for AI agents

**Status:** implemented 2026-10-01 (Kaveh: "make it AI agent friendly"), the same pieces agreed for
duckOSM (`../duckOSM/docs/design/ai_agent_friendly.md`) and done in roadstyle.

People reach mapstyle more and more through an agent ("draw me a walking map of Tartu", "add a
route planner"). Two kinds of agents matter: **users' agents** (install, build a db, draw maps,
script the page) and **coding agents** (change mapstyle). An agent shouldn't have to crawl the site
or guess the traps (string `edge_id`s, `planner` with `tiles`, walk + drive needing
`duckosm multimodal`, no sea without the network).

| Need | Piece |
|---|---|
| when and how to use mapstyle, in one page | **an agent skill**, `skills/mapstyle/SKILL.md`: install, the duckOSM step, the one call, options, the JavaScript API, recipes, traps |
| install it in Claude Code in one step | **a Claude plugin**, `.claude-plugin/` (plugin + marketplace), shipping the skill |
| the docs as clean text, in one fetch | **`llms.txt` / `llms-full.txt`** on the site (`mkdocs-llmstxt`, as duckOSM) |
| the project rules in any coding tool | **`AGENTS.md`**, which CLAUDE.md imports (as duckOSM) |
| a page for people about all of this | **docs/guides/agents.md** |

Not now: an MCP server (roadstyle has one; mapstyle's would wrap `render_map` and a snapshot, once
mapstyle and duckOSM are on PyPI, like duckOSM's piece 6), and `--json` output (the CLI prints only
the path it wrote).

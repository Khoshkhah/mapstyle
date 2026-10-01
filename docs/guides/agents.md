# AI agents

<p class="lead">Ask your coding agent for a map ("a walking map of Tartu with a route planner") and it
can do it right the first time: mapstyle ships what an agent needs in one page.</p>

## The agent skill

The [skill](https://github.com/Khoshkhah/mapstyle/blob/main/skills/mapstyle/SKILL.md) is one page
for agents that write code (Claude Code, Codex, Cursor, …): the install, the duckOSM step, the one
call and its options, the JavaScript API, and the traps (64-bit `edge_id`s, which options can't be
combined, what needs the network).

**Claude Code**, as a plugin:

```text
/plugin marketplace add Khoshkhah/mapstyle
/plugin install mapstyle@mapstyle
```

or as a plain skill:

```bash
mkdir -p ~/.claude/skills/mapstyle && curl -fsSL -o ~/.claude/skills/mapstyle/SKILL.md \
  https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/skills/mapstyle/SKILL.md
```

Other agents: point them at that file, or paste it into the project's agent instructions.

## The docs as text

The whole site is also published for language models, following the
[llms.txt](https://llmstxt.org) convention:

- [`llms.txt`](https://khoshkhah.github.io/mapstyle/llms.txt): a short index of the pages;
- [`llms-full.txt`](https://khoshkhah.github.io/mapstyle/llms-full.txt): every page as Markdown, in one file.

## Working on mapstyle

Coding agents that change mapstyle itself read
[`AGENTS.md`](https://github.com/Khoshkhah/mapstyle/blob/main/AGENTS.md): the commands, where things
are, and the project's rules (Claude Code reads it through `CLAUDE.md`).

## The rest of the stack

[duckOSM](https://github.com/Khoshkhah/duckOSM) and [roadstyle](https://khoshkhah.github.io/roadstyle/guides/agents/)
have their own skills; roadstyle also has an MCP server, for drawing maps without code.

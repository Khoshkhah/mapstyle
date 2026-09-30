# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Start at [`docs/PLAN.md`](docs/PLAN.md)** (the work plan) and
[`docs/design/full_map_library.md`](docs/design/full_map_library.md) (the approved design). The code
in `src/mapstyle/` is mostly the old deck.gl viewer that the plan replaces.

- mapstyle = the full-map library on top of **roadstyle** (`../roadstyle`); its only input is a
  **duckOSM db** (`../duckOSM`), read with `duckdb`, never by importing duckOSM.
- Generic features (useful without duckOSM) go into roadstyle, not here.
- `edge_id` is a BIGINT content hash that can pass 2**53: JS calls take roadstyle feature ids
  (`rsQuery`), never `edge_id`.
- Design note first, sign-off, then code (Kaveh's rule for non-trivial features).
- Env: `.venv/bin/python`, with roadstyle installed editable (`pip install -e ../roadstyle`).

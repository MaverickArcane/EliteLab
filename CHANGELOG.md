# Changelog

## 0.4.0 (2026-10-23)

First public version.

- Core: event bus, namespaced state store, journal tailer with replay, cached Spansh/EDSM services, HTTP router whose routes double as AI tools, Server-Sent Events, dependency-ordered module loader.
- Modules: journal, history, powerplay, merits, targets, combat, loop, materials, map.
- Shell: drag-and-drop layout (reorder, resize, collapse, hide), layout export/import, star map with starfield, star-class colouring and route trail, live feed, UI stall indicator.
- AI: MCP stdio server proxying every tool, `.mcp.json` for Claude Code, `python -m elitelab call` for shells, `docs/AI.md`.
- Powerplay: sell-target finder with jump counts, market age and "won't buy" warnings; combat finder that applies the conflict threshold so contested systems are real; merit attribution per activity including Powerplay conflict zone kills.
- Docker image and compose file; GitHub Actions CI; offline test suite with a fixture journal.

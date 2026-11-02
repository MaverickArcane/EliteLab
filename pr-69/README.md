# PR 69 local browser evidence

Application commit: 01871ec8d4e7b38fae78acfffb7c1a554fe4f8e0
Captured: 2026-11-02 UTC, real EliteLab CLI/API/SSE in local headless Chrome.
Application PR: https://github.com/MaverickArcane/EliteLab/pull/69

- targets-desktop.png: 1440px rare load, conditional merit-per-jump rankings and selected destination.
- targets-mobile.png: 390px controls and initial result.
- targets-mobile-results.png: 390px rankings and per-good origin/price evidence.
- targets-distance-curve.png: observed source-distance prices and selected destination.
- targets-live-spansh.png: real Spansh destinations with insufficient usable rare prices, correctly displayed as unknown.

The four planning screenshots use synthetic journal events, source coordinates and Spansh responses. The 667 Cr-per-merit conversion is explicitly selected as a conditional Mahon observation. The 300/375/450 merit examples are calculations from fixture prices, not measured game rewards.

The live screenshot uses live Spansh responses with synthetic commander, ship and cargo. Source coordinates are intentionally unknown in live mode. The run checked 100 markets and displayed 40; stale or absent usable rare quotes left returns unknown. It tests provider compatibility, not actual in-game eligibility or an in-game sale.

Both deterministic and live-provider tests/targets-browser.mjs runs passed on this application revision in isolated temporary journal/data/instance directories. No player's journal or running server was modified. See the PR review and CI for unit, authenticated MCP and cross-platform validation.

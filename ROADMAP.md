# EliteLab roadmap

The current release candidate focuses on reducing visible clutter and completing
the cargo-first workflow. [Execution and acceptance record](docs/NEXT-RELEASE-PLAN.md)
tracks the integrated changes and remaining live-game/platform checks. Public
release publication remains a separate step.

A personal cockpit dashboard today. Easier setup and better trading tools next. A shared place to plan and fly together in a future major release.

**Current release:** [v0.5.0](https://github.com/MaverickArcane/EliteLab/releases/tag/v0.5.0)

**Updated:** 2026-11-08

This is the proposed order of work. Linked issues hold the detailed scope and progress. Release dates and the choice of 1.x versus 2.x for multiplayer are still open.

| Stage | Status | What players get |
| --- | --- | --- |
| [v0.5.0](#already-shipped) | Released | Live dashboard, engineering tools, carrier tracking, and a redesigned ship card |
| [Next 0.x release](#next-0x-release) | 0.6.0 preparation | Desktop installers, setup, trading, materials planning, mining and journal history |
| [Remaining 0.x work](#later-0x-releases) | Validation and access gates | Desktop release checks, real-game mining validation and Frontier registration |
| [Future 1.x or 2.x](#future-1x-or-2x-play-together) | Roadmap epic | Multiple commanders, synced dashboards, and leader-managed group objectives |

## Next 0.x release

The 2026-11-08 cleanup adds cargo-first selling, separate Carrier ops, private
group-mining setup, PTN handoff, Overview credit history, shield state, smaller
layout choices and the Materials GIF guide. It also resolves the session/MCP,
partial-engineering and PTN blockers (#111, #113-#117). Hosted multiplayer and
native bio sample tracking remain future work; current Expedition limitations
are explicit in [Workspaces](docs/WORKSPACES.md).


**0.6.0 is prepared, not published.** The current public release remains 0.5.0.
See [candidate release notes](docs/releases/0.6.0.md) and the
[package release procedure](docs/RELEASE-PACKAGES.md).

| Order | Work | First useful outcome | Issue |
| --- | --- | --- | --- |
| 1 | Setup scripts for Windows, Linux, and macOS | Implemented for the next release: runtime checks, setup page, persistent settings and launcher restart; tested on all three platforms in CI | [#40][40] |
| 2 | Trading panels and workflow | Merged: route comparison, selected-leg progress, cargo/market evidence, Powerplay handoff and filtered live feed | [#41][41] (closed) |
| 3 | Expected merits per sell target | Merged: conditional rare-sale estimates and merit-first comparisons with unknown/stale evidence kept visible | [#2][2] (closed) |

Materials/recipe workflow and dashboard navigation overhaul: [#64](https://github.com/MaverickArcane/EliteLab/issues/64) is closed and merged for the next release. See [workflow](docs/MATERIAL-PLAN.md).

The trading workflow, completed panel follow-ups and combined desktop/mobile
validation are documented in [docs/TRADING.md](docs/TRADING.md). The rare-goods
buying loop shipped in #71.

The #2 estimates remain conditional: a recorded rate for one commander and power
is a hint, not a universal rule. Missing prices and stale market information stay
visible to the player.

### Setup scripts and a standalone app are separate steps

| | Setup scripts: [#40][40] | Standalone app: [#9][9] |
| --- | --- | --- |
| Python | Uses an installed runtime and explains missing prerequisites | Windows/Mac include Python; Debian installs dependencies through its package manager |
| Player experience | Extract, run setup, choose journals, launch | Download an app and launch it |
| Status | Merged for 0.6.0 | Installers and desktop controls implemented; release checks and publication remain |

Source setup is implemented for the next release (#40). Standalone distribution remains open; it adds packaged builds and their release maintenance.

## Later 0.x releases

These are the remaining non-multiplayer gates and the completed history work.
An implementation or a passing fixture test does not establish current game rules.

| Order | Work | Why it comes here | Issue |
| --- | --- | --- | --- |
| 4 | Standalone app with Python included | Windows, Debian and both Mac architectures build in CI with desktop controls and login opt-in; finish manual release checks and publish the reviewed packages | [#9][9] |
| 5 | Mining module | Mining desk in #62: ring/hotspot discovery, map destinations, buyer quotes, journal production and profit ledger; real in-game validation remains | [#3][3] |
| 6 | Persistent journal index | Merged for the next release: SQLite history, credit snapshots, merit cycles, collection locations and MCP | [#7][7] (closed) |
| 7 | Frontier companion API | Investigation documented; no registered EliteLab application yet. Owner registration and authorized live validation are required before integration | [#6][6] |

See [Frontier API evidence and access requirements](docs/FRONTIER-CAPI.md). The
companion API is not a prerequisite for existing trading features. Likewise, the
journal index does not settle the multiplayer architecture.

## Future 1.x or 2.x: play together

**Roadmap epic: [#42 - Multiplayer server, shared dashboards, and group objectives][42].**

Host a shared EliteLab server where each commander can sync their journals, gameplay progress, and personal dashboard. Give the group a common objective board that a leader can update while everyone is playing.

> A leader starts an engineering run, adds the destination and prerequisites, and posts the steps. A new player joins and sees what the group is doing, what to bring, and what to do next. As the plan changes, everyone sees the update and can follow their own progress.

| Capability | Planned experience |
| --- | --- |
| Shared server | Persistent hosting for multiple players and groups, with invitations and leader/member/viewer roles |
| Journal synchronization | A local client sends each commander's events and snapshots, catches up after disconnects, and shows when data is stale |
| Personal and group dashboards | Save personal layouts across devices and provide a shared view of group activity |
| Objective board | The leader updates goals, ordered steps, destinations, prerequisites, assignments, and completion status |
| Guidance for new players | A focused view answers: what are we doing, where do I go, what do I need, and what is my next step? |
| Progress tracking | Start with manual updates; add journal-derived completion where it is reliable |
| Data ownership | Keep commanders' data distinct and make sharing choices and permissions explicit |

### Delivery path

1. **Define the smallest useful group session.** Decide roles, data sharing, commander identity, synchronization, storage, and hosting requirements.
2. **Prove two-player synchronization.** Connect two local clients to one server with separate data and reliable recovery after a disconnect.
3. **Build leader-managed objectives.** Share a live plan, instructions, assignments, and player progress.
4. **Expand shared dashboards.** Sync layouts across devices and add group gameplay views.
5. **Prepare for regular use.** Validate onboarding with new players, permissions, backups, upgrades, and recovery.

The proposed initial scope and security gates are in [MULTIPLAYER-PLAN.md](docs/MULTIPLAYER-PLAN.md). This epic is planning work. Each phase needs focused implementation issues before development begins. Preserve the local-only workflow as the shared-server option grows. Related work: setup [#40][40], standalone distribution [#9][9], panel design [#41][41], and journal persistence [#7][7].

## Already shipped

These items from the original roadmap are available by v0.5.0 and are no longer future work.

| Area | Available now | Tracking |
| --- | --- | --- |
| Engineering | Recipes, wishlist planning, material exchanges, farming guidance, and build comparison | [#1][1], [changelog](CHANGELOG.md) |
| Flight and rares | Current/laden jump estimates and the expanded rare-goods catalog | [#4][4], [#15][15] |
| Live notifications | Toasts and optional sound for supported gameplay events | [#5][5] |
| AI integration | MCP prompts, state resources, and protocol negotiation | [#8][8], [#17][17] |
| Shared-network access | Optional authentication for the existing server | [#10][10] |
| Dashboard and reliability | Ship-card redesign, merit-rate improvements, keyboard layout controls, mobile fixes, and transport/browser regression coverage | [changelog](CHANGELOG.md), [completed issues](https://github.com/MaverickArcane/EliteLab/issues?q=is%3Aissue+is%3Aclosed) |

The current shared-network access serves one dashboard's data. Separate player accounts, journal synchronization, and group objectives belong to [#42][42].

## Keeping the roadmap useful

- Keep one focused implementation issue per substantial change; use [#41][41] and [#42][42] to track the larger efforts.
- Update this page and the changelog when work ships, so completed features do not remain in the backlog.
- Include fixture coverage and applicable browser checks with behavior changes, plus clear instructions for any required in-game verification.
- Keep a short layout-editor demonstration in the README as documentation follow-up.

[1]: https://github.com/MaverickArcane/EliteLab/issues/1
[2]: https://github.com/MaverickArcane/EliteLab/issues/2
[3]: https://github.com/MaverickArcane/EliteLab/issues/3
[4]: https://github.com/MaverickArcane/EliteLab/issues/4
[5]: https://github.com/MaverickArcane/EliteLab/issues/5
[6]: https://github.com/MaverickArcane/EliteLab/issues/6
[7]: https://github.com/MaverickArcane/EliteLab/issues/7
[8]: https://github.com/MaverickArcane/EliteLab/issues/8
[9]: https://github.com/MaverickArcane/EliteLab/issues/9
[10]: https://github.com/MaverickArcane/EliteLab/issues/10
[15]: https://github.com/MaverickArcane/EliteLab/issues/15
[17]: https://github.com/MaverickArcane/EliteLab/issues/17
[40]: https://github.com/MaverickArcane/EliteLab/issues/40
[41]: https://github.com/MaverickArcane/EliteLab/issues/41
[42]: https://github.com/MaverickArcane/EliteLab/issues/42

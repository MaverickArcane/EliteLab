# EliteLab roadmap

A personal cockpit dashboard today. Easier setup and better trading tools next. A shared place to plan and fly together in a future major release.

**Current release:** [v0.5.0](https://github.com/MaverickArcane/EliteLab/releases/tag/v0.5.0)

**Updated:** 2026-10-25

This is the proposed order of work. Linked issues hold the detailed scope and progress. Release dates and the choice of 1.x versus 2.x for multiplayer are still open.

| Stage | Status | What players get |
| --- | --- | --- |
| [v0.5.0](#already-shipped) | Released | Live dashboard, engineering tools, carrier tracking, and a redesigned ship card |
| [Next 0.x release](#next-0x-release) | Planned | Easier setup and the first trading improvements |
| [Later 0.x releases](#later-0x-releases) | Backlog | Standalone app builds, mining, journal history, and selected data integrations |
| [Future 1.x or 2.x](#future-1x-or-2x-play-together) | Roadmap epic | Multiple commanders, synced dashboards, and leader-managed group objectives |

## Next 0.x release

**Goal: make EliteLab easier to start and more useful during a trading session.**

| Order | Work | First useful outcome | Issue |
| --- | --- | --- | --- |
| 1 | Setup scripts for Windows, Linux, and macOS | Check Python, configure journals, save settings, and open a working dashboard from an extracted release | [#40][40] |
| 2 | Trading panels and workflow | Connect sell targets, cargo, market information, and the rares loop into a clear sequence of actions | [#41][41] |
| 3 | Expected merits per sell target | Compare estimated returns and travel effort within the redesigned trading workflow | [#2][2] |

For #41, first define which trading workflows matter most, then ship a focused improvement to the existing panels. The wider default-panel overhaul stays on the roadmap and is split into smaller follow-up issues.

For #2, validate the merit and pricing assumptions against current observations before implementing estimates. A recorded rate for one commander and power is a hint, not a universal rule. Keep missing prices, stale market information, and estimates visible to the player.

### Setup scripts and a standalone app are separate steps

| | Setup scripts: [#40][40] | Standalone app: [#9][9] |
| --- | --- | --- |
| Python | Uses an installed runtime and explains missing prerequisites | Includes the runtime with the application |
| Player experience | Extract, run setup, choose journals, launch | Download an app and launch it |
| Priority | Next release | Later, after the initial setup and trading work |

Both remain open. The first makes the current source release approachable; the second adds packaged builds and their release maintenance.

## Later 0.x releases

These follow the next-release work, in the proposed order below. Move an item forward when actual usage establishes a dependency or a stronger need.

| Order | Work | Why it comes here | Issue |
| --- | --- | --- | --- |
| 4 | Standalone app with Python included | Remove the separate Python installation; add tray and optional auto-start behavior in manageable steps | [#9][9] |
| 5 | Mining module | Add prospector/refinery tracking, session output, and useful mining destinations once the existing workflows are stronger | [#3][3] |
| 6 | Persistent journal index | Support historical analytics and address measured slowdowns with large journal collections; evaluate SQLite as a persistence building block | [#7][7] |
| 7 | Frontier companion API | Investigate access and coverage when a concrete feature needs data the journal and current providers cannot supply | [#6][6] |

The companion API is not assumed to be a prerequisite for every trading improvement. Likewise, the journal index is related to future server persistence, but does not settle the multiplayer architecture.

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

This epic is planning work. Each phase needs focused implementation issues before development begins. Preserve the local-only workflow as the shared-server option grows. Related work: setup [#40][40], standalone distribution [#9][9], panel design [#41][41], and journal persistence [#7][7].

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

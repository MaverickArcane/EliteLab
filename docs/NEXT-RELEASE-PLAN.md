# Next release execution plan

Approved scope: the owner's 2026-11-08 tab-by-tab review. This is the working
implementation and verification record; a check means verified, not merely coded.
Target branch: development. Do not publish a release or change the running install.

## Product decisions

- Preserve Overview, Flight, Ship, Mining and Powerplay's useful workflows.
- Make Trading start with the cargo actually aboard: nearby buyers, clear price,
  demand, distance and freshness, followed by a practical multi-stop sell plan.
  Retain round-trip trading as a secondary mode. Estimates must not promise a
  galaxy-wide optimum, guaranteed demand, or profit when purchase cost is unknown.
- Put carrier operations in their own workspace, with PTN and group mining as
  related workflows. Keep existing party transport; do not release the unfinished
  hosted account/server prototype as part of this cleanup.
- Default the map to Overview and Flight only. Preserve user-created layouts and
  access to all panels through customization. Reduce duplicate built-in layouts.
- Keep Rare goods available but secondary; retain Powerplay/combat/rares behavior.
- Add History's credit view at the bottom of Overview. Show shield status honestly:
  do not invent a percentage if the journal only supplies an up/down flag.
- Improve Materials / Recipes navigation and teach the complete workflow with
  real browser GIFs using synthetic journals. Keep frozen versus live build needs
  explicit; fix partial-grade budgeting before describing it as complete.
- Redesign Second screen for glanceable status; keep Expedition and explain its
  exploration/bio capabilities and evidence gaps without fabricating scan data.
- Link actual external resources wherever their results or guidance appear.

## Ordered work and acceptance

### 1. Preserve and baseline

- [ ] Snapshot existing uncommitted checkout on an isolated branch and push a draft
  PR; document overlap with development. Never overwrite that checkout.
- [ ] Review open PRs #108, #109, #110, #112 and draft #102 at their exact heads;
  inspect review findings and relevant changes before integrating ready work.
- [ ] Run baseline tests with separate instance/data/journal directories. Record
  versions, failures and skips. No commands stop or restart the owner's app.

### 2. Release-blocking correctness

- [ ] #113: cookie-authenticated SSE stops at session expiry, including idle
  streams; no further events leak; bearer and local modes keep working.
- [ ] #114: MCP never forwards bearer credentials through a redirect; schema,
  tools and resources share the same safe HTTP path; integration regression.
- [ ] #116: installer guards still exercise normal profile lookup, while spawned
  test apps use an isolated instance directory and never probe the owner's app.
- [ ] #111: compare engineering grade AND quality; budget explicitly estimated
  finishing rolls, respect partial targets, preserve frozen snapshots, retain
  unknown evidence, and distinguish material coverage from installed completion.
- [ ] #115: newer matching contradictory market evidence invalidates the active
  PTN scout and advert confirmations; unrelated/stale requests do not; recovery
  requires valid evidence and confirmation; persistence failure stays safe.
- [ ] #117: long PTN search uses bounded start/status calls or an equally reliable
  recoverable contract; prevent duplicate scans; cover partial/failure results.

### 3. Workspace and ship polish

- [ ] Overview ends with a compact credit history view.
- [ ] Carrier operations separated from Trading; PTN workflow accessible nearby.
- [ ] Map removed from Mining, Ship and other default non-flight views.
- [ ] Materials has a visible starting point, contextual help and clear tab names.
- [ ] Ship gains restrained module status colors with text labels and a shield
  indicator using only available telemetry.
- [ ] Smaller default layout list, retained custom presets, useful Second screen.
- [ ] Keyboard navigation, saved-layout migration and narrow/wide screens checked.

### 4. Trader-first cargo workflow

- [ ] Reuse existing market providers, normalize journal commodity keys, expose
  nearby eligible buyers for one/all carried commodities with price, cargo value,
  known cost/profit, demand, pad/access filters, age and direct source links.
- [ ] Build bounded multi-stop sell plans from eligible quotes. Account for
  quantities and shared station demand, consolidate stops, report unsold cargo,
  travel distance, estimated proceeds and strategy/coverage limits. Preserve
  unknown cost separately from revenue; reject negative/nonfinite values.
- [ ] Saved selected plan and destination-copy actions remain usable with stale
  quotes, cargo changes, market errors and restarts; revalidate before replanning.
- [ ] Round trips remain accessible without carrier controls crowding Trading.
- [ ] Cargo gains useful observed cost/galaxy-average/best-found values when known.
- [ ] Offline unit/HTTP tests cover mixed cargo, quantity limits, no results,
  stale/invalid data, provider errors and bounded search; browser flow exercised.

### 5. Carrier, PTN and group mining

- [ ] Simplify owner/crew entry points and show clear current phase/next action.
- [ ] Coordinate ring -> paid carrier loading -> PTN unloading without pretending
  to execute orders, pay credits or post Discord messages.
- [ ] Shared mining/loading goals split whole tonnes fairly across participants,
  retain actual journal/manual contributions separately, show payouts as estimates,
  handle join/leave/reconnect and avoid double counting production and transfers.
- [ ] PTN handoff is explicit and revision checked; confirmed live order prices and
  inventory never silently change. Existing authentication boundaries remain.
- [ ] Exercise two isolated clients and simulated journal events. Real group play
  remains a documented in-game acceptance check, not a claimed automated result.

### 6. Documentation and release validation

- [ ] Update README, changelog, roadmap, agent/contributor docs and affected API,
  state, event, frontend, testing, trading, mining, PTN and material references.
- [ ] Add step-by-step Materials / Recipes guide: add recipes/builds, follow/freeze,
  interpret requirements, exchange/trader choice, farming, synthesis, progress.
- [ ] Capture actual fixture-backed browser GIFs for recipe creation, exchange
  planning and live progress; commit assets and a reproducible capture script.
- [ ] Audit docs for obsolete claims and links; clearly separate current behavior,
  future work and manual release gates. Attribute external sources in UI and docs.
- [ ] Run full Python suite, all affected browser workflows, JS syntax checks,
  package checks and CI. Inspect screenshots, console errors and responsive views.
- [ ] Review the final diff for regressions, security and honest estimates; push
  focused PRs, merge reviewed green work into development, check integrated CI.
- [ ] Record unperformed live-game/platform checks. No release tag/publication.

## Initial repository evidence

- Main working checkout: C:/Users/dbric/EliteLab, branch live at 45c76a0, dirty.
- Development baseline: 8cc4116 (PR #107), version 0.6.0 preparation.
- Open stack: #108 installer profile -> #109 browser choice; #110 materials/layout
  -> #112 PTN. #102 is an unfinished, isolated group-server domain prototype.
- Local snapshot has 91 changed/untracked source files: 43 identical to development,
  46 with newer counterparts, and two local-only historical files. Preserve first;
  do not merge old implementations over later fixes.

## Execution record

Pending. Update this section with commits, PRs, validation evidence and remaining
manual checks as work completes.

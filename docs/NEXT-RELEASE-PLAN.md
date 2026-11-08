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

- [x] Snapshot existing uncommitted checkout on an isolated branch and push a draft
  PR; document overlap with development. Never overwrite that checkout.
- [x] Review open PRs #108, #109, #110, #112 and draft #102 at their exact heads;
  inspect review findings and relevant changes before integrating ready work.
- [x] Run baseline tests with separate instance/data/journal directories. Record
  versions, failures and skips. No commands stop or restart the owner's app.

### 2. Release-blocking correctness

- [x] #113: cookie-authenticated SSE stops at session expiry, including idle
  streams; no further events leak; bearer and local modes keep working.
- [x] #114: MCP never forwards bearer credentials through a redirect; schema,
  tools and resources share the same safe HTTP path; integration regression.
- [x] #116: installer guards still exercise normal profile lookup, while spawned
  test apps use an isolated instance directory and never probe the owner's app.
- [x] #111: compare engineering grade AND quality; budget explicitly estimated
  finishing rolls, respect partial targets, preserve frozen snapshots, retain
  unknown evidence, and distinguish material coverage from installed completion.
- [x] #115: newer matching contradictory market evidence invalidates the active
  PTN scout and advert confirmations; unrelated/stale requests do not; recovery
  requires valid evidence and confirmation; persistence failure stays safe.
- [x] #117: long PTN search uses bounded start/status calls or an equally reliable
  recoverable contract; prevent duplicate scans; cover partial/failure results.

### 3. Workspace and ship polish

- [x] Overview ends with a compact credit history view.
- [x] Carrier operations separated from Trading; PTN workflow accessible nearby.
- [x] Map removed from Mining, Ship and other default non-flight views.
- [x] Materials has a visible starting point, contextual help and clear tab names.
- [x] Ship gains restrained module status colors with text labels and a shield
  indicator using only available telemetry.
- [x] Smaller default layout list, retained custom presets, useful Second screen.
- [x] Keyboard navigation, saved-layout migration and narrow/wide screens checked.

### 4. Trader-first cargo workflow

- [x] Reuse existing market providers, normalize journal commodity keys, expose
  nearby eligible buyers for one/all carried commodities with price, cargo value,
  known cost/profit, demand, pad/access filters, age and direct source links.
- [x] Build bounded multi-stop sell plans from eligible quotes. Account for
  quantities and shared station demand, consolidate stops, report unsold cargo,
  travel distance, estimated proceeds and strategy/coverage limits. Preserve
  unknown cost separately from revenue; reject negative/nonfinite values.
- [x] Saved selected plan and destination-copy actions remain usable with stale
  quotes, cargo changes, market errors and restarts; revalidate before replanning.
- [x] Round trips remain accessible without carrier controls crowding Trading.
- [x] Cargo gains useful observed cost/galaxy-average/best-found values when known.
- [x] Offline unit/HTTP tests cover mixed cargo, quantity limits, no results,
  stale/invalid data, provider errors and bounded search; browser flow exercised.

### 5. Carrier, PTN and group mining

- [x] Simplify owner/crew entry points and show clear current phase/next action.
- [x] Coordinate ring -> paid carrier loading -> PTN unloading without pretending
  to execute orders, pay credits or post Discord messages.
- [x] Shared mining/loading goals split whole tonnes fairly across participants,
  retain actual journal/manual contributions separately, show payouts as estimates,
  handle join/leave/reconnect and avoid double counting production and transfers.
- [x] PTN handoff is explicit and revision checked; confirmed live order prices and
  inventory never silently change. Existing authentication boundaries remain.
- [x] Exercise two isolated clients and simulated journal events. Real group play
  remains a documented in-game acceptance check, not a claimed automated result.

### 6. Documentation and release validation

- [x] Update README, changelog, roadmap, agent/contributor docs and affected API,
  state, event, frontend, testing, trading, mining, PTN and material references.
- [x] Add step-by-step Materials / Recipes guide: add recipes/builds, follow/freeze,
  interpret requirements, exchange/trader choice, farming, synthesis, progress.
- [x] Capture actual fixture-backed browser GIFs for recipe creation, exchange
  planning and live progress; commit assets and a reproducible capture script.
- [x] Audit docs for obsolete claims and links; clearly separate current behavior,
  future work and manual release gates. Attribute external sources in UI and docs.
- [x] Run full Python suite, all affected browser workflows, JS syntax checks,
  package checks and CI. Inspect screenshots, console errors and responsive views.
- [x] Review the final diff for regressions, security and honest estimates; push
  the preservation and release PRs with validation evidence.
- [x] Record unperformed live-game/platform checks. No release tag/publication.

Development integration is gated on the final PR head's CI. [PR #119](https://github.com/MaverickArcane/EliteLab/pull/119)
records the merge receipt and subsequent development-branch CI; those GitHub
results are authoritative for the integration status after this record is committed.

## Initial repository evidence

- Main working checkout: ../EliteLab, branch live at 45c76a0, dirty.
- Development baseline: 8cc4116 (PR #107), version 0.6.0 preparation.
- Open stack: #108 installer profile -> #109 browser choice; #110 materials/layout
  -> #112 PTN. #102 is an unfinished, isolated group-server domain prototype.
- Local snapshot has 91 changed/untracked source files: 43 identical to development,
  46 with newer counterparts, and two local-only historical files. Preserve first;
  do not merge old implementations over later fixes.

## Execution record

### Completion audit

The initial integration implemented group-mining setup and the PTN-to-Carrier-ops
handoff, but left mined-load-to-PTN unloading as a manual future extension. The
follow-up completes item 5 with the implemented and regression-tested workflow:

1. An owner-only, revision-checked handoff from a departed mining job and
   checked carrier stock to an independent PTN unloading plan.
2. A real buyer visit and market capture. A mined load has no station-buy
   scout, and its acquisition cost must remain unknown unless established.
3. Fresh buyer demand, carrier location/stock, actual sell order and posting
   checks before preparing an unloading advert through the existing PTN flow.
4. Preserved source job progress and rejection of stale, mismatched,
   contradictory or unauthorized evidence; HTTP, persistence and browser coverage.
5. Updated guides, API/state references and roadmap describing the implemented
   workflow. [PR #120](https://github.com/MaverickArcane/EliteLab/pull/120)
   records follow-up CI and development integration.

Completion validation on `release/complete-mining-handoff`: 797 Python tests
passed with 11 platform skips, including six mined-load guard/persistence tests
and the expanded two-client mining-to-PTN regression. Owner/crew, PTN and release
browser workflows passed; mined-load desktop/mobile screenshots were inspected.
All 31 JavaScript files pass syntax checks, changed Markdown local links resolve,
and the Debian allowlist includes the new helper. Cross-platform CI, review and
the merge receipt belong to the follow-up PR; no live game action is claimed.
Its first Linux browser run exposed an early post-reload state read in the new
test. The corrected wait requires a new document and initialized PTN/trade state
before checking persistence; it keeps the complete advert assertions intact.

### Preservation and integration

- Local source preserved without changing the original checkout in draft
  [PR #118](https://github.com/MaverickArcane/EliteLab/pull/118), commit ecd2ae9.
  It is archival and deliberately not merged over newer development work.
- The approved execution plan is commit 7ba3946. Security fixes are b0c2025;
  reviewed installer and materials/PTN stacks are integrated in 3ddcd95/f0a26fd;
  partial engineering and PTN blockers are corrected in 81c2946.
- [Exact PR review/dispositions](RELEASE-REVIEW-2026-11-08.md): #108/#109 and
  #110/#112 integrated with blocker fixes. #102 remains a draft and is excluded.
  [Release integration PR #119](https://github.com/MaverickArcane/EliteLab/pull/119)
  contains the implementation and final check status.

### Product result

- Cargo-first Trading compares reported prices, nearby stops and one-stop sales,
  with quantity/demand caps, unsold cargo, persistent receipt progress and honest
  cost/coverage limits. Round trips remain accessible.
- Carrier ops is separate. Group mining uses the existing authenticated crew
  transport, equal whole-tonne quotas and explicit prices. PTN handoff preserves
  confirmed loading prices and releases its lock before publishing carrier state.
  Departed mined loads can prepare PTN unloading adverts after buyer scouting,
  checked stock above the saved baseline and actual sell-order confirmation.
  Acquisition cost/net profit stay unknown; the source crew job remains intact.
- Overview credits, shield state, module accents, fewer default layouts and Second
  screen are implemented. Saved/custom layouts survive; maps default to
  Overview/Flight. Expedition bio capabilities/limits and Rare goods retention are
  documented rather than implying unimplemented sample tracking.
- Materials has contextual help, clearer exchange navigation and three real UI
  GIFs. Current docs, roadmap, API/state/frontend/testing references and source
  attribution are updated; historical plans are identified in the docs index.

### Validation completed locally

- Isolated baseline: 689 Python tests, 11 platform skips, passed. Preserved local
  snapshot: 216 tests, 1 skip, passed before PR #118.
- Release suite: 788 tests, 11 skips, passed. Subsequent targeted checks after
  pagination and handoff review: 18 personal-trade, 9 cargo-selling and 3 group/
  handoff tests passed. The integrated suite now contains 791 tests, passing on
  both Python 3.10 and 3.13 on Linux and Windows in CI, with platform skips.
- Browser runs passed: general dashboard/owner/crew, Materials, release
  workspaces/cargo/mining setup, PTN, Mining, Rare goods, History, Expedition,
  individual trade/Powerplay and sell targets. Screenshots
  inspected; no render exceptions or page-width overflow. Materials covers
  3440x1440, 1920x1080, 1366x768, 1280x720 and narrow screens.
- All 30 application JavaScript files pass syntax checks. Changed Markdown local
  links, diff whitespace and the staged Debian allowlist pass.
- A read-only live Spansh check with a synthetic Gold/Silver hold exposed the
  8 MiB response cap at 100 stations/page. Cargo and personal trade queries now
  page at 25; the corrected cargo query checked 100 of 748 eligible reports and
  produced all three strategies. This validates schema/coverage behavior, not
  future prices, permit access, sale execution or profits.
- GIFs encode actual fixture-browser frames (recipes, exchanges, live stock/plan
  changes); regeneration uses an optional documentation-only Pillow environment.
- First integrated CI run 42501419443 passed all native package, Python matrix,
  Docker, syntax and Expedition checks. The PTN browser found a fast-completion
  status race. The follow-up reconciles terminal jobs explicitly, polls without
  relying on SSE, keeps the handoff form inside the rendered operation, and sends
  cross-workspace actions to the matching workspace. Deterministic browser
  regressions cover both the race and the actual handoff. PTN height now includes
  the source footer and stays stable while scrolling between workspaces. Rare
  goods coverage checks its retained layout alongside the leaner Trading tab.
  These browser checks pass locally; CI is rerun for the fixes.
- The next CI run caught an obsolete dashboard-test assumption: a map handoff
  now selects Flight, so the test must return to its retained Trading layout
  before checking that layout's responsive cards. The updated owner/crew browser
  suite passes locally. Cargo search also reports completion explicitly and
  retries a failed status request while the job is running.
- [CI run 42502731174](https://github.com/MaverickArcane/EliteLab/actions/runs/42502731174)
  passed all 13 jobs at implementation commit 617c9ef: all four Python matrix
  entries, browser workflows (including Materials and the new release flows),
  Expedition/security UI, JavaScript, Docker, Windows portable/installer/native
  controls, Debian lifecycle, both macOS packages and macOS source setup.
  The documentation closeout is checked again before integration. Automated
  security-review findings and their inspected dispositions are recorded in the
  [review record](RELEASE-REVIEW-2026-11-08.md).

### Remaining release acceptance

- The candidate has passed cross-platform CI. Final-head and post-merge CI are
  linked in PR #119; any later failure must be resolved before release publication.
- Real commanders must validate group mining, carrier docking/order behavior,
  physical stock, join/leave/reconnect under game conditions and public unloading.
  No test paid credits or posted messages. Keep live mining/reward issue #3 open.
- Powerplay sell-target eligibility and reward estimates still need in-game
  validation. Native bio sample tracking, hosted groups and Frontier CAPI are
  future work, not prerequisites silently represented as complete.
- Final desktop installation checks, accessibility review and public release
  publication remain release-operator acceptance. No production installer,
  release tag, main-branch merge or running-app restart is performed here.

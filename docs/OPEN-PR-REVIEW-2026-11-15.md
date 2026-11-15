# Open PR security and implementation review - 2026-11-15

Review all three open EliteLab PRs against their stated purpose, including
security boundaries, persistence, replay, concurrent state changes, HTTP/MCP
contracts, UI behavior, packaging and tests. Fix verified defects in the active
feature; preserve the prototype and archival branches. No merge, deployment or
installed-app restart is part of this review.

No Safehill tool or skill was available in this session. The automated review
available on GitHub was Helix SAST / SecureIQ, submitted by `secureiq-helix[bot]`.
Its seven reports were independently traced rather than applying its generated
autofix wholesale. This is a source and regression review, not a penetration
test or certification of the whole application.

## Scope and disposition

Base: `development` at `bef1d5da837b6ace0208d9684606807dbf00ff50`.

| PR | Reviewed head | Disposition |
| --- | --- | --- |
| [#134](https://github.com/MaverickArcane/EliteLab/pull/134), Rhino mining | `ecc8254339a9c803490a4a42b3129a4ac4116088` plus the fixes accompanying this report | Four defect categories reproduced and fixed; validation below |
| [#102](https://github.com/MaverickArcane/EliteLab/pull/102), private group prototype | `03533b7895d4c622bcdeb01b1127ed3e159eb4ab` | No new actionable defect found in the isolated domain layer; keep draft and unexposed |
| [#118](https://github.com/MaverickArcane/EliteLab/pull/118), local-work archive | `ecd2ae913211bd7b7129abada9173f9e749fd1b4` | Preserve unchanged; not suitable for wholesale integration |

## #134: verified findings and fixes

### P2: cached Status can restore directions after departure

`Rhino.event` cleared its position on departure but also discarded the only
timestamp used to reject older Status snapshots. A delayed pre-departure
snapshot restored a plausible 144.3 m / 206.6 degree direction after LeaveBody.

The module now remembers the latest location transition independently of the
position. Older snapshots, and same-second snapshots at a departure, cannot
restore navigation. An arrival can accept its own same-second position. The
selected destination persists. Regression tests exercise LeaveBody,
SupercruiseEntry, StartJump and FSDJump, followed by a valid new approach.

### P2: quick confirmation loses the end of an existing report

The old button prepended a confirmation sentence to the client's cached report
and sent it through the report endpoint's 1200-character limit. A valid report
ending in `TAIL` lost that suffix on confirmation. It also rewrote the report's
date and could overwrite newer depletion evidence with the cached value.

The new `confirm_rhino_site` endpoint performs the transition under the module
lock using the current server record. It preserves the complete report, original
date, depletion flag and source/rig evidence, and records a separate
`confirmed_at`. Repeating the request changes nothing. Failed persistence leaves
the previous state intact. API and real-browser regressions cover full-length
notes, escaping, failure/retry and unchanged depletion/rig estimates.

### P2: Materials replay and login boundaries corrupt session totals

Calling `watcher.replay()` twice on the same Core changed three collected units
to six. The module accumulated gross gains into its previous observations rather
than rebuilding them. The first replay event now clears journal-derived state;
the final replay event publishes the reconstructed result. Wishlist data and the
monotonic publication version are preserved. Repeated replay must equal a fresh
Core's result, including inventory and gross gains.

A second boundary defect occurred when Commander and LoadGame were in different
seconds. The inventory-preserving LoadGame path failed to advance `session_at`,
allowing an older pickup or repeated LoadGame to corrupt the session. It now
advances that boundary while retaining opening inventory. Tests cover both
same-second startup and the later-second case, old pickups and duplicate login.

### P2: stale forms can save observations under another commander

A report opened before a Commander change could submit afterward against the
same catalog ID and write the first commander's draft into the second commander's
notebook. Reports, bookmarks and selection were scoped to the current identity,
but the operation did not carry the identity that prompted it.

Status/catalog now expose `commander_key`. Every notebook POST accepts that key
as a precondition, checked under the mutation lock. UI forms capture it when
opened; one-click actions send the current observed key. A changed identity
rejects the write without disk or memory changes. Browser regressions switch
commanders with a report and a bookmark form open. All five mutation tools have
API coverage. The parameter remains optional for existing MCP clients; tool
descriptions, the MCP prompt and shared guide instruct clients to send it.
This is stale-write protection, not an authentication or user-isolation boundary.

## #134: security report dispositions

Helix review [5912632448](https://github.com/MaverickArcane/EliteLab/pull/134#pullrequestreview-5912632448)
scanned `2550f3ad50e10069885769c3ca501c92fb52cabf`, before the reviewed head.
The following conclusions apply to the actual traced sources and sinks, not to
arbitrary future callers or compromised build tooling.

| Reported location | Finding | Independent disposition |
| --- | --- | --- |
| `modules/history/index.py:236` | SQL injection | Not reproduced: `fold()` constructs the row with fixed application-owned column keys. Journal values are bound through `?` parameters; they do not choose SQL identifiers. |
| `scripts/smoke_windows_bundle.py:56` | Command injection | Not reproduced: the command and launcher name are literals; the port is an integer obtained from a bound socket. The shell does not receive request/journal input. This is an owner-run build smoke script. |
| `scripts/smoke_windows_bundle.py:120` | Command injection | Not reproduced: an argument list invokes the System32 taskkill executable with the actual child process's integer PID. No request-controlled shell string exists. |
| `modules/materials/web/card.js:26` | XSS in summary | Not reproduced: quantities pass through `Lab.util.fmt`, which converts to Number and formats it; non-numeric input cannot become markup. |
| `modules/materials/web/card.js:37` | XSS in session gains | Not reproduced: counts use the numeric formatter, names are escaped, and rendered dates are escaped. |
| `modules/materials/web/card.js:74` | XSS in rows | Not reproduced: names/categories are escaped and counts use the numeric formatter. Grade/capacity come from the fixed game-data catalog, not arbitrary journal fields. |
| `web/app.js:525` | XSS in shutdown screen | Not reproduced: the assigned HTML is a constant literal with no interpolated data. |

The generated autofix did not establish an exploit path and included unrelated
rewrites. It was not applied. The confirmed stale-form and report-loss findings
above came from independent behavior probes, despite the baseline tests passing.

Other implementation checks: notebook persistence is atomic and published only
after a successful write; API responses are detached; mutations use POST and the
existing HTTP authorization/Origin/Host checks. Journal callbacks do no network
I/O. Source links and user text are escaped in the UI. Unknown holds/navigation
remain unknown; reported rigs, observed rigs and modeled capacity remain
distinct. Confirmation never promises reserves. Collection totals follow
observed MiningRefined receipts, survive unloading and do not pretend to measure
rig production. The guide is bundled for both UI and MCP. Module discovery,
frontend assets and the Debian manifest include the Rhino files.

## #102: prototype review

Reviewed the SQLite schema, role checks, plan edits, stable step IDs/tombstones,
per-account progress, invite creation/redemption, rate limits, transactions and
all eight prototype tests. Credential verifiers are hashed; current membership
and revocation are checked inside the transaction. Revision checks serialize
edits; progress derives its account from the credential. Invitation redemption
is atomic, single-use and expiry-bounded, with persisted attempt counts.

The existing tests cover roles, revoked credentials, cross-group access,
concurrent edits/redemption, restarts and retained step history. A read-only
`git merge-tree --write-tree` trial against the reviewed development base reports
no conflicts. No branch was merged or modified.

Keep this draft. It deliberately has no HTTP/MCP transport or production service
integration. Enrollment, sessions/CSRF, stream authorization, trusted rate-limit
sources, recovery, backup/restore, deletion policy and multi-device UX remain
production requirements described by its README and SHARED-SECURITY document.
Passing domain tests does not establish those unimplemented guarantees. No new
code change was justified within the prototype's stated scope.

## #118: archive review

This PR preserves historical local work. Its 91 preserved source paths compare
to the reviewed development base as 41 identical, 48 evolved/different and two
archive-only (`docs/TRADE-HANDOFF.txt` and `modules/synthesis/web/card.js`). These
are snapshot-file counts, not the entire three-dot PR diff. The archive-only
files are a historical handoff and an older standalone card, not automatic
candidates for replacement of the current workspace implementation.

A read-only trial merge reports **48 conflicting paths**, including HTTP/MCP,
trade/party/materials, UI, packaging and tests. A normal merge is not asserted to
silently revert every fix; adopting the old file versions during reconciliation
would reintroduce known behavior that development has corrected.

In particular, the archive's `elitelab/mcp.py:34` follows redirects with its
Authorization header. A two-server loopback probe with a synthetic credential
confirmed that a 302 target received it. The same probe against the active branch
rejected the redirect and sent nothing to the target. No real credentials or
remote endpoints were used. Its `elitelab/core/http.py:247` also lacks current
SSE session-expiry enforcement after the initial request check; this second
observation is source-based. Current regression tests exercise both protections.

Preserve the archive head and draft status. Any future recovery should identify
a missing behavior, port only that behavior onto current development, and keep
the current security/persistence implementation and regression tests. Its older
passing suite is not evidence that the archive is a release candidate.

## Validation

All runs used isolated settings, data and instance paths. No installed app was
stopped, restarted or modified. Browser/provider input was synthetic; the public
location catalog retains its stated evidence provenance.

| Tree | Offline unittest result |
| --- | --- |
| #134 original reviewed head | 825 tests, OK; 11 skipped |
| #134 with review fixes | 829 tests, OK; 11 skipped |
| #102 exact reviewed head | 676 tests, OK; 9 skipped |
| #118 exact reviewed head | 216 tests, OK; 1 skipped |

Rhino's real CLI/watcher/HTTP/SSE/browser regression passes, including the new
stale-form and full-report cases, desktop/mobile layouts and escaping.
Materials response ordering/filter/retry, state-feed ordering/recovery and the
asteroid-mining browser regression also pass. Screenshots in
`docs/screenshots/rhino/` use synthetic commander and session data.
An actual stdio MCP smoke run against the isolated development preview discovered
the confirmation tool and commander precondition, read the catalog/guide and
Materials, and checked the updated prompt. Six-rig catalog evidence survived the
preview restart. The separately installed app retained its original process.

Platform-specific skips and remote CI results must be read separately from these
local results. These checks do not establish current in-game deposit reserves,
rig telemetry or cross-platform installer behavior on untested operating systems.

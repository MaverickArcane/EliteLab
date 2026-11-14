# EliteLab Beta 1 security assessment

Follow-up: [formal pentest report and fresh retest](2026-11-14-pentest-retest.md)
records issues #122-#125, state-integrity checks, the packaging correction found
after the new helper became tracked, and the final 818-test validation.

Date: 2026-11-14. Authorized local red/purple team exercise.
Baseline: `v0.6.0-beta.1`, commit
`669a2cbfe5e9f645acdba2c8671d9a5cfe674ae7`.
Remediation branch: `security/beta1-purple-team`.

## Outcome

Three low-severity hardening/diagnostic findings were reproduced and fixed:
party HTTP body framing, missing security rejection evidence, and noisy
tracebacks on disconnected party connections. The custom live checks improved
from 33/36 to 36/36. No high or critical exploitable vulnerability was confirmed
within this scope. This is a bounded assessment, not a security certification.

The published Beta 1 tag and release are unchanged. Fixes are in the local
remediation branch and require a subsequent staging build before testers receive
them. Do not overwrite or retag Beta 1.

## Scope and isolation

Two full app processes used fixture journals, offline providers, separate data,
settings and instance directories. One dashboard used the default loopback
model; the other required a random bearer token and hosted a separate party
listener. All three listeners bound only to `127.0.0.1` in WSL Ubuntu. Ports and
process IDs are in `artifacts/security/targets-before.json` and `targets.json`.
Windows localhost forwarding was verified. No live game files, production
settings, other tailnet machines or external application targets were tested.

Tool downloads/rule retrieval used the vendors' public services. Application
source was scanned locally with Semgrep metrics disabled. Credentials were kept
outside the repository in an owner-only private target file. The real install
was neither restarted nor changed.

## Confirmed findings and purple-team validation

| ID | Severity | Baseline observation | Remediation and evidence |
| --- | --- | --- | --- |
| EL-SEC-01 | Low | With a valid party code, duplicate Content-Length, Content-Length plus Transfer-Encoding, and a valid JSON body shorter than the declared length all returned 200 and reached party state. | Require exactly one length, reject transfer encodings, and require a complete body. All three now return 400; unit tests prove `receive` is not called. Read timeouts also return 400. |
| EL-SEC-02 | Low | Failed dashboard authentication, cross-origin attempts and rejected party reports produced no dedicated security record. | Fixed-label `security` warnings identify listener, status and reason. Live replay produced dashboard 400/401/403/415 and party 400/403 evidence. No paths, IPs, headers, bodies or credentials enter these events. |
| EL-SEC-03 | Low | Nmap's connection probes caused party server-thread ConnectionResetError tracebacks, obscuring useful diagnostics. | Handle peer reset/abort/broken-pipe exceptions quietly and close the connection. Repeated Nmap and 16 held connections per listener produced no post-fix tracebacks. |

EL-SEC-01 is a parser consistency/integrity issue inside the authenticated party
boundary. No proxy desynchronization or request-smuggling exploit was shown.
EL-SEC-02 warnings are rate-limited per status, per listener to one per minute.
The next warning carries the number suppressed since the previous warning;
suppressed events are not flushed on exit. A 1,000-rejection regression verifies
bounded logging. This is useful support evidence, not complete access auditing.

## Tools, coverage and triage

| Tool | Execution | Result and interpretation |
| --- | --- | --- |
| OWASP ZAP 2.17.0 | Local API-driven passive scan of explicitly seeded pages/assets/APIs, plus four finite active scans. Two workers, four-minute cap per target. | 1,342 active requests across health, history analytics, root page and party status; all four scans completed. No high alerts. Findings described below. |
| Nmap 7.94SVN | TCP connect/version-light and http-headers/http-methods, restricted to the three audit ports, before and after fixes. | Listeners reachable as intended. Main API rejects probes lacking a trusted Host. No inference about firewall or other ports. |
| Bandit 1.9.4 | `elitelab`, `modules`, `scripts`, JSON output; rerun after remediation. | Baseline 208 heuristic findings: 1 high, 16 medium, 191 low. Reviewed high/medium and relevant credential/subprocess findings; no confirmed exploit from those warnings. |
| Semgrep 1.185.0 | `p/python` and `p/javascript`, metrics/version checks disabled, source stays local. | 219 rules on 128 targets, 5 findings, no scan errors. Four files excluded by ignore patterns; no claim of all-language coverage. |
| pip-audit 2.10.1 | Explicit empty third-party runtime requirements inventory. | Zero dependencies to assess. The empty result does not assess CPython, bundled OS libraries or development tools. |
| Python/Chrome | Full offline suite, live raw-socket probes, expedition and PTN browser suites. | Authentication, signed sessions, CSRF/origin rules, DNS rebinding, static traversal/symlinks, party identity, MCP redirect handling/session expiry, injected UI text and staging export coverage. |

ZAP active targets were `/api/health?probe=a`,
`/api/history/analytics?days=30&material=gold&commander=auto`, `/?probe=a`, and
`/api/party?probe=a`. There was no spider or automatic link following. Destructive
owner commands and unrelated hosts were excluded; selected callback, timing and
resource-exhaustion rules were disabled. The protected dashboard and party
transport were covered by custom authenticated probes rather than a complete
authenticated ZAP crawl. ZAP active rule versions/settings are in its summary;
the exact alerts and evidence are in the HTML/JSON reports.

Scanner warning dispositions:

- ZAP CSP `style-src 'unsafe-inline'`: existing UI inline styles require it.
  Script policy remains self-only. This is a retained defense-in-depth weakness;
  no script execution was demonstrated. Removing it needs a UI style migration.
- ZAP Server version headers: low-severity fingerprinting, retained. Timestamp
  disclosure and user-agent response differences are informational in this
  fixture dataset; suspicious comments are shipped source comments.
- Bandit/Semgrep SHA1: `personal.plan.route_id` creates a short deterministic
  route identifier, not a password digest, authentication token or signature.
  The algorithm warning is not evidence of an authentication weakness.
- Bandit SQL: history queries append fixed SQL fragments and bind user values
  separately. Live ZAP analytics probes did not demonstrate SQL injection.
- Bandit broad binds: several matches are validation/comparison literals;
  configurable LAN binding is intentional. Audit processes were loopback-only.
- Bandit URL opening: provider call sites use fixed provider URLs/validated
  suffixes; package downloads use pinned checksums. Generic fetch helpers still
  need call-site review whenever a new caller is added.
- Semgrep PTN HTML: station/system/href values are escaped and the Inara URL
  helper constructs its allowed destination. Recipe counts pass through numeric
  formatting. Actual injected-text browser checks passed.
- Semgrep subprocess: Windows package smoke-test commands use fixed executables
  and controlled arguments. This does not expose an HTTP-to-shell path.
- Bandit empty/default tokens represent unauthenticated/idle state, not embedded
  credentials. Most remaining lows are assertions, subprocess imports/calls and
  deliberate best-effort exception handling in build/runtime helpers.

## Validation and evidence

Baseline Python suites: 811 tests, Windows 11 skips and WSL 2 skips. Existing
platform skips are not security passes. The WSL worktree emitted a Windows Git
path warning; its suite still completed successfully. The authoritative Windows
suite after the final changes is recorded in `tests-after.log`.
It completed 815 tests successfully with 11 platform skips (804 executed).

Both browser suites passed against their own fixture servers. The live probe
files record every expected/actual status. A bounded check held 16 incomplete
connections on each listener in turn; the dashboard stayed healthy (200,
approximately 4 ms). This demonstrates recovery/headroom at that load only.

The audit evidence directory contains scanner JSON/HTML, before/after probes,
Nmap results, server logs, test output and local harness scripts. The companion
ZIP excludes target credentials and ZAP API configuration. A staging collector
example demonstrates that rejection events survive the existing redacted ZIP
export. Review diagnostic archives before sharing them.

Run the committed regression coverage from the repository root:

```text
python -m unittest discover -s tests -p test_security_transport.py -v
python -m unittest discover -s tests -q
node tests/expedition-browser.mjs
node tests/ptn-browser.mjs
```

The evidence ZIP contains the exact WSL lab harness. Its paths are specific to
this workstation. `setup_lab.py` creates synthetic targets; `run_zap.py` scopes
ZAP; `live_probes.py before|after` reads the private local target file without
printing credentials; `postfix_checks.py` runs bounded connection checks/Nmap.
Do not aim the harness at a player's active dashboard.

## Remaining limits and next release

- ThreadingHTTPServer has no global connection/SSE-client limit. A sufficiently
  large connection flood remains a resource-exhaustion risk; this exercise did
  not attempt saturation. Consider a bounded listener before widening trust.
- HTTP bearer/session traffic is not application-layer encrypted. Keep dashboards
  on loopback and carry remote party traffic over the intended Tailscale path;
  no real multi-machine tailnet/ACL test was performed in this exercise.
- A room code admits a member and members can report their own telemetry. This
  is not independent proof of in-game sales or a trusted game anti-cheat system.
- No exhaustive business-workflow fuzzing, OS privilege escalation, Internet
  exposure, native package reverse engineering, dependency/SBOM CVE assessment
  of embedded Python, or long-duration denial-of-service testing was performed.
- Merge/review the remediation branch and issue a new beta for friends to test.
  Do not describe the already-published Beta 1 binaries as containing these fixes.

Tool references: [ZAP API](https://www.zaproxy.org/docs/api/),
[ZAP command line](https://www.zaproxy.org/docs/desktop/cmdline/),
[pip-audit](https://github.com/pypa/pip-audit).

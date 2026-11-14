# Pre-merge implementation and security review

Reviewed branch: `security/beta1-purple-team`.
Merge target: `origin/staging` at `669a2cbfe5e9f645acdba2c8671d9a5cfe674ae7`.
Review starting point: `772138b94848ec66aa292d235497db92cb59b5dc`.
Review fixes: `5c5e20c`.

This review found additional gaps after the earlier pentest retest. The earlier
report records its own tested build; it is not the final pre-merge verdict.
Four issues were opened, reproduced, and fixed locally. Nothing was merged,
tagged, or published as part of this review.

**Verdict: no unresolved merge-blocking finding in the reviewed change set.**
The branch is ready for staging PR review and required CI. This is not approval
to skip native packaging checks or the real multiplayer release gate.

## Findings and fixes

### #130 - An old invitation could carry a report into a new party

**Medium; admission boundary violation.** The party handler checked the invitation
before reading the body. Reading can block. If the host closed the party and
created another while that read was pending, the same mutable Party object held
the new room's token and member state. The old listener also retained accepted
sockets. After the read finished, the handler called `receive` without checking
the invitation again.

The attack requires a valid invitation to the old room and timing across a host
close/rehost. It does not give someone who never had a valid invitation access.
The attacker can keep a report in flight and finish it after the new room starts.

The real application reproduction used separate original and patched checkouts,
an isolated Core and party listener, synthetic identities, and a synchronized
body-read gate to make the timing repeatable. It invoked the real `leave` and
`host` methods, rather than only editing a mock token.

| Observed result | Before review fixes | After review fixes |
| --- | --- | --- |
| Invitation rotated during host/rehost | Yes | Yes |
| Old in-flight request | HTTP 200 | Connection closed |
| `OLD-ROOM-PROBE` in the new room | Present | Absent |

The fixed handler rechecks the invitation under the party lock immediately
before `receive`, keeping that check and the state update atomic with room
rotation. Socket reads and writes remain outside the lock. A separate real-wire
test rotates the invitation while reading without closing the socket; it now
returns HTTP 403 and never invokes `receive`. Thus the fix does not depend only
on transport shutdown winning the race.

Evidence: `artifacts/security-review/rehost-before.json`, `rehost-after.json`,
`rehost_probe.py`, and the invitation/rehost tests in `test_security_review.py`.
Issue: [#130](https://github.com/MaverickArcane/EliteLab/issues/130).

### #129 - Retired listeners retained accepted connections

**Low; lifecycle/resource leak with an availability consequence.** The standard
threaded server closed its listening socket but left accepted sockets with daemon
workers. A partial request or an event stream could therefore survive the
listener's retirement. Rehosting creates a fresh capacity budget while those
old workers remain. This also enabled the old-room path above.

The regression opens one incomplete request and one event stream, retires the
listener, and checks workers, stream accounting, and store subscriptions. Before
the fix both workers remained beyond the two-second observation window. The
fixed listener marks admission closed and terminates accepted sockets; finalizers
release capacity and unsubscribe streams. The regression passes on Windows and
Linux.

Windows required explicit handle closure because handler `makefile` wrappers
retain socket references. The implementation uses public `detach` and
`socket.close` APIs after shutdown, invalidating the socket object before closing
its handle so later wrapper cleanup does not double-close a reused handle.
Only expected closed-socket errors during retirement are quiet. An unrelated
route I/O failure still logs, including during shutdown.

This does not cancel arbitrary application work already executing in a handler,
and it does not make the app immune to a network flood. It closes retired network
connections and prevents admission to the retired listener.

Evidence: the listener-close regression, Windows/Linux test logs, and
[Python socket lifecycle documentation](https://docs.python.org/3/library/socket.html).
Issue: [#129](https://github.com/MaverickArcane/EliteLab/issues/129).

### #131 - Request framing accepted non-HTTP integer syntax

**Low; parser consistency defect.** Both handlers used Python's `int` parser for
Content-Length, accepting values such as `+2` and `0_2`. The dashboard's check for
Transfer-Encoding also treated an empty header value as if the header were absent.
Real HTTP tests reached the mutation receiver and returned 200 for these inputs.

Both lengths now require ASCII decimal digits, allowing only surrounding HTTP
space/tab whitespace. Any Transfer-Encoding header is rejected, including an
empty one. Valid requests still work, while malformed requests return 400 before
state changes. Missing or zero-length dashboard bodies retain their existing
intentional behavior; party reports still require a nonempty body.

No proxy desynchronization or cross-user request-smuggling chain was demonstrated.
The confirmed result is inconsistent parsing of malformed messages, not a claim
of account takeover.

The input review also added handling for JSON decoder recursion failures. The
regression forces that decoder error at the parsing boundary because actual
nesting behavior differs across Python versions. An initial test using a fixed
depth was not a valid Windows reproduction: Python 3.14 accepted that nesting.
That failed test log is retained; it is not counted as proof of a Windows exploit.

Evidence: `review-reproductions-before.log`, the final boundary regressions, and
`deep-json-before.log` with the test-limit explanation above.
Issue: [#131](https://github.com/MaverickArcane/EliteLab/issues/131).

### #132 - A stalled dashboard body produced a server error and traceback

**Low; error handling and diagnostic disruption.** Sending a partial JSON body
and waiting beyond the socket timeout previously produced HTTP 500 and an
application-error log. The handler then attempted another keep-alive read on a
timed-out file object, producing another traceback. The request did not reach
the mutation callback.

The regression shortens the socket timeout to reproduce this without waiting
30 seconds. The fixed body reader converts the timeout to HTTP 400, records the
bounded rejection category, and closes the connection. The callback remains
uninvoked, no application exception is logged, and no second request is attempted.

Evidence: the body-timeout test in `test_security_review.py` and before/after logs.
Issue: [#132](https://github.com/MaverickArcane/EliteLab/issues/132).

### Test reliability correction - Overload may close before a 503 is readable

The first fresh full suite failed on Windows because a capacity test demanded
HTTP 503 from every rejected socket. Admission rejection intentionally uses a
nonblocking, best-effort response; Windows can instead report an aborted/reset
connection. Requiring a fully delivered response would contradict that contract.

The test now accepts either 503 or the specific connection-closed exceptions.
It still fails on timeouts or successful admission, verifies that worker counts
stay capped, and checks another peer and later recovery. No limit was increased
and no network test was skipped to obtain a pass.

## Implementation coverage

The review covered the complete branch change set against staging, plus the
callers and lifecycle paths affected by those changes. It is not a claim that
every line in every unchanged module has been independently audited.

| Area | Review performed |
| --- | --- |
| HTTP admission | Limits before worker creation; per-peer/global accounting; worker-start failure; stream quotas; disconnect and shutdown cleanup; nonblocking overload response |
| Party admission | Initial and post-read token checks; token rotation; identity-secret binding; no secret in shared roster; close acknowledgements; real rehost regression |
| HTTP request processing | Host/origin checks and authentication ordering; duplicate/empty/framing headers; body size/type/completeness; timeout behavior; malformed JSON; static path containment |
| Error evidence | Fixed categories and bounded counters; suppression counts; request data/credentials excluded; meaningful application failures preserved |
| Browser policy migration | Every changed template and stylesheet rule; escaped attributes; bounded percentages/colors; observer scope; direct CSS property use; no general CSS declaration or URL setter |
| UI compatibility | Gauges, colors, map keys, hidden recipe/farming details, layout controls, sign-in state; browser suites exercise major workspaces and responsive layouts |
| Packaging | New security helper in shared Debian/macOS manifest; Windows folder copy; isolated packaged imports; Windows embedded-runtime launch/restart; Debian build |
| Delivery | Beta version/tag identity and staging ancestry checks; CI dependency before publish; draft/prerelease handling; source/archive checksums; no changes to workflow permissions |

The strict CSS probe remains conditional: no remotely reachable HTML injection
sink was established. The capacity limits remain resource bounds, not a guarantee
against distributed or volumetric denial of service. The source-assisted review
does not certify real Tailscale ACLs or the owner's firewall.

## Validation record

The final machine-readable results and exact source hashes are in
`artifacts/security-review/review-manifest.json`. The raw evidence preserves the
initial failing tests as well as the final passing runs.

- The final Windows suite reports 831 tests: 820 executed successfully and 11
  skipped. Linux also reports 831: 829 executed successfully and two skipped.
  Both runs use committed runtime fixes `5c5e20c`.
- Seven new review regressions cover framing, body timeout, decoder error,
  listener retirement, atomic invitation recheck, and real party rehosting.
- The HTTP regression also verifies unrelated I/O errors remain visible during
  shutdown.
- All 11 browser suites passed: main, release, PTN, restart, mining, rares,
  trade-to-Powerplay, history, targets, material plan, and expedition.
  Main and restart were repeated on the final committed runtime after narrowing
  the shutdown exception handling; both passed again.
- All 39 existing live boundary probes passed after the review fixes.
- Windows portable bundle build and embedded-runtime smoke test passed; Debian
  package build and shared packaged-source import/discovery checks passed.
- Bandit retained the same 208 findings (1 high, 16 medium, 191 low), with no
  scan errors or added findings. The high warning remains a SHA1 route identifier,
  not a credential or signature primitive.
- Semgrep is rerun with the prior `p/python` and `p/javascript` configuration.
  It ran 219 rules on 129 targets and retained the same five source findings.
  Its source findings and comparison are preserved. The tool can report zero
  top-level errors while recording per-function taint fixed-point timeouts in
  `time.fixpoint_timeouts`; this run records 42 such entries. They are coverage
  limits, not a complete analysis
  pass. The prior report did not make that distinction clear enough.
- An additional Semgrep security-audit/secrets scan ran 146 applicable rules
  over 348 targets, with five findings and no top-level errors. These are a SHA1
  route identifier plus four generic urllib call-site warnings: two shared
  provider helpers and two runtime-download build scripts. Reviewed helper
  callers construct fixed provider hosts; build downloads use fixed URLs and
  verified hashes. No request-controlled `file://` path was established. These
  are separate scan results, not the same five findings as the language scans.
- Final ZAP completed 1,342 active requests with zero high or medium alerts,
  one low timestamp observation, and 16 informational alert records. Its passive
  queue drained. Nmap checked the three exact final test ports. Both used freshly
  started synthetic apps on the final runtime source; exclusions and raw results
  are preserved.

The Linux run under WSL cannot resolve the Windows worktree's Git metadata with
Linux Git. Its Git-dependent manifest check may skip for that reason. The same
manifest is checked on Windows and exercised through the real Debian source
copier/package build; this limitation is not presented as a Linux Git pass.

Native macOS package installation and native installer UI checks still require
their platform CI runners. Those release checks and a real host-plus-two-friends
Tailscale exercise remain delivery gates. Local loopback and package checks do
not stand in for a real multiplayer acceptance run.

## Merge boundary

The implementation fixes and regression evidence are local on the review branch.
The four review issues remain open until delivery. The next step after a clean
review verdict is to merge through staging, run required CI/package jobs, then
prepare a new numbered beta with release notes and repeat the multiplayer test.
Published Beta 1 remains unchanged. No files from this review belong on the
Desktop; all review artifacts stay under the repository's `artifacts` directory.

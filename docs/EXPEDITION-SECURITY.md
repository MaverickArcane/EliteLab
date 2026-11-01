# Expedition security review

Scope: the expedition/research modules, their shared HTTP/MCP boundary, external
API reads, saved state and browser rendering. This is a source and regression
review, not a claim that the application is free of every vulnerability.

## Findings fixed

| Finding | Change and regression coverage |
|---|---|
| Matching attacker-controlled Host and Origin could pass write checks after DNS rebinding | Validate Host on all requests; allow loopback, IP literals, configured bind host and explicitly trusted DNS names. Test hostile matching Host/Origin and malformed authorities. |
| API error responses could expose local exception details | Return a generic 500 message; keep details in local logs. Test that a simulated private path is absent from the response. |
| Static path checks followed symlinks outside the mounted root | Resolve real paths before the boundary check. Test on systems with symlink privileges. |
| Compressed Coriolis modification data expanded without a bound | Read at most 64 KiB plus one byte, reject larger output before parsing. Regression uses highly compressible input. |
| Community API responses were read without a size bound | Cap JSON responses at 8 MiB before decoding; preserve request timeouts. |
| Ambiguous body framing and unbounded socket waits | Reject duplicate Content-Length and Transfer-Encoding, validate lengths and incomplete bodies, set a 30-second socket timeout. |
| Missing browser defense headers | Add CSP with same-origin scripts/connects, no frames/objects/base overrides; nosniff, DENY framing and no-referrer. Desktop/mobile browser checks exercise normal operation. |

## Controls verified

- Existing bearer/session authentication covers new API routes. Cross-origin
  mutations remain blocked; cross-site browser API reads are also rejected.
- Spansh destinations are form fields, not network destinations. Result polling
  uses a fixed HTTPS origin and a restricted job ID. Endpoint/result mismatches
  and invalid waypoint numbers cannot become navigation instructions.
- Route mutations are commander-scoped and serialized. Failed saves preserve
  the previous published plan; stale clear requests require the expected ID.
- Material timestamps reject older replay contamination, and a Commander / Materials / LoadGame startup sequence retains its baseline.
- Synthesis is read-only planning. Shared-material budgets sum costs exactly;
  recipe requests do not spend or reserve inventory.
- Journal and API text is HTML-escaped. Adversarial system-name browser tests
  verify that tags remain text. CSV formula-leading names are prefixed safely.
- No game input, subprocess execution, arbitrary URL fetch, credential storage
  or journal upload is introduced by these modules.

## Deployment boundary

EliteLab defaults to loopback. For a trusted DNS name behind a reverse proxy or
on a private network, set `ELITELAB_ALLOWED_HOSTS=lab.example` (comma-separated,
hostnames only). Existing IP-address URLs work without this setting. Host
validation is not authentication: configure `ELITELAB_AUTH_TOKEN` and use a
trusted TLS proxy for access beyond your local machine. The stdlib HTTP server
is not an internet-facing production server.

SSE exposes the authorized dashboard state, including commander identity and
loadout context. No personal runtime data is included in the publication tree.
Local journal files and local processes are within the trusted-machine boundary.
The symlink regression is skipped on Windows when symlink creation privileges
are unavailable; Linux CI exercises it.

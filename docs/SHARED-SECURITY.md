# Shared-server security gate: private prototype

Status: proposed design for #90 and #42. This is not implemented, not an
independent security approval, and not a claim of compliance with a standard.
Its scope is an isolated two-player prototype with synthetic data. A public
service requires a separate design, review, deployment decision and release gate.

## Concrete prototype choices

- Run a separate group service on the host's loopback interface. Use HTTPS
  through a locally managed reverse proxy; the prototype binds only to its own
  loopback interface behind that proxy. Two machines reach the host through an
  authenticated private encrypted network configured by the operator. Public
  forwarding, automatic certificates and Internet discovery are out of scope.
- The proxy must authenticate its server certificate to each client. Pinning
  the host certificate or explicitly trusting a test CA is an operator action;
  no disabled verification or trust-on-first-use fallback. Document how to
  rotate a test certificate. Reject non-loopback backends and untrusted proxy
  headers; configure the exact external origin instead of trusting Host or
  forwarded headers for security decisions.
- The host creates the first administrator in a local interactive bootstrap.
  This action is unavailable over HTTP and prints a one-time enrollment secret
  only on the host's terminal. The host's local client exchanges it once to
  enroll the administrator's device credential, then the server consumes it.
  Never put a secret in a URL, source file, screenshot, application log or
  example transcript.
- The first prototype has server-generated account IDs and one device credential
  per account. A player accepts a leader's one-use invitation and creates an
  independent, random device credential. The invite binds membership and role,
  not identity from the game. Subsequent device login uses that credential. A
  new device requires a new invitation and account for now; account merging and
  multi-device enrollment are deliberately disabled.
- Generate invite, device, browser pairing and browser session secrets using an operating-system
  CSPRNG, at least 256 random bits. Transmit secrets only in authenticated HTTPS
  request bodies or authorization headers, never query strings. Store only
  verifiers for high-entropy random secrets, compare in constant time, never log
  them, and rate-limit redemption and login by account, invitation and source.
  The design does not invent a password hashing scheme: passwords and email
  recovery are out of scope for the prototype.
- Prototype device credentials are stored in a private local file with a
  restrictive ACL or file mode and a warning that local malware or a local
  administrator can read them. Verify the permissions after creation; refuse to
  run the prototype if they cannot be restricted. Do not claim OS keychain
  protection. Real desktop distribution needs an OS credential-store design.
- A local client uses its device credential over authenticated HTTPS to request
  a one-use browser pairing secret. The player enters that secret into a browser
  form; the server atomically consumes it and issues an opaque random session
  cookie. The raw device credential stays in the local client. Neither secret is
  written into page URLs, localStorage, sessionStorage or a JavaScript-readable
  cookie. Pairing secrets expire after five minutes, are bound to the requesting
  device and cannot be reused. The server stores only pairing and session
  verifiers. Use `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/` and no domain
  attribute for the session cookie. Rotate the session on
  authentication and role changes. Enforce a 30-minute idle timeout, a 12-hour
  absolute timeout and explicit server-side logout. Cookie-authenticated mutations also require a
  per-session CSRF token and exact Origin verification; CORS defaults to deny.
  Never accept the CSRF token as proof of identity.

These are choices for a private experiment, not a finished onboarding design.
The operator controls the machine, proxy, backups and database and can inspect
or alter server-side group data. Neither the prototype nor TLS protects against
that operator or malware on the host or a player device. Participants must know
this before sharing; do not offer private journal upload in the prototype.

## Trust boundaries and assets

| Boundary | Attacker or failure | Required outcome |
| --- | --- | --- |
| Remote network to proxy | Eavesdrop, alter requests, spoof proxy headers | TLS validation, private-network gate, trusted proxy configuration |
| Browser to service | Cross-site request, stolen session, script injection | Same-origin/CSRF checks, bounded session, escaped untrusted content |
| Device to service | Forged account, replay, credential leakage | Per-device credentials, authorization on each request, no token in logs |
| Member to group | Guess IDs, change another person's progress, access private records | Deny by default and resolve membership and role on every operation |
| Stream or MCP client | Reuse old authorization or call a broader local tool | Scope each event/tool call; close or expire streams after revocation |
| Host storage and backup | Corruption, stale restore, stolen disk | Restrictive access, encrypted offline backups, tested restore and rotation |
| Old local EliteLab services | Reuse a single-user global state or shared token | Separate service and credentials; local-only workflow stays independent |

An Elite Dangerous FID, commander name, source file path or journal timestamp
is untrusted context. None authenticates the caller. The prototype does not
claim to prove ownership of a commander.

## Invitations, membership and loss

An administrator or group leader creates a role-limited invitation for one
redemption, expiring within 24 hours or earlier if revoked. The server stores a
verifier and metadata, never the raw invitation. Generate and display the raw
secret once; the leader sends it through a channel they trust. Redemption is an
atomic transaction that consumes the invitation, creates the account/device
binding and membership, and creates no broader role. Simultaneous redemption
has one winner. Failed attempts are rate-limited without revealing whether a
secret exists. An unused invite can be revoked; expired or redeemed invites
cannot be replayed. Rate limits persist across restart and have documented
operator recovery so an attacker cannot permanently lock out an account.

A member can revoke their own credential and sign out. A leader can remove a
membership; that group access and its streams cease immediately, but this does
not delete the account or its other memberships. Administrators can revoke a
compromised device. Revocation invalidates associated sessions and active
streams; the next request is denied. A player can turn off each status category,
which removes its current group-visible value transactionally. The first
prototype keeps only the latest shared snapshot, no status history. Plan and
progress retention and backup expiry are specified below.

If the only device credential is lost, there is no automatic self-service
recovery in the prototype. The group leader removes the old membership and
invites a new account after an out-of-band identity check. The old account is
not silently merged into the new one. Its progress remains associated with the
old account until explicitly deleted; the host may document a manual migration
only after an audit. Leader loss requires host-console recovery by the trusted
operator, with other participants informed. Production recovery and ownership
transfer require a separate review.

## Authorization matrix

All actions require a current account, current group membership and an explicit
role; a missing or unknown role denies. The service uses server-side account and
group IDs, not caller-supplied identity fields, to scope queries and writes.

| Operation | Leader | Member | Viewer | No membership / revoked |
| --- | --- | --- | --- | --- |
| Read shared plan and opted-in current status | yes | yes | yes | deny |
| Create/revise/reorder plan and steps | yes | deny | deny | deny |
| Create/revoke invitation or remove member | yes | deny | deny | deny |
| Set own manual progress | yes | yes | deny | deny |
| Change own sharing/revoke own device | yes | yes | yes | no membership: own account if authenticated; revoked: deny |
| Read others' private data | deny | deny | deny | deny |
| Host bootstrap, backup, restore and recovery | host console only | host console only | host console only | host console only |

A leader cannot grant a role above their own or remove the last leader through
the group API. Cross-group references are validated against the same group in
the same transaction. A leader can read shared status and group progress, not
an unshared private journal. Group viewers see member display names only after
members explicitly opt in; absent consent, use a stable group-local pseudonym.
All role changes invalidate affected browser sessions and streams; stream
consumers reauthenticate and reauthorize after reconnect. MCP tools use the
same account and group checks and return only scoped results. No global state,
raw journal, personal token or unfiltered event stream is exposed through MCP.

## Data, retention and restore

Status sharing defaults off per category. The prototype permits current system
and observation time only; each field is optional, bounded, and marked stale
based on receipt time. The server keeps the latest snapshot per device; turning
sharing off removes the current shared value. Client queues contain only the
latest allowed snapshot and have a fixed size; overflow requests a fresh snapshot.
Device sequence and duplicate handling follow `MULTIPLAYER-PLAN.md`.

Keep plan revisions and manual progress until the group is deleted. A leader
may remove a plan; the prototype uses a deleted marker until the group deletion
process completes so clients cannot resurrect it with stale edits. Delete a
removed member's current snapshot immediately and revoke access immediately;
retained manual progress is visible to leaders and the former member only if
still authorized by an explicit export path. Complete account deletion removes
its credentials, sessions, snapshots and progress from the live store, replacing
any necessary plan audit attribution with a non-identifying tombstone.

A host-operated daily encrypted backup is kept for at most seven days in the
prototype; encryption keys are stored separately by the host. Backups may
contain data deleted after the snapshot: document the seven-day maximum before
sharing begins. Restore is an offline operator operation and must not reactivate
old credentials, sessions, invitations or sharing consent: restore group content
into a quarantined instance, invalidate all credentials and invitations, set
sharing off, and require fresh enrollment before any network access. Restoring
content from before a deletion can resurrect that content; the host must retain a
separate deletion ledger outside the restored backup and replay it before
reopening, or decline the restore. If that ledger is unavailable, do not claim
that deletion survives restore. Test this with synthetic data before use.

## Validation gate

Before implementing or exposing the prototype, turn the matrix into tests for
HTTP, every stream subscription and event, and every MCP tool. Exercise leader,
member, viewer, removed member, revoked device and unrelated account against
own and other group resources, including guessed IDs. Check stale session and
role-change behavior, stream revocation, cross-site requests, malformed and
oversized input, token redaction, duplicate and concurrent invite redemption,
rate limits, server restart, offline retry and crash after commit before reply.

The test harness creates two groups, two leaders, a member, a viewer, an
unrelated account and a revoked device, with opaque synthetic IDs. For each
route and tool it tests: no credential and malformed credential are denied;
valid credential with wrong group, role or resource is denied; the allowed actor
succeeds; and a role change takes effect on the next request. Assert response
bodies, stream frames and timing-independent outcomes do not contain another
account's private data or credential. Try cross-group step and progress IDs,
including IDs embedded in batches and stale revision requests. Test both
cookie and device-token paths and every HTTP method, not just the visible UI.

For invitation and enrollment tests, redeem one invite twice and concurrently,
try a revoked and expired invite, simulate a crash after commit but before the
response, and confirm no second account or membership appears. Try invalid
origins, absent and wrong CSRF tokens, a session copied to a new context after
logout, privilege changes, idle and absolute expiry, and an already-open stream
when membership is revoked. Assert credentials never occur in logs or error
responses. For device status, test sequences 1, 1 (same bytes), 1 (different
bytes), 3 then 2, lost acknowledgements, quota overflow and restored local state.
A device may resynchronize without silently applying a stale observation. These
cases are a specification for future automated tests, not tests already run.

A separate integration test restores a backup after a deletion and verifies
that content, credentials, membership, sharing and invitations do not return.
Run a second test with the deletion ledger missing and confirm restore stays
quarantined. Test the public listener is disabled and certificate validation
cannot be bypassed by client configuration. Review proxy setup and threat model
before a two-person synthetic-data trial. Run the existing local-only and party
regressions with the group service absent.

## Explicitly deferred

Public hosting; password and federated login; self-service recovery; multi-device
accounts; long-lived journal upload; cross-device journal identity; personal
browser layout sync; inferred completion; onboarding beyond a private trial; and
production backup key custody. Resolve these in focused issues before expanding
the prototype. #89 and #91 are blocked on this gate and the implementation
review, not approval to expose a service.

## Reference material

- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default and authorize every request.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session renewal, expiration and secret handling.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): authentication and lifecycle guidance. The prototype does not claim NIST conformance.

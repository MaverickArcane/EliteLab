# Shared server and group objectives: proposed first slice

Status: design proposal for #42, not an implemented service or a release date.
The existing local dashboard remains the supported experience. Validate this
proposal with two real players before treating it as a deployment promise.

## Current starting point

- The local watcher replays recent journal files, tails new lines and publishes
  snapshots to a single-commander in-memory store. The dashboard's HTTP and MCP
  interfaces expose that store. A shared token on this server does not create
  separate users or isolate their state.
- The history index is a rebuildable local SQLite cache of selected journal
  evidence. Its source-file offsets are local bookkeeping, not global identities.
- Party is an opt-in LAN listener for bounded telemetry and a leader's trade
  plan. Membership and codes are ephemeral. It neither uploads raw journals nor
  provides durable accounts. Keep it available independently during any prototype.

## First useful shared session

One host invites one player to a private group. The host creates a titled plan
with a destination and ordered steps. The player sees the plan and marks their
own steps done. The host edits the plan; both see the new revision after a
refresh or reconnect. Each player may optionally share a narrow status summary
such as current system and last observed time, and can stop sharing it. The
host never sees the other player's unshared journal, credits, private dashboard
or browser layout. A viewer can read the shared plan but cannot edit or report
progress. Manual progress is the first version; game-derived completion is a
later, separately verified feature.

## Boundaries and roles

| Action or data | Leader | Member | Viewer |
| --- | --- | --- | --- |
| Read group plan and opted-in shared status | yes | yes | yes |
| Edit plan, reorder steps, invite or remove members | yes | no | no |
| Update own manual progress | yes | yes | no |
| Read another person's private journal or private dashboard | no | no | no |
| Change own sharing and revoke own device | yes | yes | yes |

This table is a proposed minimum, enforced server-side on every read, mutation,
stream and tool call. Membership alone never authorizes a private-data read.
Revocation blocks subsequent requests and closes or expires existing streams;
caches and backups have explicit retention and deletion rules. Define ownership
transfer and recovery before calling a hosted service production-ready.

## Proposed separation

1. A local client reads the player's journals and derives an allowlisted status
   locally. Sharing starts off and the user chooses each shared category.
2. A separately deployed group server owns accounts, group membership, plan
   revisions and the selected shared summaries. It never mounts another player's
   local journal folder. Its browser view and any MCP adapter go through the same
   permission checks; no direct database or global `/api/state` bypass exists.
3. A local queue sends only opted-in summaries in the first prototype. Raw event
   upload, durable private dashboard sync, and multi-device journal merging are
   later work with their own consent, retention and security review.
4. A secure transport is required for credentials and player data. The first
   test can use loopback or a private encrypted network; do not expose the
   existing party listener as an internet-facing account service.

Account IDs are server-assigned. A journal FID or commander name is evidence
about a game session, not proof that a user owns it. Binding, conflicts, renamed
commanders and multiple devices require an explicit ownership workflow; do not
merge two accounts based only on a display name or client-supplied FID.

## Status sync contract for the prototype

- Each device authenticates independently and can be revoked without replacing
  every device. A device may submit only to the account it was paired to.
- Submit a bounded, versioned snapshot with a device ID, monotonically
  increasing sequence and observation time. The server records receipt time and
  assigns its own revision. A retried sequence with identical content is
  acknowledged once; reused sequence with different content is rejected.
- Sequence is scoped to one enrolled device and durable across reconnects. If
  its local state is lost, enroll a new device; do not guess an earlier cursor.
  An offline queue has a size limit and a visible overflow/resync state.
- Last observation and last receipt are displayed separately; timestamps do not
  authenticate data and do not establish ordering between devices. A stale or
  disconnected player stays stale rather than being shown as live.
- Sharing changes are applied server-side and reflected in snapshots and streams.
  Turning a category off removes its current group-visible value and queues any
  historical removal required by the policy. UI and API state must agree.
- Journal-derived events later require a source-generation identifier and a
  stable position within that generation. Filename plus offset alone is not a
  cross-device identity. Handle truncation, replay, duplicate submission,
  crashes between durable commit and acknowledgement, and conflicting data
  before enabling event upload. Snapshot and event ordering are separate.

## Plan consistency

Plans and steps have stable server IDs and a revision. Mutations include the
revision read by the caller. On conflict, the server rejects the stale write and
returns the current revision; the UI offers reload instead of silently replacing
another leader's edits. Progress is keyed by group, plan, step and member. A
removed or reordered step retains an auditable identity; deletion semantics,
permissions and retention are specified before implementation. No completion
is inferred from a nearby journal event.

## Storage, recovery and operations

Keep group state in a server-owned durable store with schema migrations,
transactions and bounded writes. Define encryption and key ownership for
backups; a backup must be restorable in an isolated environment without
silently re-enabling revoked devices or invitations. Test interruption during
write and restore, version upgrades and rollback, disk-full behavior, backup
retention, data export and deletion. Keep credentials out of logs and fixtures.
Provide quotas and request limits for accounts, groups, devices, queue length,
body size and stream duration. Use TLS for network connections and require
explicit host setup; do not promise public hosting until authentication,
recovery, TLS and abuse controls have been reviewed and tested.

## Delivery and gates

1. **Contract and threat model:** settle account lifecycle, encrypted transport,
   invitation expiry and revocation, authorization matrix, data deletion,
   ownership recovery and conflict rules. Deliver a runnable two-user security
   test plan and decide deployment constraints before network implementation.
2. **Private prototype:** two accounts and devices on an isolated test server;
   durable plans, manual progress, opted-in status, revocation, reconnect and
   backup/restore. Verify permissions at the HTTP, stream and MCP boundaries.
3. **Real group trial:** two distinct commanders on separate machines, including
   a new player, test invitation, instruction changes, disconnect and recovery.
   Record consent and observations without publishing private journal data.
4. **Expansion:** only after the earlier gates, decide whether journal uploads,
   synced private layouts and journal-derived progress are needed. Scope each
   separately with privacy, identity, ordering and retention tests.

## Required adversarial and recovery tests

- A member, viewer, revoked device and unrelated account try every read, write,
  stream and MCP operation, including guessed IDs and cross-group references.
- An invitation is replayed, expired, revoked, guessed and used concurrently;
  credentials never appear in logs, URLs, screenshots or errors.
- A device submits duplicates, conflicting sequence values, old or malformed
  versions, oversized payloads and a snapshot after revocation. A disconnect
  and crash after server commit but before acknowledgement does not duplicate it.
- Two leaders submit conflicting edits, a step is removed during an update, and
  reconnect restores the current plan and permitted progress only.
- Restart and backup/restore preserve permitted state and do not resurrect
  removed membership or leak withdrawn data. A failed migration leaves a
  usable backup and a documented recovery route.
- Both local-only dashboard and existing party flows continue to work with the
  shared server absent. Do not claim compatibility until tested end to end.

## Open decisions before implementation

The private-prototype choices and threat model are proposed in
[SHARED-SECURITY.md](SHARED-SECURITY.md). Public hosting, production recovery,
backup key custody, broader status categories and any journal upload still
require separate product and security decisions.

# Group-plan prototype: domain layer

This directory is an isolated work in progress for #89. It is not loaded by the
existing dashboard, exposed over HTTP or MCP, or included in release bundles.
It has no enrollment, invitation, browser session, CSRF protection, rate
limiting, transport, streaming, backup/restore or graphical interface. Do not
use it as a shared service or store real player data in it.

The plan functions check a 32-byte device credential against its SHA-256
verifier and check current group membership and role within each transaction.
The caller must initialize each new SQLite connection, protect the database and
device credentials, and only use cryptographically random credentials. Tests
seed synthetic memberships and devices directly; they do not prove a safe
enrollment workflow. An authenticated service must not trust a client-supplied
account ID. Plan updates use optimistic revisions; step identities survive
reordering, and removed steps and progress remain retained. Only active steps
are returned to the current account.

Before any integration, implement and test all relevant requirements in
`docs/SHARED-SECURITY.md`, including session and invitation lifecycle, roles and
revocation for HTTP, streams and MCP, durable recovery, and two-client browser
testing. This early domain layer alone does not complete #89.

# Frontier Companion API investigation

Status: investigated for #6; live access is blocked on EliteLab's developer
registration. The owner confirmed on 2026-11-03 that no application is registered.
No authenticated requests have been made and no integration is shipped.

## First useful feature

Investigate an explicit refresh of the owner's carrier inventory and orders when
journal evidence is incomplete. Keep the response separate from journal-derived
stock until commander identity, carrier identity, observation time and field
semantics are validated. A response must not silently change an active hauling
operation or turn missing inventory into zero.

## Access

[EDCD's registration notes](https://github.com/EDCD/FDevIDs/blob/master/Frontier%20API/FrontierDevelopments-oAuth2-notes.md)
describe applying through the Frontier account portal and obtaining approval,
an application client ID and a registered redirect URI. Desktop applications use
OAuth authorization code with PKCE. The owner must complete registration at
https://user.frontierstore.net/ and consult the developer documentation available
to that account. The public documentation endpoint returned HTTP 403 during this
investigation, so current registration acceptance and redirect restrictions have
not been verified. Do not borrow another application's client ID.

## Data evidence and limits

[EDMC's implementation](https://github.com/EDCD/EDMarketConnector/blob/main/companion.py)
uses profile, market, shipyard and fleet-carrier requests, with separate Live and
Legacy service hosts. It also handles missing and inconsistent response shapes.
Its query cooldowns are implementation choices, not a published Frontier quota.
This establishes a useful implementation reference, not proof that EliteLab's
future registration grants every field or that data is always current.

## Implementation gate

After registration, validate the approved callback and scopes with synthetic
OAuth tests, then one explicit owner-authorized connection. Verify state and PKCE,
single-use callbacks, cancellation, token expiry, refresh failure, disconnect,
account changes, stale replies and unavailable carrier data. Decide and test
platform credential storage before persisting refresh tokens. Keep credentials
out of dashboard state, MCP results, logs and diagnostic exports.

Capture a redacted field inventory from authorized responses and compare it to
the game and existing journal evidence. Only then choose the carrier fields and
refresh behavior to expose. #6 remains open until this gate and its agreed
implementation scope are resolved.

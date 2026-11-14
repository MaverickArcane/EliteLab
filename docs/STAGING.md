# Private staging with friends

Use one candidate build on every machine. Each player runs their own dashboard
and reads their own local game journals. The carrier owner hosts the existing
party listener over Tailscale; there is no central account server to deploy.
This guide does not claim that a real group session has already passed.

## Start and join

1. The organizer builds a portable candidate with `python scripts/build_windows.py`
   and distributes that same ZIP to every Windows tester. Extract it into a new
   folder. Use **Start staging.cmd**, including on the owner's machine. This uses
   bundled Python and does not install, upgrade or restart the regular app.
2. Leave the terminal open. Staging opens setup at `http://127.0.0.1:18766/`.
   Select your own game journal folder. Journals are read, not copied to the host.
   State, settings, locks and logs use `~/.elitelab-staging/friends/`. Browser
   storage is separated from the usual dashboard by staging's different port.
   Staging overrides inherited EliteLab configuration and keeps the dashboard on
   loopback. Use only staging controls during the session; keep port 18766 fixed.
3. Join the organizer's private Tailscale network using its normal invitation
   process. Restrict access to the participating devices and the party TCP port.
   No router forwarding or public dashboard exposure is needed.
4. In **Carrier ops -> Connect crew**, the owner hosts on their Tailscale IPv4
   address and **18767** (separate from the normal party default of 8767).
   Allow that TCP port from the participating Tailscale addresses in the host
   firewall. If access fails, check both the host firewall and tailnet policy.
5. Privately share `http://<owner-tailscale-ip>:18767` and the generated party
   code. Friends join from **their own staging dashboard**, not the owner's
   dashboard URL. The party protocol uses HTTP inside Tailscale's encrypted
   network. Never post the code in reports or screenshots.
6. Verify all participants appear, then create/start the carrier job. Closing
   the host app ends its party. Host again and share the new code after restart.
   Saved plans and receipts persist; live membership must reconnect/rejoin.

The regular application may continue running. Staging has independent saved
plans: actions in one dashboard do not update the other. A busy staging port is
an error to investigate, not a reason to kill another application.

For source users with Python 3.10+, on Windows/Linux/macOS:

```sh
python -m elitelab.staging run
python -m elitelab.staging collect --prompt
```

Optional `run --journals PATH` selects a journal folder explicitly; `--offline`
disables external market lookups for fixture testing, and `--no-browser` keeps
the browser closed. `--profile NAME` before `run` or `collect` selects a separate
staging profile; if running multiple profiles, give each a distinct `--port`.
Use the same profile when collecting its logs. Setup restart is supervised;
the staging host/port/data isolation remain fixed across restart.

## Report a problem

While staging is running or after it stops, double-click **Collect staging
logs.cmd**. Enter what you were doing, expected versus actual result, and the
approximate time. The reports folder opens with a uniquely named ZIP. Send that
ZIP privately to the organizer. Collection works without a running server.

The ZIP contains the last run's build fingerprint/version, collector environment,
problem note, and up to three 1 MiB recent server logs. Logs rotate automatically;
collect soon after the problem. URL strings, home paths, labelled secrets and
long credential-like identifiers are redacted before log storage and again at
export. Settings, raw journals, saved plans, party state, credentials and instance
locks are excluded by an exact file allowlist. The ZIP is a copy; it does not
clear logs, stop the app, or send anything automatically.

Review the ZIP before sharing: redaction is best effort and logs/notes can still
contain commander, system or station names and non-home file paths. Browser
console errors and screenshots are not captured automatically. For a UI-only
problem, include a screenshot with codes hidden and describe the workspace,
button and visible error. Do not attach complete journals unless separately
needed and reviewed. Old reports remain in `reports/` until manually removed.

## First group session (owner plus at least two crew)

Record each participant's ZIP, role, operating system and approximate event time.
Compare `run.json` build fingerprints before diagnosing cross-client behavior.

| Exercise | Expected evidence |
| --- | --- |
| Join from two machines | Distinct members; each dashboard retains its own commander |
| Start mining/loading job | Whole-tonne quotas sum correctly; all clients see the same job |
| Mine and sell to carrier | Production alone does not count as delivery; matching sales count once |
| Disconnect/rejoin one crew | Stale/disconnected state is visible; no duplicate contributions |
| Restart crew and then owner | Saved progress survives; new host invitation restores the session |
| Late join or quota change | Explicit revision/preview; existing contributions remain intact |
| Depart, unload, prepare PTN advert | Checked stock/order/buyer guards work; actual sales advance unloading |
| Collect a ZIP during and after run | Files open, build IDs match, secrets absent, report describes failure |

Track observed game stock/payouts alongside the dashboard; estimates are not
proof of a game transaction. Use [Group mining](GROUP-MINING.md) and
[PTN trading](PTN-TRADING.md) for the complete operation. Actual game orders,
carrier jumps and Discord posting are manual player actions.

Do not promote a candidate until all participants' builds match, reconnect and
receipt checks pass, and failures have reproducible reports. Packaging/desktop
release checks remain in [Release packages](RELEASE-PACKAGES.md).

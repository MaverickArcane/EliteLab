# Unlock and nearby supply research

The `progression` module provides four read-only tools:

| Tool | Answers |
|---|---|
| `get_permit_status(system)` | Was a permit grant recorded? What separate travel evidence exists? |
| `get_faction_reputation(faction)` | What was the latest absolute minor-faction reputation, and is that faction present in the last observed system snapshot? |
| `get_mission_progress(faction, limit)` | Which accepted missions and outcomes were observed, including commodity rewards? |
| `get_engineer_unlock_progress(engineer)` | Reviewed referral chains, invitations, meeting evidence and donations for ten engineers |
| `list_engineer_unlocks(engineer)` | List reviewed engineer locations, observed access and next steps |

`MissionCompleted.PermitsAwarded` is grant evidence, not an exhaustive permit
inventory. Missing evidence is **unknown**, never proof that a permit is absent.
Travel observations and plotted routes do not establish current personal permit
ownership. The latest ship jump is retained separately from later docking or
carrier travel; Qwent's next-step advice uses it to avoid recommending a permit
grind merely because grant history is missing. No CAPI authorization or complete
permit list is available here.
Faction reputation comes from `Factions[].MyReputation`, never mission reward
indicators or superpower reputation. A faction's old reputation can remain known
while it is absent from the current system; each carries its observation time.
Mission boards and their available rewards are not exposed by journals.

Reviewed workflows cover **Farseer, Martuuk, Qwent, Palin, Dweller, Ryder, Tani,
Tarquin, Nemo and Cheung**. See [flight and upgrade research](FLIGHT-RESEARCH.md)
for rank/statistic evidence and limitations. Other engineers remain available
through `get_engineer_access`. Qwent's source is
[Inara](https://inara.cz/elite/engineer/7/), reviewed 2026-10-31: referral from
Elvira Martuuk, Sirius Corporation invitation, and 25 Modular Terminals.
Known, Invited and Unlocked are separate journal states. Recorded cumulative
`EngineerContribution.TotalQuantity` is replay-safe; absent donation history is
unknown, not zero. Cargo is separately timestamped and excludes stolen units.
An unlocked engineer never gets a recommendation to donate again.

The `sourcing` module provides `find_commodity_sources`. Example:

```json
{"commodity":"Modular Terminals","quantity":25,"max_distance_ly":25,"max_days":2,"carriers":"include","pad":"L"}
```

The origin defaults to the ship's system; `reference` overrides it. Radius is
strict (1-500 Ly), defaults to 25 Ly, and is never widened automatically. This
is a buy-source search, separate from the existing trading planner. Carriers
are included by default. Their docking access remains unknown and their
reported location/stock is not guaranteed. Read `updated_at`, `age_hours`,
`distance_ly`, `stock`, and `cost_for_quantity` before recommending travel.

The tool uses [Ardent's nearby exports endpoint](https://github.com/iaincollins/ardent-api),
resolves commodity aliases from its catalog, queries matching aliases (up to
four), and deduplicates markets using the newest report. Catalog aggregate
stock is not used to exclude commodities: carrier-only supplies can have zero
aggregate stock. Coordinates independently enforce the radius; unknown
coordinates, invalid/future/stale dates, insufficient stock and unsuitable or
unknown pads are excluded. Results are sorted by measured distance, then price.
Explicit origins resolve through EDSM when not the current journal system.

Ardent returns up to 1000 price-ranked reports per alias. A capped response is
marked; even uncapped responses are community coverage, not proof of all supply.
No matches means no matching reports within the requested radius. Provider or
coordinate failures are errors, not successful empty searches. Market results
use the shared five-minute cache; catalog names cache for one hour. Network
requests run only in tool calls, never journal handlers.

## State and verification

`progression.json` persists commander-scoped evidence in the local data directory.
FID is preferred; name is a fallback. Startup reads all available journal files
outside the watcher handlers, then normal replay/live events update by timestamp.
New session headers reset stream identity. Older replay cannot switch the active
commander or regress newer evidence. Cargo files have no FID and are accepted
only if timestamped at or after the active commander session. Missing old logs
still limit coverage; cached evidence survives removal of old logs.

`progression` store namespace contains commander, last observed location and
history file count. Evidence collections are returned by the targeted tools.
The `sourcing` module has no persisted state. Neither module changes the game,
build pin, wishlist or trade plans.

[Frontier's journal manual](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf)
documents permit rewards, faction observations, mission lifecycle and cumulative
engineer contributions. Regression fixtures live under
`tests/fixtures/journals/progression`; tests are in `tests/test_progression_sourcing.py`.

Backend changes require an EliteLab restart. Refresh the MCP tool list/reconnect
the client to discover the tools. The `engineer_unlock` MCP prompt describes
the intended tool sequence and evidence limitations.

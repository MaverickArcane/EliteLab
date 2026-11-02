# Mission supplies

The Mission supplies dashboard card reads accepted missions automatically. Expand
a mission for its required commodity, allocated cargo, recorded deliveries,
deadline, pickup/search system and hand-in station. Find supplies searches for
the combined source-and-return shopping list. The same functionality is exposed
as `get_mission_plan` and `find_mission_sources` over HTTP, CLI and MCP.

Search defaults: current ship system, 25 Ly strict radius, large pads, stations
only, reports at most two days old, three alternatives per commodity. Radius,
pad and optional carriers are configurable. Nothing silently widens the radius.
Fleet carrier location/access and local commodity legality remain unverified.
Results include stock, report time, arrival distance and estimated purchase cost.
Nearest suppliers are grouped into stops; this is not route optimization.

Cargo is allocated once, in deadline order. Untagged, unstolen cargo can cover
source-and-return needs. Mission-tagged cargo stays with its own mission.
Delivery missions require the origin depot's assigned cargo, and salvage missions
require mission-tagged items at their destination. Mining and unrecognized
mission types retain their instructions without assuming purchases qualify.
Completed, failed and abandoned missions disappear. Expired records remain visible
with a warning but do not create shopping needs. Ready-to-turn-in jobs are not shopped.

## Evidence and boundaries

Progression retains MissionAccepted Commodity, Commodity_Localised, Count, Wing,
acceptance time and origin from chronological Location/Docked events. CargoDepot
counts are cumulative. Progress is not used as a completion percentage.
MissionRedirected updates the destination without terminating the mission.
Missing depot reports leave delivered quantities unknown; an unreported partial
delivery can overstate a shortage. Missing/currently changing inventory blocks
automatic shortage calculations until a Cargo inventory snapshot arrives.
Cargo markers, depot events and mission completion invalidate older inventory.
Snapshots older than the active commander session are excluded.

Available mission boards and unrecorded reward options cannot be read. Cargo
allocation is a planning estimate, not an in-game reservation. The tools never
purchase cargo, accept missions, change the route or move a carrier.

The progression namespace publishes active_missions, cargo and cargo_changed_at.
The missions namespace publishes plan for SSE/dashboard updates. Network searches
run only in the sources request, with up to three concurrent commodity lookups
using the shared cached Ardent client. Individual lookup failures preserve the
checklist and successful results for other commodities. modules/sourcing and
modules/missions share elitelab/core/commodity_sources.py and never import each other.

Schema reference: Frontier's Player Journal manual, CargoDepot, MissionAccepted,
MissionRedirected and Cargo sections:
https://hosting.zaonce.net/community/journal/v20/Journal_Manual_v20.pdf
Also checked against local 2026-11-01 journal events for collect, delivery and
illegal salvage missions. Fixtures use future deadlines to keep tests stable.

Validation: tests/test_mission_supplies.py covers lifecycle, partial deliveries,
replay, origin, aliases, inventory allocation, unknown/stale evidence, commander
isolation, bounded searches, grouped stops and partial provider failure.

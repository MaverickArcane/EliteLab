# Expedition workspace

Choose **Layout > Expedition** for neutron waypoints, ship readiness, synthesis,
current location and the star map. The next waypoint has a copy button; the map
shows the next five reported waypoints. Nothing controls the game or changes the
clipboard without a click.

## Plan and fly

1. Enter a destination. Origin defaults to the observed ship system. Normal range
   defaults to the available full-fuel/full-cargo estimate, rounded down. Check
   it after changing the ship or fit; never enter an already boosted range.
2. Plan submits a form to [Spansh](https://spansh.co.uk/plotter). The fitted
   Caspian special size-8 Mk II FSD selects 6x; other or unverified drives select
   4x. Manual overrides are available under Route options.
3. The card checks a queued job every five seconds, for up to five minutes per
   mounted card. Check result resumes checks. Network errors preserve the job.
4. Plot the next waypoint in the galaxy map. A waypoint leg can contain several
   ordinary jumps. Arrival advances saved progress; intermediate systems do
   not discard the plan. A new ship/fit prompts a range check and a new plan.
5. Refuel at scoopable K/G/B/F/O/A/M stars as needed. This basic Spansh endpoint
   does not plan fuel stops. The scoop/AFMU indicators reflect the last valid
   Loadout; FSD health is dated loadout evidence, not continuous telemetry.

Saved plans survive EliteLab restarts and are scoped to commander identity.
Download CSV exports the completed waypoint list. Its historical Spansh column
`Distance To Arrival` is leg distance in Ly, not station arrival distance in Ls.
Formula-leading system names are neutralized in the CSV.

## Palin evidence

The progress bar uses the journal's `Greatest_Distance_From_Start`, with its
observation time. Cumulative travel does not satisfy the distance milestone.
An optional user-confirmed career starting system enables an endpoint geometry
check and a 100 Ly margin check. Sol, route origin and first available journal
location are never substituted for a missing career origin. The distance check
does not confirm the invitation or Sensor Fragments donation.

## Synthesis supplies

The bundled catalogue has 35 recipes: FSD injections, AFMU refills, heat sinks,
life support, limpets, SRV supplies, chaff and common combat ammunition. Search
aliases include jumponium, AFMU, oxygen, heatsink and frag cannon. This is a
reviewed subset, not a claim to cover every current synthesis recipe.

Each recipe shows material costs, available crafts and shortages for a chosen
quantity. Add several recipes to the combined budget to account for shared
ingredients. Individual craftable counts are alternatives; do not add them.
Planning neither reserves nor spends materials. Missing current-session
`Materials` evidence yields unknown availability rather than zero stock.

`Synthesis` records exact materials spent and matches recipes by journal name
and ingredients. Unknown or changed recipes remain unidentified. The last 200
observed syntheses are retained per commander, with replay deduplication. These
counts are an evidence window, not lifetime statistics.

An FSD synthesis or `JetConeBoost` records the most recent boost observation.
The bonuses do not stack. A ship `FSDJump` clears that observation; a carrier
jump does not. Relog, shutdown or ship change makes current boost evidence
unknown. `BoostUsed` is preserved verbatim on the last jump, and alone does not
identify whether an injection or jet cone supplied the boost.

## HTTP and MCP

| Tool | Purpose |
|---|---|
| `get_neutron_route(limit=10)` | Read saved plan, next waypoints, ship preparation and Palin evidence |
| `plan_neutron_route(destination, ...)` | Submit Spansh job and save it locally |
| `refresh_neutron_route(id)` | Check the job once, throttled to one check per three seconds |
| `clear_neutron_route(id)` | Clear the expected local plan |
| `export_neutron_route()` | Return CSV text and filename |
| `get_fsd_injection_status(limit=10)` | Boost observations, injection availability and recent craft history |
| `list_synthesis_recipes(query, grade, quantity, limit)` | Recipes, costs and shortages |
| `plan_synthesis(items)` | Combined budget of `{key, quantity}` objects |

The `neutron_trip` MCP prompt coordinates these tools. Routes appear under
`/api/neutron/` and `/api/synthesis/`; the schema documents exact methods and
parameters. Restart the server after Python changes; reconnect an MCP client
that caches its tool list.

## Sources and maintenance

- [Spansh neutron plotter](https://spansh.co.uk/plotter): form submission,
  asynchronous results and special-drive multiplier checked against its
  published application and live API on 2026-11-01.
- [EDDiscovery synthesis data](https://github.com/EDDiscovery/EliteDangerousCore/blob/master/EliteDangerous/FrontierData/Items/RecipesSynthesis.cs):
  recipe names, journal identifiers and factual ingredient quantities; FSD
  costs cross-checked with [Inara](https://inara.cz/elite/synthesis/).
- [Frontier journal manual](https://hosting.zaonce.net/community/journal/v10/Journal_Manual_v10.pdf):
  `Synthesis`, `JetConeBoost` and `FSDJump` evidence fields.

Data and provenance live in `elitelab/core/synthesis.json`; route contracts in
`elitelab/core/neutron.py`. Tests use synthetic commander logs and a reduced
Spansh-shaped result. Update fixtures and reviewed dates when provider contracts
or game recipes change.

# Data sources and attribution

EliteLab reads the commander's local journal for ship, cargo, material, credit,
engineering and activity evidence. Community search results remain reports with
age and coverage limits. Card footers identify the provider; result links point
to a market or station when an appropriate resource is available.

| Feature | Resource used | Notes |
| --- | --- | --- |
| Cargo buyers and personal trades | [Spansh station search](https://spansh.co.uk/stations) | Community EDDN markets; cargo buyers link directly to `/station/{market_id}` |
| Flight route generation | [Spansh neutron planner](https://spansh.co.uk/plotter) | Asynchronous external route job, saved locally after validation |
| Mining rings and buyers | [Spansh body search](https://spansh.co.uk/bodies), [station search](https://spansh.co.uk/stations) | Reported rings/hotspots and commodity markets |
| Mining merit route guidance | [MeritMiner](https://meritminer.cc/) | External planning guidance; no reward guarantee |
| Carrier routes, PTN discovery, buy-source search | [Ardent Insight API](https://api.ardent-insight.com/v2) | Community markets and commodity catalog; not Inara scraping |
| PTN competition board | [PTN missions](https://pilotstradenetwork.com/missions/) | Official public board; read only, no Discord actions |
| Rare targets and combat systems | [Spansh stations](https://spansh.co.uk/stations), [systems](https://spansh.co.uk/systems) | Reported power/system conditions require local confirmation |
| Station cross-checks and round-trip handoff | [Inara market search](https://inara.cz/elite/market-traderoutes-search/) | External links are labeled separately from provider data |
| Coordinate lookup | [EDSM API](https://www.edsm.net/en/api-v1) | System-name coordinate cache |
| Material names and families | [EDCD FDevIDs](https://github.com/EDCD/FDevIDs/blob/master/material.csv) | Bundled catalog; see engineering.json provenance |
| Blueprints and experimentals | [EDCD Coriolis modifications](https://github.com/EDCD/coriolis-data/tree/master/modifications) | Bundled data, with EliteLab planning hints identified separately |
| Ship build decoding | [EDSY](https://edsy.org/), [EDCD Coriolis data](https://github.com/EDCD/coriolis-data) | Local decoders and generated tables; no build upload required |
| Technology broker costs | [Community broker reference](https://scotty.newlevels.org/techbroker/) | Corrections and provenance recorded in engineering.json |
| Farm-site catalog | [ED Mining](https://edmining.com/), [ED Blackbox](https://edblackbox.com/), [Frontier guides](https://forums.frontier.co.uk/forums/elite-dangerous-guides-tutorials/) | Bundled community guidance; sites.json records the review period, not live spawn confirmation |

The bundled data files and research documents retain detailed provenance and
review dates. A provider label is not an endorsement or a claim that the resource
operates EliteLab. Missing data remains unknown; links do not turn a plan into
observed journal evidence.

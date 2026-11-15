# Rhino surface mining

Open **Mining > Rhino surface mining**. The panel has Mining run, Saved sites
and Field guide tabs. It reads journals and keeps a local notebook; it never
controls the game or uploads sites.

## Mine and unload

Deploy a player-controlled Rhino to start a run. The panel counts each
`MiningRefined` event as one tonne and separates commodities, so water cannot
silently count as tritium. The rate includes setup, driving and cargo transfers
from deployment through the latest recorded activity. It becomes available
after 60 seconds. Boarding, destruction or logout closes the run. The next
deployment starts another run; restarting EliteLab reconstructs the current
deployment from its journal replay window, not a persistent lifetime counter.

Rhino and ship holds use separate `Cargo.Vessel` observations. A missing count
stays unknown. The last ship count can be advanced by recorded SRV transfers;
the panel labels that derivation and its timestamp. Transfers are gross tonnes
moved to the ship, not additional production, sales or proof all cargo was mined.

To unload, recall the ship nearby, drive into its boarding area and use the
Rhino's **Inventory > Transfer > Transfer all to ship**. Remain in the Rhino;
the rigs can keep working. Recover the rigs before boarding the ship to leave.
The panel's 72 t SRV capacity is the Rhino specification, not ship capacity.

## Save and revisit

Use **Saved sites > Use current position**, enter commodity, reported rig fit
and notes, then save. Positions require a recent Status snapshot (120 seconds)
with valid latitude/longitude. You can also enter coordinates from a report.
Saved sites and selected destination belong to the current commander (FID when
available, otherwise commander name), in `rhino-sites.json`. Up to 100 personal
sites are supported, with edit and removal. No paths come from site input.

Navigation uses spherical surface distance and an initial compass bearing.
It requires a recent position on the matching system and body and a known
planet radius. It is not terrain routing or a ship flight path. Latitude is
north-positive; longitude is east-positive. Directions handle the date line.

The built-in reference is **Shinrarta Dezhra AB 2 j, 35.9491, -31.2339**.
The video at 2:11 supplied the position; the owner reported three operating
rigs there on 2026-11-15, with live journal coordinates approximately 144 m
away and later Tritium refinement. It is a dated reference, not a promise of
current reserves, rig fit or the video's 330 t/h rate.

## Evidence limits

Rig counts are manual reports, cleared on a new deployment, departure or
EliteLab restart.
The journal does not expose rig positions, remaining carried rigs, deposit
footprints, hopper contents, efficiency or remaining reserves. Site rig fit
is a historical observation, separate from the current reported rig count.
Rates do not extrapolate through unobserved time or continue after logout.
No site generator, reset timer, overlap bonus or guaranteed yield is assumed.

## Tools and state

- `get_rhino_status`: GET `/api/rhino`; small summary, notebook and navigation.
- `save_rhino_site`: POST `/api/rhino/sites/save`; create/update a personal site.
- `select_rhino_site`: POST `/api/rhino/sites/select`; select or clear a target.
- `remove_rhino_site`: POST `/api/rhino/sites/remove`; remove a personal site.
- `report_rhino_rigs`: POST `/api/rhino/rigs`; record 0-6 working rigs manually.

The module requires `journal` and writes only `rhino.summary`. It subscribes
to journal events and Status/Cargo snapshots. Persistence happens only on
explicit notebook actions; event processing does no network I/O. Mutations
and events share a reentrant lock; store snapshots are detached copies.

## Sources

- [Frontier Player Journal v34](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf): Cargo, CargoTransfer and MiningRefined contracts.
- [Three-rig tritium video, 2:11](https://www.youtube.com/watch?v=pmkU1LqwPjA&t=131s): reference site, read by the owner and reproduced locally.
- [Rhino field research](https://inara.cz/elite/logbook/98900/): collection routes, rig fit and replenishment uncertainty.
- [Cargo transfer without boarding](https://www.reddit.com/r/EliteDangerous/comments/1w7ypln/psa_offload_your_rhino_while_your_ship_is_landed/): practical transfer procedure.
- [Rig replacement reports](https://www.reddit.com/r/EliteDangerous/comments/1w7ymkg/fd_please_let_us_buy_replacement_mining_rigs_from/): synthesis and outfitting workaround.

## Validation

`python -m unittest discover -s tests -p test_rhino.py -v` covers replay/live
parity, cargo separation, non-Rhino exclusion, lifecycle/rate boundaries,
manual reports, malformed input, commander isolation and navigation.
`node tests/rhino-browser.mjs` runs the real CLI with isolated synthetic
journals, settings, data and instance directories. It checks the browser/API/
SSE workflow, stable drafts, HTML escaping, persistence and desktop/mobile
screenshots under `artifacts/rhino` (or `ELITELAB_SCREENSHOT_DIR`).

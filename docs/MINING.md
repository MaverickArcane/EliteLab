# Mining session tracker

The Mining card and `get_mining_status` (`GET /api/mining`) show the latest
prospector report and refinery output for the current game session. Enable
Mining in the Layout menu if a saved preset hides it. It works offline.

Each `MiningRefined` event adds one ton. Output is grouped by normalized
commodity key; localized journal names are used for display. Buying, selling,
ejecting or transferring cargo never changes production totals. Unknown
commodity types appear in Other / unknown. This is not a profit, cargo-in-hold
or Powerplay merit estimate.

Prospector reports show composition, material content, remaining percentage,
and a core material when the journal supplies it. Zero remaining is valid;
missing or invalid percentages show unknown. The journal supplies no asteroid
identifier, so the report counter does not claim to count unique asteroids.
The latest report stays visible with its recorded timestamp after travel.

## Sessions and rate

- Every `LoadGame` resets the session. A changed Commander name or FID also
  clears totals. Journal file continuation alone does not reset them.
- Replay rebuilds the session using the same events as live tracking. If the
  loaded journal window has no `LoadGame`, partial history is explicitly shown.
  No separate mining file is written. Adjust `ELITELAB_RECENT_JOURNALS` if a
  long session's beginning falls outside the replay window.
- The rate is refined tons divided by hours from the first mining event to
  the latest recorded journal timestamp. Travel and idle gaps are included.
  It becomes available after 60 recorded seconds; missing/invalid mining
  timestamps suppress it. Older timestamps cannot move the end time backward.
- `Shutdown` freezes the session. The card shows the journal's `as_of` time;
  a silent or disconnected game does not keep changing the displayed rate.
  This is a recorded-session average, not an instantaneous mining speed.
- Two refinery events in the same second both count. There is no deduplication
  by timestamp, because those can represent two legitimate units.

Event semantics come from Frontier's [Player Journal manual v34, sections
7.7 and 13.33](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf).
The tests use synthetic records matching those fields, not a recorded mining run.
In-game validation should compare a fresh session's prospector composition,
refined units and timestamps with the journal, then reload the game and verify
the reset. A ring/acquisition-system finder remains separate work under #3.

## State and input limits

`mining.summary` is one atomic store snapshot. It includes `commander`,
`partial`, `ended`, `started_at`, `as_of`, `elapsed_seconds`,
`timing_incomplete`, `tons_per_hour`, `prospector_reports`, `last_prospect`,
`refined_tons`, `commodities`, `other_tons`, and `rate_note`.
The API returns the same snapshot. It is read-only and uses the existing
HTTP authentication and host checks; there are no external requests or writes.

The latest composition is limited to 32 entries, text fields to 160 characters,
and named output to 256 commodity keys. Additional distinct keys accumulate in
Other / unknown so the total remains correct. Percentages must be finite numbers
between 0 and 100. The browser escapes journal text before rendering it.

## Validation

`python -m unittest discover -s tests -p test_mining.py -v` covers replay/live
equivalence, session boundaries, duplicate-second output, rate timing, malformed
and bounded input, and separation from cargo transactions.

`node tests/mining-browser.mjs` (Node 22+, Chrome) starts the real CLI against a
temporary journal directory, appends records, checks API and SSE results, tests
HTML escaping, reloads a saved layout, and checks desktop/390px layouts. Set
`ELITELAB_SCREENSHOT_DIR` to save screenshots in a chosen directory. It never
uses the player's journal or data directory.

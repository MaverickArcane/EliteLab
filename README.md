# Pull request browser evidence

This branch hosts screenshot evidence for PR comments. It is not an application
branch and should not be merged into development. Comments use immutable commit
URLs so later captures do not change earlier evidence.

Captured locally on Windows in headless Chrome, 2026-11-01 America/Phoenix
(2026-11-02 UTC), against source commit
`4cb08870130497f946853a4485a668be29aa576c`.

- `pr-63/mining-desktop.png`: 1440 x 1000, real CLI/journal watcher/API/SSE,
  synthetic mining journal, recorded session ended with 3 tons and 6 t/h.
- `pr-63/mining-mobile.png`: same run at 390 x 844, responsive Mining card.
- `pr-61/source-setup-saved.png`: 1280 x 900, post-merge setup regression
  rerun. Real Windows setup launcher; synthetic journal/profile directories;
  changed port saved, Restart offered. The subsequent restart check verified
  a new server PID and dashboard navigation to the new port.

Commands: `node tests/mining-browser.mjs` and
`node tests/restart-browser.mjs`, using `ELITELAB_SCREENSHOT_DIR`.
The screenshots show fixture data, not an actual in-game mining session.

## Expanded mining desk, PR #63

`pr-63/mining-desk/` captures source commit
`e5260f83114bce987afd195bfa7963283beb2d19` on 2026-11-01 America/Phoenix
(2026-11-02 UTC), locally on Windows in headless Chrome.

- `mining-desktop.png`: 1440 x 1000, nearby rings with live Spansh body data.
- `mining-mobile.png`: 390 x 844, same desk and search on a narrow viewport.
- `mining-buyers.png`: 1440 x 1100, live Spansh quotes for the tracked 40t Platinum haul.

Command: `node tests/mining-browser.mjs`, with `ELITELAB_MINING_LIVE=1` and
`ELITELAB_SCREENSHOT_DIR` set. Real CLI, journal watcher, API, SSE and browser;
synthetic commander journals and financial data, live Spansh rings/markets.
The demo produces 54t, sells 8t for 2,224,000 Cr, records 29,400 Cr costs and
2,194,600 Cr net. Quotes value unsold units separately and change with time.
This is local integration evidence, not a real in-game mining session.

## Plain UI copy, PR 63

pr-63/plain-copy captures source a2a64c6e2c38591450a902276e231ed424a92e4f after removing promotional headings. Local Chrome browser run; synthetic commander journals AND synthetic Spansh responses. Desktop 1440px, mobile 390px, buyers 1440px. Command: node tests/mining-browser.mjs. All browser checks passed.


## Mining Powerplay and MCP, PR 63

pr-63/powerplay captures source 1555d39c0da6fd724aa9d96ae7aadd2dbece952f on November 1, 2026 America/Phoenix (November 2 UTC). Local Windows Chrome, real CLI/API/SSE/journal watcher, LIVE Spansh rings and buyer quotes, SYNTHETIC commander journals, financial figures and merit gains. The fixture records 1,800 gained merits, temporally associated with a mined sale, and 11,800 total merits. This is not an in-game mining session.

Command: node tests/mining-browser.mjs with ELITELAB_MINING_LIVE=1 and ELITELAB_SCREENSHOT_DIR. All browser checks passed, including Powerplay filters, quote clearing on filter changes, persistence, retry, stale responses and escaping. Desktop 1440x1000, mobile 390x844, buyers 1440x1100; mining-powerplay-buyers.png scrolls to the Powerplay controls/results.


## Journal history, PR 65

pr-65 captures source 692cc741aff0e4429d2c2b960df07fa4c9046ed4 on November 1, 2026 America/Phoenix (November 2 UTC). Local Windows Chrome, real CLI/API/SSE/journal watcher and SQLite, isolated SYNTHETIC commander journals. No external providers. This is not an in-game session or a real commander's archive.

Command: node tests/history-browser.mjs with ELITELAB_SCREENSHOT_DIR. Browser checks passed: snapshot chart, merit cycles, material locations, commander switching, hostile text escaping, cache rebuilding, saved/dirty filters, live updates, errors/retry, stale responses and map remount. Desktop 1440x1100; mobile 390x844 (top of scrollable panel).

## Materials and recipe workflow, PR 67

pr-67 after captures use source ab12c78c122347b933e8ae9cc717fbf0dabdf696 on November 1, 2026 America/Phoenix (November 2 UTC). Before captures use bed996987a1f63921f9338394378a3881ae3d8e3, the PR65 code, with the same initial synthetic fixture and pre-existing material target. Before is the Engineering preset; after uses Materials / Recipes and Overview workspaces. After images include the synthesis plans and live collection/craft events exercised by the test, so recorded totals differ intentionally.

Local Windows Chrome, real CLI, HTTP, SSE, journal watcher and file persistence. All commander identity, inventory, balances, planned quantities and craft events are SYNTHETIC. No game session or live provider data. Command: node tests/material-plan-browser.mjs with ELITELAB_SCREENSHOT_DIR. Passed persistence, shared stock, inline edits, live updates, dirty input, source lookup, inventory, recorded FSD evidence, errors/retry, response ordering, layout compatibility and HTML escaping. Desktop 1440x1100; mobile 390x844. The requirements images scroll down within the page; mobile tables scroll internally. Overview screenshots demonstrate navigation outside the materials workflow. The before images are captures, not additional functional test claims.

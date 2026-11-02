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

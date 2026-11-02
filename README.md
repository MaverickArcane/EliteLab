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

# PR 72 local browser evidence

Application commit: 0436eecf78e3c711ae515ac7115bf9d7d8c1e1b7
PR: https://github.com/MaverickArcane/EliteLab/pull/72
Captured: 2026-11-02
Command: node tests/rares-browser.mjs

Real isolated EliteLab CLI, journal watcher, HTTP/SSE and headless Chrome on
Windows. Desktop 1440 px; mobile viewport 390 px. These screenshots use synthetic
journal, Cargo.json and Market.json files for Rare Tester. Network providers
were offline, so distances remain unknown. The images demonstrate the local UI
and evidence transitions, not current game stock/prices or Powerplay rewards.
The user's running EliteLab process and real game files were left untouched.

- rares-buying-desktop.png: next buy stop and six stop cards; four tons of rare cargo.
- rares-buying-mobile.png: narrow-screen next-stop controls and stop list.
- rares-cargo-market-desktop.png: cargo/free space and current-visit market snapshot.
- rares-market-mobile.png: narrow-screen stock source, time, prices and quantities.
- rares-previous-visit.png: a stale market snapshot remains visibly unverified.

The same test checks exact-station docking, unknown versus empty cargo, manual
marks across reload and cargo/commander changes, request failure/recovery,
market-text escaping, cross-panel navigation and stable station selection.
Map callbacks use separate deterministic coordinates after the screenshots.

This evidence branch is for review images only; do not merge it into development.

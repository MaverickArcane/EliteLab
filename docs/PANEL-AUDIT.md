# Default panel workflow audit

This is the remaining default-panel audit for #41. It was checked against the
development dashboard after the trading route, rare sell-target and Powerplay
handoff changes (#73, #69, #75). The trading flow and its evidence limits are
in [TRADING.md](TRADING.md) and [TRADE-POWERPLAY.md](TRADE-POWERPLAY.md).
This document proposes work; it does not claim the mockups are implemented.
The focused follow-ups are #77 (cargo and market), #78 (merit context), and
#79 (live feed), in that order.

## What the default layout offers now

The default preset starts with location and ship, then build and engineering,
materials, Powerplay, sell targets, combat, feed, cargo, rare market, carrier,
rares loop and map. Other available cards include Trading, Mining, missions,
expedition history, party, carrier job and neutron routing. A saved layout can
override the preset, so changes to card behavior must not depend on position.

| Panels | Player question | Current strength | Remaining gap | Decision |
|---|---|---|---|---|
| Location, Ship, Build | Where am I and what can this ship do? | Current system, docking, range, capacity, modules and build comparison are visible. | Location has no single next-action context; a build comparison is a separate deliberate task. | Keep. Let workflow panels own next actions. |
| Trading, Rares loop, Targets | Which route or sale should I take? | General route selection, rare buying, conditional merit estimates and explicit Powerplay handoff now exist. | Actual commodity acceptance and Powerplay rewards still depend on game evidence. | Keep uncertainty explicit; use the selected route as context in cargo and market. |
| Cargo, Rares at this market | What is aboard and can I buy or sell here? | Cargo snapshot integrity and current-visit rare stock are distinguished from old data. | Cargo has no selected-leg context; the market card only lists rares, so a general trade's local buy/sell evidence is elsewhere. | First implementation follow-up. |
| Powerplay, Merit rate, Combat merits | What merits did I earn and why? | Pledge, total, session gains and activity-specific counters are shown. | A recent gain list has little source context; nearby sale and combat events may be confused with confirmed attribution. | Second follow-up; keep attribution conditional. |
| Live feed, Journal history | What just happened? | Recent journal events and historical travel are available. | Feed is a flat list with no filtering or clear session boundary; important transactions can be buried. | Third follow-up. |
| Materials, Wishlist, Recipes, Farm sites | What do I need to engineer? | Inventory, session gains, requirements, trader and farm guidance exist. | Several panels repeat material totals and can compete for attention in the default layout. | Keep the planning flow; revisit density after the first three. |
| Carrier, Carrier job, Crew progress | What is my carrier or crew doing? | Status, job and crew progress are available. | These are opt-in workflows; no default-layout change is needed to make trading work. | Keep separate. |
| Mining, Missions, Neutron highway, Star map | What is the next activity-specific destination? | Each has its own search or progress context; map layers can show choices. | Mining still needs real-session validation (#3); other panels need evidence from use before redesign. | Do not infer defects from the audit alone. |

## Priority 1: cargo and market at the selected trade stop

Today, the cargo card lists every commodity and the market card lists only
rares. A player following a selected general trade route must read the Trading
card to learn the planned commodity and stop, then mentally match that with
the hold and any local market record. A community quote does not prove the
current station has stock or demand.

Before (three disconnected cards):

```text
Trading:  Buy 80 t Palladium at Station A -> sell at Station B
Cargo:    Palladium 25 t | Gold 8 t | Limpets 4 t
Market:   Rares at this market | no rare stock
```

After (one context line in each existing card, without moving controls):

```text
Trading:  Next: buy 55 t Palladium at Station A
Cargo:    Planned load 25 / 80 t Palladium aboard; 55 t remain
          Other cargo: Gold 8 t, Limpets 4 t
Market:   Station A | observed this visit at 14:32
          Palladium buy: 252,000 Cr/t | stock 120 t
          Planned need: 55 t | quote may change
```

If there is no selected route, show the ordinary cargo and rare-market view.
If the commander changes, the active leg changes or the market snapshot belongs
to another station or visit, remove the contextual claim. If the snapshot has
no matching commodity, say "No local quote recorded" rather than zero stock.
Keep community route quotes separately labeled. Only the journal and local
Market.json can establish observed cargo and a local snapshot; neither proves
a future purchase or sale.

Acceptance: context follows the selected route without copying it into a new
store namespace; exact system, station and market ID are checked where present;
other cargo remains visible; unknown cargo remains unknown; stale or missing
market evidence is explicit; desktop and narrow views keep the same facts;
HTTP/MCP expose any newly parsed market evidence with its timestamp and scope.

## Priority 2: merit activity context

The Powerplay card shows a recent `+N` list. The activity cards show their own
estimates or counters. A player selling cargo may read adjacency as causation.

Before:

```text
Powerplay:  +190 14:05 | +30 13:48
Mining:     190 merits associated with sales (estimated)
```

After:

```text
Powerplay:  +190 14:05 | after Platinum sale | association uncertain
            +30 13:48 | source not established
Mining:     Recorded session gains 220; sale association estimated 190
```

Use recorded PowerplayMerits events as the authoritative amounts. An event
near a sale is only an association, not proof of an eligible commodity or a
conversion rate. Show pledge changes and session boundaries so an old rate is
not carried across commanders or powers. Do not sum a sale estimate into the
recorded total.

Acceptance: chronology is stable, labels distinguish recorded and inferred
facts, unknown sources remain unknown, and live updates do not duplicate gains.
MCP output preserves the same distinction.

## Priority 3: live feed for current work

The live feed is a flat forty-event list. Important buys, sells, merits and
travel changes can be lost among routine events.

Before:

```text
14:05 +190 merits
14:04 sold 80 t Platinum
14:03 docked at Station B
... up to 40 rows
```

After:

```text
Current session | All  Trading  Travel  Combat  Engineering
14:05  +190 merits          recorded
14:04  Sold 80 t Platinum  recorded
14:03  Docked at Station B
```

Filtering is local to the card and does not alter the journal history or its
MCP data. Keep a visible empty state for a filter with no matches. New events
must not reset the selected filter or scroll position unexpectedly; clearing
the game session must be visible, not silently treated as an empty event list.

## Sequence and validation

Implement #77, #78 and #79 in focused PRs against `development`. Keep #41 open
until the chosen follow-ups merge and the combined flow is tested in a browser.
Use synthetic journals and market snapshots for automated tests, label them in
screenshots, and record what still needs a real game session. Desktop and
narrow screenshots belong in each visible-change PR comment. Do not change a
saved layout just to make a new card easier to find.

# Roadmap

Where this is going, roughly in order. Each item is also a GitHub issue. Pick one and say so, or add your own.

## Next

1. Blueprint recipes for the wishlist. `set_wishlist` should accept "FSD G5 Increased Range x3" and expand it. Needs a recipe dataset (EDOMH publishes one under an open licence) and a `get_blueprint` tool.
2. Expected merits per sell target. Rares pay by distance from origin; a real run measured a flat 1 merit per 667 Cr of sale value. Add a price-by-distance curve and rank targets by merits per jump.
3. Mining module. Prospector results, refinery output, tons per hour, and a finder for ringed planets inside acquisition systems (EDSM bodies API has rings). This is the top merit method by every guide.
4. Laden jump range. The ship card shows unladen max. Compute laden range from FSD class, optimal mass and current cargo so jump counts are honest.
5. Notifications. Toast and optional sound on merits gained, loop complete, fuel under 25 percent, interdiction, carrier jump lock.

## Later

6. Frontier companion API. OAuth with Frontier unlocks the live carrier market and cargo, fleet locations and station markets. Biggest data jump available.
7. Journal index. A small SQLite index over all journals for instant all-time history and analytics (credits over time, merits per cycle).
8. Richer MCP surface. Prompts ("plan a rares run from here"), resources (live state as a readable resource), composite tools like `plan_sell_run`.
9. Packaging. Single-file executable with a tray icon and auto-start with the game.
10. Auth for LAN use. Optional token so the tablet-next-to-the-HOTAS setup is safe on shared networks.

## Housekeeping

- Short GIF of the layout editor in the README.
- A fixture journal scenario per module as they grow.

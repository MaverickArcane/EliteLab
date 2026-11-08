# Group mining and carrier loading

Use **Mining** to select a ring and compare buyers, then open **Carrier ops**.
The existing private LAN/tailnet party supports this workflow. Hosted accounts,
shared journal uploads and the draft private-group server are future work.

1. Open the owned carrier's market in game so EliteLab knows its market ID.
2. Expand **Set up group mining and paid carrier loading**. Enter the mineral,
   ring/system, eventual buyer station/system, additional tonnes, checked starting
   stock, actual miner buy price and reported buyer price. **Use selected mining
   spot** copies the ring chosen in Mining. A verified buyer market ID enables
   automatic unloading sale matching; leave it unknown when you cannot verify it.
3. Save the group mining plan. This creates a local draft, not an in-game order.
   Set the carrier buy order, funds, docking permissions and parking in game.
4. Use **Connect crew** to host the party and share its private address/code.
   Crew join from their own EliteLab installations. Start the saved job after
   participants have joined. The default fixed allocation divides whole tonnes
   equally, even for ships with different capacities; the owner participates.
5. Crew mine their assigned loads and sell to the carrier's buy order. Refinery
   events are production evidence, not delivered tonnes. Matching carrier sales
   and direct transfers advance loading, with duplicate receipts ignored.
6. Check reported contributions and the physical carrier stock before departure.
   Depart, jump in game, and start unloading when ready. Confirm the carrier's
   actual sell order for this phase: the old buy price is not a sell order.
   Unloading advances on matched destination sales, not on taking cargo aboard.

The miner's agreed Cr/t is an estimated payout for **sales** to the buy order.
Direct transfers do not pay credits. Mining acquisition cost is unknown; ore is
not treated as a zero-cost purchased commodity for a net-profit claim. Public
buyer quotes may change before the carrier arrives. Recheck them in game.

Use the existing workload preview/revision controls when participants change.
Saved quotas retain delivered and committed work; a reconnect does not erase
contributions, and a late join is not permission to redistribute absent members'
assignments. Owner corrections remain explicit and auditable. Crew telemetry and
manual claims are advisory; the inventory ledger remains separate evidence.

## Working with PTN

**PTN desk** has its own scouting, confirmation and advert stages. For a freshly
scouted trade route, expand **Coordinate route with Carrier ops**, enter checked
starting stock, and copy the route into Carrier ops. This uses the current PTN
revision and refuses to overwrite an active carrier job. It does not advance a
PTN phase or place an order. Each desk's phase changes remain explicit.

For a mined load, use the reverse handoff to prepare public unloading:

1. Finish loading and depart the unpaused mining job. Dock at the intended
   large-pad orbital buyer and open its commodity market. If the job has a
   verified destination market ID, the buyer must match it.
2. In Carrier ops, click **Prepare PTN unloading**. Finish or cancel any existing
   PTN plan first. Enter the physical carrier stock you have checked, tonnes to
   advertise and minimum public payout. The advertised quantity must fit both
   the job size and checked stock above the job's saved starting stock.
3. Create the mined-load plan, then capture the buyer market in PTN. There is no
   loading-station scout: this cargo came from mining. Check the buyer's current
   price and demand, then open unloading.
4. Move the carrier and set its sell order in game. Refresh Carrier Management.
   Confirm physical stock again, the actual sell price and remaining tonnes,
   parking near the buyer, open docking, market service and competition.
5. Prepare and review the unloading advert. Follow the existing PTN posting
   steps, then record posting locally. Recheck stock, prices, demand and order
   when they change; buyer, stock, order and carrier confirmations expire after
   an hour. Newer contradictory ledger or order evidence blocks advertising.
6. Track crew deliveries in Carrier ops and public order progress in PTN. Set
   each desk's stages explicitly; the handoff does not change crew progress or
   complete the source job. Confirm zero remaining before completing PTN.

The desk shows the hauler's sale spread and estimated carrier proceeds. Mining
acquisition cost and owner net profit remain unknown; it does not invent a
zero-cost purchase. Stock below the saved baseline cannot be advertised through
this plan. A stock recheck is available before opening unloading if the initial
confirmation expires. EliteLab does not post messages, pay commanders, close
adverts or control Roomba.

`plan_mining_loading` exposes the setup through HTTP/MCP/CLI.
`handoff_ptn_to_carrier` copies a scouted loading route to Carrier ops;
`handoff_mining_to_ptn` imports a departed mined load with revision, source-job
version and checked stock. The offline regression
uses two real HTTP clients to verify equal shares, duplicate/replay protection,
reconnect, PTN advert preparation and continued crew unloading. Real group play
remains an in-game release check.
See [Trading](TRADING.md), [PTN desk](PTN-TRADING.md) and
[future shared server](MULTIPLAYER-PLAN.md).

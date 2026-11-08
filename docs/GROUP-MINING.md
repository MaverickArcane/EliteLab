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

Mining loading can feed the same carrier unloading workflow. The PTN desk's
station-buy scout is not mining acquisition evidence: do not fabricate a buy
visit or import a mined load as a scouted station round trip. For a mining load,
use Carrier ops' unloading job and follow PTN's current manual posting procedure
with checked stock, order price and buyer quote. Automatic mining-specific PTN
advert preparation remains a future extension. EliteLab does not post messages,
pay commanders, close adverts or control Roomba.

`plan_mining_loading` exposes the setup through HTTP/MCP/CLI.
`handoff_ptn_to_carrier` performs the explicit PTN handoff. The offline regression
uses two real HTTP clients to verify equal shares, duplicate/replay protection,
reconnect and unloading; real group play remains an in-game release check.
See [Trading](TRADING.md), [PTN desk](PTN-TRADING.md) and
[future shared server](MULTIPLAYER-PLAN.md).

# Materials and recipe planning

Use **Materials / Recipes** in the dashboard navigation. The main panel has
three views: Plan recipes, Inventory, and Recorded synthesis / FSD. The pinned
build panel follows the planner. Existing recipe-search and material panels
remain available in Custom layout; synthesis no longer has a separate basket.

## Workflow

1. Select synthesis/FSD injection, a material target, engineering blueprint,
   experimental effect, technology broker unlock, or pinned build.
2. Choose the recipe and quantity. For engineering choose current and target
   grades. The preview shows per-ingredient stock, earlier requirements, this
   addition's costs and shortages before saving.
3. Add to saved plan. Edit a quantity in place or remove its entry. The combined
   requirements and material exchange plan update with journal inventory changes.
4. Find sources for a material, search sites for all shortfalls, or find traders.
   Source results are cleared when the plan or stock changes; refresh explicitly.
5. Use Inventory for current stock and session receipts. Use Recorded synthesis /
   FSD for actual journal craft history, injection alternatives and boost evidence.

Planning does not perform a game action. A saved synthesis quantity is a manual
planning target, not a queue that runs in game. Observed crafts reduce journal
inventory but do not automatically reduce planned quantities. Edit the plan when
your intended remaining work changes. Injection and jet-cone boosts do not stack;
a planned injection is not evidence that one was applied.

## Shared stock and unknown inventory

Requirements sum across entries. Stock is allocated once in displayed order;
legacy material targets come first, then saved entries in insertion order. A
recipe's `craftable` count uses stock left after earlier entries. Counts on
separate entries must not be added together as independent stock pools. Removing
an earlier entry or changing its quantity releases its planning allocation.
No game material is reserved or consumed by a plan.

A current commander Materials snapshot establishes known inventory. Before it,
readiness and synthesis craftability are null; the UI says Unknown. Numeric
have/short fields retain provisional observed arithmetic for API compatibility,
so clients must check `inventory_known`. Exchange suggestions are withheld until
stock is known. Commander changes clear inventory evidence. Saved plans remain
local to this EliteLab installation, as before; they are not commander accounts.

Blueprint costs retain the existing estimated roll counts and grade-range rules.
Pinned build entries have a **Follow current ship** checkbox. Leave it checked
to update requirements from live build progress, or uncheck it while flying the
engineering ship to save its current requirements before switching ships. Fixed
requirements survive restarts; inventory, shortfalls and sourcing remain live.
Check it again to resume tracking. Ordinary recipe quantities already stay fixed.
Broker cargo requirements remain
visible separately from engineering material costs. Farm sites and trader data
retain their existing community/provider coverage limits.

## Persistence and compatibility

`engineering_wishlist.json` retains the existing list format, entry IDs, notes,
engineering grades and roll settings. Synthesis adds `kind: synthesis`, an exact
catalogue key, a tier and quantity. Save/update/remove writes finish before the
in-memory plan changes. A failed write preserves the old plan. Up to 200 saved
entries can be added, with new/edited quantities from 1 to 10,000.

Legacy `wishlist.json` material targets are not deleted or copied. They appear as
editable `legacy:<material-key>` entries and keep their original API/file. Their
quantities are additional planning requirements, not duplicate inventory.
`wishlist_remove(all=true)` clears saved engineering/synthesis/material entries;
legacy targets use individual removal or `set_wishlist(mode=clear)`. `mode=set`
updates selected legacy targets without removing other targets.

Composer choices persist in browser storage. Unsaved quantity edits and expanded
ingredients survive live stock updates. Workspaces lazily mount their panels and
change visibility/order separately from the saved custom layout. An old layout
containing the synthesis card reveals the unified wishlist instead; other panel
settings remain. Named/imported layouts get the same compatibility treatment.

## API and MCP

| Tool | Behavior |
|---|---|
| `wishlist_options` | Engineering/material choices plus synthesis keys, tiers and exact costs |
| `preview_material_plan` | POST `/api/wishlist/preview`; same inputs as wishlist_add; read-only additional-entry preview using remaining stock |
| `wishlist_add` | `kind=synthesis`, exact `item` key, `qty`; existing engineering/material/build inputs remain supported |
| `wishlist_update` | POST `/api/wishlist/update`; saved `id` and replacement `qty` |
| `get_engineering_wishlist` | All entries, ordered ingredient allocations, combined needs, coverage and exchange suggestions |
| `get_fsd_injection_status` | Recorded synthesis, observed/used boost evidence and alternatives from total stock |

The `materials_recipe_plan` MCP prompt connects preview, saving, adjustment,
sourcing and evidence checks. The older `plan_synthesis` tool remains a read-only
hypothetical budget; it neither saves a plan nor incorporates existing saved
requirements. Use the unified preview for additions to the saved plan.

## Validation

`test_material_plan.py` covers pooled stock, existing saved data and legacy targets,
quantities, commander switches, unknown inventory, observed crafts, failed writes,
concurrent edits, authenticated MCP tools/prompt and HTTP authentication/Host checks.

`node tests/material-plan-browser.mjs` runs the real CLI with isolated synthetic
journals and data. It checks persistence, live SSE updates, dirty edits, inventory,
sourcing, FSD evidence, errors/retry, old preview rejection, layout compatibility,
escaping and responsive screenshots. Images are fixture evidence, not an in-game
crafting session. Existing owner/crew, expedition, mining and history browser
suites continue to exercise Custom layout.

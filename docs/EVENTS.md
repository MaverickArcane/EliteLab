# Journal events consumed

Frontier's Player Journal manual is the source of truth for the format (https://hosting.zaonce.net/community/journal/). This file lists only what EliteLab actually reads, the fields it uses, and what we learned about them in practice. Every line in a journal file is one JSON object with `timestamp` and `event`.

Replay: at startup the watcher re-emits events from the newest `RECENT_JOURNALS` files with `_replay: true`. Modules treat replayed events exactly like live ones, except `history` does not bump its version for them and `merits` counts them (a `LoadGame` resets the session, so only the current session's gains survive).

## Session and commander

| Event | Fields used | Module | Notes |
|---|---|---|---|
| `Fileheader` | `gameversion` | journal | one per journal file |
| `Commander` | `Name` | journal | |
| `LoadGame` | `Commander, Credits, Ship, Ship_Localised, ShipName, ShipIdent` | journal, powerplay, merits | resets session counters |
| `Powerplay` | `Power, Rank, Merits, TimePledged` | powerplay | emitted at load when pledged |
| `PowerplayJoin` / `PowerplayDefect` / `PowerplayLeave` | `Power`, `ToPower`/`FromPower` | powerplay, merits | reset merits/rank |
| `PowerplayRank` | `Rank`, `Power` | powerplay, feed | |
| `PowerplayMerits` | `Power, MeritsGained, TotalMerits` | powerplay, merits, feed | carries no cause; see merits attribution |

## Ship

| Event | Fields used | Notes |
|---|---|---|
| `Loadout` | `Ship, Ship_Localised, ShipID, ShipName, ShipIdent, HullValue, ModulesValue, Rebuy, HullHealth, UnladenMass, CargoCapacity, MaxJumpRange, FuelCapacity{Main,Reserve}, Hot, Modules[{Slot, Item, On, Priority, Health, Engineering{Engineer, BlueprintName, Level, Quality, ExperimentalEffect}}]` | `Ship_Localised` is often absent for newer hulls (e.g. `smallcombat01_nx` = Kestrel Mk II, `panthermkii`). `MaxJumpRange` is unladen. `Item` is lower-cased; cosmetic slots (`PaintJob`, `Decal`, `ShipKit`, `Bobble`, `VesselVoice`...) and fixed fittings (`CargoHatch`, `PlanetaryApproachSuite`...) are dropped from `ship_info.modules`. Core slot names: `Armour, PowerPlant, MainEngines, FrameShiftDrive, LifeSupport, PowerDistributor, Radar, FuelTank`; hardpoints `Small/Medium/Large/HugeHardpointN`, utilities `TinyHardpointN`, internals `SlotNN_SizeS`, `MilitaryNN`. |
| `ShipyardSwap` | `ShipType, ShipType_Localised, ShipID` | sets the ship name immediately; a `Loadout` follows |
| `ShipyardNew`, `ShipyardBuy` | `ShipType, ShipType_Localised` | learned names only |
| `StoredShips` | `ShipsHere[], ShipsRemote[]` each `{ShipType, ShipType_Localised, Name, StarSystem?}` | best source of internal-id -> display-name pairs for the whole fleet |

## Location

| Event | Fields used | Notes |
|---|---|---|
| `Location` | `StarSystem, StarPos, Docked, StationName, StationType, ControllingPower, Powers, PowerplayState` | at load; `Docked` true means we start docked |
| `FSDJump` | same plus `JumpDist, FuelUsed, FuelLevel` | no `StarClass` here |
| `StartJump` | `JumpType (Hyperspace|Supercruise), StarSystem, StarClass` | `StarClass` of the destination's main star; used by history for colouring |
| `CarrierJump` | `StarSystem, StarPos`, Powerplay fields | emitted when you are aboard a jumping carrier; also updates `carrier.system` |
| `Docked` | `StationName, StationType, StarSystem, MarketID, StationGovernment_Localised, StationEconomy_Localised` | |
| `Undocked` | `StationName` | |
| `SupercruiseDestinationDrop` | `Type, Type_Localised, Threat` | `Type` like `$Warzone_Powerplay_Med:#index=4;` with `Type_Localised` `Power Conflict Zone [Medium Intensity]`; the merits module uses this to know it is inside a Powerplay zone |
| `SupercruiseExit`, `SupercruiseEntry` | `Body` | entry clears the zone flag |
| `FSSSignalDiscovered` | `SignalName, SignalName_Localised, SignalType` | not stored; useful for diagnosing whether a zone exists in a system |

## Trade and cargo

| Event | Fields used | Notes |
|---|---|---|
| `MarketBuy` | `Type, Type_Localised, Count, BuyPrice, TotalCost, MarketID` | feed; the cargo itself comes from `Cargo.json` |
| `MarketSell` | `Type, Type_Localised, Count, SellPrice, TotalSale, AvgPricePaid, IllegalGoods` | feed; merits cause (`rares` if `Type` in `KNOWN_RARES`, else `trade`) |
| `Cargo.json` (snapshot) | `Count, Inventory[{Name, Name_Localised, Count, Stolen}]` | names are plain keys (`alieneggs`) |
| `Market.json` (snapshot) | `StationName, StarSystem, Items[{Name, Name_Localised, Category, BuyPrice, SellPrice, Stock, Demand, Rare}]` | names are `$alieneggs_name;`; `Rare: true` marks rare goods; a rare absent from the list is not accepted at that station |

Rare goods keys seen so far: `leestianeviljuice`, `bluemilk` (Azure Milk), `lavianbrandy`, `disomacorn`, `orrerianviciousbrew`, `uszaiantreegrub`, `alieneggs` (Leathery Eggs), `zeesszeantgrubglue`. Do not guess keys; add them when observed.

## Combat

| Event | Fields used | Notes |
|---|---|---|
| `ShipTargeted` | `TargetLocked, Ship, Ship_Localised, PilotName_Localised, PilotRank, Power, Faction, HullHealth, ScanStage` | fields appear progressively with `ScanStage`; `Power` is present for Powerplay-aligned NPCs; merits keeps the last one with a `Ship` for zone attribution |
| `Bounty` | `Target, Target_Localised, TotalReward, VictimFaction` | merits cause `bounty hunting`; absent for Powerplay zone kills |
| `FactionKillBond` | `Reward, AwardingFaction, VictimFaction` | ordinary conflict zones only; merits cause `combat zone` (faction) |
| `PVPKill` | `Victim` | |
| `UnderAttack`, `HullDamage`, `ShieldState`, `HeatWarning` | | not stored; counts only |
| `Died` | | feed |
| `Interdicted` | `Interdictor_Localised` | feed |

Observed in a Medium Powerplay conflict zone (LP 673-42, 2026-10-23): `PowerplayMerits` of 14 (assist or shared kill), 172 (kill of a Crusader/Phantom-sized ship), 216 (Expert Fer-de-Lance). No `Bounty` or `FactionKillBond` was logged for any of them.

## Materials and engineering

| Event | Fields used | Notes |
|---|---|---|
| `Materials` | `Raw[], Manufactured[], Encoded[]` each `{Name, Name_Localised?, Count}` | at load; rebuilds the inventory |
| `MaterialCollected`, `MaterialDiscarded` | `Category, Name, Name_Localised, Count` | |
| `MaterialTrade` | `Paid{Material, Quantity, Category}, Received{...}` | |
| `EngineerCraft` | `Slot, BlueprintName, Level, Ingredients[{Name, Count}]` | feed + inventory decrement |
| `Synthesis`, `TechnologyBroker`, `ScientificResearch` | `Materials[]` or `Ingredients[]` | decrement |
| `EngineerContribution` | `Type == Materials, Material, Quantity` | decrement |
| `MissionCompleted` | `LocalisedName, Name, MaterialsReward[{Name, Count, Category}]` | feed, merits cause `missions`, inventory increment |

## Carrier

| Event | Fields used | Notes |
|---|---|---|
| `CarrierStats` | `Name, Callsign, FuelLevel, SpaceUsage{FreeSpace, Cargo}, Finance{CarrierBalance}, DockingAccess, Crew[{CrewRole, Activated}]` | only written when the carrier management screen is opened; hence the backfill scan of older journals |
| `CarrierLocation` | `StarSystem` | written at load when you own a carrier |
| `CarrierJumpRequest` | `SystemName` | feed |

## Other feed-only events

`FuelScoop` (`Scooped`), `MissionCompleted`, `Bounty`, `Interdicted`, `Died`, `CarrierJump*`, `MaterialCollected`, `EngineerCraft`. The feed formatter table is `FEED` in `modules/journal/module.py`; add an entry there to show a new event.

## Snapshot files watched but not yet used

`ModulesInfo.json`, `ShipLocker.json`, `Backpack.json`, `NavRoute.json` (the plotted route; a natural input for a route card), `Shipyard.json`, `Outfitting.json`. The watcher emits `journal.file.<Name>` for each when it changes.

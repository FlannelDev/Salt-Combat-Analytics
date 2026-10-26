# Heroes WoW Combat Analyzer — Fight Roster & Gear Edition

Client-only WoW 3.3.5a combat analyzer. Start with `Start-Heroes-Analyzer.bat`.

## Per-fight roster
Import or tail your combat log as before. Select an individual Fight in the dashboard, then open **Fight Roster / Gear**. Player participation is inferred from damage/healing and cast/miss events in that fight; simply being in a raid does not count. Pet-only participation may not be credited to its owner.

## Gear history
The bundled addon inspects nearby party/raid equipment about every five seconds, capturing item links, enchants, gems, names and quoted tier flavor. Stat collection has been removed. After `/reload` or logout, import the WoW `WTF/Account/<account>/SavedVariables/HeroesCombatSnapshot.lua` file. Each distinct capture is preserved in `gear_history.json`; the latest per-character profile remains in `profiles.json`. Importing the same file twice does not duplicate history.

Gear is associated with a fight only when a dated snapshot is from *before* that fight (within 15 days by the combat log's local month/day clock). It is labeled **Prior known snapshot (not verified at pull)**. If none exists, the report says so. The 3.3.5a combat log does not contain year or full equipment; clock changes, different years and timezone mismatches can prevent matching. Existing old SavedVariables contain only the latest snapshot for each member, not a recoverable historical record. No exact gear-at-pull guarantee is possible without a live data bridge or server support.

WoW 3.3.5a addons cannot directly write custom `.log` files or force SavedVariables to disk; `/reload`, logout or clean shutdown are required. `Start-Snapshot-Sync.bat` can copy newly saved snapshots to Logs, but does not force a write.

## Testing
Select a fight and inspect the roster. Import a SavedVariables file captured *before* a later fight and verify the gear appears as a prior known snapshot; importing a file with a later timestamp must not be presented as that earlier fight's equipment.

## Automatic sync
With `wow_path.txt` configured, the analyzer itself watches every account's SavedVariables file every three seconds and automatically imports newly written snapshots into history. No manual upload is required after a successful `/reload` or logout. A running WoW client still cannot flush data on demand. The bundled launcher also starts the legacy copy-to-Logs helper; it is optional for the analyzer's new history importer.


## Fight gear history auto-sync (v2)
Run `Start-Heroes-Analyzer.bat`. Its companion `snapshot_sync.py` watches every
`WTF/Account/*/SavedVariables/HeroesCombatSnapshot.lua` file and atomically copies
each account into `WoW/Logs/HeroesCombatSnapshots/<account>/HeroesCombatSnapshot.lua`
when WoW writes the file on `/reload`, logout or normal exit. The analyzer reads
these **Logs** copies every three seconds and imports the addon's `gearHistory`
records. It does not require reloading after every fight. The addon stores up to
1,500 changed equipment snapshots per client in SavedVariables; snapshots are
written to disk only on reload/logout. Existing combat log processing remains live.
Note: addon inspection records are equipment observation times, not independently
verified boss-pull loadouts.


## Salt guild edition (v7)
Branded Salt Combat Analytics, developed by Flannel. Crimson/gold HeroesWoW-inspired styling and spell icons for a curated set of Wrath-era spell IDs. Spell icons require internet access to the WoW icon CDN; unsupported/custom spell IDs use a neutral fallback. Combat calculations remain those of v6.


## Automatic combat logging (v10)
The bundled HeroesCombatSnapshot addon enables disk combat logging on login and world entry and rechecks every 10 seconds. Combat events are written by WoW to `World of Warcraft\Logs\WoWCombatLog.txt`. The addon must be installed in `Interface\AddOns\HeroesCombatSnapshot` and enabled on each WoW client/account. Use `/hcs log` to check whether disk logging is enabled. Do not use `/combatlog` to turn it on manually: that command toggles logging. This change does not alter encounter detection in the Python analyzer.

## v11 — Expanded combat event engine and enemy balancing (2026-10-22)

- Encounter detection now includes normal attacks, misses, spell casts, healing and death events, rather than only positive damage/healing. One-event encounters are retained instead of discarded. Segments are still estimated from 18-second activity gaps; this is not a server-authoritative pull boundary.
- **Enemy Balancing** sidebar displays non-player, non-pet actors' outgoing damage/healing, incoming damage/healing, per-spell hit counts, averages, crit percentage, min/max and targets affected. The `/api/enemies?segment=<id>` endpoint exposes these results for future reports.
- Existing player-only Damage Done, owner-attributed pet damage, spell-ID-aware offhand grouping, gear snapshots, and addon auto combat logging remain available.
- **Not yet implemented:** live incremental log tailing, SQLite persistence, complete WCL parity, verified encounter phases, mitigation inference, a packaged .exe, and complete custom enemy classification. Use the provided .bat launcher and Python for this build.
- Client combat logs can omit mechanics or events outside client visibility; enemy statistics represent observed data, not hidden server configuration.

### Verification
`python -m py_compile server.py` and `node --check` on extracted browser JavaScript passed. The bundled log parsed 212,502 events, with 6 estimated combat segments; the enemy endpoint returned results for the first segment. Browser and in-game addon testing remain outstanding.

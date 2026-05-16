# FS25 Savegame Mover

> Move a Farming Simulator 25 farm — vehicles, animals, bales, pallets, stored
> grain, food, money — from one map savegame to another, with a PDA-styled GUI
> for picking where everything should land on the new map.

![Status](https://img.shields.io/badge/status-v0.2_dev_preview-orange) ![Platform](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.11+-green) ![License](https://img.shields.io/badge/license-MIT-yellow)

## What it does

FS25 has no built-in way to move a farm between maps. This tool reads your
existing savegame, lets you point at a fresh save on the new map, and rewrites
the new save with your farm — placed exactly where you click on the PDA-style
overview.

**Migrates:**

- All vehicles & equipment owned by your farm (`farmId=1`)
  - Snapped to the ground via the target map's heightmap
  - Rotated to face one direction (N / E / S / W)
  - Arranged in a configurable grid (default 10m × 10m)
  - Attached implements automatically detached so each unit lands individually
- Bales, pallets and other items sitting in the world (`items.xml`)
- Bales & pallets in **auto-storage sheds** (`<objectStorage>`)
- Animal herds (cows, sheep, pigs, chickens, horses, etc.) merged into target
  pens you pick
- Pen-internal storage — food (hay/grass/silage/TMR/grain/forage), bedding
  (straw), water, and produced outputs (slurry / manure / milk)
- Loose grain / diesel / fertiliser / seeds / lime stored in silos — both
  `<fillUnit><unit>` and `<silo><storage><node>` shapes
- Farm money and loans

**Doesn't migrate:**

- **Bunker silo silage** — the visible mound is runtime physics state that XML
  can't recreate. Optionally **cashed out**: a toggle on the Assign page
  averages the source save's silage prices from `economy.xml` and adds the
  proceeds to the target farm's money instead of losing it.
- Placeables you've bought (sheds, silos, animal pens) — re-purchase on the
  new map. You can then migrate animals / grain / bales INTO them via the
  wizard.

## Quick start

1. Grab the latest `FS25SavegameMover.exe` from
   [Releases](../../releases). No Python install required.
2. Start a **fresh save on your target map** in FS25 first. We use it to
   discover where the silos, animal pens and other points-of-interest sit on
   the new map.
3. Double-click `FS25SavegameMover.exe`. The wizard opens maximised
   (10–15 s on first launch — PyInstaller unpacking).
4. Walk through the 6 wizard pages (see below).
5. Migrate. The tool writes a **new** savegame folder — your originals are
   never touched. Copy the new folder into an empty `savegameN` slot under
   `Documents\My Games\FarmingSimulator2025\` to load it in-game.

The tool **remembers** your FS25 folder across launches in
`%APPDATA%\fs25-savegame-mover\config.json`.

## Wizard flow

| # | Page | What you do |
|---|---|---|
| 1 | **FS25 folder** | The tool auto-detects `Documents\My Games\FarmingSimulator2025` and lists the savegames it found. Also auto-resolves the mods directory (including `modsDirectoryOverride` in `gameSettings.xml`) and the FS25 game install (scraped from `log.txt`). Path is remembered for next launch. |
| 2 | **Source save** | Dropdown of detected saves. Pick the one to migrate FROM. Summary shows vehicles / animals / bales / silage / money. |
| 3 | **Target save + map** | Dropdown of fresh-ish saves (excluding the source). The map mod is **auto-resolved** to a `.zip` / unpacked folder / base-game install path. Manual Browse fallback for edge cases. |
| 4 | **Assign destinations** | PDA viewer on the left, dropdowns on the right. Right-click the PDA to set the vehicle drop zone (terrain height auto-sampled). Pick heading, row spacing, grid width. Map each source silo / pen / auto-storage shed onto a target placeable. Toggle pen-internal storage and bunker-silage cash-out on/off. |
| 5 | **Review** | Migration summary + a table of every mod the source uses. You must install matching mods on the target system before loading. |
| 6 | **Run** | Pick an output folder (defaults to `<target>_migrated`), click **Migrate**, results log appears. |

### PDA viewer

- Drag = pan, mouse wheel = zoom, right-click = set vehicle drop zone.
- POI markers are colour-coded by category:
  - 🟡 silo · 🔵 pen · 🟣 bale/pallet storage · 🟢 sell point · 🟣 production · 🟠 shop · ⚪ shed/other
- Above the PDA, a row of checkboxes lets you show/hide categories
  independently. Default-on: silo, pen, storage. Default-off: the rest.
- Marker labels are bright white bold text next to each dot.

## Map mod support

The tool reads the map mod to:

- Decode the PDA `overview.dds` (BC1/BC3) into the viewer.
- Sample the heightmap (`dem.png`) so vehicles spawn on the ground rather than
  falling from y=100m.
- Resolve preplaced placeable positions from the `.i3d` or
  `maps/config/placeables.xml`, so silos / pens that show as
  `position="0 0 0"` in the savegame get their real coordinates.

Supported layouts:

| Source | Where | Example |
|---|---|---|
| Third-party map mods (zip) | `<mods>/MyMap.zip` | `F:\Fs25Mods\FS25_Witcombe.zip` |
| Third-party map mods (unpacked) | `<mods>/MyMap/` | `F:\Fs25Mods\FS25_Mechet\` |
| Base-game maps | `<install>/data/maps/<name>/` | `…\data\maps\mapEU\` |
| DLC maps | `<install>/pdlc/<name>.dlc` | Encrypted — **source only**, can't be used as target |

`maps/maps.xml` and `map/map.xml` layouts both work, as do French/multi-locale
placeable names — POIs are classified by what the placeable *contains*
(`<husbandryAnimals>` → pen, `<bunkerSilo>` / `<fillUnit>` / `<silo>` → silo,
`<objectStorage>` → bale/pallet storage), not by English keywords.

## Limitations & gotchas

- **Mod parity.** Vehicles / items / placeables that reference a mod
  (`modName=…`) will silently fail to load on the target system if that mod
  isn't installed there. The Review page lists every mod required.
- **Bunker silo silage** is not migrated. Use the silage cash-out toggle, or
  sell / consume it on the source map before migrating.
- **DLC maps as TARGET** are not supported because their content is encrypted
  by GIANTS. DLC saves can be migrated FROM, just not INTO.
- **Single farm only.** Only farm 1 (your farm) is migrated; showcase
  vehicles / AI farms stay behind.
- **Target's existing starter vehicles** stay where they are on the new map —
  the migration adds your fleet next to them, not in place of them.

## Building from source

Requires Python 3.11+ on Windows.

```powershell
git clone https://github.com/ConGan98/fs25-savegame-mover.git
cd fs25-savegame-mover
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Run the wizard:

```powershell
python -m fs25_mover
```

Build a standalone `.exe`:

```powershell
pyinstaller --noconfirm --onefile --windowed --name FS25SavegameMover `
  --icon assets\icon.ico `
  --collect-submodules PySide6 --collect-submodules PIL `
  --collect-binaries lxml launcher.py
```

Output lands in `dist\FS25SavegameMover.exe` (~244 MB).

## CLI subcommands

The same `.exe` (or `python -m fs25_mover`) can be driven from the
command line — useful for batch jobs or debugging.

| Command | Purpose |
|---|---|
| `fs25_mover` (no args) | Launch the wizard. |
| `fs25_mover wizard` | Same as above, explicit. |
| `fs25_mover summary <save>` | Print a text summary of a savegame. |
| `fs25_mover pda <map> [--savegame <save>]` | Open the standalone PDA viewer. |
| `fs25_mover init-plan --source <s> --target <t> --output <o> --plan <p.json>` | Generate a starter migration plan JSON. |
| `fs25_mover migrate --plan <p.json>` | Apply a migration plan headlessly. |

## Project layout

```
src/fs25_mover/
├── __main__.py              CLI / wizard entry
├── parsers/
│   ├── savegame.py          FS25 savegame folder reader / writer
│   ├── fs25_root.py         FS25 root + savegame + mods + install discovery
│   ├── map_zip.py           Map mod (.zip or folder) — overview, i3d, heightmap, hotspots
│   ├── i3d.py               Streaming i3d parser → uniqueId → world position
│   └── dds.py               DDS → QImage via Pillow
├── model/
│   ├── farm.py              FarmSnapshot — derived view of a savegame
│   ├── poi.py               PoiMarker resolution + content-based classification
│   └── migration_plan.py    MigrationPlan dataclass + JSON IO
├── migrate/
│   ├── engine.py            Orchestrator
│   ├── vehicles.py          Reposition, rotate, ground-snap, detach implements
│   ├── animals.py           Move <husbandryAnimals> clusters + <husbandry><storage>
│   ├── silos.py             Merge <fillUnit> + <silo><storage><node> grain
│   ├── object_storage.py    Bale/pallet auto-storage (<objectStorage>)
│   ├── silage_sale.py       Optional bunker-silage cash-out
│   ├── items.py             items.xml (bales, pallets, world items)
│   ├── money.py             farms.xml money + loan transfer
│   └── ids.py               uniqueId collision handling
├── ui/
│   ├── wizard.py            QWizard + WizardState
│   ├── pages/               setup, source, target, assign, review, run
│   ├── pda_view.py          Pan/zoom QGraphicsView + marker layer + category groups
│   ├── pda_window.py        Standalone PDA viewer
│   └── theme.py             FS25-flavoured QSS
└── util/
    ├── config.py            Persistent app config (%APPDATA%)
    └── paths.py             Default-path helpers
```

## Tech stack

- **Python 3.11+**
- **PySide6** (Qt 6) for the GUI
- **lxml** for fast, attribute-order-preserving XML
- **Pillow** for DDS decoding and heightmap sampling
- **PyInstaller** for single-file `.exe` packaging

## Contributing

Issues and PRs welcome. If a particular map mod isn't detecting POIs
correctly, please attach the map mod `.zip` filename and a screenshot of the
in-game PDA showing where the missing markers should be. The classifier is
content-based so it generally handles non-English map placeables out of the
box — but new file layouts may still need a path tweak in `parsers/map_zip.py`.

## License

[MIT](LICENSE). Code is original; the Farming Simulator trademark, savegame
XML schemas and map mod contents belong to GIANTS Software and the respective
mod authors.

## Acknowledgements

- GIANTS Software for Farming Simulator 25.
- The FS25 modding community for the maps and mods this tool reads from.

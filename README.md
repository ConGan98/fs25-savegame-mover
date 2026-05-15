# FS25 Savegame Mover

> Move a Farming Simulator 25 farm — vehicles, animals, bales, money, stored
> grain — from one map savegame to another, with a PDA-styled GUI for picking
> where everything should land on the new map.

![Status](https://img.shields.io/badge/status-dev_preview-orange) ![Platform](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.11+-green)

## What it does

FS25 has no built-in way to move a farm between maps. This tool reads your
existing savegame, lets you point at a fresh save on the new map, and rewrites
the new save with your vehicles, animals, bales and money — placed exactly
where you click on the PDA-style overview.

**Migrates:**
- All vehicles & equipment owned by your farm
- Bales, pallets, and other world items
- Animal herds (cows, sheep, pigs, chickens, horses, etc.) — merged into a
  target animal pen you pick
- Loose-grain silo contents (per fillType) — merged into a target storage silo
- Farm money and loans

**Doesn't migrate:**
- Bunker silo silage. The visible silage mound is runtime physics state that
  XML alone can't recreate, and bunker dimensions differ between maps. The
  wizard warns you upfront; sell or feed off the silage before migrating.
- Placeables (sheds, silos, animal pens you've bought). These need to be
  re-purchased on the new map — but you can target your migrated animals
  into them via the assignment step.

## Quick start (end users)

1. Grab the latest `FS25SavegameMover.exe` from
   [Releases](../../releases). No Python install required.
2. Start a **fresh save on your target map** in FS25 first. We use this fresh
   save to discover where the silos, animal pens, and other points-of-interest
   sit on the new map.
3. Double-click `FS25SavegameMover.exe`. The wizard opens (10–15s on first
   launch — PyInstaller unpacks itself).
4. Walk through the 6 wizard pages (see [Wizard flow](#wizard-flow) below).
5. Migrate. The tool writes a **new** savegame folder — your originals are
   never touched. Copy the new folder into an empty `savegameN` slot under
   `Documents\My Games\FarmingSimulator2025\` to load it in-game.

## Wizard flow

| Step | What you do |
|---|---|
| **Welcome** | Read the intro & bunker-silage caveat. |
| **Source** | Browse to the savegame folder you want to migrate FROM. Tool shows a summary (vehicles, animals, money). |
| **Target + map** | Browse to the fresh save on the new map, then to the map's mod `.zip` file. POIs are auto-detected from the i3d + placeables config. |
| **Assign** | Right-click the PDA where you want vehicles to land. Pick the heading (N/E/S/W) and spacing. For each source silo/pen, pick a destination from the dropdown. |
| **Review** | Migration summary + a table of every mod the source uses. You must install matching mods on the target system before loading. |
| **Run** | Pick an output folder, click Migrate. Done. |

## Limitations & known gotchas

- **Mod parity.** Vehicles, items and placeables that reference a mod
  (`modName=...`) will silently fail to load on the target system if that mod
  isn't installed. The Review page lists every mod required.
- **Bunker silo silage** is not migrated (see above).
- **Multiplayer farms.** Only farm 1 (your farm) is migrated by default.
- **Witcombe-style starter vehicles** on the target fresh save remain in
  place — they sit at the new map's farmyard alongside your migrated row.
- **Map variations.** The tool supports both `map/` and `maps/` zip layouts
  and base-game map paths (mapDE/mapUS/mapFR). Maps that pre-place placeables
  via the i3d (Witcombe) AND maps that use `maps/config/placeables.xml`
  (Mechet) are both handled. If a new map breaks detection, open an issue
  with the mod zip name.

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
  --collect-submodules PySide6 --collect-submodules PIL `
  --collect-binaries lxml launcher.py
```

Output lands in `dist\FS25SavegameMover.exe` (~250 MB).

## CLI subcommands

The same `.exe` (or `python -m fs25_mover`) can also be driven from the
command line — useful for batch jobs or debugging.

| Command | Purpose |
|---|---|
| `fs25_mover` | Launch the wizard (default). |
| `fs25_mover summary <save>` | Print a text summary of a savegame. |
| `fs25_mover pda <map.zip> [--savegame <save>]` | Open the standalone PDA viewer for a map. |
| `fs25_mover init-plan --source <s> --target <t> --output <o> --plan <plan.json>` | Generate a starter migration plan JSON for editing. |
| `fs25_mover migrate --plan <plan.json>` | Apply a migration plan headlessly. |

## Project layout

```
src/fs25_mover/
├── __main__.py           CLI / wizard entry
├── launcher.py           PyInstaller entry shim
├── parsers/
│   ├── savegame.py       FS25 savegame folder reader / writer
│   ├── map_zip.py        Map mod (.zip or folder) — overview.dds, i3d, terrain
│   ├── i3d.py            Streaming i3d parser → uniqueId → world position
│   └── dds.py            DDS → QImage via Pillow
├── model/
│   ├── farm.py           FarmSnapshot — derived view of a savegame
│   ├── poi.py            PoiMarker resolution + classification
│   └── migration_plan.py MigrationPlan dataclass + JSON IO
├── migrate/
│   ├── engine.py         Orchestrator
│   ├── vehicles.py       Reposition, rotate, detach implements
│   ├── animals.py        Move <husbandryAnimals> clusters between pens
│   ├── silos.py          Merge <fillUnit> grain (bunker silage skipped)
│   ├── items.py          items.xml (bales, pallets)
│   ├── money.py          farms.xml money + loan transfer
│   └── ids.py            uniqueId collision handling
├── ui/
│   ├── wizard.py         QWizard + WizardState
│   ├── pages/            One file per wizard step
│   ├── pda_view.py       Pan/zoom QGraphicsView + marker layer
│   ├── pda_window.py     Standalone PDA viewer
│   └── theme.py          FS25-flavoured QSS
└── util/paths.py
```

## Tech stack

- **Python 3.11+**
- **PySide6** (Qt 6) for the GUI
- **lxml** for fast, format-preserving XML
- **Pillow** for DDS decoding and heightmap sampling
- **PyInstaller** for single-file `.exe` packaging

## Contributing

Issues and PRs welcome. If a particular map mod isn't detecting POIs
correctly, please attach the map mod `.zip` filename and a screenshot of the
in-game PDA showing where the missing markers should be.

## License

[MIT](LICENSE). Code is original; the Farming Simulator trademark, savegame
XML schemas and map mod contents belong to GIANTS Software and the
respective mod authors.

## Acknowledgements

- GIANTS Software for Farming Simulator 25.
- The FS25 modding community for the maps and mods this tool reads from.

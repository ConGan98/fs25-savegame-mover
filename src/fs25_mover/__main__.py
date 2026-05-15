"""Entry point.

Phase 1 (current): CLI smoke test.
    python -m fs25_mover summary <savegame_folder>

Later phases will launch the Qt wizard when no args are passed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .migrate.engine import apply as apply_migration
from .model.farm import FarmSnapshot
from .model.migration_plan import MigrationPlan
from .parsers.savegame import Savegame


def cmd_summary(args: argparse.Namespace) -> int:
    sg = Savegame.load(args.path)
    snap = FarmSnapshot.from_savegame(sg)

    print(f"Savegame:   {sg.path}")
    print(f"Map:        {snap.map_title or '(unknown)'}  [{snap.map_id or '(no mapId)'}]")
    print()
    print(f"Vehicles:   {snap.vehicle_count}")
    if snap.vehicles_by_mod:
        for mod, n in snap.vehicles_by_mod.most_common():
            print(f"  {n:4d}  {mod or '(base game)'}")
    print()
    print(f"Items:      {snap.item_count}")
    if snap.items_by_mod:
        for mod, n in snap.items_by_mod.most_common():
            print(f"  {n:4d}  {mod or '(base game)'}")
    print()
    print(f"Bunker silos: {len(snap.silos)}")
    for s in snap.silos:
        ft = s.fill_type or "(state-driven)"
        print(f"  uid={s.placeable_uid[:12]}..  state={s.state}  {ft:16s}  level={s.fill_level:,.0f}  pos={s.position}")
    print()
    if snap.grain_totals:
        print("Grain / fill totals across placeables:")
        for ft, total in sorted(snap.grain_totals.items(), key=lambda kv: -kv[1]):
            print(f"  {ft:20s}  {total:,.0f}")
        print()
    print(f"Husbandries: {len(snap.husbandries)}")
    for h in snap.husbandries:
        subs = ", ".join(f"{n}x{t}" for t, n in h.sub_types.most_common())
        print(f"  uid={h.placeable_uid[:12]}..  total={h.total_animals}  ({subs})  pos={h.position}")
    print()
    print("Farms:")
    for fid in sorted(snap.farm_money):
        print(f"  farm {fid}:  money={snap.farm_money[fid]:>18,.2f}  loan={snap.farm_loans.get(fid, 0):>14,.2f}")
    return 0


def cmd_init_plan(args: argparse.Namespace) -> int:
    """Write a starter plan.json with auto-suggested pen/silo mappings."""
    src = Savegame.load(args.source)
    tgt = Savegame.load(args.target)

    # Auto-suggest pen mapping: for each source husbandry with animals, pick the
    # first target husbandry of any pen (user will refine in GUI / by hand).
    src_pens_with_animals = [
        p for p in src.placeables()
        if p.find(".//husbandryAnimals/clusters/animal") is not None
    ]
    tgt_pens = [
        p for p in tgt.placeables()
        if p.find(".//husbandryAnimals") is not None
    ]
    pen_mapping: dict[str, str] = {}
    for i, sp in enumerate(src_pens_with_animals):
        if i < len(tgt_pens):
            pen_mapping[sp.get("uniqueId")] = tgt_pens[i].get("uniqueId")

    # Auto-suggest silo mapping: only <fillUnit>-bearing storage silos with grain
    # in them. Bunker silos (silage) are intentionally excluded — see silos.py.
    src_storage = [
        p for p in src.placeables()
        if any(
            float(u.get("fillLevel") or 0) > 0
            for u in p.findall(".//fillUnit/unit")
        )
    ]
    tgt_storage = [
        p for p in tgt.placeables()
        if p.find(".//fillUnit/unit") is not None
    ]
    silo_mapping: dict[str, str] = {}
    for i, sp in enumerate(src_storage):
        if i < len(tgt_storage):
            silo_mapping[sp.get("uniqueId")] = tgt_storage[i].get("uniqueId")

    plan = MigrationPlan(
        source_path=str(Path(args.source).resolve()),
        target_path=str(Path(args.target).resolve()),
        output_path=str(Path(args.output).resolve()),
        drop_xyz=(args.drop_x, args.drop_y, args.drop_z),
        silo_mapping=silo_mapping,
        pen_mapping=pen_mapping,
    )
    plan.to_json(args.plan)
    print(f"Wrote plan to {args.plan}")
    print(f"  pen mappings: {len(pen_mapping)}")
    print(f"  silo mappings: {len(silo_mapping)}")
    print("Edit the JSON to refine mappings or change drop_xyz, then run `migrate --plan ...`.")
    return 0


def _qt_app():
    """Build (or reuse) a QApplication with the FS25-flavoured stylesheet applied."""
    from PySide6.QtWidgets import QApplication

    from .ui.theme import QSS

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    return app


def cmd_wizard(args: argparse.Namespace) -> int:
    from .ui.wizard import MigrationWizard

    app = _qt_app()
    w = MigrationWizard()
    w.show()
    return app.exec()


def cmd_pda(args: argparse.Namespace) -> int:
    from .ui.pda_window import PdaWindow

    app = _qt_app()
    win = PdaWindow(
        str(args.map),
        world_size=args.world_size,
        savegame_path=str(args.savegame) if args.savegame else None,
    )
    win.show()
    return app.exec()


def cmd_migrate(args: argparse.Namespace) -> int:
    plan = MigrationPlan.from_json(args.plan)
    report = apply_migration(plan)

    print(f"Migration written to: {report.output_path}")
    if report.vehicles:
        print(f"  vehicles moved: {report.vehicles.moved} (uid remaps: {len(report.vehicles.remap)})")
    if report.items:
        print(f"  items moved:    {report.items.moved} (uid remaps: {len(report.items.remap)})")
    if report.silos:
        f = len(report.silos.fillunit_moves)
        print(f"  storage moves:  {f} fillUnit grain transfers (skipped pairs: {len(report.silos.skipped)})")
        if report.silos.bunkers_abandoned:
            total = sum(lvl for _, lvl in report.silos.bunkers_abandoned)
            print(f"  WARNING: {len(report.silos.bunkers_abandoned)} bunker silo(s) with {total:,.0f} kg silage")
            print(f"           NOT migrated (silage mound geometry is runtime state).")
            print(f"           Consume / sell that silage on the source map before migrating,")
            print(f"           otherwise it is lost on the new map.")
    if report.animals:
        print(f"  animals moved:  {report.animals.total_moved} into {len(report.animals.moved_by_pen)} pens")
        if report.animals.unmatched_src_pens:
            print(f"    unmatched source pens: {report.animals.unmatched_src_pens}")
    if report.money and report.money.applied:
        print(f"  money:          ${report.money.money:,.2f}  loan: ${report.money.loan:,.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fs25-mover")
    sub = parser.add_subparsers(dest="cmd")

    p_sum = sub.add_parser("summary", help="Print a text summary of a savegame folder.")
    p_sum.add_argument("path", type=Path)
    p_sum.set_defaults(func=cmd_summary)

    p_init = sub.add_parser("init-plan", help="Generate a starter migration plan JSON.")
    p_init.add_argument("--source", type=Path, required=True)
    p_init.add_argument("--target", type=Path, required=True)
    p_init.add_argument("--output", type=Path, required=True, help="Folder for migrated save (will be created).")
    p_init.add_argument("--plan", type=Path, required=True, help="Path to write the plan JSON.")
    p_init.add_argument("--drop-x", type=float, default=0.0)
    p_init.add_argument("--drop-y", type=float, default=100.0)
    p_init.add_argument("--drop-z", type=float, default=0.0)
    p_init.set_defaults(func=cmd_init_plan)

    p_mig = sub.add_parser("migrate", help="Apply a migration plan.")
    p_mig.add_argument("--plan", type=Path, required=True)
    p_mig.set_defaults(func=cmd_migrate)

    p_pda = sub.add_parser("pda", help="Open the standalone PDA viewer for a map mod (.zip or folder).")
    p_pda.add_argument("map", type=Path, help="Path to a map mod .zip or unpacked folder.")
    p_pda.add_argument("--world-size", type=float, default=None, help="Terrain side length in metres (auto-detected from map.i3d if omitted).")
    p_pda.add_argument("--savegame", type=Path, default=None, help="Optional savegame folder to overlay (markers for silos, animal pens, etc.).")
    p_pda.set_defaults(func=cmd_pda)

    p_wiz = sub.add_parser("wizard", help="Launch the migration wizard GUI (default if no command given).")
    p_wiz.set_defaults(func=cmd_wizard)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        # No subcommand -> launch the wizard.
        return cmd_wizard(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

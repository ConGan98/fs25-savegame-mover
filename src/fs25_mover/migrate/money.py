"""Migrate farm money + loan from source farmId to target farmId."""
from __future__ import annotations

from dataclasses import dataclass

from ..parsers.savegame import Savegame


@dataclass
class MoneyMigrationResult:
    src_farm_id: int
    tgt_farm_id: int
    money: float
    loan: float
    applied: bool


def migrate_money(
    src: Savegame,
    tgt: Savegame,
    src_farm_id: int = 1,
    tgt_farm_id: int = 1,
) -> MoneyMigrationResult:
    src_root = src.root("farms.xml")
    tgt_root = tgt.root("farms.xml")
    if src_root is None or tgt_root is None:
        return MoneyMigrationResult(src_farm_id, tgt_farm_id, 0.0, 0.0, applied=False)

    src_farm = next(
        (f for f in src_root.findall("farm") if f.get("farmId") == str(src_farm_id)),
        None,
    )
    tgt_farm = next(
        (f for f in tgt_root.findall("farm") if f.get("farmId") == str(tgt_farm_id)),
        None,
    )
    if src_farm is None or tgt_farm is None:
        return MoneyMigrationResult(src_farm_id, tgt_farm_id, 0.0, 0.0, applied=False)

    money = float(src_farm.get("money") or 0)
    loan = float(src_farm.get("loan") or 0)
    tgt_farm.set("money", f"{money:.6f}")
    tgt_farm.set("loan", f"{loan:.6f}")
    return MoneyMigrationResult(src_farm_id, tgt_farm_id, money, loan, applied=True)

"""Optional: sell bunker silage on the source map and add the proceeds to the
migrated farm's money. Avoids losing silage outright (it can't be migrated
across map bunkers — see migrate/silos.py).

Pricing source: the source savegame's `economy.xml` keeps a 12-period price
history per fillType. We average the SILAGE periods to estimate a fair sale
price per litre.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from ..parsers.savegame import Savegame


@dataclass
class SilageSaleResult:
    total_litres: float
    price_per_litre: float
    proceeds: float
    bunkers_sold: int


def silage_avg_price_per_litre(sg: Savegame) -> float:
    """Average SILAGE price per litre from economy.xml's 12-period history.

    Period values are stored as price-per-1000-litres, so we divide by 1000.
    Returns 0.0 if economy.xml is missing or has no SILAGE entry.
    """
    root = sg.root("economy.xml")
    if root is None:
        return 0.0
    ft = root.find(".//fillType[@fillType='SILAGE']")
    if ft is None:
        return 0.0
    values: list[float] = []
    for p in ft.findall("./history/period"):
        if p.text:
            try:
                values.append(float(p.text))
            except ValueError:
                pass
    if not values:
        return 0.0
    return (sum(values) / len(values)) / 1000.0


def total_bunker_silage(sg: Savegame) -> tuple[float, int]:
    """Returns (total fillLevel litres, bunker count) for all bunker silos
    with content on the source map."""
    total = 0.0
    n = 0
    for p in sg.placeables():
        for bs in p.findall(".//bunkerSilo"):
            try:
                fl = float(bs.get("fillLevel") or 0)
            except ValueError:
                fl = 0.0
            if fl > 0:
                total += fl
                n += 1
    return total, n


def sell_silage_to_money(src: Savegame, tgt: Savegame, tgt_farm_id: int) -> SilageSaleResult:
    """Compute silage proceeds and add them to the target farm's money.
    Returns a SilageSaleResult; if there's nothing to sell, proceeds=0."""
    litres, n = total_bunker_silage(src)
    if litres <= 0:
        return SilageSaleResult(total_litres=0.0, price_per_litre=0.0, proceeds=0.0, bunkers_sold=0)
    price = silage_avg_price_per_litre(src)
    proceeds = litres * price

    farms_root = tgt.root("farms.xml")
    if farms_root is not None:
        farm = next(
            (f for f in farms_root.findall("farm") if f.get("farmId") == str(tgt_farm_id)),
            None,
        )
        if farm is not None:
            try:
                current = float(farm.get("money") or 0)
            except ValueError:
                current = 0.0
            farm.set("money", f"{current + proceeds:.6f}")

    return SilageSaleResult(
        total_litres=litres,
        price_per_litre=price,
        proceeds=proceeds,
        bunkers_sold=n,
    )

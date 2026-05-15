"""uniqueId collision handling.

FS25 uniqueIds look like `vehicle<32 hex>` or `placeable<32 hex>` (or `item<32 hex>`).
When merging two savegames, any source uniqueId that already exists in the target
must be regenerated with a fresh hex suffix. We keep a remap dict so cross-references
(e.g. an item attached to a placeable) can be patched if needed.
"""
from __future__ import annotations

import secrets


def new_uid(prefix: str) -> str:
    """Return e.g. 'vehicleXXXXXXXX...' with a fresh 32-hex suffix."""
    return f"{prefix}{secrets.token_hex(16)}"


def collect_ids(*roots) -> set[str]:
    """Collect every uniqueId attribute under the given XML roots."""
    seen: set[str] = set()
    for root in roots:
        if root is None:
            continue
        for el in root.iter():
            uid = el.get("uniqueId")
            if uid:
                seen.add(uid)
    return seen


def remap_collisions(src_elements, taken: set[str]) -> dict[str, str]:
    """For each source element with a uniqueId already in `taken`, mint a new id.

    Returns a dict of old_uid -> new_uid. Mutates `taken` to include the new ids
    so successive calls don't collide. Does NOT mutate the source elements yet —
    callers are responsible for applying the remap when they copy the elements
    into the target tree (so the source XML stays clean if we re-run).
    """
    remap: dict[str, str] = {}
    for el in src_elements:
        uid = el.get("uniqueId")
        if not uid:
            continue
        if uid in taken:
            prefix = _prefix_for(uid)
            new = new_uid(prefix)
            while new in taken:
                new = new_uid(prefix)
            remap[uid] = new
            taken.add(new)
        else:
            taken.add(uid)
    return remap


def _prefix_for(uid: str) -> str:
    """Extract the non-hex prefix from a uniqueId (e.g. 'vehicle' from 'vehicleabc123...')."""
    for i, ch in enumerate(uid):
        if ch in "0123456789abcdefABCDEF":
            return uid[:i] or "uid"
    return uid or "uid"

"""Parse `map.i3d` to resolve preplaced placeable uniqueIds to world positions.

map.i3d layout (relevant fragments):

    <TransformGroup nodeId="N" name="preplaced_bunkerSiloMedium"
                    translation="X Y Z" rotation="..."/>
    ...
    <UserAttribute nodeId="N">
      <Attribute name="uniqueId" type="string"
                 value="preplaced_bunkerSiloMedium_<32hex>"/>
    </UserAttribute>

So uniqueId is linked to a TransformGroup via the shared nodeId. We stream the
file with iterparse (it can be 20MB+) and emit a {uniqueId -> (x, y, z)} map.
"""
from __future__ import annotations

from pathlib import Path
from typing import IO

from lxml import etree

from .map_zip import MapSource


def parse_i3d_positions(i3d_bytes: bytes) -> dict[str, tuple[float, float, float]]:
    """Return uniqueId -> (x, y, z) for every preplaced placeable found."""
    return _parse_stream(_BytesStream(i3d_bytes))


def positions_for_savegame(map_src: MapSource) -> dict[str, tuple[float, float, float]]:
    """Convenience: read the map's i3d via MapSource and return the position map.

    Routes through MapSource._i3d() which handles every known map layout
    (map/, maps/, base-game variants, mod-named .i3d files).
    """
    i3d = map_src._i3d()
    if i3d is None:
        return {}
    # We have the parsed root already; serialise+reparse is wasteful but matches
    # the streaming parser's API. Cheap enough for a 20MB i3d.
    return parse_i3d_positions(etree.tostring(i3d[1]))


# ---------------------------------------------------------------------------

class _BytesStream:
    """Adapt a bytes blob to a minimal read()/close() file-like for iterparse."""

    def __init__(self, data: bytes) -> None:
        from io import BytesIO

        self._bio = BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._bio.read(n)

    def close(self) -> None:
        self._bio.close()


def _parse_stream(stream: IO[bytes]) -> dict[str, tuple[float, float, float]]:
    node_pos: dict[str, tuple[float, float, float]] = {}     # nodeId -> xyz
    node_uid: dict[str, str] = {}                            # nodeId -> uniqueId
    current_user_attr_node: str | None = None

    # iterparse with end events; clear elements as we go to keep memory flat.
    context = etree.iterparse(stream, events=("start", "end"))
    for event, el in context:
        tag = el.tag
        if event == "start":
            if tag == "UserAttribute":
                current_user_attr_node = el.get("nodeId")
            continue

        # event == "end"
        if tag == "TransformGroup":
            nid = el.get("nodeId")
            trans = el.get("translation")
            if nid and trans:
                parts = trans.split()
                if len(parts) == 3:
                    try:
                        node_pos[nid] = (float(parts[0]), float(parts[1]), float(parts[2]))
                    except ValueError:
                        pass
            el.clear()
        elif tag == "Attribute":
            if (
                current_user_attr_node is not None
                and el.get("name") == "uniqueId"
                and el.get("value")
            ):
                node_uid[current_user_attr_node] = el.get("value")
            el.clear()
        elif tag == "UserAttribute":
            current_user_attr_node = None
            el.clear()

    # Merge: uniqueId -> position
    out: dict[str, tuple[float, float, float]] = {}
    for nid, uid in node_uid.items():
        pos = node_pos.get(nid)
        if pos is not None:
            out[uid] = pos
    return out

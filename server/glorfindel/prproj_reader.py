"""Liest Premiere-Projekte (.prproj = gzip-XML), nur lesend.

Zweck: Struktur und Effekt-Rezepte aus einem fertigen Schnitt (z. B. S2 E7) lernen. Die Bridge baut Rohschnitte nach diesem Vorbild.
Das Format ist nicht öffentlich dokumentiert; es werden nur die für uns nötigen Teile gelesen (Sequenzen, Spuren, Clips, Effekte).
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree as ET

TICKS = 254_016_000_000.0
VIDEO_GROUP = "228cda18-3625-4d2d-951e-348879e4ed93"
AUDIO_GROUP = "80b8e3d5-6dca-4195-aefb-cb5f407ab009"


@dataclass
class Param:
    index: int
    name: str
    time_varying: bool
    static: str = ""
    keyframes: list[tuple[float, str]] = field(default_factory=list)   # (Sekunden relativ zum Clipanfang, Wert)


@dataclass
class Comp:
    match_name: str
    display: str
    params: list[Param]


@dataclass
class Item:
    name: str
    kind: str            # "sequenz" | "medium" | "grafik" | "einstellungsebene" | "unbekannt"
    start: float
    end: float
    comps: list[Comp]
    track: str = ""


@dataclass
class SeqInfo:
    name: str
    uid: str
    video: dict[int, list[Item]]
    audio: dict[int, list[Item]]


class Project:
    def __init__(self, xml: bytes):
        self.root = ET.fromstring(xml)
        self.by_id: dict[str, object] = {}
        self.by_uid: dict[str, object] = {}
        for el in self.root:
            if el.get("ObjectID"):
                self.by_id[el.get("ObjectID")] = el
            if el.get("ObjectUID"):
                self.by_uid[el.get("ObjectUID")] = el

    @classmethod
    def open(cls, path: str | Path) -> "Project":
        raw = Path(path).read_bytes()
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass  # bereits entpackt
        return cls(raw)

    # ---- Hilfen ----
    def deref(self, el):
        if el is None:
            return None
        if el.get("ObjectRef"):
            return self.by_id.get(el.get("ObjectRef"))
        if el.get("ObjectURef"):
            return self.by_uid.get(el.get("ObjectURef"))
        return el

    @staticmethod
    def _txt(el, path: str, default: str = "") -> str:
        c = el.find(path) if el is not None else None
        return (c.text or default) if c is not None else default

    # ---- Sequenzen ----
    def sequences(self) -> list[SeqInfo]:
        out = []
        for s in self.root:
            if s.tag != "Sequence":
                continue
            out.append(SeqInfo(self._txt(s, "Name"), s.get("ObjectUID") or "", self._tracks(s, VIDEO_GROUP, "V"), self._tracks(s, AUDIO_GROUP, "A")))
        return out

    def sequence(self, name: str) -> SeqInfo | None:
        return next((s for s in self.sequences() if s.name == name), None)

    def _tracks(self, seq, kind: str, prefix: str) -> dict[int, list[Item]]:
        res: dict[int, list[Item]] = {}
        for tg in seq.findall("TrackGroups/TrackGroup"):
            if self._txt(tg, "First") != kind:
                continue
            grp = self.deref(tg.find("Second"))
            if grp is None:
                continue
            for t in grp.iter("Track"):
                track = self.deref(t)
                idx = int(t.get("Index", "0"))
                items = []
                if track is not None:
                    for ti in track.iter("TrackItem"):
                        d = self.deref(ti)
                        if d is not None:
                            items.append(self._item(d, f"{prefix}{idx + 1}"))
                items.sort(key=lambda i: i.start)
                res[idx] = items
        return res

    def _item(self, it, track: str) -> Item:
        sub = self.deref(it.find("ClipTrackItem/SubClip"))
        name = self._txt(sub, "Name") if sub is not None else ""
        st, en = it.find(".//Start"), it.find(".//End")
        start = int(st.text) / TICKS if st is not None and st.text else -1.0
        end = int(en.text) / TICKS if en is not None and en.text else -1.0
        comps = self._components(it)
        kind = self._kind(name, sub, comps)
        return Item(name or "?", kind, start, end, comps, track)

    def _kind(self, name: str, sub, comps: list[Comp]) -> str:
        if name == "Einstellungsebene":
            return "einstellungsebene"
        if any(c.match_name in ("AE.ADBE Text", "AE.ADBE Graphic Group") for c in comps) or name == "Grafik":
            return "grafik"
        if name.startswith("Verschachtelte Sequenz") or name in ("Play", "Pause") or name.endswith("Sequenz"):
            return "sequenz"
        return "medium" if name else "unbekannt"

    # ---- Effekte ----
    def _components(self, it) -> list[Comp]:
        chain = self.deref(it.find("ClipTrackItem/ComponentOwner/Components"))
        if chain is None:
            return []
        out = []
        for c in chain.iter("Component"):
            d = self.deref(c)
            if d is None or d.find("Component/Params") is None and d.find("MatchName") is None:
                continue
            params = []
            for p in d.findall("Component/Params/Param"):
                pd = self.deref(p)
                if pd is None:
                    continue
                params.append(self._param(int(p.get("Index", "0")), pd))
            out.append(Comp(self._txt(d, "MatchName"), self._txt(d, "Component/DisplayName"), params))
        return out

    def _param(self, index: int, pd) -> Param:
        tv = self._txt(pd, "IsTimeVarying") == "true"
        start = self._txt(pd, "StartKeyframe")
        static = start.split(",")[1] if start.count(",") >= 1 else self._txt(pd, "CurrentValue")
        kfs = []
        for part in self._txt(pd, "Keyframes").split(";"):
            f = part.split(",")
            if len(f) >= 2 and f[0].strip():
                kfs.append((int(f[0]) / TICKS, f[1].strip()))
        return Param(index, self._txt(pd, "Name"), tv, static.strip(), kfs)


def effect_recipe(comp: Comp, clip_len: float, anchor: str = "start") -> dict:
    """Effekt eines Clips als Rezept: nur Parameter, die sich ändern (Keyframes) oder nicht dem Standard entsprechen können.
    Zeiten relativ zum Clipanfang (`anchor='start'`) bzw. zum Clipende (`'end'`, negativ)."""
    base = clip_len if anchor == "end" else 0.0
    params = []
    for p in comp.params:
        if not p.name.strip():
            continue
        entry = {"index": p.index, "name": p.name, "static": p.static, "time_varying": p.time_varying}
        if p.time_varying and p.keyframes:
            entry["keyframes"] = [[round(t - base, 4), v] for t, v in p.keyframes]
        params.append(entry)
    return {"match_name": comp.match_name, "display": comp.display, "anchor": anchor, "params": params}


def parse_value(raw: str):
    """Parameterwert aus dem Projekt in einen JSON-tauglichen Wert: bool, Zahl, Punkt {x,y} oder Farbe {argb16}."""
    r = (raw or "").strip()
    if r in ("true", "false"):
        return r == "true"
    if ":" in r:
        try:
            x, y = r.split(":", 1)
            return {"point": [float(x), float(y)]}
        except ValueError:
            return r
    try:
        f = float(r.rstrip("."))
    except ValueError:
        return r
    if f.is_integer() and abs(f) >= 2 ** 40:       # 64-Bit-Farbwert: je 16 Bit A, R, G, B
        v = int(f)
        v = int(r.rstrip("."))
        return {"argb16": [(v >> 48) & 0xFFFF, (v >> 32) & 0xFFFF, (v >> 16) & 0xFFFF, v & 0xFFFF]}
    return int(f) if f.is_integer() and "." not in r else f

"""Bildbibliothek (Heft §5.4): XMP-Index (SQLite), Suche, Web-Import, Credit-Vorbelegung, Konturfarbe."""
from __future__ import annotations

import colorsys
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from defusedxml import ElementTree as ET

from . import media

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
VIDEO_EXT = {".mov", ".mp4", ".mkv", ".webm"}  # animierte Wallpaper
NS = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "dc": "http://purl.org/dc/elements/1.1/",
      "lr": "http://ns.adobe.com/lightroom/1.0/", "x": "adobe:ns:meta/"}


# ---------- XMP ----------
def _li_texts(el) -> list[str]:
    if el is None:
        return []
    return [(li.text or "").strip() for li in el.iter("{%s}li" % NS["rdf"]) if (li.text or "").strip()]


def parse_xmp_packet(xml: str) -> dict:
    """Keywords (dc:subject + hierarchische lr:hierarchicalSubject), Titel, Beschreibung, Ersteller."""
    root = ET.fromstring(xml.encode("utf-8"))
    kw: list[str] = []
    title = desc = ""
    creators: list[str] = []
    for d in root.iter("{%s}Description" % NS["rdf"]):
        kw += _li_texts(d.find("dc:subject", NS))
        for h in _li_texts(d.find("lr:hierarchicalSubject", NS)):
            kw += [p for p in re.split(r"[|/]", h) if p]
        t = _li_texts(d.find("dc:title", NS))
        title = title or (t[0] if t else d.get("{%s}title" % NS["dc"], ""))
        ds = _li_texts(d.find("dc:description", NS))
        desc = desc or (ds[0] if ds else "")
        creators += _li_texts(d.find("dc:creator", NS))
    seen, kws = set(), []
    for k in kw:
        if k.lower() not in seen:
            seen.add(k.lower())
            kws.append(k)
    return {"keywords": kws, "title": title, "description": desc, "creator": ", ".join(creators)}


def read_xmp(path: Path) -> dict:
    """XMP aus Sidecar `.xmp` oder eingebettetem Paket (erste 2 MB) lesen."""
    side = path.with_suffix(".xmp")
    packets: list[str] = []
    if side.exists():
        packets.append(side.read_text(encoding="utf-8", errors="replace"))
    elif path.suffix.lower() in IMAGE_EXT:
        with open(path, "rb") as f:
            head = f.read(2 * 1024 * 1024)
        a, b = head.find(b"<x:xmpmeta"), head.find(b"</x:xmpmeta>")
        if a >= 0 and b > a:
            packets.append(head[a:b + len(b"</x:xmpmeta>")].decode("utf-8", errors="replace"))
    for p in packets:
        try:
            return parse_xmp_packet(p)
        except Exception:  # noqa: BLE001
            continue
    return {"keywords": [], "title": "", "description": "", "creator": ""}


# ---------- Index ----------
class ImageIndex:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("""CREATE TABLE IF NOT EXISTS images(
            path TEXT PRIMARY KEY, mtime REAL, title TEXT, description TEXT, creator TEXT,
            keywords TEXT, haystack TEXT, animated INTEGER)""")

    def index_folder(self, root: Path, folder: Path, limit: int | None = None) -> dict:
        """Neue/geänderte Dateien indizieren. Online-only-Dateien nur über Dateiname/Sidecar."""
        added = skipped = 0
        known = {r[0]: r[1] for r in self.db.execute("SELECT path, mtime FROM images")}
        for f in folder.rglob("*"):
            if f.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
                continue
            rel = f.relative_to(root).as_posix() if root in f.parents else f.as_posix()
            mt = f.stat().st_mtime
            if known.get(rel) == mt:
                skipped += 1
                continue
            meta = ({"keywords": [], "title": "", "description": "", "creator": ""}
                    if media.is_online_only(f) and not f.with_suffix(".xmp").exists() else read_xmp(f))
            hay = " ".join([f.stem.replace("_", " "), meta["title"], meta["description"], meta["creator"],
                            " ".join(meta["keywords"])]).lower()
            self.db.execute("INSERT OR REPLACE INTO images VALUES(?,?,?,?,?,?,?,?)",
                            (rel, mt, meta["title"], meta["description"], meta["creator"],
                             "|".join(meta["keywords"]), hay, int(f.suffix.lower() in VIDEO_EXT)))
            added += 1
            if limit and added >= limit:
                break
        self.db.commit()
        return {"added": added, "unchanged": skipped}

    def search(self, query: str = "", tags: list[str] | None = None, limit: int = 60) -> list[dict]:
        terms = [t for t in re.split(r"\s+", query.lower().strip()) if t] + [t.lower() for t in (tags or [])]
        sql, args = "SELECT path,title,description,creator,keywords,animated FROM images", []
        if terms:
            sql += " WHERE " + " AND ".join("haystack LIKE ?" for _ in terms)
            args = [f"%{t}%" for t in terms]
        sql += " ORDER BY path LIMIT ?"
        rows = self.db.execute(sql, args + [limit]).fetchall()
        return [{"path": r[0], "title": r[1], "description": r[2], "creator": r[3],
                 "keywords": [k for k in r[4].split("|") if k], "animated": bool(r[5])} for r in rows]

    def all_keywords(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for (k,) in self.db.execute("SELECT keywords FROM images"):
            for w in k.split("|"):
                if w:
                    counts[w] = counts.get(w, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    def get(self, path: str) -> dict | None:
        r = self.search_exact(path)
        return r

    def search_exact(self, path: str) -> dict | None:
        r = self.db.execute("SELECT path,title,description,creator,keywords,animated FROM images WHERE path=?",
                            (path,)).fetchone()
        return None if not r else {"path": r[0], "title": r[1], "description": r[2], "creator": r[3],
                                   "keywords": [k for k in r[4].split("|") if k], "animated": bool(r[5])}


# ---------- Credit / Konturfarbe ----------
def default_credit(path: str, meta: dict | None = None, artist_db: dict[str, str] | None = None) -> str:
    """Priorität: Künstler-Datenbank (Dateiname) > XMP-Ersteller > Dateiname."""
    from .rough_cut import credit_from_filename
    base = credit_from_filename(path)
    if artist_db and base in artist_db:
        return artist_db[base]
    if meta and meta.get("creator"):
        return meta["creator"].lower()
    return base


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def dominant_edge_color(img_path: Path, border: float = 0.08, size: int = 128) -> str:
    """Dominanter Farbton am Bildrand (gesättigte Farben bevorzugt, sehr dunkle/helle ignoriert)."""
    from PIL import Image
    im = Image.open(img_path).convert("RGB")
    im.thumbnail((size, size))
    w, h = im.size
    bw, bh = max(1, int(w * border)), max(1, int(h * border))
    px = []
    data = im.load()
    for x in range(w):
        for y in list(range(bh)) + list(range(h - bh, h)):
            px.append(data[x, y])
    for y in range(h):
        for x in list(range(bw)) + list(range(w - bw, w)):
            px.append(data[x, y])
    buckets: dict[tuple[int, int, int], list] = {}
    for r, g, b in px:
        key = (r // 32, g // 32, b // 32)
        buckets.setdefault(key, []).append((r, g, b))
    best, best_score = None, -1.0
    for pts in buckets.values():
        r, g, b = (sum(c[i] for c in pts) / len(pts) for i in range(3))
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        score = len(pts) * (0.4 + ss) * (0.3 + min(vv, 1 - 0.5 * max(0, vv - 0.85)))
        if vv < 0.12 or (vv > 0.95 and ss < 0.1):
            score *= 0.2
        if score > best_score:
            best, best_score = (r, g, b), score
    return _hex(best or (0x75, 0x24, 0x16))


def contour_color(path: Path, frames: int = 5) -> str:
    """Konturfarbe pro Artwork; bei animierten Wallpapern über mehrere Frames gemittelt."""
    if path.suffix.lower() in IMAGE_EXT:
        return dominant_edge_color(path)
    info = media.probe(path)
    colors = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(frames):
            f = Path(td) / f"f{i}.png"
            try:
                media.extract_frame(path, info["duration"] * (i + 0.5) / frames, f, width=256)
                colors.append(dominant_edge_color(f))
            except Exception:  # noqa: BLE001
                continue
    if not colors:
        return "#752416"
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]
    return _hex(tuple(sum(c[k] for c in rgb) / len(rgb) for k in range(3)))


# ---------- Web-Import ----------
def web_import(url: str, dest_dir: Path, client=None, max_bytes: int = 60 * 1024 * 1024) -> dict:
    """Bild per URL laden. Nur http/https, nur Bild-Content-Types, Größenlimit. Quell-URL wird zurückgegeben."""
    import httpx
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError("Nur http(s)-URLs erlaubt")
    dest_dir.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30,
                                    headers={"User-Agent": "Glorfindel/0.1 (Folgenbesprechung)"})
    try:
        r = client.get(url)
        r.raise_for_status()
    finally:
        if own:
            client.close()
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        raise ValueError(f"Kein Bild (Content-Type {ctype or 'unbekannt'})")
    if len(r.content) > max_bytes:
        raise ValueError("Bild zu groß")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(ctype, ".img")
    name = re.sub(r"[^\w .-]", "_", unquote(Path(u.path).stem) or "bild")[:80]
    dst = dest_dir / f"{name}{ext}"
    n = 1
    while dst.exists():
        dst = dest_dir / f"{name}_{n}{ext}"
        n += 1
    dst.write_bytes(r.content)
    return {"path": dst, "source_url": url, "content_type": ctype}

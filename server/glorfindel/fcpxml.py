"""Fallback ohne Panel: Final-Cut-Pro-7-XML (xmeml v4) aus dem Schnittpaket (Heft §6), für „Datei > Importieren“ in Premiere.

Enthält Clips, Standbilder, Audio und Marker. Credits, Effektvorgaben und Play/Pause müssen von Hand
ergänzt werden (Premiere importiert sie über xmeml nicht).

Aufbau folgt dem, was Premiere selbst exportiert: eindeutige IDs, `masterclipid`, `rate` an jedem Clip, vollständige
`file`-Blöcke (Video/Audio-Eigenschaften), `sourcetrack` an Audio-Clips, URL-kodierte `pathurl`, ganzzahlige Frames.
`validate_xmeml()` prüft das Ergebnis auf typische Importfehler, bevor die Datei geschrieben wird.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from xml.dom import minidom

VIDEO_TRACKS = ["V1", "V3", "V4"]
AUDIO_TRACKS = ["A2", "A3", "A4"]
SAMPLERATE = 48000


def _rate(parent: ET.Element, timebase: int, ntsc: bool) -> None:
    r = ET.SubElement(parent, "rate")
    ET.SubElement(r, "timebase").text = str(timebase)
    ET.SubElement(r, "ntsc").text = "TRUE" if ntsc else "FALSE"


def _text(parent: ET.Element, tag: str, value) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = str(value)
    return el


def path_url(full: str) -> str:
    """`file://localhost/F%3a/OneDrive/…` wie Premiere es schreibt (Leerzeichen und Sonderzeichen kodiert)."""
    p = full.replace("\\", "/")
    if p.startswith("/"):
        return "file://localhost" + quote(p, safe="/")
    head, _, rest = p.partition("/")
    if len(head) == 2 and head[1] == ":":
        return f"file://localhost/{head[0]}%3a/" + quote(rest, safe="/")
    return "file://localhost/" + quote(p, safe="/")


def to_fcpxml(pkg: dict, episode_file: str, episode_dur: float, folder: Path | str = "", stills_base: Path | str | None = None) -> str:
    seq = pkg["sequence"]
    fps = int(round(seq["fps"]))
    ep_fps = pkg["episode_fps"]
    ep_tb, ep_ntsc = int(round(ep_fps)), abs(ep_fps - round(ep_fps)) > 1e-3
    W, H = int(seq["width"]), int(seq["height"])

    def fr(t: float) -> int:
        return int(round(t * seq["fps"]))

    def efr(t: float) -> int:
        return int(round(t * ep_fps))

    # Aufnahmedateien: benötigte Länge je Datei vorab bestimmen
    rec_len: dict[str, float] = {}
    for c in (c for cl in pkg["tracks"].values() for c in cl):
        if c["type"] == "comment" and c.get("src_in") is not None:
            key = c.get("rec_path") or f"aufnahme_{c.get('rec')}.wav"
            rec_len[key] = max(rec_len.get(key, 0.0), c["src_out"])

    root = ET.Element("xmeml", version="4")
    s = ET.SubElement(root, "sequence", id="sequence-1")
    _text(s, "name", seq["name"])
    _text(s, "duration", max(1, fr(pkg["duration"])))
    _rate(s, fps, False)
    tc = ET.SubElement(s, "timecode")
    _rate(tc, fps, False)
    _text(tc, "string", "00:00:00:00")
    _text(tc, "frame", 0)
    _text(tc, "displayformat", "NDF")
    media = ET.SubElement(s, "media")
    video = ET.SubElement(media, "video")
    fmt = ET.SubElement(video, "format")
    sc = ET.SubElement(fmt, "samplecharacteristics")
    _rate(sc, fps, False)
    _text(sc, "width", W)
    _text(sc, "height", H)
    _text(sc, "anamorphic", "FALSE")
    _text(sc, "pixelaspectratio", "square")
    _text(sc, "fielddominance", "none")
    audio = ET.SubElement(media, "audio")
    _text(audio, "numOutputChannels", 2)
    afmt = ET.SubElement(audio, "format")
    asc = ET.SubElement(afmt, "samplecharacteristics")
    _text(asc, "depth", 16)
    _text(asc, "samplerate", SAMPLERATE)

    files: dict[str, str] = {}
    counter = {"clip": 0}

    def resolve(path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p)
        base = Path(stills_base) if (stills_base is not None and path.replace("\\", "/").startswith("Videoelemente/")) else Path(folder)
        return str(base / path)

    def file_el(parent: ET.Element, key: str, path: str, dur_frames: int, tb: int, ntsc: bool, kind: str) -> None:
        """`kind`: 'video' (Film mit Ton), 'still' (Bild), 'audio' (nur Ton)."""
        if key in files:
            ET.SubElement(parent, "file", id=files[key])
            return
        fid = f"file-{len(files) + 1}"
        files[key] = fid
        f = ET.SubElement(parent, "file", id=fid)
        _text(f, "name", Path(path).name)
        _text(f, "pathurl", path_url(resolve(path)))
        _rate(f, tb, ntsc)
        _text(f, "duration", max(1, dur_frames))
        m = ET.SubElement(f, "media")
        if kind in ("video", "still"):
            v = ET.SubElement(ET.SubElement(m, "video"), "samplecharacteristics")
            _rate(v, tb, ntsc)
            _text(v, "width", W if kind == "still" else W)
            _text(v, "height", H)
            _text(v, "anamorphic", "FALSE")
            _text(v, "pixelaspectratio", "square")
        if kind in ("video", "audio"):
            a = ET.SubElement(m, "audio")
            ac = ET.SubElement(a, "samplecharacteristics")
            _text(ac, "depth", 16)
            _text(ac, "samplerate", SAMPLERATE)
            _text(a, "channelcount", 2 if kind == "video" else 1)

    def clip_el(track: ET.Element, c: dict, media_type: str, track_index: int) -> bool:
        start, end = fr(c["start"]), fr(c["end"])
        if end <= start:
            return False  # leere Clips lässt Premiere beim Import scheitern
        counter["clip"] += 1
        ci = ET.SubElement(track, "clipitem", id=f"clipitem-{counter['clip']}")
        kind = c["type"]
        if kind in ("scene_segment", "scene_audio"):
            src_in, src_out = efr(c["src_in"]), efr(c["src_out"])
            if src_out <= src_in:
                src_out = src_in + 1
            _text(ci, "masterclipid", "masterclip-episode")
            _text(ci, "name", Path(episode_file).name)
            _text(ci, "enabled", "TRUE")
            _text(ci, "duration", efr(episode_dur))
            _rate(ci, ep_tb, ep_ntsc)
            _text(ci, "start", start)
            _text(ci, "end", end)
            _text(ci, "in", src_in)
            _text(ci, "out", src_out)
            file_el(ci, "episode", episode_file, efr(episode_dur), ep_tb, ep_ntsc, "video")
        elif kind in ("still", "artwork", "map_placeholder") and c.get("file"):
            n = end - start
            _text(ci, "masterclipid", f"masterclip-{Path(c['file']).stem}")
            _text(ci, "name", Path(c["file"]).name)
            _text(ci, "enabled", "TRUE")
            _text(ci, "duration", n)
            _rate(ci, fps, False)
            _text(ci, "start", start)
            _text(ci, "end", end)
            _text(ci, "in", 0)
            _text(ci, "out", n)
            file_el(ci, c["file"], c["file"], n, fps, False, "still" if not str(c["file"]).lower().endswith((".mov", ".mp4")) else "video")
        elif kind == "comment" and c.get("src_in") is not None:
            key = c.get("rec_path") or f"aufnahme_{c.get('rec')}.wav"
            src_in, src_out = fr(c["src_in"]), fr(c["src_out"])
            if src_out <= src_in:
                src_out = src_in + 1
            _text(ci, "masterclipid", f"masterclip-{Path(key).stem}")
            _text(ci, "name", Path(key).name)
            _text(ci, "enabled", "TRUE")
            _text(ci, "duration", fr(rec_len.get(key, c["src_out"]) + 1))
            _rate(ci, fps, False)
            _text(ci, "start", start)
            _text(ci, "end", end)
            _text(ci, "in", src_in)
            _text(ci, "out", src_out)
            file_el(ci, key, key, fr(rec_len.get(key, c["src_out"]) + 1), fps, False, "audio")
        else:
            # Platzhalter (z. B. Kommentar ohne Aufnahme): benannter Clip ohne Medien
            counter["clip"] -= 1
            track.remove(ci)
            return False
        if media_type == "audio":
            st = ET.SubElement(ci, "sourcetrack")
            _text(st, "mediatype", "audio")
            _text(st, "trackindex", 1)
        else:
            st = ET.SubElement(ci, "sourcetrack")
            _text(st, "mediatype", "video")
            _text(st, "trackindex", 1)
        return True

    for names, parent, mtype in ((VIDEO_TRACKS, video, "video"), (AUDIO_TRACKS, audio, "audio")):
        for ti, name in enumerate(names, 1):
            clips = sorted((c for c in pkg["tracks"].get(name, []) if c["type"] not in ("credit", "blur", "anim", "free_block")), key=lambda c: c["start"])
            lanes: list[list[dict]] = [[]]
            ends = [-1]
            for c in clips:                       # überlappende Clips (z. B. zwei Artworks gleichzeitig) auf Zusatzspuren legen
                s0 = fr(c["start"])
                for li, e in enumerate(ends):
                    if s0 >= e:
                        lanes[li].append(c)
                        ends[li] = fr(c["end"])
                        break
                else:
                    lanes.append([c])
                    ends.append(fr(c["end"]))
            for lane in lanes:
                track = ET.SubElement(parent, "track")
                for c in lane:
                    clip_el(track, c, mtype, ti)
                _text(track, "enabled", "TRUE")
                _text(track, "locked", "FALSE")
                if mtype == "audio":
                    _text(track, "outputchannelindex", 1)
    for m in pkg["markers"]:
        mk = ET.SubElement(s, "marker")
        _text(mk, "name", m["text"][:60])
        _text(mk, "comment", m["text"])
        _text(mk, "in", fr(m["time"]))
        _text(mk, "out", -1)
    problems = validate_xmeml(root)
    if problems:
        raise ValueError("Premiere-XML wäre ungültig: " + "; ".join(problems[:5]))
    xml = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml).toprettyxml(indent="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + "\n".join(pretty.split("\n")[1:])


def validate_xmeml(root: ET.Element) -> list[str]:
    """Prüft typische Importfehler: doppelte IDs, leere/ungeordnete Clips, nicht ganzzahlige Frames, fehlende Pflichtfelder."""
    problems: list[str] = []
    ids = [e.get("id") for e in root.iter("clipitem")]
    if len(ids) != len(set(ids)):
        problems.append("doppelte clipitem-IDs")
    defined = {f.get("id") for f in root.iter("file") if f.find("pathurl") is not None}
    for f in root.iter("file"):
        if f.find("pathurl") is None and f.get("id") not in defined:
            problems.append(f"file {f.get('id')} wird verwendet, aber nie definiert")
    for tag in ("start", "end", "in", "out", "duration"):
        for e in root.iter(tag):
            try:
                int(e.text or "")
            except ValueError:
                problems.append(f"{tag} ist keine ganze Zahl: {e.text!r}")
    for tr in root.iter("track"):
        last_end = -1
        for ci in tr.findall("clipitem"):
            try:
                s, e = int(ci.findtext("start")), int(ci.findtext("end"))
            except (TypeError, ValueError):
                problems.append(f"{ci.get('id')}: start/end fehlen")
                continue
            if e <= s:
                problems.append(f"leerer Clip {ci.get('id')}")
            if s < last_end:
                problems.append(f"überlappende Clips in einer Spur bei Frame {s}")
            last_end = e
            for need in ("name", "rate", "in", "out", "file"):
                if ci.find(need) is None:
                    problems.append(f"{ci.get('id')}: <{need}> fehlt")
    if root.find("sequence/media/video/format/samplecharacteristics/width") is None:
        problems.append("Sequenzformat fehlt")
    return problems

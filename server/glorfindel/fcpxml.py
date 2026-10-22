"""Fallback ohne Panel: Final-Cut-Pro-XML (xmeml v4) aus dem Schnittpaket (Heft §6).

Enthält Clips, Standbilder, Audio und Marker. Credits, Effektvorgaben und Play/Pause müssen von Hand
ergänzt werden (Premiere importiert sie über xmeml nicht).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

VIDEO_TRACKS = ["V1", "V3", "V4"]
AUDIO_TRACKS = ["A2", "A3", "A4"]


def _rate(parent: ET.Element, timebase: int, ntsc: bool) -> None:
    r = ET.SubElement(parent, "rate")
    ET.SubElement(r, "timebase").text = str(timebase)
    ET.SubElement(r, "ntsc").text = "TRUE" if ntsc else "FALSE"


def _text(parent, tag, value):
    ET.SubElement(parent, tag).text = str(value)


def to_fcpxml(pkg: dict, episode_file: str, episode_dur: float, folder: Path | str = "") -> str:
    seq = pkg["sequence"]
    fps = int(round(seq["fps"]))
    ep_fps = pkg["episode_fps"]
    ep_tb, ep_ntsc = int(round(ep_fps)), abs(ep_fps - round(ep_fps)) > 1e-3

    def fr(t: float) -> int:
        return int(round(t * seq["fps"]))

    def efr(t: float) -> int:
        return int(round(t * ep_fps))

    root = ET.Element("xmeml", version="4")
    s = ET.SubElement(root, "sequence", id="seq1")
    _text(s, "name", seq["name"])
    _text(s, "duration", fr(pkg["duration"]))
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
    _text(sc, "width", seq["width"])
    _text(sc, "height", seq["height"])
    audio = ET.SubElement(media, "audio")

    files: dict[str, str] = {}

    def file_el(parent: ET.Element, key: str, path: str, dur_frames: int, tb: int, ntsc: bool, has_video=True):
        if key in files:
            ET.SubElement(parent, "file", id=files[key])
            return
        fid = f"file{len(files) + 1}"
        files[key] = fid
        f = ET.SubElement(parent, "file", id=fid)
        _text(f, "name", Path(path).name)
        full = path if Path(path).is_absolute() else str(Path(folder) / path)
        _text(f, "pathurl", "file://localhost/" + full.replace("\\", "/"))
        _rate(f, tb, ntsc)
        _text(f, "duration", dur_frames)
        m = ET.SubElement(f, "media")
        if has_video:
            ET.SubElement(ET.SubElement(m, "video"), "samplecharacteristics")
        ET.SubElement(ET.SubElement(m, "audio"), "samplecharacteristics")

    def clip_el(track: ET.Element, idx: int, c: dict, is_video: bool) -> None:
        ci = ET.SubElement(track, "clipitem", id=f"{c['type']}_{idx}_{c['start']}")
        _text(ci, "name", c.get("scene", "") + " " + c["type"])
        _text(ci, "start", fr(c["start"]))
        _text(ci, "end", fr(c["end"]))
        if c["type"] in ("scene_segment", "scene_audio"):
            _text(ci, "in", efr(c["src_in"]))
            _text(ci, "out", efr(c["src_out"]))
            file_el(ci, "episode", episode_file, efr(episode_dur), ep_tb, ep_ntsc, True)
        elif c["type"] in ("still", "artwork", "map_placeholder") and c.get("file"):
            _text(ci, "in", 0)
            _text(ci, "out", fr(c["end"]) - fr(c["start"]))
            file_el(ci, c["file"], c["file"], fr(c["end"] - c["start"]), fps, False, True)
        elif c["type"] == "comment" and c.get("src_in") is not None:
            _text(ci, "in", int(round(c["src_in"] * 48000)))
            _text(ci, "out", int(round(c["src_out"] * 48000)))
            file_el(ci, f"rec_{c.get('rec')}", c.get("rec_path", f"aufnahme_{c.get('rec')}.wav"),
                    int(round((c["src_out"] + 10) * 48000)), 48000, False, False)
        else:
            _text(ci, "in", 0)
            _text(ci, "out", fr(c["end"]) - fr(c["start"]))

    for names, parent in ((VIDEO_TRACKS, video), (AUDIO_TRACKS, audio)):
        for name in names:
            track = ET.SubElement(parent, "track")
            for i, c in enumerate(sorted(pkg["tracks"].get(name, []), key=lambda c: c["start"])):
                if c["type"] in ("credit", "blur", "anim", "free_block"):
                    continue
                clip_el(track, i, c, parent is video)
    for m in pkg["markers"]:
        mk = ET.SubElement(s, "marker")
        _text(mk, "name", m["text"][:60])
        _text(mk, "comment", m["text"])
        _text(mk, "in", fr(m["time"]))
        _text(mk, "out", -1)
    xml = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml).toprettyxml(indent="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + "\n".join(pretty.split("\n")[1:])

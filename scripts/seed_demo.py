"""Erzeugt eine saubere Demo-Folge (synthetische Medien) für Hilfe-Screenshots und manuelle Tests.

Aufruf: python scripts/seed_demo.py <Arbeitsordner> [Port]
Startet den Server mit eigenem GLORFINDEL_HOME, legt Folge S3 E1 mit Szenen, Bildern, Karte, Aufnahmen und Rohschnitt an
und lässt den Server danach laufen (Strg+C beendet). Nur für Entwicklung.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

work = Path(sys.argv[1]).resolve()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
root, home = work / "od", work / "home"
for d in ("Mythen-Archiv/Videos", "Videomaterial/Bilder", "Videomaterial/Karten", "Filme", "Aufnahmen"):
    (root / d).mkdir(parents=True, exist_ok=True)
home.mkdir(parents=True, exist_ok=True)
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "server"))
os.environ["GLORFINDEL_HOME"] = str(home)
B = f"http://127.0.0.1:{port}"


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *a], check=True)


def media():
    ref = root / "Filme" / "Episode S3E1.mp4"
    if not ref.exists():
        ff("-f", "lavfi", "-i", "mandelbrot=s=640x360:r=24", "-f", "lavfi", "-i", "sine=f=220:d=80", "-t", "80", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ref))
    hq = root / "Filme" / "Episode S3E1 HQ deutsch.mp4"
    if not hq.exists():
        ff("-ss", "1.5", "-i", str(ref), "-t", "76", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(hq))
    from PIL import Image, ImageDraw
    pics = {"Alan Lee - Celebrimbor.jpg": ((30, 60, 110), (210, 160, 60)), "Ted Nasmith - Armenelos.jpg": ((20, 90, 80), (230, 220, 180)),
            "John Howe - Barad-dur.jpg": ((60, 20, 30), (240, 90, 40))}
    for name, (c1, c2) in pics.items():
        f = root / "Videomaterial/Bilder" / name
        if f.exists():
            continue
        im = Image.new("RGB", (1200, 800))
        px = im.load()
        for y in range(800):
            for x in range(0, 1200):
                t = y / 800
                px[x, y] = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        d = ImageDraw.Draw(im)
        d.polygon([(0, 800), (300, 420), (520, 640), (760, 330), (1200, 800)], fill=(15, 20, 25))
        d.ellipse([850, 90, 1010, 250], fill=(250, 240, 200))
        im.save(f, quality=88)
    f = root / "Videomaterial/Karten" / "Mittelerde Karte.png"
    if not f.exists():
        im = Image.new("RGB", (1600, 1000), (222, 205, 160))
        d = ImageDraw.Draw(im)
        d.polygon([(100, 300), (500, 180), (900, 260), (1300, 150), (1500, 400), (1200, 700), (800, 820), (400, 760), (150, 560)], fill=(175, 160, 110), outline=(110, 90, 50))
        d.polygon([(260, 380), (420, 340), (520, 460), (330, 520)], fill=(120, 150, 100))
        d.polygon([(900, 400), (1100, 360), (1180, 520), (980, 580)], fill=(140, 120, 90))
        im.save(f)
    for sp, freq in (("philipp", 180), ("danny", 140)):
        w = root / "Aufnahmen" / f"{sp.capitalize()} S3E1.wav"
        if not w.exists():
            ff("-f", "lavfi", "-i", f"sine=f={freq}:d=70", str(w))


def api(m, u, b=None):
    r = urllib.request.Request(B + u, method=m, data=json.dumps(b).encode() if b is not None else None, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r))


def wait(j):
    while True:
        r = api("GET", "/api/jobs/" + j["job"])
        if r["status"] != "laeuft":
            if r["status"] != "fertig":
                raise SystemExit(f"Job fehlgeschlagen: {r.get('error')}")
            return r
        time.sleep(0.4)


SCENES = [
    ("Celebrimbor und Annatar", "eregion", [(5, 12), (20, 27)], [("philipp", "Celebrimbor steht nach dem Verlust seiner Familie unter enormem Druck und lässt sich auf Annatar ein."), ("danny", "Die Schmiede in Eregion wird zum Mittelpunkt der Geschichte.")]),
    ("Die Schmiede von Eregion", "eregion", [(40, 49.5)], [("philipp", "Hier entstehen die ersten Ringe, und die Karte zeigt, wie nah Mordor liegt.")]),
    ("Ankunft in Armenelos", "numenor", [(30, 38)], [("danny", "Armenelos zeigt die ganze Pracht Númenors, doch hinter den Mauern wächst die Sorge.")]),
    ("Sauron zeigt sein wahres Gesicht", "rhun", [(55, 67)], [("philipp", "Die Szene ist bewusst lang gehalten, damit man Annatars Wandel sieht.")]),
    ("Epilog (noch offen)", "khazaddum", [], [("danny", "")]),
]


def main():
    media()
    srv = subprocess.Popen([sys.executable, "-c", f"import uvicorn; from glorfindel.api import create_app; uvicorn.run(create_app(), host='127.0.0.1', port={port}, log_level='warning')"], env=os.environ.copy(), cwd=repo)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(B + "/api/health")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.3)
        s = api("GET", "/api/settings")
        s.update(onedrive_root=str(root), user="Philipp")
        s["llm"]["enabled"] = False
        api("PUT", "/api/settings", s)
        api("POST", "/api/episodes", {"season": 3, "episode": 1, "title": "Der Schmied und der Fremde"})
        E = "/api/ep/3/1"
        j = wait(api("POST", E + "/sources", {"path": "Filme/Episode S3E1.mp4", "role": "referenz"}))
        ref = j["result"]["id"]
        wait(api("POST", f"{E}/sources/{ref}/proxy"))
        j = wait(api("POST", E + "/sources", {"path": "Filme/Episode S3E1 HQ deutsch.mp4", "role": "hq"}))
        hq = j["result"]["id"]
        wait(api("POST", f"{E}/sources/{hq}/proxy"))
        api("PUT", f"{E}/sources/{hq}/anchors", {"anchors": [{"ref": 2, "src": 0.5}, {"ref": 70, "src": 68.5}]})
        wait(api("POST", "/api/images/index"))
        assets = [api("POST", E + "/assets", {"path": f"Videomaterial/Bilder/{n}"}) for n in ("Alan Lee - Celebrimbor.jpg", "Ted Nasmith - Armenelos.jpg", "John Howe - Barad-dur.jpg")]
        api("PUT", E + "/maps/map_01", {"id": "map_01", "titel": "Mittelerde Karte", "bild": "Videomaterial/Karten/Mittelerde Karte.png", "dauer": 6, "hinweise": "Erst Eregion, dann Fahrt nach Osten.",
            "elemente": [{"typ": "marker", "x": .27, "y": .45, "text": "Eregion", "t0": 0.5}, {"typ": "pfeil", "punkte": [[.27, .45], [.6, .4], [.7, .5]], "text": "", "t0": 2, "dauer": 2},
                         {"typ": "region", "punkte": [[.56, .38], [.7, .35], [.74, .55], [.6, .6]], "text": "Mordor", "t0": 3}], "kamera": [{"t": 0, "rect": [0, 0, 1, 1]}, {"t": 4, "rect": [.15, .2, .6, .55]}]})
        ids = []
        for titel, strang, segs, blocks in SCENES:
            sc = api("POST", E + "/scenes", {"titel": titel, "strang": strang, "segmente": [{"in": a, "out": b} for a, b in segs], "kommentar": [{"sprecher": sp, "text": t} for sp, t in blocks]})
            ids.append(sc["id"])
        sc = api("GET", E + "/scenes")
        def put(i, fn):
            s = api("GET", E + "/scenes")[i]
            for k in ("report", "lock", "problems", "ausgabe"):
                s.pop(k, None)
            fn(s)
            api("PUT", f"{E}/scenes/{s['id']}", s)
        put(0, lambda s: s["kommentar"][0].update(anker=[{"asset": assets[0]["id"], "karte": None, "von": 2, "bis": 9, "layout": "einzel", "einheit": "wort"}]))
        put(2, lambda s: s["kommentar"][0].update(anker=[{"asset": assets[1]["id"], "karte": None, "von": 0, "bis": None, "layout": "einzel", "einheit": "wort"}]))
        put(1, lambda s: s["kommentar"][0].update(anker=[{"asset": None, "karte": "map_01", "von": 5, "bis": None, "layout": "einzel", "einheit": "wort"}]))
        put(0, lambda s: s["kommentar"][1].update(modus="stichpunkte", text="", stichpunkte=["Schmiede in Eregion", "Mittelpunkt der Geschichte"]))
        # Segment-Workflow: Kommentare gehören zu Segmenten, Notizen als Kontext, Dialog der Episode für die Anzeige
        put(0, lambda s: [s["kommentar"][0].update(segment=0), s["kommentar"][1].update(segment=1), s["segmente"][0].update(notiz="Celebrimbor allein in der Schmiede"), s.update(bereich=[2, 30])])
        put(1, lambda s: [s["kommentar"][0].update(segment=0), s.update(bereich=[38, 52])])
        put(2, lambda s: [s["kommentar"][0].update(segment=0), s.update(bereich=[30, 38])])
        put(3, lambda s: [s["kommentar"][0].update(segment=0), s.update(bereich=[52, 70])])
        put(4, lambda s: s.update(bereich=[70, 78]))
        lines = ["I will not fail my people.", "The forge must be ready before the winter comes.", "You have my word, Annatar, as a smith and as a friend.", "Then we begin at dawn.", "Armenelos shines like a jewel in the evening light.", "Nothing here is what it seems.", "Show me the rings."]
        words, tt = [], 5.0
        for ln in lines:
            for w in ln.split():
                words.append({"w": w, "start": round(tt, 2), "end": round(tt + 0.3, 2)})
                tt += 0.36
            tt += 2.2 if ln is not lines[0] else 6.0
        api("PUT", E + "/dialog", {"words": words, "sprache": "en", "quelle": ref})
        api("PUT", E + "/free-blocks", [{"titel": "Werbung", "text": "", "after": ids[2], "dauer": 81}])
        # Aufnahmen: Transkript direkt in den Cache (kein Whisper nötig) und Abgleich
        from glorfindel.config import load_settings
        from glorfindel.service import Episode
        ep = Episode(load_settings(), 3, 1)
        for sp in ("philipp", "danny"):
            rec = api("POST", E + "/recording", {"path": f"Aufnahmen/{sp.capitalize()} S3E1.wav", "speaker": sp})
            t, words = 1.0, []
            for s in api("GET", E + "/scenes"):
                for b in s["kommentar"]:
                    if b["sprecher"] != sp:
                        continue
                    txt = b["text"] if b["modus"] == "text" else " ".join(b["stichpunkte"])
                    for w in txt.split():
                        words.append({"w": w, "start": round(t, 2), "end": round(t + 0.33, 2)})
                        t += 0.36
                    t += 1.8
            (ep.p.recording).mkdir(parents=True, exist_ok=True)
            (ep.p.recording / f"transkript_{rec['id']}.json").write_text(json.dumps(words), encoding="utf-8")
        wait(api("POST", E + "/recording/align?prefer=last"))
        # Board-Vorschläge mit Vorschaubildern
        th = ep.p.cache() / "thumbs"
        th.mkdir(parents=True, exist_ok=True)
        props = [(2, 18, "eregion"), (18, 34, ""), (34, 52, ""), (52, 70, "")]
        out = []
        for i, (a, b, st) in enumerate(props):
            ff("-ss", str(a + 2), "-i", str(root / "Filme/Episode S3E1.mp4"), "-frames:v", "1", "-vf", "scale=320:-1", str(th / f"demo{i}.jpg"))
            out.append({"start": a, "end": b, "thumb": f"demo{i}.jpg", "strang": st, "done": False})
        api("PUT", E + "/board", {"source": ref, "scenes": out})
        wait(api("POST", E + "/rough-cut", {"by_strand": True, "with_stills": False}))
        print(json.dumps({"ref": ref, "hq": hq, "port": port, "ids": ids}), flush=True)
        if "--serve" in sys.argv:
            srv.wait()
    finally:
        if "--serve" not in sys.argv:
            srv.terminate()
            srv.wait(timeout=10)


if __name__ == "__main__":
    main()

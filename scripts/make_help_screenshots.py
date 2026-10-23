"""Erzeugt die annotierten Hilfe-Screenshots (web/help/img/*.png) gegen einen laufenden Demo-Server (scripts/seed_demo.py).

Aufruf: python scripts/make_help_screenshots.py <Basis-URL> <Arbeitsordner> [Ausgabeordner]
Chromium ohne H.264: Proxy-Videos werden für die Aufnahme per ffmpeg nach WebM umgewandelt und abgefangen.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = sys.argv[1].rstrip("/")
work = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parents[1] / "web/help/img"
out.mkdir(parents=True, exist_ok=True)
EP = "#/3/1"

proxy = next((work / "home").rglob("proxy_q1*.mp4"), None) or next((work / "home").rglob("*q1*.mp4"))
webm = work / "proxy.webm"
if not webm.exists():
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(proxy), "-t", "40", "-c:v", "libvpx", "-b:v", "1M", "-an", str(webm)], check=True)

ANN_JS = r"""
(items) => {
  document.getElementById('ann')?.remove();
  const layer = document.createElement('div'); layer.id = 'ann';
  layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99999';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', innerWidth); svg.setAttribute('height', innerHeight); svg.style.cssText = 'position:absolute;inset:0';
  svg.innerHTML = '<defs><marker id="ah" markerUnits="userSpaceOnUse" markerWidth="18" markerHeight="18" refX="15" refY="9" orient="auto"><path d="M0,1 L17,9 L0,17 z" fill="#ff5a36"/></marker></defs>';
  layer.append(svg); document.body.append(layer);
  const SEL = 'button,a,h1,h2,h3,label,span,th,td,.nav,.chip,select,input,textarea,canvas,video,.player,.block,.seg-row,.scene-item,.tc,.lane,.card,.scrub,.shot,.thumb,.wave,.toast,.job,.phase,.pill,.dual,.timeline,.modal-head,.editor-cols,.fs-item';
  const find = (s, nth = 0) => {
    if (s.startsWith('text:')) {
      const t = s.slice(5).toLowerCase();
      const c = [...document.querySelectorAll(SEL)].filter((e) => e.offsetParent !== null && (e.innerText || e.value || e.placeholder || '').trim().toLowerCase().startsWith(t));
      c.sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height - b.getBoundingClientRect().width * b.getBoundingClientRect().height);
      return c[nth];
    }
    return document.querySelectorAll(s)[nth];
  };
  items.forEach((it, i) => {
    let el = find(it.sel, it.nth || 0); if (el && it.up) el = el.closest(it.up) || el; if (!el) { console.log('FEHLT', it.sel); return; }
    const r = el.getBoundingClientRect(), pad = it.pad ?? 3;
    const box = document.createElement('div');
    box.style.cssText = `position:absolute;left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + 2 * pad}px;height:${r.height + 2 * pad}px;border:3px solid #ff5a36;border-radius:9px;box-shadow:0 0 0 2px rgba(0,0,0,.35)`;
    layer.append(box);
    const num = document.createElement('div'); num.textContent = String(i + 1);
    num.style.cssText = `position:absolute;left:${r.left - pad - 12}px;top:${r.top - pad - 12}px;width:26px;height:26px;border-radius:50%;background:#ff5a36;color:#fff;font:800 14px/26px system-ui,sans-serif;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.5)`;
    layer.append(num);
    if (!it.at) return;
    const b = document.createElement('div');
    b.textContent = `${i + 1}  ${it.text || ''}`;
    b.style.cssText = `position:absolute;left:${it.at[0]}px;top:${it.at[1]}px;background:#ff5a36;color:#fff;font:700 13px/1.25 system-ui,sans-serif;padding:6px 11px;border-radius:10px;max-width:${it.w || 230}px;box-shadow:0 3px 10px rgba(0,0,0,.45)`;
    layer.append(b);
    const bx = b.offsetLeft, by = b.offsetTop, bw = b.offsetWidth, bh = b.offsetHeight;
    // Zielpunkt: nächster Punkt des Elements zur Sprechblase; Startpunkt: nächster Punkt der Sprechblase zum Ziel
    const tx = Math.max(r.left - pad, Math.min(bx + bw / 2, r.right + pad)), ty = Math.max(r.top - pad, Math.min(by + bh / 2, r.bottom + pad));
    const sx = Math.max(bx, Math.min(tx, bx + bw)), sy = Math.max(by, Math.min(ty, by + bh));
    if (Math.hypot(tx - sx, ty - sy) < 14) return;
    const ln = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    ln.setAttribute('x1', sx); ln.setAttribute('y1', sy); ln.setAttribute('x2', tx); ln.setAttribute('y2', ty);
    ln.setAttribute('stroke', '#ff5a36'); ln.setAttribute('stroke-width', '3.5'); ln.setAttribute('marker-end', 'url(#ah)'); ln.setAttribute('stroke-linecap', 'round');
    svg.append(ln);
  });
}
"""

SAN_JS = r"""(prefix) => {
  const rep = 'C:\\Users\\Philipp\\OneDrive';
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const n = w.currentNode; if (n.nodeValue.includes(prefix)) n.nodeValue = n.nodeValue.split(prefix).join(rep); }
  document.querySelectorAll('input').forEach((i) => { if (i.value.includes(prefix)) i.value = i.value.split(prefix).join(rep); });
}"""

shots = []


def shot(pg, name, items=None, wait=900, clip=None):
    try:  # erst fotografieren, wenn die Ladeanzeige verschwunden ist (kalter Start ist langsam)
        pg.wait_for_function("!document.body.innerText.includes('Wird geladen')", timeout=30000)
    except Exception:  # noqa: BLE001
        pass
    pg.wait_for_timeout(wait)
    pg.evaluate(SAN_JS, str(work / 'od'))
    if items:
        pg.evaluate(ANN_JS, items)
    pg.screenshot(path=str(out / f"{name}.png"), clip=clip)
    pg.evaluate("document.getElementById('ann')?.remove()")
    shots.append(name)
    print("ok", name, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None,
                           args=["--no-sandbox"] if sys.platform.startswith("linux") else [])
    pg = br.new_page(viewport={"width": 1440, "height": 860})
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text) if "FEHLT" in m.text else None)
    pg.route("**/media/**", lambda r: r.fulfill(status=200, body=webm.read_bytes(), headers={"Content-Type": "video/webm", "Accept-Ranges": "none"}))
    go = lambda v: pg.goto(f"{base}/{EP}/{v}")

    pg.goto(f"{base}/#/settings")
    shot(pg, "01-einstellungen", [
        dict(sel="text:Ersteinrichtung", text="Selbsttest: alles grün? Sonst steht dort, was fehlt", at=[640, 126], w=300),
        dict(sel="text:Wählen", text="OneDrive-Stammordner wählen", at=[300, 497], w=240),
        dict(sel="text:Dein Name", text="Dein Name (für Sperren und Protokoll)", at=[560, 365], w=230),
        dict(sel="text:Speichern", text="Danach speichern", at=[1130, 104], w=130)])
    go("home")
    shot(pg, "02-uebersicht", [
        dict(sel=".phases", text="Phasen: Haken = erledigt, Klick öffnet die Ansicht", at=[700, 40], w=300),
        dict(sel=".stat", nth=1),
        dict(sel="text:Als Nächstes", up=".card", text="Was als Nächstes fehlt – ein Klick springt direkt hin", at=[300, 590], w=300),
        dict(sel="text:Aufgaben", text="Hintergrundaufgaben", at=[250, 790], w=170)])
    go("sources")
    shot(pg, "03-quellen", [
        dict(sel="text:Referenz importieren", text="Zuerst die Referenz-Episode wählen", at=[1000, 120], w=250),
        dict(sel="#main select", nth=0, text="Rolle der Quelle", at=[330, 330], w=160),
        dict(sel="text:Proxy", nth=0, text="Proxy = schnelle Vorschau", at=[1000, 330], w=200),
        dict(sel="text:Anker", nth=0, text="Ankerpunkte für HQ/Screener", at=[1150, 270], w=230)])
    go("board")
    pg.wait_for_timeout(600)
    pg.locator(".shot").nth(0).click()
    pg.locator(".shot").nth(1).click(modifiers=["Shift"])
    shot(pg, "04-board", [
        dict(sel="text:Stränge", text="Stränge und ihre Reihenfolge festlegen", at=[560, 16], w=300),
        dict(sel=".board-bar", text="Mehrere Vorschläge wählen (Strg/Umschalt) und mit einem Klick einem Strang zuordnen", at=[600, 476], w=420),
        dict(sel=".shot.selected", nth=0, text="Ausgewählt · Doppelklick oder ▶ spielt die Szene ab", at=[560, 620], w=290),
        dict(sel="text:Zugeordnete", text="Als Szenen anlegen", at=[1210, 448], w=190)])
    go("editor")
    pg.wait_for_timeout(1800)
    pg.evaluate("document.querySelector('.scene-item')?.click()")
    shot(pg, "05-editor", [
        dict(sel=".scene-list-head", text="Suchen und filtern", at=[250, 520], w=200),
        dict(sel=".si-meta", nth=0, text="Auf einen Blick: Segmente, Kommentare, Bilder", at=[250, 600], w=260),
        dict(sel=".tl2", text="Zeitleiste: Szenenbereich, Segmente, Kommentarmarken", at=[600, 104], w=330),
        dict(sel=".dlg-card", text="Dialog der Episode: Wörter ziehen = Stelle markieren", at=[570, 700], w=330),
        dict(sel=".seg-card", nth=0, text="Segment mit Dialog, Notiz und Kommentaren", at=[1040, 740], w=300),
        dict(sel=".playseg, .seg-card .btn.primary", nth=0, text="Segment abspielen", at=[1010, 100], w=150)])
    pg.evaluate("const ta=document.querySelector('.seg-card .mt-ta'); ta.focus(); ta.setSelectionRange(24, 44)")
    pg.click("text=Bild / Karte einblenden >> nth=0")
    shot(pg, "06-bild-zuordnen", [
        dict(sel=".modal .seg", text="Bilder oder Karten", at=[260, 120], w=170),
        dict(sel=".pick-grid", nth=0, text="Bild anklicken = einblenden, ab dem markierten Wort", at=[560, 140], w=300),
        dict(sel=".modal input[type=search]", text="Bibliothek durchsuchen", at=[1000, 140], w=200)], wait=900)
    pg.keyboard.press("Escape")
    go("script")
    shot(pg, "07-word", [
        dict(sel="text:Gesamtes Skript", text="Exportieren: alles, nur Philipp oder nur Danny", at=[560, 22], w=290),
        dict(sel="text:Word-Datei wählen", text="Bearbeitetes Word zurückspielen", at=[1020, 22], w=250),
        dict(sel="text:Für Philipp", text="Sprecherskript: nur zum Vorlesen, ohne technische Marken", at=[760, 330], w=300),
        dict(sel="text:Rahmenteil +", text="Rahmenteile (Werbung, Outro) mit fester Dauer", at=[620, 358], w=420)])
    go("ablauf")
    shot(pg, "17-ablauf", [
        dict(sel=".ab-head", nth=0, text="Ganzen Strang ziehen = Reihenfolge ändern", at=[1000, 260], w=260),
        dict(sel=".ab-row", nth=1, text="Einzelne Szenen frei einsortieren", at=[1000, 320], w=250),
        dict(sel="text:Automatisch", text="Zurück zur Reihenfolge nach Strängen", at=[560, 130], w=260)])
    go("images")
    shot(pg, "08-bilder", [
        dict(sel=".thumb", nth=2, text="Bild der Folge anklicken: Credit und Konturfarbe bearbeiten", at=[980, 180], w=300),
        dict(sel="text:Künstler-Datenbank", text="Credits einmal pflegen, gilt für alle Folgen", at=[1020, 120], w=250),
        dict(sel="input[type=search]", text="Bibliothek durchsuchen (Name, Stichwort, Ordner)", at=[980, 590], w=300)])
    go("maps")
    shot(pg, "09-karten", [
        dict(sel="text:Einzeichnen", text="Karte einzeichnen", at=[950, 170], w=150),
        dict(sel="text:Platzhalter rendern", text="Kartenblatt + Platzhalter-Clip erzeugen", at=[900, 260], w=240)])
    pg.click("text=Einzeichnen")
    pg.wait_for_timeout(1500)
    shot(pg, "10-karteneditor", [
        dict(sel=".seg", nth=0, text="Werkzeug wählen (Marker, Text, Pfeil, Region, Kamera)", at=[620, 118], w=330),
        dict(sel="canvas", text="Ins Bild klicken; Pfeil/Region: mehrere Punkte, Enter beendet", at=[400, 650], w=360),
        dict(sel=".modal .col.gap-s", text="Beschriftung und Einsatzzeitpunkt je Element", at=[850, 600], w=250)], wait=500)
    pg.keyboard.press("Escape")
    go("recording")
    pg.wait_for_timeout(1200)
    shot(pg, "11-aufnahme", [
        dict(sel="text:Philipp", nth=0, text="Aufnahme je Sprecher hinzufügen", at=[940, 130], w=200),
        dict(sel="text:Abgleich starten", text="Abgleich starten", at=[1260, 130], w=150),
        dict(sel=".wave", text="Wellenform: Klick spielt ab, Farbflächen = zugeordnete Blöcke", at=[620, 300], w=330),
        dict(sel="text:Nur unsichere", text="Nur unsichere Stellen prüfen", at=[640, 380], w=210),
        dict(sel=".pill", nth=0, text="Sicherheit der Zuordnung", at=[800, 540], w=170)])
    go("compare")
    pg.wait_for_timeout(2500)
    pg.evaluate("const r=document.querySelector('.cmp-slider'); r.value=12; r.dispatchEvent(new Event('input'))")
    pg.wait_for_timeout(1500)
    shot(pg, "12-kontrolle", [
        dict(sel=".cmp-slider", text="Zeit in der Referenz wählen (grüne Marken = gesetzte Anker)", at=[560, 120], w=300),
        dict(sel=".cmp-view", text="Links Referenz, rechts Quelle – flüssig, ohne Server-Rechnerei", at=[560, 540], w=300),
        dict(sel=".seg", nth=0, text="Nebeneinander, Überblendung oder Differenz", at=[980, 214], w=200),
        dict(sel=".pill", nth=0, text="Live-Übereinstimmung", at=[1200, 214], w=190),
        dict(sel="text:HQ-Conform", text="HQ-Datei erzeugen", at=[1280, 135], w=120)])
    pg.evaluate("document.querySelector('#main').scrollTo(0, 400)")
    shot(pg, "13-anker-setzen", [
        dict(sel=".card .row.wrap.gap-s", nth=0, text="Quelle auf dasselbe Bild nachjustieren (Bild für Bild)", at=[760, 400], w=300),
        dict(sel="text:Hier verknüpfen", text="Gleiches Bild? Dann Anker setzen (Enter)", at=[760, 560], w=300),
        dict(sel="text:Gesetzte Anker", up=".card", text="Gesetzte Anker – Hin springt dorthin", at=[560, 800], w=300)], wait=500)
    pg.evaluate("document.querySelector('#main').scrollTo(0, 0)")
    pg.set_viewport_size({"width": 1440, "height": 1040})
    go("cut")
    pg.wait_for_timeout(1200)
    shot(pg, "14-rohschnitt", [
        dict(sel="text:Rohschnitt erzeugen", text="Rohschnitt erzeugen", at=[1100, 110], w=170),
        dict(sel=".timeline", text="Vorschau aller Spuren", at=[780, 520], w=180),
        dict(sel="text:Warnungen", text="Warnungen mit Sprung zur Szene", at=[700, 960], w=240)])
    pg.set_viewport_size({"width": 1440, "height": 860})
    go("log")
    shot(pg, "15-protokoll", [dict(sel="table", text="Wer hat wann was geändert", at=[900, 120], w=200)])
    go("home")
    pg.evaluate("fetch('/api/ep/3/1/conform', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({source: 'q2', codec: 'h264', stills: true})})")
    pg.wait_for_timeout(3500)
    pg.locator(".tasks-nav").click()
    shot(pg, "16-aufgaben", [dict(sel=".jc .pbar", nth=0, text="Gesamtfortschritt, Laufzeit, Restzeit und Uhrzeit der Fertigstellung", at=[300, 108], w=360),
                              dict(sel=".jc-now", nth=0, text="Aktueller Schritt mit Teilfortschritt (z. B. Videozeit und Tempo)", at=[760, 108], w=330),
                              dict(sel=".jc-steps", nth=0, text="Alle Schritte: fertig, läuft, wartet – mit Dauer", at=[780, 300], w=260),
                              dict(sel="text:Abbrechen", text="Abbrechen", at=[1000, 70], w=100)], wait=500)
    print("FEHLENDE Elemente:", [m for m in msgs])
    br.close()

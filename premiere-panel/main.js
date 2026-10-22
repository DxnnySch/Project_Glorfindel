// Glorfindel-Panel (UXP, Premiere Pro). STATUS: ungetestetes Skelett (Meilenstein 0 des Projektheftes).
// Liest das Schnittpaket (schnitt_vN.json) und zeigt Zusammenfassung/Warnungen. Die Funktionen, die Premiere ansprechen,
// sind absichtlich defensiv und in `PPRO` gekapselt, damit nach dem Vorab-Test nur diese Stelle angepasst werden muss.
const log = (m, cls = '') => { const p = document.getElementById('log'); const s = document.createElement('div'); s.className = cls; s.textContent = m; p.appendChild(s); };
let pkg = null;

async function loadFromTool() {
  const ep = document.getElementById('ep').value.trim();
  const v = document.getElementById('ver').value.trim();
  const base = 'http://localhost:8765/api/ep/' + ep + '/rough-cut';
  if (!v) { const list = await (await fetch(base)).json(); if (!list.length) throw new Error('Noch kein Rohschnitt erzeugt'); setPkg(await (await fetch(base + '/' + list[list.length - 1].version + '/json')).json()); return; }
  setPkg(await (await fetch(base + '/' + v + '/json')).json());
}

async function loadFromFile() {
  const storage = require('uxp').storage;
  const f = await storage.localFileSystem.getFileForOpening({ types: ['json'] });
  if (f) setPkg(JSON.parse(await f.read()));
}

function setPkg(p) {
  pkg = p;
  const n = Object.values(p.tracks).reduce((a, t) => a + t.length, 0);
  document.getElementById('summary').textContent = 'Version ' + p.version + ': ' + n + ' Clips, ' + p.markers.length + ' Marker, ' + Math.round(p.duration) + ' s';
  (p.warnings || []).forEach((w) => log(w, 'warn'));
  document.getElementById('build').disabled = false;
  document.getElementById('markers').disabled = false;
}

// ---- Alles, was Premiere ansprechen muss, an einer Stelle (nach Vorab-Test anpassen) ----
const PPRO = {
  async project() { const ppro = require('premierepro'); return ppro.Project.getActiveProject(); },
  async sequence() { const pr = await this.project(); return pr.getActiveSequence(); },
  async addMarkers(markers) {
    const seq = await this.sequence();
    const ppro = require('premierepro');
    const mk = await ppro.Markers.getMarkers(seq);
    for (const m of markers) {
      // API-Form je nach Version unterschiedlich; hier bewusst einfach gehalten und zu prüfen.
      await mk.createMarker(m.time).catch((e) => log('Marker ' + m.text + ': ' + e.message, 'err'));
    }
  },
  async buildAll(p) {
    log('Rohschnitt-Aufbau ist noch nicht implementiert (Go/No-Go-Test offen). Nutze solange die FCP-XML aus dem Tool.', 'warn');
    // Plan: Spuren V1/V2/V9.., A2..A4 anlegen; je Clip type: scene_segment/still/comment/artwork/credit/anim/free_block;
    // Effekt-Rezepte (vorlagen/effekt_rezepte.json) als Keyframes setzen; Konturfarbe pro Artwork (ARGB 16 Bit).
  },
};

document.getElementById('load').onclick = () => loadFromTool().catch((e) => log(e.message, 'err'));
document.getElementById('file').onclick = () => loadFromFile().catch((e) => log(e.message, 'err'));
document.getElementById('markers').onclick = () => PPRO.addMarkers(pkg.markers).then(() => log('Marker gesetzt', 'ok')).catch((e) => log(e.message, 'err'));
document.getElementById('build').onclick = () => PPRO.buildAll(pkg).catch((e) => log(e.message, 'err'));

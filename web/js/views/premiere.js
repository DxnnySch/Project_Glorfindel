// Premiere: Verbindung zur Bridge, Rohschnitt direkt in Premiere bauen, Proxy ↔ HQ tauschen, Diagnose.
import { h, btn, icon, toast, runJob, modal, empty } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

// replaceChildren wandelt null in den Text „null“ um: leere Einträge auslassen
const fill = (el, ...kids) => el.replaceChildren(...kids.flat().filter(Boolean));

export async function render(main, ctx) {
  const ep = S.ep;
  let bridge = { connected: false, info: {}, log: [] }, st = { active: 'proxy' }, report = null, polling = null;

  const statusCard = h('div', { class: 'card col' });
  const buildCard = h('div', { class: 'card col' });
  const swapCard = h('div', { class: 'card col' });
  const diagCard = h('div', { class: 'card col' });
  const reportBox = h('div', { class: 'col', style: { marginTop: '14px' } });

  const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString('de-DE');

  // ---------- Verbindung ----------
  async function installPanel() {
    try {
      const r = await api.post('/api/bridge/install-panel');
      modal({ title: 'Panel einrichten', body: h('div', { class: 'col' }, h('p', {}, r.text), h('p', { class: 'help' }, `Paket: ${r.datei}`),
        h('p', { class: 'help' }, 'Funktioniert der Installer nicht: Adobe UXP Developer Tool öffnen → „Add Plugin“ → die Datei manifest.json aus dem Ordner premiere-panel wählen → „Load“.')),
        actions: [{ label: 'Verstanden', kind: 'primary' }] });
    } catch (e) { toast(e.message, 'err'); }
  }
  function drawStatus() {
    const ok = bridge.connected;
    const proj = bridge.info?.project;
    fill(statusCard, 
      h('div', { class: 'row' }, h('span', { class: `dot ${ok ? 'gruen' : 'rot'}`, style: { width: '12px', height: '12px' } }),
        h('h2', { class: 'grow' }, ok ? 'Mit Premiere verbunden' : 'Premiere ist nicht verbunden'),
        ok ? h('span', { class: 'chip' }, `Premiere ${bridge.info?.premiere || '?'}`) : null),
      ok ? h('p', { class: 'muted' }, proj ? `Aktives Projekt: ${proj.name}` : 'In Premiere ist kein Projekt geöffnet.')
        : h('div', { class: 'col gap-s' },
          h('p', { class: 'muted' }, 'Die Bridge ist ein kleines Fenster in Premiere, das mit dieser App spricht. So kann die App den Rohschnitt direkt im Premiere-Projekt bauen und später die Dateien tauschen.'),
          h('ol', { class: 'help', style: { margin: '0 0 0 18px' } },
            h('li', {}, 'Einmalig: „Panel einrichten“ klicken und die Rückfrage von Creative Cloud bestätigen.'),
            h('li', {}, 'Premiere neu starten, dann Fenster → Erweiterungen → „Glorfindel Bridge“ öffnen (offen lassen).'),
            h('li', {}, 'Hier erscheint „verbunden“. Premiere kann dafür auch schon ein Projekt geöffnet haben.')),
          h('div', { class: 'row gap-s' }, btn('Panel einrichten', { kind: 'primary', icon: 'download', onClick: installPanel }),
            btn('Installationspaket laden', { icon: 'download', onClick: () => { location.href = '/api/bridge/panel.ccx'; } }))));
    drawBuild(); drawSwap(); drawDiag();
  }

  // ---------- Bauen ----------
  const ui = { strand: true };
  function showReport(r, title) {
    report = r;
    const rep = r.report || r;
    const errs = rep.errors || [], warns = [...(r.warnings || []), ...(rep.warnings || [])];
    const counts = Object.entries(rep.placed || {}).map(([k, v]) => h('span', { class: 'chip' }, `${v} ${k}`));
    fill(reportBox, h('div', { class: 'card col' }, h('div', { class: 'row' }, h('h2', { class: 'grow' }, title || 'Ergebnis'),
      h('span', { class: `pill ${errs.length ? 'bad' : 'ok'}` }, errs.length ? `${errs.length} Fehler` : 'ohne Fehler')),
    counts.length ? h('div', { class: 'row wrap gap-s' }, ...counts) : null,
    errs.length ? h('details', { open: true }, h('summary', {}, `Nicht gebaut (${errs.length})`), h('ul', { class: 'help' }, ...errs.slice(0, 80).map((e) => h('li', {}, `${e.was}: ${e.fehler}`)))) : null,
    warns.length ? h('details', {}, h('summary', {}, `Hinweise (${warns.length})`), h('ul', { class: 'help' }, ...warns.slice(0, 120).map((w) => h('li', {}, w)))) : null));
  }
  async function build() {
    try {
      const r = await runJob('Rohschnitt in Premiere bauen', () => api.post(epUrl(ep, '/premiere/build'), { by_strand: ui.strand }));
      showReport(r, `Rohschnitt v${r.version} in Premiere gebaut`);
      toast(`Fertig: Sequenz „${r.sequence}“ in Premiere.`, 'ok', 8000);
      await refresh();
    } catch (e) { toast(e.message, 'err'); }
  }
  function drawBuild() {
    const ok = bridge.connected && S.data.scenes.some((s) => s.segmente.length || s.kommentar.length);
    fill(buildCard, 
      h('div', { class: 'card-head' }, icon('scissors'), h('h2', { class: 'grow' }, 'Rohschnitt in Premiere bauen')),
      h('p', { class: 'muted' }, 'Erzeugt in deinem geöffneten Premiere-Projekt eine neue Sequenz („Rohschnitt … vN“, bestehende bleiben unberührt) mit Szenen aus einer verschachtelten Episoden-Sequenz, Standbildern, Sprecher-Spuren, Pause/Play, Artworks mit Fancy In/Out, Credits und Markern – wie im Ursprungsschnitt.'),
      h('p', { class: 'help' }, 'Effekte (Zoom schnell/langsam, Fancy In/Out, Karten-Animation …) und Artwork-Größe wählst du unter ', h('a', { href: '#/settings' }, 'Einstellungen → Premiere-Rohschnitt'), '.'),
      h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: ui.strand, onChange: (e) => { ui.strand = e.target.checked; } }), 'Reihenfolge nach Strängen / Ablauf'),
      h('div', { class: 'row gap-s' }, btn('In Premiere bauen', { kind: 'primary', icon: 'play', disabled: !ok, onClick: build }),
        !bridge.connected ? h('span', { class: 'help' }, 'Zuerst Premiere verbinden.') : !ok ? h('span', { class: 'help' }, 'Noch keine Segmente im Szenen-Editor markiert.') : null),
      st.sequence ? h('div', { class: 'help' }, `Zuletzt gebaut: ${st.sequence}`) : null);
  }

  // ---------- Tausch ----------
  async function swapTo(to) {
    try {
      const r = await runJob(to === 'hq' ? 'Premiere auf HQ umstellen' : 'Premiere zurück auf Proxy', () => api.post(epUrl(ep, '/premiere/swap'), { to }));
      toast(`Fertig: ${r.report.neu_geladen} Standbilder neu geladen, Schnitt unverändert.`, 'ok', 8000);
      await refresh();
    } catch (e) { toast(e.message, 'err'); }
  }
  function drawSwap() {
    const built = !!st.ref_cfr, hq = !!st.hq_vorhanden;
    fill(swapCard, 
      h('div', { class: 'card-head' }, icon('film'), h('h2', { class: 'grow' }, 'Proxy ↔ HQ'), h('span', { class: `pill ${st.active === 'hq' ? 'ok' : 'info'}` }, st.active === 'hq' ? 'HQ aktiv' : 'Proxy aktiv')),
      h('p', { class: 'muted' }, 'Tauscht nur die Datei der Episoden-Sequenz in Premiere und ersetzt die Standbilder am gleichen Ort. Alle Clips, Effekte, Animationen und deine Handarbeit bleiben erhalten. Zurück auf Proxy ist jederzeit möglich.'),
      h('div', { class: 'row gap-s wrap' },
        btn('Auf HQ umschalten', { kind: 'primary', icon: 'refresh', disabled: !(bridge.connected && built && hq) || st.active === 'hq', onClick: () => swapTo('hq') }),
        btn('Zurück auf Proxy', { icon: 'refresh', disabled: !(bridge.connected && built) || st.active !== 'hq', onClick: () => swapTo('proxy') })),
      !built ? h('p', { class: 'help' }, 'Zuerst oben einen Rohschnitt in Premiere bauen.') : null,
      built && !hq ? h('div', { class: 'banner info' }, icon('info'), h('span', {}, 'Für die HQ-Fassung fehlt die zeitgleiche Datei. Unter „Kontrolle“ Anker setzen und „HQ-Conform“ ausführen. '),
        btn('Zur Kontrolle', { size: 'sm', onClick: () => ctx.go('compare') })) : null);
  }

  // ---------- Diagnose ----------
  async function selftest() {
    try {
      const r = await runJob('Premiere-Selbsttest', () => api.post('/api/bridge/selftest'));
      modal({ title: r.ok ? 'Selbsttest bestanden' : 'Selbsttest: Auffälligkeiten', wide: true, body: h('div', { class: 'col' },
        h('table', {}, h('tbody', {}, r.steps.map((s) => h('tr', {}, h('td', {}, h('span', { class: `pill ${s.ok ? 'ok' : 'bad'}` }, s.ok ? 'ok' : 'Fehler')), h('td', {}, s.name), h('td', { class: 'mono help' }, typeof s.detail === 'string' ? s.detail : JSON.stringify(s.detail).slice(0, 220)))))),
        h('details', {}, h('summary', {}, 'Technische Details'), h('pre', { class: 'mono', style: { whiteSpace: 'pre-wrap' } }, JSON.stringify(r.findings, null, 1)))),
        actions: [{ label: 'Schließen', kind: 'primary' }] });
    } catch (e) { toast(e.message, 'err'); }
  }
  async function dumpSeq() {
    try {
      const r = await api.post('/api/bridge/call', { op: 'sequence.dump', args: { maxItems: 40 }, timeout: 120 });
      const d = r.data;
      modal({ title: `Sequenz „${d.name}“`, wide: true, body: h('div', { class: 'col' },
        h('p', { class: 'help' }, `${d.video} Video- und ${d.audio} Audiospuren. Zum Vergleich mit dem Ursprungsschnitt.`),
        h('table', {}, h('thead', {}, h('tr', {}, ['Spur', 'Clips', 'Beispiel', 'Effekte'].map((x) => h('th', {}, x)))),
          h('tbody', {}, d.tracks.map((t) => h('tr', {}, h('td', {}, t.track), h('td', {}, String(t.count)), h('td', {}, t.items[0]?.name || ''), h('td', { class: 'help' }, (t.items[0]?.components || []).map((c) => c.name).join(', ')))))),
        h('details', {}, h('summary', {}, 'Alles (JSON)'), h('pre', { class: 'mono', style: { whiteSpace: 'pre-wrap', maxHeight: '320px', overflow: 'auto' } }, JSON.stringify(d, null, 1)))),
        actions: [{ label: 'Schließen', kind: 'primary' }] });
    } catch (e) { toast(e.message, 'err'); }
  }
  async function introspect() {
    try {
      const r = await api.post('/api/bridge/call', { op: 'introspect', args: {}, timeout: 120 });
      modal({ title: 'Premiere-Schnittstelle', wide: true, body: h('pre', { class: 'mono', style: { whiteSpace: 'pre-wrap', maxHeight: '60vh', overflow: 'auto' } }, JSON.stringify(r.data, null, 1)), actions: [{ label: 'Schließen', kind: 'primary' }] });
    } catch (e) { toast(e.message, 'err'); }
  }
  function drawDiag() {
    fill(diagCard, 
      h('div', { class: 'card-head' }, icon('wand'), h('h2', { class: 'grow' }, 'Diagnose')),
      h('p', { class: 'muted' }, 'Der Selbsttest legt kurz ein Test-Fach und eine Test-Sequenz an, prüft Effekte, Farben und Keyframes und räumt alles wieder auf. Dein Schnitt wird nicht berührt.'),
      h('div', { class: 'row gap-s wrap' }, btn('Selbsttest', { icon: 'check', disabled: !bridge.connected, onClick: selftest }),
        btn('Aktive Sequenz auslesen', { icon: 'search', disabled: !bridge.connected, onClick: dumpSeq }),
        btn('Schnittstelle anzeigen', { icon: 'info', disabled: !bridge.connected, onClick: introspect })),
      h('div', { class: 'help' }, 'Letzte Meldungen der Bridge:'),
      h('div', { class: 'mono help', style: { maxHeight: '160px', overflow: 'auto' } }, ...(bridge.log || []).slice().reverse().map((l) => h('div', { style: { color: l.level === 'warn' ? 'var(--warn)' : l.level === 'err' ? 'var(--bad)' : '' } }, `${fmtTime(l.t)}  ${l.text}`))));
  }

  async function refresh() {
    try {
      [bridge, st] = await Promise.all([api.get('/api/bridge/status'), api.get(epUrl(ep, '/premiere'))]);
      drawStatus();
    } catch (e) { /* nächste Runde */ }
  }

  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Premiere'), h('p', {}, 'Direkte Verbindung zu Premiere Pro: Die App baut den Rohschnitt im Projekt und tauscht später Proxy gegen HQ, ohne dass Effekte und Handarbeit verloren gehen.'))),
    h('div', { class: 'col gap-l' }, statusCard, buildCard, reportBox, swapCard, diagCard)));
  await refresh();
  polling = setInterval(refresh, 2500);
  return () => clearInterval(polling);
}

import { h, btn, toast, field, pickPath, icon, busy } from '../ui.js';
import { api } from '../api.js';
import { S, loadGlobal } from '../state.js';

export async function render(main) {
  const s = JSON.parse(JSON.stringify(S.settings));
  const inp = (key, obj = s, type = 'text') => h('input', { type, value: obj[key], onInput: (e) => { obj[key] = type === 'number' ? +e.target.value : e.target.value; } });
  const check = (label, obj, key) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: obj[key], onChange: (e) => { obj[key] = e.target.checked; } }), label);
  const root = h('input', { type: 'text', value: s.onedrive_root, placeholder: 'Ordner, der „Mythen-Archiv“ enthält', onInput: (e) => { s.onedrive_root = e.target.value; } });
  const suggest = h('div', { class: 'row wrap gap-s' });
  api.get('/api/detect-onedrive').then((c) => c.forEach((p) => suggest.append(h('button', { class: 'chip accent', style: { cursor: 'pointer' }, onClick: () => { root.value = p; s.onedrive_root = p; } }, p)))).catch(() => {});
  const transcription = h('select', { onChange: (e) => { s.transcription = e.target.value; } },
    [['auto', 'Automatisch (lokal, wenn möglich)'], ['lokal', 'Nur lokal (Whisper auf diesem Rechner)'], ['scads', 'ScaDS.AI Whisper – sendet Audio an ScaDS.AI']].map(([v, l]) => h('option', { value: v, selected: s.transcription === v }, l)));
  const save = async () => {
    try { await api.put('/api/settings', s); await loadGlobal(); toast('Einstellungen gespeichert.', 'ok');
      if (s.onedrive_root) location.hash = S.ep ? location.hash : '#/home'; } catch (e) { toast(e.message, 'err'); }
  };
  const theme = h('select', { onChange: (e) => { localStorage.setItem('gl-theme', e.target.value); document.documentElement.dataset.theme = e.target.value; } },
    [['dark', 'Dunkel'], ['light', 'Hell']].map(([v, l]) => h('option', { value: v, selected: (localStorage.getItem('gl-theme') || 'dark') === v }, l)));
  const th = s.thresholds, llm = s.llm, pr = s.premiere;
  // Premiere-Rohschnitt: Effekte je Artwork/Karte aus den .prfpset-Vorgaben wählen
  const ORDER = ['drop_shadow', 'zoom_schnell', 'zoom_langsam', 'fancy_out', 'fancy_in'];
  const effectGroup = (key, box, effekte) => {
    box.replaceChildren(...effekte.map((e) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: pr[key].includes(e.id), onChange: (ev) => {
      const on = new Set(pr[key]); ev.target.checked ? on.add(e.id) : on.delete(e.id);
      const rank = (id) => (ORDER.includes(id) ? ORDER.indexOf(id) : ORDER.length + effekte.findIndex((x) => x.id === id));
      pr[key] = [...on].sort((a, b) => rank(a) - rank(b));
    } }), e.name)));
  };
  const artBox = h('div', { class: 'grid g2' }, h('span', { class: 'help' }, 'Effekte werden geladen …'));
  const mapBox = h('div', { class: 'grid g2' });
  const presetInfo = h('div', { class: 'help' });
  api.get('/api/premiere/effects').then((r) => { effectGroup('artwork_effects', artBox, r.effekte); effectGroup('map_effects', mapBox, r.effekte.filter((e) => e.id !== 'drop_shadow'));
    presetInfo.textContent = `Die Effekte stammen aus den .prfpset-Vorgaben in ${r.ordner} – Änderungen daran gelten beim nächsten Bau.`; })
    .catch(() => { artBox.textContent = 'Effekte konnten nicht geladen werden.'; });
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Einstellungen'), h('p', {}, 'Diese Einstellungen gelten nur für diesen Rechner und werden nicht über OneDrive geteilt.')), btn('Speichern', { kind: 'primary', icon: 'check', onClick: save })),
    !S.settings.onedrive_root ? h('div', { class: 'banner info', style: { marginBottom: '16px' } }, icon('info'), 'Willkommen! Wähle zuerst den OneDrive-Stammordner, in dem „Mythen-Archiv“ und „Videomaterial“ liegen.') : null,
    h('div', { class: 'card', style: { marginBottom: '16px' } }, h('div', { class: 'card-head' }, h('h2', {}, 'Ersteinrichtung – Selbsttest')),
      h('div', { class: 'col gap-s' }, ...[
        [S.system?.ffmpeg && S.system?.ffprobe, 'ffmpeg/ffprobe gefunden', 'ffmpeg fehlt – ohne geht kein Video (install-Skript ausführen)'],
        [!!S.settings.onedrive_root && S.settings._onedrive_ok, 'OneDrive-Stammordner gesetzt und vorhanden', 'OneDrive-Stammordner wählen (siehe unten)'],
        [!!(S.settings.user || '').trim(), `Dein Name: ${S.settings.user}`, 'Trage deinen Namen ein (für Sperren und Protokoll)'],
        [S.system?.whisper || S.settings.transcription === 'scads', 'Transkription verfügbar', 'Kein lokales Whisper: installieren oder ScaDS-Whisper wählen (optional, nur für den Aufnahme-Abgleich)'],
        [S.settings._scads_key_present, 'ScaDS-Schlüssel vorhanden (KI-Hilfen)', 'Kein ScaDS-Schlüssel – KI-Hilfen sind aus (optional)']].map(([ok, good, bad]) => h('div', { class: 'row' }, icon(ok ? 'check' : 'alert'), h('span', { style: { color: ok ? 'var(--text)' : 'var(--warn)' } }, ok ? good : bad))))),
    h('div', { class: 'grid g2' },
      h('div', { class: 'card col' }, h('h2', {}, 'Grundlagen'),
        field('Dein Name (für Sperren und Änderungsprotokoll)', inp('user')),
        field('OneDrive-Stammordner', h('div', { class: 'row' }, root, btn('Wählen …', { onClick: async () => { const p = await pickPath({ title: 'OneDrive-Stammordner', start: s.onedrive_root }); if (p) { root.value = p; s.onedrive_root = p; } } }))), suggest,
        field('Folgenordner (relativ zum Stamm)', inp('episodes_dir')), field('Bilderordner (relativ, mehrere mit Komma)', h('input', { type: 'text', value: s.images_dirs.join(', '), onInput: (e) => { s.images_dirs = e.target.value.split(',').map((x) => x.trim()).filter(Boolean); } })),
        field('Kartenordner', inp('maps_dir')), field('Vorlagen-/Programm-Vorgaben-Ordner', inp('templates_dir')), field('Darstellung', theme)),
      h('div', { class: 'col' },
        h('div', { class: 'card col' }, h('h2', {}, 'Transkription'), field('Verfahren', transcription), field('Whisper-Modell (auto = large-v3 mit GPU, sonst small)', inp('whisper_model')),
          h('p', { class: 'help' }, 'Aufnahmen verlassen den Rechner nur, wenn ausdrücklich „ScaDS.AI Whisper“ gewählt ist.'),
          h('div', { class: 'help' }, `Aktives Verfahren: ${S.system?.transcription_backend || '–'}`)),
        h('div', { class: 'card col' }, h('h2', {}, 'KI-Hilfen (ScaDS.AI)'),
          h('div', { class: 'help' }, S.settings._scads_key_present ? '✔ API-Schlüssel gefunden.' : '⚠ Kein API-Schlüssel (.env mit SCADS_API_KEY) – KI-Funktionen sind inaktiv.'),
          btn('Verbindung testen', { size: 'sm', icon: 'refresh', onClick: async () => { try { const r = await busy('Verbindung zu ScaDS.AI wird getestet …', api.get('/api/llm/status'), 'Modelle werden abgefragt'); toast(r.key ? (r.models.length ? `Verbunden – ${r.models.length} Modelle verfügbar.` : `Schlüssel da, aber keine Antwort: ${r.error || 'unbekannt'}`) : 'Kein API-Schlüssel gefunden.', r.models.length ? 'ok' : 'warn', 7000); } catch (e) { toast(e.message, 'err'); } } }),
          check('KI-Funktionen aktiv', llm, 'enabled'), ...Object.keys(llm.features).map((k) => check({ transcript_fix: 'Transkript-Nachkorrektur', name_check: 'Namensprüfung', image_suggest: 'Bild-Suchbegriffe', map_suggest: 'Kartenvorschläge', scene_titles: 'Szenentitel', autoframe: 'Automatischer Bildausschnitt für Artworks (sendet verkleinerte Bilder an ScaDS.AI)' }[k] || k, llm.features, k))),
        h('div', { class: 'card col' }, h('h2', {}, 'Premiere-Rohschnitt'),
          h('p', { class: 'help' }, 'Gilt für „Rohschnitt in Premiere bauen“. Wähle, welche Effekte jedes Bild/Artwork und jede Karte bekommt (z. B. „Zoom langsam“ statt „Zoom schnell“).'),
          field('Effekte auf Bildern/Artworks', artBox), field('Effekte auf Karten', mapBox), presetInfo,
          field('Bildrate der Premiere-Sequenz', h('select', { onChange: (e) => { pr.sequence_fps = +e.target.value; } }, [[60, '60 fps (wie im Ursprungsschnitt: weiche Animationen)'], [24, '24 fps (wie der Film: kein Ruckeln, Schnitte bildgenau)'], [24000 / 1001, '23,976 fps']].map(([v, l]) => h('option', { value: v, selected: Math.abs((pr.sequence_fps || 60) - v) < 0.001 }, l)))),
          h('div', { class: 'grid g2' }, field('Kantenlänge eines Artworks (px)', inp('art_size_px', pr, 'number')),
            field('Maske', h('select', { onChange: (e) => { pr.mask = e.target.value; } }, [['Maske Quadrat.png', 'Abgerundetes Quadrat'], ['Maske.png', 'Vollbild']].map(([v, l]) => h('option', { value: v, selected: pr.mask === v }, l))))),
          field('Pause-Animation (relativ zum Stamm; Play entsteht rückwärts daraus)', inp('pause_mov', pr)), field('Ordner mit den Premiere-Vorgaben (.prfpset)', inp('presets_dir', pr))),
        h('div', { class: 'card col' }, h('h2', {}, 'Längenampel & Sprechtempo'),
          h('div', { class: 'grid g2' }, field('Max. Segmentlänge (s)', inp('max_segment_s', th, 'number')), field('Warnschwelle (Anteil)', inp('warn_ratio', th, 'number')),
            field('Ziel-Serienanteil', inp('target_series_share', th, 'number')), field('Wörter pro Sekunde', inp('words_per_second', th, 'number')), field('Sekunden pro Stichpunkt', inp('bullet_seconds', th, 'number'))),
          check('Conform-Dateien in OneDrive ablegen (statt lokal)', s, 'keep_hq_in_onedrive'))))));
}

import { h, btn, toast, field, pickPath, icon } from '../ui.js';
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
  const th = s.thresholds, llm = s.llm;
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Einstellungen'), h('p', {}, 'Diese Einstellungen gelten nur für diesen Rechner und werden nicht über OneDrive geteilt.')), btn('Speichern', { kind: 'primary', icon: 'check', onClick: save })),
    !S.settings.onedrive_root ? h('div', { class: 'banner info', style: { marginBottom: '16px' } }, icon('info'), 'Willkommen! Wähle zuerst den OneDrive-Stammordner, in dem „Mythen-Archiv“ und „Videomaterial“ liegen.') : null,
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
          check('KI-Funktionen aktiv', llm, 'enabled'), ...Object.keys(llm.features).map((k) => check({ transcript_fix: 'Transkript-Nachkorrektur', name_check: 'Namensprüfung', image_suggest: 'Bild-Suchbegriffe', map_suggest: 'Kartenvorschläge', scene_titles: 'Szenentitel' }[k] || k, llm.features, k))),
        h('div', { class: 'card col' }, h('h2', {}, 'Längenampel & Sprechtempo'),
          h('div', { class: 'grid g2' }, field('Max. Segmentlänge (s)', inp('max_segment_s', th, 'number')), field('Warnschwelle (Anteil)', inp('warn_ratio', th, 'number')),
            field('Ziel-Serienanteil', inp('target_series_share', th, 'number')), field('Wörter pro Sekunde', inp('words_per_second', th, 'number')), field('Sekunden pro Stichpunkt', inp('bullet_seconds', th, 'number'))),
          check('Conform-Dateien in OneDrive ablegen (statt lokal)', s, 'keep_hq_in_onedrive'))))));
}

import { h, btn, toast, modal, icon, runJob } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep;
  const dl = (q) => { location.href = epUrl(ep, `/script.docx?${q}`); };
  const pick = (cb, accept = '.docx') => { const i = h('input', { type: 'file', accept, style: { display: 'none' } }); i.onchange = () => i.files[0] && cb(i.files[0]); document.body.append(i); i.click(); i.remove(); };
  const importWord = (f) => api.upload(epUrl(ep, '/script/import-preview'), f).then((pv) => {
    modal({ title: 'Änderungen aus Word übernehmen', body: h('div', { class: 'col' }, h('p', {}, `${pv.changed.length} Szene(n) wurden in Word geändert${pv.changed.length ? ': ' + pv.changed.join(', ') : '.'}`),
      pv.unknown.length ? h('div', { class: 'banner' }, `Unbekannte Szenenmarken: ${pv.unknown.join(', ')} – werden ignoriert.`) : null,
      h('p', { class: 'help' }, 'Übernommen werden Text, Stichpunkte und Sprecher. Zeiten und Bilder bleiben unverändert.')),
    actions: [{ label: 'Abbrechen' }, { label: 'Übernehmen', kind: 'primary', onClick: async () => { try { const r = await api.upload(epUrl(ep, '/script/import'), f); toast(`${r.changed.length} Szene(n) aktualisiert.`, 'ok'); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  }).catch((e) => toast(e.message, 'err'));
  const legacy = (f, replace) => api.upload(epUrl(ep, `/script/import-legacy?replace=${replace}`), f).then((r) => { toast(`Skript importiert (${JSON.stringify(r)})`, 'ok'); ctx.go('editor'); }).catch((e) => toast(e.message, 'err'));
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Word-Skript'), h('p', {}, 'Zum Mitlesen, Aufnehmen und Gegenlesen: Skript als Word exportieren, dort ändern und zurückspielen.'))),
    h('div', { class: 'grid g2' },
      h('div', { class: 'card col' }, h('h2', {}, 'Exportieren'),
        h('div', { class: 'row wrap' }, btn('Gesamtes Skript', { kind: 'primary', icon: 'download', onClick: () => dl('') }), btn('Nur Philipp', { icon: 'download', onClick: () => dl('speaker=philipp') }), btn('Nur Danny', { icon: 'download', onClick: () => dl('speaker=danny') })),
        h('p', { class: 'help' }, 'Die Szenenmarken im Dokument (z. B. [sz_01]) bitte nicht löschen – darüber werden Änderungen zugeordnet.')),
      h('div', { class: 'card col' }, h('h2', {}, 'Aus Word zurückübernehmen'), h('p', { class: 'help' }, 'Das bearbeitete Word-Dokument wählen. Du siehst vorab, welche Szenen sich ändern.'), btn('Word-Datei wählen …', { icon: 'upload', onClick: () => pick(importWord) })),
      h('div', { class: 'card col', style: { gridColumn: '1 / -1' } }, h('h2', {}, 'Bestehendes Skript einlesen (Altformat)'), h('p', { class: 'help' }, 'Skripte mit [Szenen] und P:/D:-Zeilen werden als Szenen übernommen. Zeiten/Segmente setzt du danach im Szenen-Editor.'),
        h('div', { class: 'row' }, btn('Zu bestehenden Szenen hinzufügen', { icon: 'upload', onClick: () => pick((f) => legacy(f, false)) }), btn('Alle Szenen ersetzen', { icon: 'refresh', kind: 'danger', onClick: () => { if (confirm('Alle vorhandenen Szenen werden gelöscht und ersetzt. Fortfahren?')) pick((f) => legacy(f, true)); } }))))));
}

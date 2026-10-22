import { h, btn, toast, modal, icon, runJob } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep;
  const opt = { markers: true, by_strand: true };
  const dl = (q) => { location.href = epUrl(ep, `/script.docx?${q}${q ? '&' : ''}markers=${opt.markers}&by_strand=${opt.by_strand}`); };
  const pick = (cb, accept = '.docx') => { const i = h('input', { type: 'file', accept, style: { display: 'none' } }); i.onchange = () => i.files[0] && cb(i.files[0]); document.body.append(i); i.click(); i.remove(); };
  const importWord = (f) => api.upload(epUrl(ep, '/script/import-preview'), f).then((pv) => {
    modal({ title: 'Änderungen aus Word übernehmen', body: h('div', { class: 'col' }, h('p', {}, `${pv.changed.length} Szene(n) wurden in Word geändert${pv.changed.length ? ':' : '.'}`), h('ul', {}, (pv.changed_titles || pv.changed).map((x) => h('li', {}, x))), h('p', { class: 'help' }, pv.free_blocks.length ? `${pv.free_blocks.length} Rahmenteil(e) im Dokument.` : ''),
      pv.unknown.length ? h('div', { class: 'banner' }, `Unbekannte Szenenmarken: ${pv.unknown.join(', ')} – werden ignoriert.`) : null,
      h('p', { class: 'help' }, 'Übernommen werden Text, Stichpunkte und Sprecher. Zeiten und Bilder bleiben unverändert.')),
    actions: [{ label: 'Abbrechen' }, { label: 'Übernehmen', kind: 'primary', onClick: async () => { try { const r = await api.upload(epUrl(ep, '/script/import'), f); toast(`${r.changed.length} Szene(n) aktualisiert.`, 'ok'); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  }).catch((e) => toast(e.message, 'err'));
  const legacy = (f, replace) => api.upload(epUrl(ep, `/script/import-legacy?replace=${replace}`), f).then((r) => { toast(`Skript importiert (${JSON.stringify(r)})`, 'ok'); ctx.go('editor'); }).catch((e) => toast(e.message, 'err'));
  let blocks = await api.get(epUrl(ep, '/free-blocks'));
  const scenes = S.data.scenes;
  const fbBox = h('div', { class: 'col' });
  const drawFb = () => fbBox.replaceChildren(...(blocks.length ? blocks.map((b, i) => h('div', { class: 'card tight col gap-s' }, h('div', { class: 'row' },
    h('input', { type: 'text', value: b.titel || '', placeholder: 'Titel, z. B. Werbung', onInput: (e) => { b.titel = e.target.value; } }),
    h('select', { onChange: (e) => { b.after = e.target.value || null; } }, h('option', { value: '' }, 'Ganz am Anfang'), scenes.map((s) => h('option', { value: s.id, selected: b.after === s.id }, `nach „${s.titel || s.id}“`))),
    h('input', { type: 'number', min: 0, value: b.dauer ?? '', placeholder: 'Dauer s', style: { width: '100px' }, title: 'Bekannte Länge in Sekunden (leer = aus dem Text schätzen)', onInput: (e) => { b.dauer = e.target.value === '' ? null : +e.target.value; } }),
    btn('', { icon: 'trash', kind: 'ghost', onClick: () => { blocks.splice(i, 1); drawFb(); } })),
    h('textarea', { rows: 2, placeholder: 'Text/Notiz (optional, erscheint im Word)', value: b.text || '', onInput: (e) => { b.text = e.target.value; } }))) : [h('p', { class: 'help' }, 'Keine Rahmenteile. Intro, Werbung oder Outro mit bekannter Länge hier eintragen: Der Rohschnitt reserviert dafür eine Lücke exakter Länge.')]));
  drawFb();
  const saveFb = async () => { try { await api.put(epUrl(ep, '/free-blocks'), blocks.map((b) => ({ titel: b.titel || '', text: b.text || '', after: b.after || null, dauer: b.dauer ?? null }))); toast('Rahmenteile gespeichert.', 'ok'); } catch (e) { toast(e.message, 'err'); } };
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Word-Skript'), h('p', {}, 'Zum Mitlesen, Aufnehmen und Gegenlesen: Skript als Word exportieren, dort ändern und zurückspielen.'))),
    h('div', { class: 'grid g2' },
      h('div', { class: 'card col' }, h('h2', {}, 'Exportieren'),
        h('div', { class: 'row wrap' }, btn('Gesamtes Skript', { kind: 'primary', icon: 'download', onClick: () => dl('') }), btn('Nur Philipp', { icon: 'download', onClick: () => dl('speaker=philipp') }), btn('Nur Danny', { icon: 'download', onClick: () => dl('speaker=danny') })),
        h('div', { class: 'row wrap gap-l' }, h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: true, onChange: (e) => { opt.markers = e.target.checked; } }), 'Bild-/Kartenmarken zeigen'), h('label', { class: 'check', title: 'Aus: Reihenfolge wie im Szenen-Editor' }, h('input', { type: 'checkbox', checked: true, onChange: (e) => { opt.by_strand = e.target.checked; } }), 'Nach Strängen sortieren')),
        h('p', { class: 'help' }, 'Die Szenenmarken im Dokument (⟦sz:sz_01⟧) und Bildmarken (⟦+bild:…⟧) bitte nicht löschen – darüber werden Änderungen zugeordnet. Eigene Rahmenteile (Werbung, Outro) als „Überschrift 1“ anlegen.')),
      h('div', { class: 'card col' }, h('h2', {}, 'Aus Word zurückübernehmen'), h('p', { class: 'help' }, 'Das bearbeitete Word-Dokument wählen. Du siehst vorab, welche Szenen sich ändern.'), btn('Word-Datei wählen …', { icon: 'upload', onClick: () => pick(importWord) })),
      h('div', { class: 'card col', style: { gridColumn: '1 / -1' } }, h('div', { class: 'card-head' }, h('h2', { class: 'grow' }, 'Rahmenteile (Intro, Werbung, Outro …)'), btn('Rahmenteil +', { size: 'sm', icon: 'plus', onClick: () => { blocks.push({ titel: '', text: '', after: null, dauer: null }); drawFb(); } }), btn('Speichern', { size: 'sm', kind: 'primary', onClick: saveFb })), fbBox),
      h('div', { class: 'card col', style: { gridColumn: '1 / -1' } }, h('h2', {}, 'Bestehendes Skript einlesen (Altformat)'), h('p', { class: 'help' }, 'Skripte mit [Szenen] und P:/D:-Zeilen werden als Szenen übernommen. Zeiten/Segmente setzt du danach im Szenen-Editor.'),
        h('div', { class: 'row' }, btn('Zu bestehenden Szenen hinzufügen', { icon: 'upload', onClick: () => pick((f) => legacy(f, false)) }), btn('Alle Szenen ersetzen', { icon: 'refresh', kind: 'danger', onClick: () => { if (confirm('Alle vorhandenen Szenen werden gelöscht und ersetzt. Fortfahren?')) pick((f) => legacy(f, true)); } }))))));
}

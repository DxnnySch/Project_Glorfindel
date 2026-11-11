import { h, btn, pickPath, runJob, toast, empty, fmtTC, parseTC, icon, modal, field } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

const ROLES = { referenz: 'Referenz (Zeitachse)', screener: 'Screener', hq: 'HQ deutsch', screencapture: 'Bildschirmaufnahme' };

export async function render(main, ctx) {
  const d = S.data, ep = S.ep;
  const add = async (role) => {
    const start = S.settings.onedrive_root;
    const p = await pickPath({ title: 'Videodatei wählen', start, files: true, accept: ['.mp4', '.mov', '.mkv', '.mxf', '.m4v', '.avi', '.webm'] });
    if (!p) return;
    try { await runJob('Quelle wird analysiert …', () => api.post(epUrl(ep, '/sources'), { path: p, role })); toast('Quelle importiert.', 'ok'); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const proxy = async (s) => { try { await runJob(`Proxy für ${s.id} …`, () => api.post(epUrl(ep, `/sources/${s.id}/proxy`))); toast('Proxy fertig.', 'ok'); ctx.refresh(); } catch (e) { toast(e.message, 'err'); } };
  const setRole = async (s, role) => { try { await api.patch(epUrl(ep, `/sources/${s.id}`), { role }); ctx.refresh(); } catch (e) { toast(e.message, 'err'); } };
  // HQ-Modus: Vorschau-Proxy aus der HQ-Datei (zeitgleich zur Referenz), Dialog aus deren Untertiteln
  const hqSrc = d.sources.find((s) => s.role === 'hq' && s.id !== d.project.reference_source);
  const setHq = async (on) => {
    try {
      await api.patch(epUrl(ep, '/project'), { hq_modus: on });
      if (on) {
        await runJob('HQ-Proxy erzeugen', () => api.post(epUrl(ep, `/sources/${d.project.reference_source}/proxy`)));
        const sub = (await api.get(epUrl(ep, '/dialog/subtitles'))).find((c) => c.source === hqSrc.id);
        if (sub) { await api.post(epUrl(ep, '/dialog/subtitles'), { path: sub.path, source: sub.source }); toast(`HQ-Modus an – Dialog aus ${sub.path.split(/[\\/]/).pop()}.`, 'ok'); }
        else toast('HQ-Modus an. Neben der HQ-Datei wurde keine Untertitel-Datei gefunden – der Dialog bleibt unverändert.', 'info', 8000);
      } else toast('HQ-Modus aus – die Vorschau zeigt wieder die Referenz.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
    ctx.refresh();
  };
  const hqCard = hqSrc ? h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'row' }, icon('film'),
    h('div', { class: 'grow' }, h('b', {}, 'HQ-Modus'), h('div', { class: 'help' }, hqSrc.anchors.length
      ? 'Die Vorschau stammt aus der HQ-Datei (zeitgleich zur Referenz) und der Dialog aus ihren Untertiteln (SRT, VTT, TTML), sofern vorhanden. Aus: wie bisher.'
      : 'Zuerst für die HQ-Quelle mindestens einen Anker setzen (gleiches Bild in Referenz und HQ).')),
    h('label', { class: 'row gap-s' }, h('input', { type: 'checkbox', checked: !!d.project.hq_modus, disabled: !hqSrc.anchors.length && !d.project.hq_modus, onChange: (e) => setHq(e.target.checked) }), 'HQ vorhanden – nutzen')))
    : null;
  const crop = async (s) => {
    try { const r = await api.post(epUrl(ep, `/sources/${s.id}/detect-crop`));
      if (!r.crop) { toast('Keine Letterbox erkannt.', 'info'); return; }
      await api.patch(epUrl(ep, `/sources/${s.id}`), { crop: r.crop }); toast(`Zuschnitt gesetzt: ${r.crop.join(', ')}`, 'ok'); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const anchors = (s) => {
    let rows = s.anchors.map((a) => ({ ...a }));
    const list = h('div', { class: 'col gap-s' });
    const draw = () => { list.replaceChildren(...rows.map((a, i) => h('div', { class: 'row' },
      field('Referenz-Zeit', h('input', { type: 'text', value: fmtTC(a.ref), onChange: (e) => { const v = parseTC(e.target.value); if (v != null) a.ref = v; } })),
      field('Zeit in dieser Quelle', h('input', { type: 'text', value: fmtTC(a.src), onChange: (e) => { const v = parseTC(e.target.value); if (v != null) a.src = v; } })),
      btn('', { icon: 'trash', kind: 'ghost', onClick: () => { rows.splice(i, 1); draw(); } })))); };
    draw();
    modal({ title: `Ankerpunkte – ${s.path.split('/').pop()}`, wide: false,
      body: h('div', { class: 'col' }, h('p', { class: 'help' }, 'Gleiche Bildinhalte in Referenz und Quelle zuordnen. Mit zwei oder mehr Ankern wird Tempo und Versatz stückweise ausgeglichen. Format: mm:ss.bb (Bild).'), list, btn('Anker hinzufügen', { icon: 'plus', onClick: () => { rows.push({ ref: 0, src: 0 }); draw(); } })),
      actions: [{ label: 'Abbrechen' }, { label: 'Speichern', kind: 'primary', onClick: async () => { try { await api.put(epUrl(ep, `/sources/${s.id}/anchors`), { anchors: rows }); ctx.refresh(); } catch (e) { toast(e.message, 'err'); return false; } } }] });
  };
  const rows = d.sources.map((s) => h('tr', {},
    h('td', {}, h('div', {}, h('b', {}, s.path.split('/').pop())), h('div', { class: 'faint mono' }, s.path)),
    h('td', {}, h('select', { onChange: (e) => setRole(s, e.target.value) }, Object.entries(ROLES).map(([k, v]) => h('option', { value: k, selected: s.role === k }, v)))),
    h('td', { class: 'mono' }, `${s.width}×${s.height} · ${s.fps.toFixed(3)} fps · ${fmtTC(s.duration)}`, s.crop ? h('div', { class: 'faint' }, `Zuschnitt ${s.crop.join(',')}`) : null),
    h('td', {}, s.role === 'referenz' ? h('span', { class: 'faint' }, '–') : h('span', { class: `chip ${s.anchors.length >= 2 ? 'accent' : ''}` }, `${s.anchors.length} Anker`)),
    h('td', {}, h('div', { class: 'row gap-s' }, btn('Proxy', { size: 'sm', icon: 'video', onClick: () => proxy(s), title: 'Schnell abspielbare Vorschau erzeugen' }),
      btn('Zuschnitt', { size: 'sm', onClick: () => crop(s), title: 'Letterbox automatisch erkennen' }),
      s.role !== 'referenz' ? btn('Anker', { size: 'sm', icon: 'link', onClick: () => anchors(s) }) : null))));
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Quellen'), h('p', {}, 'Die Referenz bestimmt die Zeitachse aller Szenen. Weitere Fassungen (HQ, Screener) werden über Ankerpunkte darauf abgebildet.')),
      btn('Referenz importieren', { kind: 'primary', icon: 'plus', onClick: () => add('referenz') }), btn('Weitere Quelle', { icon: 'plus', onClick: () => add('hq') })),
    hqCard,
    d.sources.length ? h('div', { class: 'card' }, h('table', {}, h('thead', {}, h('tr', {}, ['Datei', 'Rolle', 'Format', 'Zeitabbildung', ''].map((t) => h('th', {}, t)))), h('tbody', {}, rows)))
      : h('div', { class: 'card' }, empty('film', 'Noch keine Quellen', 'Wähle die Episode (die Referenz-Zeitachse) aus deinem OneDrive.', btn('Referenz wählen', { kind: 'primary', onClick: () => add('referenz') })))));
}

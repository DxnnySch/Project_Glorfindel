import { h, btn, empty, runJob, toast, pickPath, fmtTC, parseTC, icon, field, remember } from '../ui.js';
import { api, epUrl } from '../api.js';
import { S } from '../state.js';

export async function render(main, ctx) {
  const ep = S.ep;
  const data = await api.get(epUrl(ep, '/recording'));
  const recs = data.recordings || [];
  const add = async (speaker) => {
    const p = await pickPath({ title: `Aufnahme von ${speaker} wählen`, start: S.settings.onedrive_root, files: true, accept: ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.mp4', '.mov', '.ogg'] });
    if (!p) return;
    try { await api.post(epUrl(ep, '/recording'), { path: p, speaker }); toast('Aufnahme hinzugefügt.', 'ok'); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const align = async () => {
    try { await runJob('Aufnahme wird transkribiert und zugeordnet (kann dauern) …', () => api.post(epUrl(ep, '/recording/align?prefer=last'))); toast('Abgleich fertig.', 'ok'); ctx.refresh(); } catch (e) { toast(e.message, 'err'); }
  };
  const audio = h('audio', { controls: true, style: { width: '100%' } });
  const wave = h('canvas', { height: 130 }), waveBox = h('div', { class: 'wave' }, wave);
  let peaksCache = null, marks = [];
  const drawWave = () => {
    if (!peaksCache) return;
    const c = wave, w = c.width = c.clientWidth * devicePixelRatio, hh = c.height = 130 * devicePixelRatio, g = c.getContext('2d');
    const st = getComputedStyle(document.documentElement);
    g.clearRect(0, 0, w, hh);
    marks.forEach((m) => { g.fillStyle = m.missing ? 'rgba(239,91,91,.0)' : 'rgba(212,170,79,.18)'; g.fillRect(m.in / peaksCache.duration * w, 0, (m.out - m.in) / peaksCache.duration * w, hh); });
    g.fillStyle = st.getPropertyValue('--info') || '#5aa7ff';
    const p = peaksCache.peaks, n = p.length;
    for (let i = 0; i < n; i++) { const x = i / n * w, a = Math.max(1, (Array.isArray(p[i]) ? Math.max(...p[i].map(Math.abs)) : Math.abs(p[i])) * hh * .9); g.fillRect(x, (hh - a) / 2, Math.max(1, w / n), a); }
  };
  const showRec = async (r) => {
    audio.src = epUrl(ep, `/recording/${r.id}/audio`);
    try { peaksCache = await api.get(epUrl(ep, `/recording/${r.id}/waveform`)); marks = Object.values(data.scenes || {}).flat().filter((b) => b.rec === r.id && b.in != null); drawWave(); } catch (e) { toast(e.message, 'err'); }
  };
  wave.addEventListener('click', (e) => { if (!peaksCache) return; const r = wave.getBoundingClientRect(); audio.currentTime = (e.clientX - r.left) / r.width * peaksCache.duration; audio.play(); });
  const ui = remember(`${ep.season}-${ep.episode}:recording`, { onlyUnsure: false });
  let onlyUnsure = !!ui.onlyUnsure;
  const isUnsure = (e) => !e || e.missing || e.uncertain || (e.confidence != null && e.confidence < 0.8);
  const unsureCount = S.data.scenes.reduce((n, sc) => n + sc.kommentar.filter((b, i) => (b.text.trim() || b.stichpunkte.length) && isUnsure(((data.scenes || {})[sc.id] || []).find((x) => x.block === i))).length, 0);
  const sceneHost = h('div');
  const buildRows = () => S.data.scenes.map((sc) => {
    const entries = (data.scenes || {})[sc.id] || [];
    const visible = sc.kommentar.map((b, i) => i).filter((i) => !onlyUnsure || ((sc.kommentar[i].text.trim() || sc.kommentar[i].stichpunkte.length) && isUnsure(entries.find((x) => x.block === i))));
    if (!visible.length) return null;
    return h('div', { id: `rs_${sc.id}`, class: 'card tight', style: { marginBottom: '10px' } }, h('div', { class: 'card-head' }, h('b', {}, sc.titel || sc.id), h('span', { class: `chip ${sc.status === 'veraltet' ? 'accent' : ''}` }, sc.status)),
      visible.map((i) => {
        const b = sc.kommentar[i];
        const e = entries.find((x) => x.block === i);
        const t0 = h('input', { type: 'text', value: e && e.in != null ? fmtTC(e.in) : '', placeholder: 'In', style: { width: '90px' } }), t1 = h('input', { type: 'text', value: e && e.out != null ? fmtTC(e.out) : '', placeholder: 'Out', style: { width: '90px' } });
        const saveT = async () => { const a = parseTC(t0.value), z = parseTC(t1.value); if (a == null || z == null) return; try { await api.put(epUrl(ep, '/recording/block'), { scene: sc.id, block: i, t_in: a, t_out: z }); toast('Zeiten gespeichert.', 'ok'); } catch (er) { toast(er.message, 'err'); } };
        return h('div', { class: 'row', style: { padding: '6px 0', borderTop: '1px solid var(--line)' } }, h('span', { class: `chip ${b.sprecher === 'danny' ? '' : 'accent'}` }, b.sprecher),
          h('div', { class: 'grow help' }, (b.modus === 'stichpunkte' ? b.stichpunkte.join(' · ') : b.text).slice(0, 140) || '(leer)', b.gesprochen ? h('div', { style: { color: 'var(--text)' } }, `Gesprochen: ${b.gesprochen.slice(0, 160)}`) : null, e && (e.ergaenzungen || []).length ? h('div', { style: { color: 'var(--info)' } }, `Spontan ergänzt: ${e.ergaenzungen.join(' … ')}`) : null),
          e ? (e.missing ? h('span', { class: 'pill bad' }, 'nicht gefunden') : h('span', { class: `pill ${e.confidence > .8 ? 'ok' : 'warn'}` }, `${Math.round((e.confidence || 0) * 100)} %`)) : h('span', { class: 'faint' }, '–'),
          e && (e.takes || []).length > 1 ? h('select', { style: { width: 'auto' }, title: 'Mehrere Takes gefunden – welchen verwenden?', onChange: async (ev) => { try { await api.put(epUrl(ep, '/recording/take'), { scene: sc.id, block: i, take: +ev.target.value }); toast('Take gewählt.', 'ok'); ctx.refresh(); } catch (er) { toast(er.message, 'err'); } } },
            e.takes.map((tk, k) => h('option', { value: k, selected: k === e.chosen }, `Take ${k + 1} · ${fmtTC(tk.start)} · ${Math.round(tk.score)} %`))) : null,
          t0, t1, btn('', { icon: 'check', size: 'sm', title: 'Zeiten speichern', onClick: saveT }),
          e && e.in != null ? btn('', { icon: 'play', size: 'sm', kind: 'ghost', onClick: () => { audio.currentTime = e.in; audio.play(); } }) : null,
          b.modus === 'stichpunkte' && b.gesprochen ? btn('Als Skript', { size: 'sm', title: 'Gesprochenen Text als Skript übernehmen', onClick: async () => { try { await api.post(epUrl(ep, '/recording/adopt'), { scene: sc.id, block: i }); toast('Übernommen.', 'ok'); ctx.refresh(); } catch (er) { toast(er.message, 'err'); } } }) : null);
      }));
  });
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, 'Aufnahme'), h('p', {}, 'Sprachaufnahmen importieren und den Szenen automatisch zuordnen. Mehrfache Takes: der letzte zählt.')),
      btn('Philipp', { icon: 'mic', onClick: () => add('philipp') }), btn('Danny', { icon: 'mic', onClick: () => add('danny') }), btn('Abgleich starten', { kind: 'primary', icon: 'wand', disabled: !recs.length, onClick: align })),
    recs.length ? h('div', { class: 'card col', style: { marginBottom: '16px' } }, h('div', { class: 'row wrap' }, recs.map((r) => h('button', { class: 'chip accent', style: { cursor: 'pointer' }, onClick: () => showRec(r) }, icon('mic'), `${r.speaker} · ${fmtTC(r.duration)} · ${r.path.split('/').pop()}`))), waveBox, audio)
      : h('div', { class: 'card', style: { marginBottom: '16px' } }, empty('mic', 'Noch keine Aufnahme', 'Füge die eingesprochene Tonspur von Philipp und/oder Danny hinzu.')),
    S.data.scenes.length ? h('div', { class: 'row', style: { margin: '4px 0 12px' } }, h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: onlyUnsure, onChange: (e) => { onlyUnsure = e.target.checked; ui.onlyUnsure = onlyUnsure; drawRows(); } }), `Nur unsichere Stellen (${unsureCount})`),
      btn('Nächste unsichere', { size: 'sm', icon: 'chevron', disabled: !unsureCount, onClick: () => { const all = [...document.querySelectorAll('[id^=rs_]')]; const first = all.find((el) => el.getBoundingClientRect().top > 120 && el.querySelector('.pill.bad, .pill.warn, .faint')) || all[0]; first?.scrollIntoView({ behavior: 'smooth', block: 'center' }); } })) : null,
    sceneHost));
  const drawRows = () => sceneHost.replaceChildren(...buildRows().filter(Boolean));
  drawRows();
  if (recs.length) showRec(recs[0]);
  const onResize = () => drawWave(); window.addEventListener('resize', onResize);
  const onKey = (e) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === ' ' || k === 'k') { e.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
    else if (k === 'j') audio.currentTime = Math.max(0, audio.currentTime - 3);
    else if (k === 'l') audio.currentTime += 3;
  };
  document.addEventListener('keydown', onKey);
  return () => { window.removeEventListener('resize', onResize); document.removeEventListener('keydown', onKey); };
}

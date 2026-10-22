// Einstieg: Seitenleiste, Hash-Routing, Folgenwahl, Live-Nachladen.
import { h, $, clear, icon, toast, btn, modal, field } from './ui.js';
import { api, epUrl } from './api.js';
import { S, loadGlobal, loadEpisode, slug } from './state.js';

const VIEWS = {
  home:     { label: 'Übersicht',   icon: 'home',     mod: './views/home.js' },
  sources:  { label: 'Quellen',     icon: 'film',     mod: './views/sources.js', sec: 'Vorbereitung' },
  board:    { label: 'Strang-Board', icon: 'layers',  mod: './views/board.js' },
  editor:   { label: 'Szenen',      icon: 'edit',     mod: './views/editor.js', sec: 'Skript' },
  script:   { label: 'Word-Skript', icon: 'doc',      mod: './views/script.js' },
  images:   { label: 'Bilder',      icon: 'image',    mod: './views/images.js', sec: 'Material' },
  maps:     { label: 'Karten',      icon: 'map',      mod: './views/maps.js' },
  recording:{ label: 'Aufnahme',    icon: 'mic',      mod: './views/recording.js', sec: 'Produktion' },
  cut:      { label: 'Rohschnitt',  icon: 'scissors', mod: './views/cut.js' },
  settings: { label: 'Einstellungen', icon: 'gear',   mod: './views/settings.js', sec: 'System', global: true },
};
let cleanup = null, current = null;

export function go(view, ep = S.ep) {
  location.hash = ep && !VIEWS[view]?.global ? `#/${ep.season}/${ep.episode}/${view}` : `#/${view}`;
}

function parse() {
  const p = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (/^\d+$/.test(p[0] || '') && /^\d+$/.test(p[1] || '')) return { ep: { season: +p[0], episode: +p[1] }, view: p[2] || 'home' };
  return { ep: null, view: p[0] || 'home' };
}

function renderSide(view) {
  const side = clear($('#side'));
  side.append(h('div', { class: 'brand' }, h('div', { class: 'brand-logo' }, 'G'), h('div', {}, h('b', {}, 'Glorfindel'), h('small', {}, 'Folgenbesprechung'))));
  const sel = h('select', { class: 'ep-switch', onChange: (e) => {
    const v = e.target.value;
    if (v === '+') return newEpisode();
    if (v === '') { location.hash = '#/home'; return; }
    const [s, ep] = v.split('-'); location.hash = `#/${s}/${ep}/${view === 'settings' ? 'home' : view}`;
  } },
  h('option', { value: '' }, S.episodes.length ? 'Folge wählen …' : 'Noch keine Folge'),
  S.episodes.map((e) => h('option', { value: `${e.season}-${e.episode}`, selected: S.ep && S.ep.season === e.season && S.ep.episode === e.episode }, `${slug(e)}${e.title ? ' – ' + e.title : ''}`)),
  h('option', { value: '+' }, '+ Neue Folge anlegen …'));
  side.append(sel);
  for (const [k, v] of Object.entries(VIEWS)) {
    if (v.sec) side.append(h('div', { class: 'nav-sec' }, v.sec));
    const disabled = !v.global && !S.ep;
    side.append(h('a', { class: `nav ${k === view ? 'active' : ''}`, href: '#', style: disabled ? { opacity: .4, pointerEvents: 'none' } : null,
      onClick: (e) => { e.preventDefault(); go(k); } }, icon(v.icon), h('span', {}, v.label),
    k === 'editor' && S.data ? h('span', { class: 'badge' }, S.data.scenes.length) : null));
  }
  side.append(h('div', { class: 'side-foot' }, `Angemeldet als ${S.settings?.user || '–'}`,
    h('br'), S.system && !S.system.ffmpeg ? h('span', { style: { color: 'var(--bad)' } }, 'ffmpeg fehlt!') : ''));
}

export function newEpisode() {
  const season = h('input', { type: 'number', value: 2, min: 1 }), ep = h('input', { type: 'number', value: 1, min: 1 }), title = h('input', { type: 'text', placeholder: 'z. B. Titel der Folge' });
  modal({ title: 'Neue Folge anlegen', body: h('div', { class: 'col' }, h('div', { class: 'row' }, field('Staffel', season), field('Folge', ep)), field('Titel (optional)', title)),
    actions: [{ label: 'Abbrechen' }, { label: 'Anlegen', kind: 'primary', onClick: async () => {
      try { await api.post('/api/episodes', { season: +season.value, episode: +ep.value, title: title.value });
        await loadGlobal(); location.hash = `#/${season.value}/${ep.value}/sources`; } catch (e) { toast(e.message, 'err'); return false; } } }] });
}

async function route() {
  const { ep, view } = parse();
  const def = VIEWS[view] || VIEWS.home;
  cleanup?.(); cleanup = null;
  const main = clear($('#main'));
  try {
    if (!S.settings) await loadGlobal();
    if (ep) await loadEpisode(ep.season, ep.episode); else { S.ep = null; S.data = null; }
  } catch (e) {
    toast(e.message, 'err');
    if (ep) { location.hash = '#/home'; return; }
  }
  if (!S.settings.onedrive_root && view !== 'settings') { location.hash = '#/settings'; return; }
  renderSide(VIEWS[view] ? view : 'home');
  current = view;
  try {
    const mod = await import(def.mod);
    cleanup = (await mod.render(main, { go, refresh: () => route() })) || null;
  } catch (e) {
    console.error(e);
    main.append(h('div', { class: 'page' }, h('div', { class: 'banner bad' }, `Ansicht konnte nicht geladen werden: ${e.message}`)));
  }
}

// Änderungen anderer (OneDrive) erkennen
let lastVer = null;
setInterval(async () => {
  if (!S.ep || document.hidden || current === 'editor') return;
  try { const v = (await api.get(epUrl(S.ep, '/version'))).version; if (lastVer && v > lastVer) toast('Daten wurden extern geändert – Ansicht neu laden (F5), um sie zu sehen.', 'warn', 6000); lastVer = v; } catch { /* offline */ }
}, 8000);

const theme = localStorage.getItem('gl-theme'); if (theme) document.documentElement.dataset.theme = theme;
window.addEventListener('hashchange', route);
route();

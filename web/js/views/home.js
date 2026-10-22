import { h, btn, empty, fmtDur, icon } from '../ui.js';
import { S, slug } from '../state.js';
import { api, epUrl } from '../api.js';
import { newEpisode } from '../main.js';

export async function render(main, ctx) {
  if (!S.ep) {
    main.append(h('div', { class: 'page' }, h('div', { class: 'hero' }, h('h1', {}, 'Projekt Glorfindel'), h('p', { class: 'muted' }, 'Vom Skript zum Premiere-Rohschnitt für die Folgenbesprechung.'),
      h('div', { class: 'steps' }, ...['Folge anlegen und Episode importieren', 'Szenen und Kommentare schreiben', 'Aufnahme einsprechen und automatisch zuordnen', 'Rohschnitt erzeugen und in Premiere öffnen'].map((t, i) => h('div', { class: 'row' }, h('div', { class: 'phase', style: { padding: 0, border: 0, background: 'none', cursor: 'default' } }, h('div', { class: 'n' }, i + 1)), t))),
      h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '26px' } }, btn('Neue Folge anlegen', { kind: 'primary', icon: 'plus', onClick: newEpisode }))),
    S.episodes.length ? h('div', { class: 'card', style: { marginTop: '18px' } }, h('h2', { style: { marginBottom: '10px' } }, 'Vorhandene Folgen'),
      S.episodes.map((e) => h('div', { class: 'row', style: { padding: '8px 0' } }, h('b', {}, slug(e)), h('span', { class: 'muted grow' }, e.title), btn('Öffnen', { onClick: () => ctx.go('home', e) })))) : null));
    return;
  }
  const d = S.data, rep = d.report, sc = d.scenes;
  const ck = await api.get(epUrl(S.ep, '/cockpit'));
  const hasSrc = ck.phases.vorbereiten, hasScenes = ck.phases.skript, hasRec = ck.phases.einsprechen, aligned = ck.phases.rohschnitt;
  const phase = (n, title, text, done, view, who) => h('div', { class: `phase ${done ? 'done' : ''}`, onClick: () => ctx.go(view) }, h('div', { class: 'n' }, done ? icon('check') : n), h('b', {}, title), h('small', {}, text), h('span', { class: 'who' }, who));
  const nowIdx = [hasSrc, hasScenes, hasRec, aligned].findIndex((x) => !x);
  const stat = (v, l) => h('div', { class: 'card stat' }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, l));
  const light = (c) => sc.filter((x) => x.report?.light === c).length || rep.scenes.filter((r) => r.light === c).length;
  main.append(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', { class: 'grow' }, h('h1', {}, `${slug(S.ep)}${d.project.title ? ' – ' + d.project.title : ''}`), h('p', {}, `${d.project.fps} fps · ${d.sources.length} Quelle(n) · ${sc.length} Szene(n)`)),
      btn('Rohschnitt', { kind: 'primary', icon: 'scissors', onClick: () => ctx.go('cut') })),
    d.conflicts.length ? h('div', { class: 'banner bad', style: { marginBottom: '14px' } }, icon('alert'), `${d.conflicts.length} OneDrive-Konfliktkopie(n) bei den Szenen – bitte im Szenen-Editor prüfen.`) : null,
    h('div', { class: 'phases' }, phase(1, 'Vorbereiten', 'Episode & Aufnahmen importieren, Anker setzen', hasSrc, 'sources', 'Philipp / Maurice'),
      phase(2, 'Skript', 'Szenen, Kommentare, Bilder', hasScenes, 'editor', 'Philipp & Danny'),
      phase(3, 'Einsprechen', 'Aufnahme importieren und zuordnen', hasRec, 'recording', 'Philipp & Danny'),
      phase(4, 'Rohschnitt', 'Paket für Premiere erzeugen', aligned, 'cut', 'Maurice')),
    h('div', { class: 'grid g4', style: { marginTop: '18px' } },
      stat(fmtDur(rep.total_s), 'Gesamtlänge (geschätzt)'), stat(`${Math.round(rep.series_share * 100)} %`, `Serienanteil (Ziel ${Math.round(S.settings.thresholds.target_series_share * 100)} %)`),
      stat(rep.scenes.filter((r) => r.light === 'rot').length, 'Szenen mit zu langem Segment'), stat(sc.filter((x) => x.fixiert).length, 'Dramaturgisch fixiert')),
    h('div', { class: 'card', style: { marginTop: '18px' } }, h('div', { class: 'card-head' }, h('h2', {}, 'Als Nächstes')),
      ck.tasks.length ? ck.tasks.map((t) => h('div', { class: 'row', style: { padding: '7px 0', borderTop: '1px solid var(--line)', cursor: 'pointer' }, onClick: () => { location.hash = `#/${S.ep.season}/${S.ep.episode}/${t.view}${t.scene ? '?id=' + t.scene : ''}`; } },
        h('span', { class: 'pill warn' }, t.n), h('span', { class: 'grow' }, t.text), icon('chevron')))
        : h('div', { class: 'row' }, icon('check'), h('span', { class: 'muted' }, 'Alles erledigt – der Rohschnitt kann erzeugt werden.'))),
    !hasSrc ? h('div', { class: 'card', style: { marginTop: '18px' } }, empty('film', 'Noch keine Quelle', 'Importiere die Referenz-Episode (z. B. die englische Bildschirmaufnahme).', btn('Quellen öffnen', { kind: 'primary', onClick: () => ctx.go('sources') }))) : null));
  void nowIdx;
}

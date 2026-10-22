// Gemeinsamer Zustand der Oberfläche (aktuelle Folge, Einstellungen) und Neuladen.
import { api, epUrl } from './api.js';

export const S = { settings: null, episodes: [], ep: null, data: null, system: null };

export async function loadGlobal() {
  [S.settings, S.episodes, S.system] = await Promise.all([api.get('/api/settings'), api.get('/api/episodes'), api.get('/api/system')]);
}
export async function loadEpisode(season, episode) {
  S.ep = { season, episode };
  S.data = await api.get(epUrl(S.ep));
  return S.data;
}
export const reload = () => (S.ep ? loadEpisode(S.ep.season, S.ep.episode) : loadGlobal());
export const slug = (e) => `S${e.season} E${e.episode}`;
export const refSource = () => S.data?.sources.find((s) => s.id === S.data.project.reference_source) || S.data?.sources.find((s) => s.role === 'referenz');
export const strandOf = (id) => S.data?.strands.find((s) => s.id === id);

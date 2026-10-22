// Schlanker API-Client; alle Fehler werden als Error mit lesbarer Meldung geworfen.
async function call(method, url, body, isForm) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body;
    else { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  }
  const r = await fetch(url, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j); } catch { /* kein JSON */ }
    const e = new Error(msg); e.status = r.status; throw e;
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('application/json') ? r.json() : r;
}
export const api = {
  get: (u) => call('GET', u),
  post: (u, b) => call('POST', u, b ?? {}),
  put: (u, b) => call('PUT', u, b),
  patch: (u, b) => call('PATCH', u, b),
  del: (u) => call('DELETE', u),
  upload: (u, file) => { const f = new FormData(); f.append('file', file); return call('POST', u, f, true); },
};
export const epUrl = (ep, path = '') => `/api/ep/${ep.season}/${ep.episode}${path}`;

// Job-Abfrage mit Fortschrittsmeldung
export async function waitJob(id, onProgress) {
  for (;;) {
    const j = await api.get(`/api/jobs/${id}`);
    onProgress?.(j);
    if (j.status === 'fertig') return j.result;
    if (j.status === 'fehler') throw new Error(j.error || 'Aufgabe fehlgeschlagen');
    await new Promise((r) => setTimeout(r, 600));
  }
}

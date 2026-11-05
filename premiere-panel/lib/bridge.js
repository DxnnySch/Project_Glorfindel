// Verbindung zum Glorfindel-Server (WebSocket, 127.0.0.1) und Verteilung der Befehle. Abhängigkeiten werden hineingereicht (testbar).
'use strict';

const { errText, sleep } = require('./core');
const plan = require('./plan');
const media = require('./media');
const dump = require('./dump');
const selftest = require('./selftest');
const { Tools } = require('./tools');

const PORTS = Array.from({ length: 20 }, (_, i) => 8765 + i);

/** Operationen, die das Panel ausführt – nur diese, keine freie Skriptausführung. */
function makeHandlers(ppro) {
  return {
    ping: async () => ({ pong: true, time: Date.now() }),
    info: async () => ({ exports: Object.keys(ppro).length }),
    introspect: async () => dump.introspect(ppro),
    selftest: async (args, emit) => selftest.selftest(ppro, args, emit),
    'project.dump': async () => dump.projectDump(ppro),
    'sequence.dump': async (args) => dump.sequenceDump(ppro, args),
    'plan.run': async (args, emit) => plan.runPlan(ppro, args.plan || args, emit),
    'media.swap': async (args, emit) => {
      const project = await ppro.Project.getActiveProject();
      return media.swapMedia(ppro, project, args, emit);
    },
    'media.refresh': async (args, emit) => {
      const project = await ppro.Project.getActiveProject();
      return media.swapMedia(ppro, project, { swaps: [], refresh: args.paths || [] }, emit);
    },
    'probe.bin': async () => dump.probeBin(ppro),
    'probe.place': async (args) => dump.probePlace(ppro, args),
    'probe.swap': async (args) => dump.probeSwap(ppro, args),
    'probe.items': async (args) => dump.probeItems(ppro, args),
    'project.save': async () => { const p = await ppro.Project.getActiveProject(); await p.save(); return { saved: true }; },
    'sequence.seek': async (args) => new Tools({ ppro, rpc: async () => { throw new Error('keine Anfrage nötig'); } }).seek(args),
  };
}

class Bridge {
  constructor({ ppro, WebSocketImpl, fetchImpl, hostInfo = {}, version = '0.6.2', log = () => {}, onStatus = () => {} }) {
    this.ppro = ppro;
    this.WS = WebSocketImpl;
    this.fetch = fetchImpl;
    this.hostInfo = hostInfo;
    this.version = version;
    this.log = log;
    this.onStatus = onStatus;
    this.handlers = makeHandlers(ppro);
    this.ws = null;
    this.stopped = false;
    this.busy = false;
    this.rpcPending = new Map();
    this.rpcNext = 1;
    this._tools = null;
  }

  /** Anfrage an den Server (Werkzeuge): Antwort kommt als `rpc_result`. */
  rpc(method, args = {}, timeoutMs = 120000) {
    return new Promise((resolve, reject) => {
      if (!this.ws) { reject(new Error('Nicht mit der Glorfindel-App verbunden.')); return; }
      const id = this.rpcNext++;
      const timer = setTimeout(() => { this.rpcPending.delete(id); reject(new Error('Die App hat nicht geantwortet (' + method + ').')); }, timeoutMs);
      this.rpcPending.set(id, { resolve, reject, timer });
      try { this.ws.send(JSON.stringify({ t: 'rpc', id, method, args })); } catch (e) { clearTimeout(timer); this.rpcPending.delete(id); reject(e); }
    });
  }

  failRpc(why) {
    for (const [id, p] of this.rpcPending) { clearTimeout(p.timer); p.reject(new Error(why)); this.rpcPending.delete(id); }
  }

  tools() {
    if (!this._tools) this._tools = new Tools({ ppro: this.ppro, rpc: (m, a) => this.rpc(m, a), log: this.log });
    return this._tools;
  }

  /** Werkzeug (Kurzbefehl) ausführen. Rückgabe immer als Daten: {ok, text, warnings, lines} oder {ok:false, error}. */
  async runTool(name, args = {}) {
    if (this.busy) return { ok: false, error: 'Premiere arbeitet noch an einem anderen Auftrag.' };
    this.busy = true;
    this.onStatus({ state: 'arbeitet', text: 'Werkzeug: ' + name });
    try {
      return { ok: true, ...(await this.tools().run(name, args)) };
    } catch (e) {
      return { ok: false, error: errText(e) };
    } finally {
      this.busy = false;
      this.onStatus({ state: this.ws ? 'verbunden' : 'getrennt', text: this.ws ? 'Verbunden mit Glorfindel' : 'Getrennt' });
    }
  }

  async findServer() {
    for (const port of PORTS) {
      try {
        const r = await this.fetch(`http://127.0.0.1:${port}/api/bridge/pairing`);
        if (r.ok) { const j = await r.json(); if (j && j.token) return { port, token: j.token }; }
      } catch (e) { /* nächster Port */ }
    }
    return null;
  }

  async projectInfo() {
    try {
      const p = await this.ppro.Project.getActiveProject();
      return p ? { name: p.name, path: p.path } : null;
    } catch (e) { return null; }
  }

  /** Verbinden und bei Abbruch immer wieder versuchen, bis `stop()`. */
  async run() {
    let wait = 1500;
    while (!this.stopped) {
      this.onStatus({ state: 'suche', text: 'Suche die Glorfindel-App …' });
      const srv = await this.findServer();
      if (!srv) { this.onStatus({ state: 'offline', text: 'App nicht gefunden – läuft „Glorfindel starten“?' }); await sleep(wait); wait = Math.min(wait * 1.5, 10000); continue; }
      wait = 1500;
      try { await this.session(srv); } catch (e) { this.log('Verbindung beendet: ' + errText(e)); }
      this.onStatus({ state: 'getrennt', text: 'Getrennt – verbinde neu …' });
      await sleep(1500);
    }
  }

  stop() { this.stopped = true; try { this.ws && this.ws.close(); } catch (e) { /* schon zu */ } }

  session({ port, token }) {
    return new Promise((resolve, reject) => {
      const ws = new this.WS(`ws://127.0.0.1:${port}/api/bridge/ws?token=${encodeURIComponent(token)}`);
      this.ws = ws;
      ws.onopen = async () => {
        const info = { premiere: this.hostInfo.version || '?', host: this.hostInfo.name || 'premierepro', panel: this.version, project: await this.projectInfo() };
        ws.send(JSON.stringify({ t: 'hello', info }));
      };
      ws.onmessage = (ev) => this.onMessage(ws, ev.data).catch((e) => this.log('Fehler: ' + errText(e)));
      ws.onerror = (e) => reject(new Error('WebSocket-Fehler'));
      ws.onclose = () => { this.failRpc('Verbindung zur App getrennt.'); resolve(); };
    });
  }

  async onMessage(ws, raw) {
    const msg = JSON.parse(raw);
    if (msg.t === 'welcome') {
      this.onStatus({ state: 'verbunden', text: 'Verbunden mit Glorfindel' });
      this.tools().config(true).catch((e) => this.log('Werkzeuge noch nicht bereit: ' + errText(e), 'warn'));
      return;
    }
    if (msg.t === 'rpc_result') {
      const p = this.rpcPending.get(msg.id);
      if (p) { clearTimeout(p.timer); this.rpcPending.delete(msg.id); if (msg.ok) p.resolve(msg.data); else p.reject(new Error(msg.error || 'Fehler in der App')); }
      return;
    }
    if (msg.t !== 'call') return;
    const send = (o) => ws.send(JSON.stringify(o));
    const fn = this.handlers[msg.op];
    if (!fn) { send({ t: 'result', id: msg.id, ok: false, error: 'Unbekannte Operation: ' + msg.op }); return; }
    if (this.busy && msg.op !== 'ping') { send({ t: 'result', id: msg.id, ok: false, error: 'Premiere arbeitet noch an einem anderen Auftrag.' }); return; }
    const emit = (name, data) => send({ t: 'event', id: msg.id, name, data });
    const isWork = msg.op !== 'ping';
    if (isWork) { this.busy = true; this.onStatus({ state: 'arbeitet', text: 'Arbeitet: ' + msg.op }); }
    try {
      const data = await fn(msg.args || {}, emit);
      send({ t: 'result', id: msg.id, ok: true, data });
    } catch (e) {
      send({ t: 'result', id: msg.id, ok: false, error: errText(e) });
    } finally {
      if (isWork) { this.busy = false; this.onStatus({ state: 'verbunden', text: 'Verbunden mit Glorfindel' }); }
    }
  }
}

module.exports = { Bridge, makeHandlers, PORTS };

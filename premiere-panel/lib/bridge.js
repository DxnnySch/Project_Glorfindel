// Verbindung zum Glorfindel-Server (WebSocket, 127.0.0.1) und Verteilung der Befehle. Abhängigkeiten werden hineingereicht (testbar).
'use strict';

const { errText, sleep } = require('./core');
const plan = require('./plan');
const media = require('./media');
const dump = require('./dump');
const selftest = require('./selftest');

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
    'project.save': async () => { const p = await ppro.Project.getActiveProject(); await p.save(); return { saved: true }; },
  };
}

class Bridge {
  constructor({ ppro, WebSocketImpl, fetchImpl, hostInfo = {}, version = '0.4.4', log = () => {}, onStatus = () => {} }) {
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
      ws.onclose = () => resolve();
    });
  }

  async onMessage(ws, raw) {
    const msg = JSON.parse(raw);
    if (msg.t === 'welcome') { this.onStatus({ state: 'verbunden', text: 'Verbunden mit Glorfindel' }); return; }
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

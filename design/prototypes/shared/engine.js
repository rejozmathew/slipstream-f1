/* Slipstream redesign prototypes — shared engine.
 *
 * Reconstructs session state from the compact recorded timelines in ../data
 * and derives the "story layer": classified events that drive motion,
 * callouts and the event feed.
 *
 * IMPORTANT (implementation note for the product): in Slipstream the
 * classification below belongs on the server (AnalyticsSnapshot), not in
 * React. It lives here only so the prototypes can demonstrate the behaviour.
 * Every rule is causal: it only uses facts available at the event time plus
 * a short confirmation window, so Live and Replay tell the same story.
 */
(function () {
  'use strict';
  const SS = (window.SS = window.SS || {});

  /* ------------------------------------------------------------ utils */
  const lapToSec = (s) => {
    if (s == null || s === '') return null;
    if (typeof s === 'number') return s;
    const m = /^(?:(\d+):)?(\d+(?:\.\d+)?)$/.exec(String(s).trim());
    return m ? (m[1] ? +m[1] * 60 : 0) + parseFloat(m[2]) : null;
  };
  const fmtLap = (sec) => {
    if (sec == null || !isFinite(sec)) return '—';
    const m = Math.floor(sec / 60);
    const s = sec - m * 60;
    return (m ? m + ':' + (s < 10 ? '0' : '') : '') + s.toFixed(3);
  };
  const fmtDelta = (sec, digits = 3) => (sec == null || !isFinite(sec) ? '—' : (sec < 0 ? '−' : '+') + Math.abs(sec).toFixed(digits));
  /** Parses a canonical gap/interval string ("+1.063", "+1 LAP", "LAP 1"). */
  const parseGap = (s) => {
    if (s == null || s === '') return { v: null, laps: 0, text: '' };
    const str = String(s).trim();
    const lap = /^\+?(\d+)\s*L(?:AP|APS)?$/i.exec(str);
    if (lap) return { v: null, laps: +lap[1], text: '+' + lap[1] + ' LAP' + (+lap[1] > 1 ? 'S' : '') };
    if (/^LAP\s*\d+/i.test(str)) return { v: 0, laps: 0, text: 'LEADER', leaderLap: true };
    const n = parseFloat(str.replace('+', ''));
    return isFinite(n) ? { v: n, laps: 0, text: '+' + n.toFixed(3) } : { v: null, laps: 0, text: str };
  };
  const clockToSec = (s) => {
    if (s == null) return null;
    const m = /^(\d+):(\d+):(\d+(?:\.\d+)?)$/.exec(String(s));
    return m ? +m[1] * 3600 + +m[2] * 60 + parseFloat(m[3]) : null;
  };
  const fmtClock = (sec, withHours) => {
    if (sec == null || !isFinite(sec)) return '—';
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return (h || withHours ? h + ':' + String(m).padStart(2, '0') : String(m).padStart(2, '0')) + ':' + String(s).padStart(2, '0');
  };
  const surname = (name) => (name ? name.split(' ').filter((w) => w === w.toUpperCase() && w.length > 1).join(' ') || name.split(' ').slice(-1)[0] : '');
  const titleCase = (s) => (s ? s.toLowerCase().replace(/(^|[\s-])\S/g, (c) => c.toUpperCase()) : '');
  SS.util = { lapToSec, fmtLap, fmtDelta, parseGap, clockToSec, fmtClock, surname, titleCase };

  const COMPOUND = { SOFT: 'S', MEDIUM: 'M', HARD: 'H', INTERMEDIATE: 'I', WET: 'W' };
  SS.compoundLetter = (c) => (c ? COMPOUND[c] || c[0] : null);

  /* ------------------------------------------------------------ status */
  /** Mirrors the server-authored display_status precedence (prototype copy). */
  SS.displayStatus = (s) => {
    const c = s.control_status, m = s.marshal_status;
    if (c === 'RED_FLAG') return 'RED_FLAG';
    if (c === 'SAFETY_CAR') return 'SAFETY_CAR';
    if (c === 'VSC') return 'VSC';
    if (c === 'VSC_ENDING') return 'VSC_ENDING';
    if (c === 'CHEQUERED') return 'CHEQUERED';
    if (s.status === 'FINISHED') return 'FINISHED';
    if (m === 'RED') return 'RED';
    if (m === 'YELLOW') return 'YELLOW';
    if (s.status === 'RUNNING') return 'GREEN';
    if (s.status === 'SCHEDULED') return 'WAITING';
    return null;
  };

  /* ------------------------------------------------------------ session */
  const QUALI_ADVANCE = { Q1: 16, Q2: 10, Q3: null, SQ1: 16, SQ2: 10, SQ3: null }; // 22-car policy (prototype)
  const PHASE_INDEX = { Q1: 0, Q2: 1, Q3: 2, SQ1: 0, SQ2: 1, SQ3: 2 };
  SS.QUALI_ADVANCE = QUALI_ADVANCE;
  SS.PHASE_INDEX = PHASE_INDEX;

  class Session {
    constructor(label) {
      const d = window.SLIPSTREAM_DATA && window.SLIPSTREAM_DATA[label];
      if (!d) throw new Error('Missing data ' + label);
      this.label = label;
      this.d = d;
      this.kind = d.kind; // race | qualifying | practice
      this.meta = d.meta;
      this.begin = d.begin;
      this.end = d.end;
      this.t0 = d.t0; // epoch seconds of t = 0
      this.drivers = {};
      for (const [num, [code, name, team, colour]] of Object.entries(d.drivers)) {
        this.drivers[num] = { num, code: code || num, name: name || code, surname: surname(name), team: team || '', colour: '#' + (colour || '77808f').replace('#', '') };
      }
      this.circuit = d.circuit || null;
      this.totalLaps = (d.initSession && d.initSession.total_laps) || null;
      this._index();
      this.events = SS.classify(this);
      this.moments = SS.moments(this);
    }

    /* Frames are per-second deltas. Build keyframes for fast random access. */
    _index() {
      const d = this.d;
      this.frames = d.frames; // [[sec, {num:{...}}]]
      this.sessionFrames = d.session; // [[sec, {...}]]
      this.keyEvery = 20;
      this.keyframes = [];
      const drivers = JSON.parse(JSON.stringify(d.init));
      for (const num of Object.keys(this.drivers)) drivers[num] = drivers[num] || {};
      const session = Object.assign({}, d.initSession);
      let fi = 0, si = 0;
      for (let sec = this.begin; sec <= this.end + this.keyEvery; sec += this.keyEvery) {
        while (fi < this.frames.length && this.frames[fi][0] < sec) {
          for (const [num, ch] of Object.entries(this.frames[fi][1])) Object.assign((drivers[num] = drivers[num] || {}), ch);
          fi++;
        }
        while (si < this.sessionFrames.length && this.sessionFrames[si][0] < sec) {
          Object.assign(session, this.sessionFrames[si][1]);
          si++;
        }
        this.keyframes.push({ sec, fi, si, drivers: JSON.parse(JSON.stringify(drivers)), session: Object.assign({}, session) });
      }
      // Per-driver mini-sector crossings for position interpolation.
      this.tp = {};
      for (const [sec, fr] of this.frames) {
        for (const [num, ch] of Object.entries(fr)) {
          if (ch.tp == null) continue;
          (this.tp[num] = this.tp[num] || []).push([sec, ch.tp]);
        }
      }
      // Mini-sector step (Hungaroring 1/22, Kuala Lumpur 1/20): the resolution of the position fact.
      const tpVals = [...new Set([].concat(...Object.values(this.tp).map((a) => a.map((x) => Math.round(x[1] * 1000)))))].sort((a, b) => a - b);
      let step = 1;
      for (let i = 1; i < tpVals.length; i++) if (tpVals[i] - tpVals[i - 1] > 0) step = Math.min(step, (tpVals[i] - tpVals[i - 1]) / 1000);
      this.tpStep = tpVals.length > 2 ? 1 / Math.round(1 / step) : null;
      // Unwrap 0..1 progress into a monotonic lap distance.
      for (const arr of Object.values(this.tp)) {
        let laps = 0, prev = null;
        for (const s of arr) {
          if (prev != null && s[1] + 0.5 < prev) laps++;
          prev = s[1];
          s.push(laps + s[1]);
        }
      }
      // Race control, weather, pits keyed by time.
      this.rc = d.rc.map(([t, category, flag, scope, sector, lap, driver, message]) => ({ t, category, flag, scope, sector, lap, driver, message }));
      this.weather = d.weather.map(([t, air, track, hum, rain, wind, dir, pressure]) => ({ t, air, track, hum, rain, wind, dir, pressure }));
      const stops = {};
      for (const [t, num, lap, prev, next, lane, ordinal] of d.pits) {
        const key = num + ':' + ordinal;
        const s = (stops[key] = stops[key] || { num, ordinal, t, lap });
        s.t = Math.min(s.t, t);
        if (lap != null) s.lap = lap;
        if (prev) s.prev = prev;
        if (next) s.next = next;
        if (lane != null) s.lane = lane;
      }
      this.stops = Object.values(stops).sort((a, b) => a.t - b.t);
      this.laps = d.laps;
    }

    keyframeFor(sec) {
      const i = Math.max(0, Math.min(this.keyframes.length - 1, Math.floor((sec - this.begin) / this.keyEvery)));
      return this.keyframes[i];
    }

    /** Full state at an integer second. Returns fresh objects. */
    snapshot(sec) {
      sec = Math.max(this.begin, Math.min(this.end, Math.floor(sec)));
      const kf = this.keyframeFor(sec);
      const drivers = JSON.parse(JSON.stringify(kf.drivers));
      const session = Object.assign({}, kf.session);
      let fi = kf.fi, si = kf.si;
      while (fi < this.frames.length && this.frames[fi][0] <= sec) {
        for (const [num, ch] of Object.entries(this.frames[fi][1])) Object.assign((drivers[num] = drivers[num] || {}), ch);
        fi++;
      }
      while (si < this.sessionFrames.length && this.sessionFrames[si][0] <= sec) {
        Object.assign(session, this.sessionFrames[si][1]);
        si++;
      }
      return { sec, drivers, session, fi, si };
    }

    order(state) {
      return Object.keys(this.drivers)
        .filter((n) => state.drivers[n])
        .sort((a, b) => (state.drivers[a].p || 99) - (state.drivers[b].p || 99) || +a - +b);
    }

    /** Clock remaining for timed sessions, extrapolated from source anchors. */
    clockAt(t) {
      let anchor = null;
      for (const [sec, ch] of this.sessionFrames) {
        if (sec > t) break;
        if (ch.session_clock != null) anchor = { sec, clock: clockToSec(ch.session_clock), running: ch.session_clock_running };
        else if (anchor && ch.session_clock_running != null) anchor.running = ch.session_clock_running;
      }
      if (!anchor && this.d.initSession.session_clock) anchor = { sec: this.begin, clock: clockToSec(this.d.initSession.session_clock), running: this.d.initSession.session_clock_running };
      if (!anchor || anchor.clock == null) return null;
      return anchor.running ? Math.max(0, anchor.clock - (t - anchor.sec)) : anchor.clock;
    }

    rcUntil(t) { return this.rc.filter((m) => m.t <= t); }
    weatherAt(t) { let w = null; for (const x of this.weather) { if (x.t > t) break; w = x; } return w || this.weather[0] || null; }
    lapAt(t) { let lap = (this.d.initSession && this.d.initSession.lap) || null; for (const [sec, l] of this.laps) { if (sec > t) break; lap = l; } return lap; }
    overtakeModeAt(t) {
      let on = null;
      for (const m of this.rc) { if (m.t > t) break; if (/OVERTAKE ENABLED/.test(m.message)) on = true; if (/OVERTAKE DISABLED/.test(m.message)) on = false; }
      return on;
    }

    /** Interpolated lap progress (0..1) for map markers.
     *  replay: between known mini-sector crossings (both ends recorded).
     *  live:   capped dead-reckoning from the last crossing (never past the next boundary). */
    progressAt(num, t, mode) {
      const arr = this.tp[num];
      if (!arr || !arr.length) return null;
      let lo = 0, hi = arr.length - 1;
      if (t < arr[0][0]) return arr[0][1];
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (arr[mid][0] <= t) lo = mid; else hi = mid - 1; }
      const a = arr[lo], b = arr[lo + 1];
      if (!b) return a[1];
      const span = b[0] - a[0];
      if (span > 40) return a[1]; // long gap (pit, stopped): hold the fact
      if (mode === 'live') {
        const step = this.tpStep || 1 / 20;
        const rate = (b[2] - a[2]) / Math.max(1, span); // prototype stand-in for average lap rate
        const est = Math.min(a[2] + step * 0.98, a[2] + rate * (t - a[0]));
        return est - Math.floor(est);
      }
      const f = Math.max(0, Math.min(1, (t - a[0]) / span));
      const v = a[2] + (b[2] - a[2]) * f;
      return v - Math.floor(v);
    }

    eventsBetween(t1, t2) { return this.events.filter((e) => e.t > t1 && e.t <= t2); }

    /** Completed laps for one driver: [{ t, lap, time }] from the last-lap field (lap = laps completed). */
    lapHistory(num) {
      this._lapHist = this._lapHist || {};
      if (this._lapHist[num]) return this._lapHist[num];
      const out = [];
      let lp = null, last = null;
      for (const [sec, fr] of this.frames) {
        const ch = fr[num];
        if (!ch) continue;
        if (ch.lp != null) lp = ch.lp;
        if (ch.l != null && ch.l !== last) {
          last = ch.l;
          const v = SS.util.lapToSec(ch.l);
          if (v != null && lp != null) out.push({ t: sec, lap: lp, time: v });
        }
      }
      return (this._lapHist[num] = out);
    }
  }
  SS.Session = Session;

  /* ------------------------------------------------------------ cursor */
  /** Incremental cursor. Small forward steps apply deltas (motion allowed);
   *  anything else is a jump (seek / reset) and must render without motion. */
  class Cursor {
    constructor(session) { this.s = session; this.reset(session.begin); }
    reset(t) {
      this.t = t;
      this.state = this.s.snapshot(Math.floor(t));
      this.sec = this.state.sec;
    }
    advanceTo(t) {
      const s = this.s;
      t = Math.max(s.begin, Math.min(s.end, t));
      const target = Math.floor(t);
      if (target < this.sec || target - this.sec > 8) {
        this.reset(t);
        return { jumped: true, changed: true };
      }
      let changed = false;
      const st = this.state;
      while (st.fi < s.frames.length && s.frames[st.fi][0] <= target) {
        for (const [num, ch] of Object.entries(s.frames[st.fi][1])) Object.assign((st.drivers[num] = st.drivers[num] || {}), ch);
        st.fi++;
        changed = true;
      }
      while (st.si < s.sessionFrames.length && s.sessionFrames[st.si][0] <= target) {
        Object.assign(st.session, s.sessionFrames[st.si][1]);
        st.si++;
        changed = true;
      }
      this.t = t;
      this.sec = st.sec = target;
      return { jumped: false, changed };
    }
  }
  SS.Cursor = Cursor;

  /* ------------------------------------------------------------ story */
  const PRIORITY = { HIDDEN: 0, FEED: 1, HIGHLIGHT: 2, TAKEOVER: 3 };
  SS.PRIORITY = PRIORITY;
  const carRx = /CAR (\d+) \(([A-Z]{3})\)/;

  /** Derive classified story events. See header note: server-side in product. */
  SS.classify = function classify(session) {
    const ev = [];
    let id = 0;
    const push = (e) => { e.id = ++id; ev.push(e); return e; };
    const D = session.drivers;
    const code = (n) => (D[n] ? D[n].code : n);
    const kind = session.kind;
    const cursor = new Cursor(session);
    const lapAt = (t) => session.lapAt(t);
    let prevOrder = null, prevState = null;
    const pitEntryAt = {}; // num -> sec when IN_PIT began
    const lastPitCount = {};
    const exitPending = {}; // num -> sec of pit exit (await rejoin position)
    let bestOverall = null; // race fastest lap / practice session best
    let prevStatus = null, prevControl = null, prevMarshal = null, prevPhase = null;
    let chequeredAt = null;
    const stoppedSeen = {};
    const pendingPasses = []; // awaiting confirmation
    const qualiBest = {}; // num -> best in current phase
    let lastCutSet = null; let lastTimed = null;
    const posHistory = {}; // num -> [[sec, p]] (recent)
    const cutAnnounced = {}; // num -> sec
    let settleAt = null; // qualifying: classification settles after the flag
    let settledPhase = null;
    const phaseRan = {};
    const initialPhase = session.d.initSession && session.d.initSession.qualifying_phase;
    // A live recording joined mid-session starts with a catch-up burst; it is not news.
    const catchUpUntil = session.kind === 'race' ? session.begin : session.begin + 45;

    const isPit = (st) => st && (st.ac === 'IN_PIT' || st.sc === 'IN_PIT');
    const isOut = (st) => st && (st.sc === 'STOPPED' || st.sc === 'RETIRED_INDICATED' || ['DNF', 'DNS', 'DSQ', 'RETIRED'].includes(st.cl));

    for (let sec = session.begin; sec <= session.end; sec++) {
      cursor.advanceTo(sec);
      const st = cursor.state;
      const S = st.session;
      const drivers = st.drivers;
      const order = session.order(st);
      const lap = lapAt(sec);
      const running = S.status === 'RUNNING';

      /* -- flags / session status */
      const status = SS.displayStatus(S);
      if (status !== prevStatus && prevStatus !== undefined) {
        if (status && prevStatus !== null || (status && sec > session.begin)) {
          const escalate = ['YELLOW', 'VSC', 'SAFETY_CAR', 'RED', 'RED_FLAG', 'CHEQUERED'].includes(status);
          const pr = ['VSC', 'SAFETY_CAR', 'RED_FLAG', 'RED', 'CHEQUERED'].includes(status) ? PRIORITY.TAKEOVER : escalate ? PRIORITY.HIGHLIGHT : PRIORITY.FEED;
          if (sec > session.begin) push({ t: sec, lap, type: 'FLAG', status, from: prevStatus, priority: pr, drivers: [] });
        }
        prevStatus = status;
      }
      if (S.status === 'FINISHED' && chequeredAt == null && running === false && prevControl != null) chequeredAt = sec;
      if (S.control_status === 'CHEQUERED' && chequeredAt == null) chequeredAt = sec;
      prevControl = S.control_status;
      prevMarshal = S.marshal_status;

      /* -- qualifying phase changes */
      if (kind === 'qualifying' && S.qualifying_phase !== prevPhase) {
        if (prevPhase != null && sec > session.begin) push({ t: sec, lap: null, type: 'PHASE', phase: S.qualifying_phase, from: prevPhase, priority: PRIORITY.TAKEOVER, drivers: [] });
        prevPhase = S.qualifying_phase;
        for (const k of Object.keys(qualiBest)) delete qualiBest[k];
      }

      /* -- pit entry / exit, stopped */
      for (const n of Object.keys(D)) {
        const cur = drivers[n], prev = prevState && prevState[n];
        if (!cur) continue;
        if (prev && !isPit(prev) && isPit(cur) && sec > session.begin + 2) {
          pitEntryAt[n] = sec;
          if (kind === 'race' && running) push({ t: sec, lap, type: 'PIT_IN', drivers: [n], pos: prev.p, priority: prev.p <= 6 ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
        }
        if (prev && isPit(prev) && !isPit(cur) && kind === 'race') exitPending[n] = sec;
        if (exitPending[n] != null && sec - exitPending[n] >= 4) {
          const stop = session.stops.find((s) => s.num === n && Math.abs(s.t - exitPending[n]) < 90);
          push({ t: sec, lap, type: 'PIT_OUT', drivers: [n], pos: cur.p, compound: stop ? stop.next : cur.c, from: stop ? stop.prev : null, lane: stop ? stop.lane : null, priority: cur.p <= 6 ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
          delete exitPending[n];
        }
        const ph = (posHistory[n] = posHistory[n] || []);
        if (cur.p && (!ph.length || ph[ph.length - 1][1] !== cur.p)) ph.push([sec, cur.p]);
        while (ph.length > 1 && ph[1][0] < sec - 150) ph.shift();
        if (isOut(cur) && !stoppedSeen[n] && sec > session.begin + 2 && (kind === 'race' ? true : running)) {
          stoppedSeen[n] = true;
          const peak = ph.reduce((m, x) => Math.min(m, x[1]), 99);
          const pos = kind === 'race' ? Math.min(peak, prev ? prev.p || 99 : 99) : prev ? prev.p : cur.p;
          const top = pos <= 10;
          push({ t: sec, lap, type: 'STOPPED', drivers: [n], pos, posNow: prev ? prev.p : cur.p, condition: cur.cl || cur.sc, priority: top ? PRIORITY.TAKEOVER : PRIORITY.HIGHLIGHT });
        }
        if (!isOut(cur) && stoppedSeen[n] && cur.sc === 'RUNNING') delete stoppedSeen[n];
        lastPitCount[n] = cur.pc;
      }

      /* -- best laps */
      if (kind === 'race') {
        for (const n of Object.keys(D)) {
          const b = lapToSec(drivers[n] && drivers[n].b);
          if (b != null && (bestOverall == null || b < bestOverall.time - 1e-6) && lap >= 2) {
            const was = bestOverall;
            bestOverall = { num: n, time: b };
            const late = session.totalLaps && lap >= session.totalLaps - 10;
            if (was) push({ t: sec, lap, type: 'FASTEST_LAP', drivers: [n], time: b, priority: late ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
          } else if (b != null && bestOverall == null) bestOverall = { num: n, time: b };
        }
      } else if (kind === 'practice') {
        for (const n of Object.keys(D)) {
          const b = lapToSec(drivers[n] && drivers[n].b);
          const pb = prevState && prevState[n] ? lapToSec(prevState[n].b) : null;
          if (b != null && pb != null && b < pb - 1e-6 && sec > session.begin + 1) {
            const isBest = bestOverall == null || b < bestOverall.time - 1e-6;
            const prevPos = prevState[n].p;
            if (isBest) { const was = bestOverall; bestOverall = { num: n, time: b }; push({ t: sec, lap: null, type: 'SESSION_BEST', drivers: [n], time: b, prevHolder: was && was.num, delta: was ? b - was.time : null, priority: PRIORITY.TAKEOVER }); }
            else push({ t: sec, lap: null, type: 'IMPROVEMENT', drivers: [n], time: b, from: prevPos, priority: PRIORITY.FEED });
          } else if (b != null && (bestOverall == null || b < bestOverall.time - 1e-6) && sec <= session.begin + 1) bestOverall = { num: n, time: b };
        }
      } else if (kind === 'qualifying') {
        const pi = PHASE_INDEX[S.qualifying_phase];
        for (const n of Object.keys(D)) {
          const qr = drivers[n] && drivers[n].qr;
          const v = qr && pi != null ? qr[pi] : null;
          const pqr = prevState && prevState[n] && prevState[n].qr;
          const pv = pqr && pi != null ? pqr[pi] : null;
          if (v != null && (pv == null || v < pv - 1e-6) && sec > session.begin + 1 && prevPhase === S.qualifying_phase) {
            // Position effect is measured a moment later (timing updates land in sequence).
            const times = Object.keys(D).map((k) => [k, drivers[k] && drivers[k].qr && drivers[k].qr[pi]]).filter((x) => x[1] != null && x[0] !== n);
            const better = times.filter((x) => x[1] < v).length;
            const bestRow = times.reduce((m, x) => (m == null || x[1] < m[1] ? x : m), null);
            const best = bestRow ? bestRow[1] : null;
            const newPos = better + 1;
            push({ t: sec, lap: null, type: newPos === 1 ? (S.qualifying_phase === 'Q3' || S.qualifying_phase === 'SQ3' ? 'PROVISIONAL_POLE' : 'SEGMENT_P1') : 'IMPROVEMENT', drivers: [n], time: v, prevTime: pv, pos: newPos, from: prevState[n].p, delta: best != null ? v - best : null, rival: bestRow ? bestRow[0] : null, phase: S.qualifying_phase, priority: newPos === 1 ? PRIORITY.TAKEOVER : newPos <= 3 ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
          }
        }
      }

      /* -- order changes */
      if (prevOrder && order.join() !== prevOrder.join() && sec > Math.max(session.begin + 1, catchUpUntil)) {
        const before = {}, after = {};
        prevOrder.forEach((n, i) => (before[n] = i));
        order.forEach((n, i) => (after[n] = i));
        const passes = [];
        for (const a of order) {
          if (after[a] >= before[a]) continue;
          for (const b of order) {
            if (a === b) continue;
            if (before[b] < before[a] && after[b] > after[a]) passes.push([a, b]);
          }
        }
        const groupedLoss = {};
        for (const [a, b] of passes) {
          const A = drivers[a], B = drivers[b];
          let cause = 'ON_TRACK';
          if (kind !== 'race') cause = kind === 'qualifying' ? 'LAP_TIME' : 'LAP_TIME';
          else if (!running && chequeredAt != null) cause = 'CLASSIFICATION';
          else if (chequeredAt != null && sec >= chequeredAt) cause = 'CLASSIFICATION';
          else if (isOut(B)) cause = 'STOPPED';
          else if (isPit(B) || (pitEntryAt[b] != null && sec - pitEntryAt[b] < 45)) cause = 'PIT';
          else if (isPit(A)) cause = 'PIT';
          else if (lap != null && lap <= 1) cause = 'START';
          else if (['VSC', 'SAFETY_CAR', 'VSC_ENDING', 'RED_FLAG'].includes(S.control_status)) cause = 'NEUTRALISED';
          if (cause === 'ON_TRACK') pendingPasses.push({ t: sec, a, b, lap, posA: after[a] + 1 });
          else if (cause === 'PIT' || cause === 'STOPPED' || cause === 'CLASSIFICATION') {
            const key = cause + ':' + b;
            (groupedLoss[key] = groupedLoss[key] || { cause, b, gainers: [] }).gainers.push(a);
          }
        }
        for (const g of Object.values(groupedLoss)) {
          if (g.cause === 'CLASSIFICATION') {
            push({ t: sec, lap, type: 'CLASSIFICATION', drivers: [g.b, ...g.gainers], loser: g.b, from: before[g.b] + 1, to: after[g.b] + 1, priority: PRIORITY.HIGHLIGHT });
          }
        }
        // Lead change bookkeeping (cause resolved after confirmation below)
        if (order[0] !== prevOrder[0] && kind === 'race' && sec > session.begin + 5) {
          const nl = order[0], ol = prevOrder[0];
          const A = drivers[nl], B = drivers[ol];
          let cause = isPit(B) || (pitEntryAt[ol] != null && sec - pitEntryAt[ol] < 45) ? 'PIT' : isOut(B) ? 'STOPPED' : chequeredAt != null ? 'CLASSIFICATION' : lap <= 1 ? 'START' : 'ON_TRACK';
          push({ t: sec, lap, type: 'LEAD_CHANGE', drivers: [nl, ol], cause, priority: PRIORITY.TAKEOVER, confirm: cause === 'ON_TRACK' ? sec + 5 : sec });
        }
        // Qualifying cut line: only timed drivers, active while running and until the result settles.
        if (kind === 'qualifying' && (running || (settleAt != null && sec <= settleAt))) {
          const adv = QUALI_ADVANCE[S.qualifying_phase];
          const pi = PHASE_INDEX[S.qualifying_phase];
          if (adv) {
            const active = order.filter((n) => !(drivers[n] && drivers[n].qe));
            const below = new Set(active.slice(adv).filter((n) => drivers[n] && drivers[n].qr && drivers[n].qr[pi] != null));
            const timedNow = new Set(active.filter((n) => drivers[n] && drivers[n].qr && drivers[n].qr[pi] != null));
            const clock = session.clockAt(sec);
            const late = !running || (clock != null && clock <= 240);
            if (lastCutSet) {
              for (const n of below) {
                if (lastCutSet.has(n) || (cutAnnounced[n] && sec - cutAnnounced[n] < 45)) continue;
                cutAnnounced[n] = sec;
                push({ t: sec, lap: null, type: 'INTO_DROP_ZONE', drivers: [n], pos: active.indexOf(n) + 1, phase: S.qualifying_phase, afterFlag: !running, first: !!lastTimed && !lastTimed.has(n), priority: late ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
              }
              for (const n of lastCutSet) if (!below.has(n) && active.indexOf(n) >= 0 && active.indexOf(n) < adv && late) push({ t: sec, lap: null, type: 'OUT_OF_DROP_ZONE', drivers: [n], pos: active.indexOf(n) + 1, phase: S.qualifying_phase, afterFlag: !running, priority: PRIORITY.HIGHLIGHT });
            }
            lastCutSet = below;
            lastTimed = timedNow;
          }
        }
      }
      if (kind === 'qualifying') {
        // A segment result settles once every car still on a lap has finished it (bounded at 150 s).
        if (running) { settleAt = null; settledPhase = null; phaseRan[S.qualifying_phase] = true; }
        else if ((S.control_status === 'CHEQUERED' || S.status === 'FINISHED') && settledPhase !== S.qualifying_phase && sec > session.begin + 4
          && (phaseRan[S.qualifying_phase] || (sec < session.begin + 240 && (S.qualifying_phase === initialPhase || !initialPhase)))) {
          if (settleAt == null) settleAt = sec + 150;
          const onTrack = Object.keys(D).filter((n) => drivers[n] && !drivers[n].qe && drivers[n].ac === 'ON_TRACK');
          if (onTrack.length === 0 && settleAt > sec + 3) settleAt = sec + 3;
          if (sec >= settleAt) {
            const phase = S.qualifying_phase;
            const adv = QUALI_ADVANCE[phase];
            const active = order.filter((n) => drivers[n] && !drivers[n].qe);
            if (adv) push({ t: sec, lap: null, type: 'ELIMINATED', phase, drivers: active.slice(adv), priority: PRIORITY.TAKEOVER });
            else push({ t: sec, lap: null, type: 'POLE', phase, drivers: [order[0]], time: drivers[order[0]] && drivers[order[0]].qr && drivers[order[0]].qr[2], top: order.slice(0, 10), priority: PRIORITY.TAKEOVER });
            settledPhase = phase;
            settleAt = null;
          }
        }
        if (!running && settleAt == null) lastCutSet = null;
      }

      /* -- confirm pending on-track passes (≤5 s window) */
      for (let i = pendingPasses.length - 1; i >= 0; i--) {
        const p = pendingPasses[i];
        if (sec - p.t < 5) continue;
        pendingPasses.splice(i, 1);
        const ia = order.indexOf(p.a), ib = order.indexOf(p.b);
        const held = ia >= 0 && ib >= 0 && ia < ib;
        const pr = p.posA <= 3 ? PRIORITY.HIGHLIGHT : p.posA <= 10 ? PRIORITY.HIGHLIGHT : PRIORITY.FEED;
        push({ t: p.t, confirmedAt: sec, lap: p.lap, type: held ? 'PASS' : 'CONTESTED', drivers: [p.a, p.b], pos: p.posA, priority: held ? (p.lap <= 1 ? PRIORITY.FEED : pr) : PRIORITY.HIDDEN });
      }

      prevOrder = order;
      prevState = JSON.parse(JSON.stringify(drivers));
    }

    /* -- pit-driven position losses as grouped events */
    for (const stop of session.stops) {
      const n = stop.num;
      const entry = ev.find((e) => e.type === 'PIT_IN' && e.drivers[0] === n && Math.abs(e.t - stop.t) < 80);
      const exit = ev.find((e) => e.type === 'PIT_OUT' && e.drivers[0] === n && e.t >= (entry ? entry.t : stop.t - 40) && e.t - stop.t < 120);
      if (entry) Object.assign(entry, { compound: stop.next, from: stop.prev, lane: stop.lane, rejoin: exit ? exit.pos : null, rejoinAt: exit ? exit.t : null, stopNo: stop.ordinal });
    }

    /* -- race control derived events */
    for (const m of session.rc) {
      const msg = m.message || '';
      const car = carRx.exec(msg);
      const lapNo = m.lap;
      if (/TIME PENALTY|DRIVE THROUGH|STOP AND GO/.test(msg) && /FIA STEWARDS/.test(msg) && !/SERVED/.test(msg)) {
        const secs = /(\d+) SECOND/.exec(msg);
        push({ t: m.t, lap: lapNo, type: 'PENALTY', drivers: car ? [car[1]] : [], penalty: secs ? '+' + secs[1] + 's' : 'PENALTY', reason: (msg.split(' - ')[1] || '').replace(/\s*\(.*$/, ''), priority: PRIORITY.HIGHLIGHT, message: msg });
      } else if (/DELETED/.test(msg) && car) {
        // Position effect of a deleted lap (timed sessions): compare just before and shortly after.
        let from = null, to = null;
        if (kind !== 'race' && m.t >= session.begin && m.t <= session.end) {
          const a = session.snapshot(Math.floor(m.t) - 1), b = session.snapshot(Math.min(session.end, Math.floor(m.t) + 12));
          from = a.drivers[car[1]] && a.drivers[car[1]].p; to = b.drivers[car[1]] && b.drivers[car[1]].p;
        }
        const matters = kind === 'qualifying' ? true : kind === 'practice' ? from != null && from <= 5 : false;
        push({ t: m.t, lap: lapNo, type: 'LAP_DELETED', drivers: [car[1]], reason: /TRACK LIMITS/.test(msg) ? 'Track limits' : 'Deleted', from, to, message: msg, priority: matters && to > from ? PRIORITY.HIGHLIGHT : PRIORITY.FEED });
      } else if (/INVESTIGAT|NOTED/.test(msg)) {
        push({ t: m.t, lap: lapNo, type: 'INVESTIGATION', drivers: [...msg.matchAll(/CARS? (\d+) \(/g)].map((x) => x[1]), message: msg, priority: PRIORITY.FEED });
      } else if (/OVERTAKE (ENABLED|DISABLED)/.test(msg)) {
        push({ t: m.t, lap: lapNo, type: 'OVERTAKE_MODE', on: /ENABLED/.test(msg), drivers: [], message: msg, priority: PRIORITY.FEED });
      } else if (/YELLOW IN TRACK SECTOR|DOUBLE YELLOW/.test(msg)) {
        push({ t: m.t, lap: lapNo, type: 'SECTOR_FLAG', flag: m.flag, sector: m.sector, drivers: [], message: msg, priority: PRIORITY.FEED });
      } else if (/MARSHALS ON TRACK|INCIDENT|BLACK AND WHITE/.test(msg)) {
        push({ t: m.t, lap: lapNo, type: 'NOTICE', drivers: car ? [car[1]] : [], message: msg, priority: PRIORITY.FEED });
      } else if (m.flag === 'BLUE') {
        push({ t: m.t, lap: lapNo, type: 'BLUE_FLAG', drivers: car ? [car[1]] : [], message: msg, priority: PRIORITY.HIDDEN });
      }
    }

    /* -- race winner */
    if (kind === 'race' && chequeredAt != null) {
      const snap = session.snapshot(Math.min(session.end, chequeredAt + 30));
      const order = session.order(snap);
      push({ t: chequeredAt + 1, lap: session.lapAt(chequeredAt), type: 'WINNER', drivers: order.slice(0, 3), priority: PRIORITY.TAKEOVER });
    }
    if (kind === 'practice') {
      const fin = ev.find((e) => e.type === 'FLAG' && e.status === 'FINISHED');
      if (fin) {
        const snap = session.snapshot(Math.min(session.end, fin.t + 60));
        const order = session.order(snap);
        push({ t: fin.t + 2, lap: null, type: 'SESSION_END', drivers: order.slice(0, 3), priority: PRIORITY.TAKEOVER });
      }
    }

    /* -- lead-change confirmation: drop ON_TRACK lead changes that did not hold */
    for (const e of ev) {
      if (e.type === 'PASS' && e.pos === 1 && ev.some((l) => l.type === 'LEAD_CHANGE' && l.drivers[0] === e.drivers[0] && l.drivers[1] === e.drivers[1] && Math.abs(l.t - e.t) <= 6)) e.priority = PRIORITY.HIDDEN;
    }
    const out = [];
    for (const e of ev) {
      if (e.type === 'LEAD_CHANGE' && e.cause === 'ON_TRACK') {
        const pass = ev.find((p) => (p.type === 'PASS' || p.type === 'CONTESTED') && p.t === e.t && p.drivers[0] === e.drivers[0] && p.drivers[1] === e.drivers[1]);
        if (pass && pass.type === 'CONTESTED') continue;
        e.t = e.confirm; // story callout lands after confirmation
      }
      out.push(e);
    }
    // Battles: pairs within 1.0 s over consecutive completed laps (race only).
    if (kind === 'race') SS.detectBattles(session, out, push);
    out.sort((a, b) => a.t - b.t || b.priority - a.priority);
    return out;
  };

  /** Sustained battles: adjacent pair under 1.0 s at ≥3 consecutive lap completions. */
  SS.detectBattles = function (session, out) {
    const runs = {};
    for (const [sec, lap] of session.laps) {
      if (lap < 3) continue;
      const snap = session.snapshot(sec + 3);
      const order = session.order(snap);
      const seen = new Set();
      for (let i = 1; i < order.length; i++) {
        const n = order[i], prev = order[i - 1];
        const d = snap.drivers[n];
        const iv = parseGap(d && d.i).v;
        if (iv == null || iv > 1.0 || d.ac === 'IN_PIT') continue;
        const key = prev + '>' + n;
        seen.add(key);
        const r = (runs[key] = runs[key] || { count: 0, started: sec, lapStart: lap, min: 9 });
        r.count++;
        r.min = Math.min(r.min, iv);
        if (r.count === 3) out.push({ id: 100000 + out.length, t: sec + 3, lap, type: 'BATTLE', drivers: [n, prev], pos: i + 1, interval: iv, priority: i <= 6 ? SS.PRIORITY.HIGHLIGHT : SS.PRIORITY.FEED });
      }
      for (const key of Object.keys(runs)) if (!seen.has(key)) delete runs[key];
    }
  };

  /** Bookmarks for review: real moments found in the data. */
  SS.moments = function (session) {
    const m = [];
    const ev = session.events;
    const first = (pred) => ev.find(pred);
    if (session.kind === 'race') {
      m.push({ t: -25, label: 'Lights out', note: 'Lap 1 reshuffle' });
      const pit = first((e) => e.type === 'PIT_IN' && e.pos <= 6);
      if (pit) m.push({ t: pit.t - 20, label: 'First pit cycle', note: 'Lap ' + pit.lap + ' · order changes caused by stops' });
      const leadPass = ev.filter((e) => e.type === 'LEAD_CHANGE' && e.cause === 'ON_TRACK' && e.lap > 3);
      if (leadPass.length) m.push({ t: leadPass[leadPass.length - 1].t - 40, label: 'Pass for the lead', note: 'Lap ' + leadPass[leadPass.length - 1].lap });
      const stop = first((e) => e.type === 'STOPPED' && e.pos <= 5);
      if (stop) m.push({ t: stop.t - 110, label: 'Leader drops back · VSC', note: 'Lap ' + stop.lap });
      const win = first((e) => e.type === 'WINNER');
      if (win) m.push({ t: win.t - 50, label: 'Chequered flag', note: 'Final laps, penalties, result' });
    } else if (session.kind === 'qualifying') {
      m.push({ t: session.begin + 2, label: 'Q1 result', note: 'Between segments' });
      const q2 = first((e) => e.type === 'FLAG' && e.status === 'GREEN');
      if (q2) m.push({ t: q2.t - 8, label: 'Q2 begins', note: 'Clock starts' });
      const q2end = first((e) => e.type === 'FLAG' && e.status === 'CHEQUERED');
      if (q2end) m.push({ t: q2end.t - 100, label: 'Q2 final runs', note: 'Drop zone pressure' });
      const pole = ev.filter((e) => e.type === 'PROVISIONAL_POLE');
      if (pole.length) m.push({ t: pole[pole.length - 1].t - 30, label: 'Provisional pole', note: 'Q3 last runs' });
      const fin = first((e) => e.type === 'POLE');
      if (fin) m.push({ t: fin.t - 5, label: 'Final grid', note: 'Q3 complete' });
    } else {
      const left = session.clockAt(session.begin + 2);
      m.push({ t: session.begin + 2, label: 'Joined mid-session', note: left != null ? 'Recording starts with ' + SS.util.fmtClock(left) + ' left' : 'Recording starts mid-session' });
      const best = ev.filter((e) => e.type === 'SESSION_BEST');
      if (best.length) m.push({ t: best[0].t - 15, label: 'New fastest lap', note: '' });
      const vsc = first((e) => e.type === 'FLAG' && e.status === 'VSC');
      if (vsc) m.push({ t: vsc.t - 30, label: 'Yellow → VSC', note: 'Flag transitions' });
      const end = first((e) => e.type === 'SESSION_END');
      if (end) m.push({ t: end.t - 20, label: 'Session end', note: '' });
    }
    return m.filter((x) => x.t >= session.begin && x.t <= session.end);
  };

  /* ------------------------------------------------------------ text */
  /** Human copy for an event (title + detail). Shared by feed, ticker, takeovers. */
  SS.describe = function (session, e, now) {
    if (now == null) now = Infinity;
    const D = session.drivers;
    const c = (n) => (D[n] ? D[n].code : n);
    const nm = (n) => (D[n] ? SS.util.titleCase(D[n].surname) : n);
    const P = (p) => (p ? 'P' + p : '');
    const cmp = (x) => ({ SOFT: 'Soft', MEDIUM: 'Medium', HARD: 'Hard', INTERMEDIATE: 'Inter', WET: 'Wet' }[x] || x || '');
    switch (e.type) {
      case 'PASS': return { tag: 'PASS', title: c(e.drivers[0]) + ' passes ' + c(e.drivers[1]), detail: 'for ' + P(e.pos) + (e.lap ? ' · lap ' + e.lap : ''), tone: 'gain' };
      case 'LEAD_CHANGE':
        if (e.cause === 'PIT') return { tag: 'LEAD', title: c(e.drivers[0]) + ' leads', detail: c(e.drivers[1]) + ' pitted from the lead', tone: 'pit' };
        if (e.cause === 'STOPPED') return { tag: 'LEAD', title: c(e.drivers[0]) + ' leads', detail: c(e.drivers[1]) + ' stopped', tone: 'out' };
        if (e.cause === 'START') return { tag: 'LEAD', title: c(e.drivers[0]) + ' takes the lead', detail: 'at the start', tone: 'gain' };
        if (e.cause === 'CLASSIFICATION') return { tag: 'LEAD', title: c(e.drivers[0]) + ' classified first', detail: 'classification change', tone: 'amber' };
        return { tag: 'NEW LEADER', title: nm(e.drivers[0]) + ' passes ' + nm(e.drivers[1]), detail: 'on track for the lead · lap ' + e.lap, tone: 'gain' };
      case 'PIT_IN': {
        const known = e.rejoinAt != null && now >= e.rejoinAt; // only say what is known at this moment
        return { tag: 'PIT', title: c(e.drivers[0]) + ' pits from ' + P(e.pos), detail: (e.from ? cmp(e.from) + ' → ' : '') + (e.compound && known ? cmp(e.compound) : known ? 'tyres' : 'in the pit lane') + (e.lane && known ? ' · lane ' + e.lane.toFixed(1) + 's' : '') + (known && e.rejoin ? ' · rejoins ' + P(e.rejoin) : ''), tone: 'pit' };
      }
      case 'PIT_OUT': return { tag: 'OUT', title: c(e.drivers[0]) + ' rejoins ' + P(e.pos), detail: e.compound ? 'on ' + cmp(e.compound) + 's' : '', tone: 'pit' };
      case 'STOPPED': return { tag: e.condition === 'STOPPED' ? 'STOPPED' : 'OUT', title: c(e.drivers[0]) + (e.condition === 'STOPPED' ? ' stopped' : ' out'), detail: (e.pos && e.posNow && e.pos < e.posNow ? 'was running ' + P(e.pos) + ' · dropped to ' + P(e.posNow) : 'was ' + P(e.pos)) + (e.lap ? ' · lap ' + e.lap : ''), tone: 'out' };
      case 'FASTEST_LAP': return { tag: 'FASTEST', title: c(e.drivers[0]) + ' fastest lap', detail: SS.util.fmtLap(e.time), tone: 'purple' };
      case 'SESSION_BEST': return { tag: 'P1', title: c(e.drivers[0]) + ' goes fastest', detail: SS.util.fmtLap(e.time) + (e.delta != null ? ' · ' + SS.util.fmtDelta(e.delta) : ''), tone: 'purple' };
      case 'IMPROVEMENT': return { tag: 'IMPROVES', title: c(e.drivers[0]) + ' improves to ' + P(e.pos), detail: SS.util.fmtLap(e.time) + (e.delta != null && e.pos > 1 ? ' · ' + SS.util.fmtDelta(e.delta) : ''), tone: 'green' };
      case 'SEGMENT_P1': return { tag: e.phase + ' P1', title: c(e.drivers[0]) + ' fastest in ' + e.phase, detail: SS.util.fmtLap(e.time) + (e.delta != null && e.rival ? ' · ' + Math.abs(e.delta).toFixed(3) + ' clear of ' + c(e.rival) : ''), tone: 'purple' };
      case 'PROVISIONAL_POLE': return { tag: 'PROVISIONAL POLE', title: nm(e.drivers[0]), detail: SS.util.fmtLap(e.time) + (e.delta != null && e.rival ? ' · ' + Math.abs(e.delta).toFixed(3) + ' clear of ' + c(e.rival) : ''), tone: 'purple' };
      case 'POLE': return { tag: 'POLE POSITION', title: nm(e.drivers[0]), detail: SS.util.fmtLap(e.time), tone: 'purple' };
      case 'INTO_DROP_ZONE': return e.first
        ? { tag: 'DROP ZONE', title: c(e.drivers[0]) + ' sets ' + P(e.pos), detail: 'first time this segment · in the drop zone' + (e.afterFlag ? ' · after the flag' : ''), tone: 'loss' }
        : { tag: 'DROP ZONE', title: c(e.drivers[0]) + ' into the drop zone', detail: 'now ' + P(e.pos) + (e.afterFlag ? ' · after the flag' : ''), tone: 'loss' };
      case 'OUT_OF_DROP_ZONE': return { tag: 'SAFE', title: c(e.drivers[0]) + ' out of the drop zone', detail: 'now ' + P(e.pos) + (e.afterFlag ? ' · on the final lap' : ''), tone: 'gain' };
      case 'ELIMINATED': return { tag: 'OUT IN ' + e.phase, title: e.drivers.map(c).join(' · '), detail: e.drivers.length + ' eliminated', tone: 'loss' };
      case 'PHASE': return { tag: e.phase, title: e.phase + ' is next', detail: 'segment change · times reset', tone: 'neutral' };
      case 'LAP_DELETED': return { tag: 'DELETED', title: c(e.drivers[0]) + ' lap deleted', detail: e.reason + (e.from && e.to && e.to !== e.from ? ' · ' + P(e.from) + ' → ' + P(e.to) : ''), tone: 'amber' };
      case 'PENALTY': return { tag: 'PENALTY', title: c(e.drivers[0]) + ' ' + e.penalty, detail: SS.util.titleCase(e.reason || ''), tone: 'amber' };
      case 'CLASSIFICATION': return { tag: 'RESULT', title: c(e.loser) + ' classified ' + P(e.to), detail: 'from ' + P(e.from) + ' · applied after the flag', tone: 'amber' };
      case 'INVESTIGATION': return { tag: 'STEWARDS', title: SS.util.titleCase(e.message.replace(/^FIA STEWARDS: /, '')).slice(0, 90), detail: '', tone: 'neutral' };
      case 'OVERTAKE_MODE': return { tag: 'OVERTAKE', title: 'Overtake mode ' + (e.on ? 'enabled' : 'disabled'), detail: '', tone: 'neutral' };
      case 'SECTOR_FLAG': return { tag: e.flag || 'FLAG', title: SS.util.titleCase(e.message), detail: '', tone: 'yellow' };
      case 'NOTICE': return { tag: 'NOTICE', title: SS.util.titleCase(e.message).slice(0, 90), detail: '', tone: 'neutral' };
      case 'BATTLE': return { tag: 'BATTLE', title: c(e.drivers[0]) + ' on ' + c(e.drivers[1]), detail: 'within 1s for 3 laps · ' + P(e.pos), tone: 'accent' };
      case 'FLAG': {
        const f = SS.flagCopy(e.status, e.from);
        if (e.status === 'CHEQUERED' && session.kind !== 'race') f.detail = 'laps started before the flag still count';
        if (e.status === 'CHEQUERED' && session.kind === 'race') f.detail = 'the leader has finished';
        return f;
      }
      case 'WINNER': return { tag: 'WINNER', title: nm(e.drivers[0]), detail: 'wins the ' + (session.meta.meeting_name || 'race'), tone: 'win' };
      case 'SESSION_END': return { tag: 'SESSION COMPLETE', title: nm(e.drivers[0]) + ' fastest', detail: '', tone: 'neutral' };
      default: return { tag: e.type, title: e.type, detail: '', tone: 'neutral' };
    }
  };
  SS.flagCopy = (status, from) => {
    switch (status) {
      case 'GREEN': return { tag: 'GREEN', title: from === 'WAITING' || from == null ? 'Session started' : 'Track clear', detail: from && from !== 'WAITING' ? 'from ' + String(from).replace('_', ' ').toLowerCase() : '', tone: 'green' };
      case 'YELLOW': return { tag: 'YELLOW', title: 'Yellow flag', detail: 'local caution', tone: 'yellow' };
      case 'VSC': return { tag: 'VSC', title: 'Virtual Safety Car', detail: 'deployed', tone: 'yellow' };
      case 'VSC_ENDING': return { tag: 'VSC ENDING', title: 'VSC ending', detail: 'racing resumes shortly', tone: 'yellow' };
      case 'SAFETY_CAR': return { tag: 'SC', title: 'Safety Car', detail: 'deployed', tone: 'yellow' };
      case 'RED_FLAG': case 'RED': return { tag: 'RED FLAG', title: 'Session suspended', detail: '', tone: 'red' };
      case 'CHEQUERED': return { tag: 'CHEQUERED', title: 'Chequered flag', detail: '', tone: 'chequered' };
      case 'FINISHED': return { tag: 'FINISHED', title: 'Session complete', detail: '', tone: 'neutral' };
      case 'WAITING': return { tag: 'WAITING', title: 'Waiting to start', detail: '', tone: 'neutral' };
      default: return { tag: status || '—', title: status || '', detail: '', tone: 'neutral' };
    }
  };
})();

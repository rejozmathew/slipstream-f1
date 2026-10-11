/* View model: one formatted snapshot per frame, shared by every posture
 * (TV, desktop, phone) so that all surfaces always agree. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;

  const OUT_LABEL = { STOPPED: 'STOPPED', RETIRED_INDICATED: 'RETIRED', DNF: 'DNF', DNS: 'DNS', DSQ: 'DSQ', RETIRED: 'RET' };

  SS.compoundBadge = (compound, age, opts = {}) => {
    const l = SS.compoundLetter(compound);
    if (!l) return '<span class="cmp cmp--none">—</span>';
    const cls = { S: 'soft', M: 'medium', H: 'hard', I: 'inter', W: 'wet' }[l] || 'none';
    const ageTxt = age == null || opts.noAge ? '' : `<span class="cmp-age mono">${age}${opts.lapSuffix === false ? '' : 'L'}</span>`;
    return `<span class="cmp cmp--${cls}${opts.fresh ? ' cmp--fresh' : ''}" title="${compound}${age != null ? ' · ' + age + ' laps' : ''}"><i>${l}</i>${ageTxt}</span>`;
  };

  /**
   * Build the frame view model.
   * @param {SS.Session} s
   * @param {SS.Cursor} cur
   * @param {object} opts { now (fractional t) }
   */
  SS.vm = function (s, cur, opts = {}) {
    const st = cur.state;
    const S = st.session;
    const now = opts.now != null ? opts.now : cur.t;
    const order = s.order(st);
    const kind = s.kind;
    const phase = S.qualifying_phase && S.qualifying_phase !== 'UNKNOWN' ? S.qualifying_phase : null;
    const pi = phase ? SS.PHASE_INDEX[phase] : null;

    // Session-wide references derived from canonical per-driver facts.
    let fastest = null; // race: fastest lap; practice: session best
    const bestOf = {};
    for (const n of order) {
      const d = st.drivers[n] || {};
      const b = U.lapToSec(d.b);
      bestOf[n] = b;
      if (b != null && (!fastest || b < fastest.time)) fastest = { num: n, time: b };
    }
    // Qualifying: current-segment bests.
    const qTime = {};
    let qFastest = null;
    if (kind === 'qualifying' && pi != null) {
      for (const n of order) {
        const qr = st.drivers[n] && st.drivers[n].qr;
        const v = qr ? qr[pi] : null;
        qTime[n] = v;
        if (v != null && (qFastest == null || v < qFastest)) qFastest = v;
      }
    }
    const finished = S.status === 'FINISHED' || S.control_status === 'CHEQUERED';
    const lapNow = kind === 'race' ? s.lapAt(now) : null;
    const battleOn = kind === 'race' && lapNow != null && lapNow >= 3 && !['VSC', 'VSC_ENDING', 'SAFETY_CAR', 'RED', 'RED_FLAG'].includes(SS.displayStatus(S));

    const rows = [];
    let prevRow = null;
    order.forEach((n, i) => {
      const d = st.drivers[n] || {};
      const D = s.drivers[n];
      const out = d.cl && d.cl !== 'FINISHED' ? OUT_LABEL[d.cl] || d.cl : d.sc === 'STOPPED' || d.sc === 'RETIRED_INDICATED' ? OUT_LABEL[d.sc] : null;
      const inPit = !out && (d.ac === 'IN_PIT' || d.sc === 'IN_PIT');
      const gap = U.parseGap(d.g);
      const int = U.parseGap(d.i);
      const r = {
        num: n, code: D.code, surname: D.surname, team: D.team, colour: D.colour,
        pos: d.p || i + 1, index: i,
        gapText: i === 0 && kind === 'race' ? 'LEADER' : gap.text || '', gapVal: gap.v, gapLaps: gap.laps,
        intText: i === 0 ? '' : int.text || '', intVal: int.v, intLaps: int.laps,
        last: d.l || '', lastSec: U.lapToSec(d.l), best: d.b || '', bestSec: bestOf[n],
        compound: d.c || null, age: d.a, stint: d.st, usage: d.u, pits: d.pc || 0,
        lap: d.lp, inPit, out, finished: d.cl === 'FINISHED',
        activity: d.ac, s1: d.s1, s2: d.s2, s3: d.s3,
        qr: d.qr || null, qe: !!d.qe, qp: d.qp,
      };
      r.lastIsPB = r.lastSec != null && r.bestSec != null && Math.abs(r.lastSec - r.bestSec) < 1e-6;
      r.lastIsFastest = r.lastIsPB && fastest && fastest.num === n;
      r.bestIsFastest = fastest && fastest.num === n;
      if (kind === 'qualifying') {
        r.qTime = qTime[n];
        r.qGap = r.qTime != null && qFastest != null ? r.qTime - qFastest : null;
        r.qInt = r.qTime != null && prevRow && prevRow.qTime != null ? r.qTime - prevRow.qTime : null;
      }
      if (kind === 'practice') {
        r.pGap = r.bestSec != null && fastest ? r.bestSec - fastest.time : null;
        r.pInt = r.bestSec != null && prevRow && prevRow.bestSec != null ? r.bestSec - prevRow.bestSec : null;
      }
      // Battle = within 1.0 s in green-flag running, from lap 3 (lap 1–2 and neutralised packs would light up everyone).
      r.battle = kind === 'race' && battleOn && !inPit && !out && r.intVal != null && r.intVal <= 1.0 && i > 0 && !finished;
      rows.push(r);
      prevRow = r;
    });

    // Latest active sector flag for the rail (scoped race-control evidence).
    let sectorFlag = null;
    if (S.marshal_status === 'YELLOW') {
      for (const m of s.rc) {
        if (m.t > now) break;
        if (/YELLOW IN TRACK SECTOR|DOUBLE YELLOW/.test(m.message)) sectorFlag = { flag: m.flag, sector: m.sector, t: m.t };
        if (/CLEAR IN TRACK SECTOR/.test(m.message) && sectorFlag && sectorFlag.sector === m.sector) sectorFlag = null;
      }
    }

    const lap = kind === 'race' ? s.lapAt(now) : null;
    const clock = kind !== 'race' ? s.clockAt(now) : null;
    const status = SS.displayStatus(S);
    return {
      t: now, sec: cur.sec, kind, phase, status, S, rows, order, finished,
      lap, totalLaps: s.totalLaps, clock,
      fastest, qFastest,
      advance: kind === 'qualifying' && phase ? SS.QUALI_ADVANCE[phase] : null,
      weather: s.weatherAt(now),
      overtakeMode: kind === 'race' ? s.overtakeModeAt(now) : null,
      sectorFlag,
      leader: rows[0] || null,
    };
  };

  /* Per-lap interval history for a pair (battle module). Cached per session. */
  SS.pairHistory = function (s, ahead, behind, uptoT, laps = 8) {
    s._pairCache = s._pairCache || {};
    const out = [];
    const lapTimes = s.laps.filter(([sec]) => sec <= uptoT).slice(-laps - 1);
    for (const [sec, lap] of lapTimes) {
      const key = ahead + '>' + behind + '@' + sec;
      if (!(key in s._pairCache)) {
        const snap = s.snapshot(sec + 4);
        const a = snap.drivers[ahead], b = snap.drivers[behind];
        let v = null;
        if (a && b) {
          const ga = U.parseGap(a.g), gb = U.parseGap(b.g);
          if (a.p === 1 && gb.v != null) v = gb.v;
          else if (ga.v != null && gb.v != null) v = gb.v - ga.v;
          if (b.p === (a.p || 0) + 1) { const iv = U.parseGap(b.i).v; if (iv != null) v = iv; }
        }
        s._pairCache[key] = v;
      }
      out.push({ lap: lap - 1, v: s._pairCache[key] });
    }
    // Only laps where the two were genuinely racing each other (within 5 s either way).
    // A negative value means the order was the other way round: the line crossing zero is the pass.
    return out.filter((x) => x.v != null && Math.abs(x.v) <= 5);
  };

  /* Recently active causes for the tower (causal: only facts up to now). */
  SS.recentContext = function (s, now) {
    const ctx = { pitEntry: {}, deleted: {}, improved: {}, penalty: {}, passes: [] };
    for (const e of s.events) {
      if (e.t > now) break;
      if (e.t < now - 60) continue;
      if (e.type === 'PIT_IN') ctx.pitEntry[e.drivers[0]] = e.t;
      if (e.type === 'LAP_DELETED') ctx.deleted[e.drivers[0]] = e.t;
      if (e.type === 'IMPROVEMENT' || e.type === 'SEGMENT_P1' || e.type === 'PROVISIONAL_POLE' || e.type === 'SESSION_BEST') ctx.improved[e.drivers[0]] = { t: e.t, type: e.type };
    }
    for (const e of s.events) {
      if (e.t > now) break;
      if (e.type === 'PENALTY' && e.drivers[0]) ctx.penalty[e.drivers[0]] = e.penalty;
    }
    return ctx;
  };
})();

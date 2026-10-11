/* Feature modules shared by TV, desktop and phone: battle, followed driver,
 * pit board (race), on-track board (timed sessions). Factual inputs only. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;

  /* Pick the battle worth watching: closest pair under 1.0 s, weighted to the front. */
  SS.pickBattle = function (vm, pinned) {
    if (pinned) {
      const a = vm.byNum[pinned[0]], b = vm.byNum[pinned[1]];
      if (a && b) return a.index < b.index ? [a, b] : [b, a];
    }
    let best = null;
    vm.rows.forEach((r, i) => {
      if (!r.battle || i === 0) return;
      const score = r.intVal + i * 0.06;
      if (!best || score < best.score) best = { score, pair: [vm.rows[i - 1], r] };
    });
    return best ? best.pair : null;
  };

  const spark = (pts, w, h, opts = {}) => {
    if (!pts.length) return '';
    const max = Math.max(1.2, ...pts.map((p) => p.v));
    const min = Math.min(0, ...pts.map((p) => p.v));
    const x = (i) => (pts.length === 1 ? w / 2 : (i / (pts.length - 1)) * w);
    const y = (v) => h - ((v - min) / (max - min)) * h;
    const d = pts.map((p, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(p.v).toFixed(1)).join(' ');
    const one = y(1.0), zero = y(0);
    const pct = (v) => ((y(v) / h) * 100).toFixed(1) + '%';
    const lastV = pts[pts.length - 1].v;
    return `<div class="spark-wrap"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="spark"><line x1="0" x2="${w}" y1="${one}" y2="${one}" class="spark-ref"/>${min < 0 ? `<line x1="0" x2="${w}" y1="${zero}" y2="${zero}" class="spark-zero"/>` : ''}<path d="${d}" class="spark-line"/></svg>${pts.map((p, i) => `<i class="spark-dot${p.v < 0 ? ' is-rev' : ''}" style="left:${((x(i) / w) * 100).toFixed(2)}%;top:${pct(p.v)}"></i>`).join('')}${min < 0 && Math.abs(y(1) - y(0)) < h * 0.16 ? '' : `<span class="spark-l" style="top:${pct(1)}">1.0 s</span>`}${min < 0 ? `<span class="spark-l is-zero" style="top:${pct(0)}">0</span>` : ''}<span class="spark-v mono" style="top:${pct(lastV)}">${lastV.toFixed(2)}</span></div>`;
  };
  SS.spark = spark;

  class BattleView {
    constructor(root, o) { this.root = root; this.o = o; this.s = o.session; root.classList.add('battle', 'battle--' + o.posture); }
    render(vm, pair, now) {
      if (!pair) {
        const html = `<div class="bt-empty"><b>No close battle right now</b><span>Shown when two cars run within 1.0 s in green-flag running.</span></div>`;
        if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
        this._key = null;
        return;
      }
      const [a, b] = pair;
      const tv = this.o.posture === 'tv', phone = this.o.posture === 'phone';
      const hist = SS.pairHistory(this.s, a.num, b.num, now, phone ? 6 : 8);
      // Trend over the last three completed laps only, and only while this order held.
      const tail = hist.slice(-3);
      const first = tail.length ? tail[0].v : null, last = tail.length ? tail[tail.length - 1].v : null;
      const swapped = hist.some((p) => p.v < 0);
      const trend = tail.length < 3 || first < 0 ? (swapped ? 'JUST PASSED' : 'NEW') : last < first - 0.15 ? 'CLOSING' : last > first + 0.15 ? 'OPENING' : 'STEADY';
      const side = (r, ahead) => `<div class="bt-side ${ahead ? 'is-ahead' : 'is-behind'}" style="--team:${r.colour}">
          <span class="bt-pos mono">P${r.pos}</span><b class="bt-code">${r.code}</b><span class="bt-name">${U.titleCase(r.surname)} · ${r.team}</span>
          <div class="bt-facts">${SS.compoundBadge(r.compound, r.age)}<span class="dim">${r.pits} stop${r.pits === 1 ? '' : 's'}</span>${SS.stints ? `<span class="bt-seq">${SS.compoundSeq(SS.stints(this.s, r.num, now).list.map((x) => x.c))}</span>` : ''}</div></div>`;
      // Lap-by-lap: laps both drivers completed, newest first.
      const ha = this.s.lapHistory(a.num).filter((x) => x.t <= now), hb = this.s.lapHistory(b.num).filter((x) => x.t <= now);
      const byLap = new Map(hb.map((x) => [x.lap, x.time]));
      const laps = ha.filter((x) => byLap.has(x.lap)).slice(-(tv ? 6 : phone ? 3 : 4)).reverse();
      // In-laps and out-laps carry the stop: they are labelled, not compared.
      const pitLaps = (num) => new Set(this.s.events.filter((e) => e.type === 'PIT_IN' && e.drivers[0] === num && SS.avail(e) <= now).flatMap((e) => [e.lap, e.lap + 1]));
      const pa = pitLaps(a.num), pb = pitLaps(b.num);
      const lapRows = laps.map((x) => {
        const ta = x.time, tb = byLap.get(x.lap), d = tb - ta;
        const pit = pa.has(x.lap) || pb.has(x.lap);
        const faster = pit || Math.abs(d) < 0.0005 ? null : d < 0 ? b : a;
        const who = pit ? [pa.has(x.lap) ? a.code : null, pb.has(x.lap) ? b.code : null].filter(Boolean).join(' & ') : '';
        return `<tr class="${pit ? 'is-pitlap' : ''}"><td class="mono dim">L${x.lap}</td><td class="mono ${faster === a ? 'is-fast' : ''}">${U.fmtLap(ta)}</td><td class="mono ${faster === b ? 'is-fast' : ''}">${U.fmtLap(tb)}</td><td class="bt-d">${pit ? `<span class="bt-pitlap">PIT LAP · ${who}</span>` : faster ? `<b style="--team:${faster.colour}">${faster.code}</b><span class="mono">−${Math.abs(d).toFixed(3)}</span>` : '<span class="dim">level</span>'}</td></tr>`;
      }).join('');
      // The number must answer this pair: interval only when adjacent; otherwise the gap between them
      // (server pair-gap semantics when available), a lap difference, or unknown.
      const adjacent = b.index === a.index + 1;
      let iv = null, ivLbl = adjacent ? 'INTERVAL' : 'GAP', ivTxt = null;
      const pg = SS.pairGap ? SS.pairGap(this.s, vm, a.num, b.num) : null;
      if (pg) { iv = pg.v; if (pg.basis === 'interval') ivLbl = 'INTERVAL'; else if (pg.basis !== 'none') ivLbl = 'GAP'; if (pg.laps) ivTxt = `+${pg.laps} LAP${pg.laps === 1 ? '' : 'S'}`; }
      else if (adjacent) { iv = b.intLaps ? null : b.intVal; if (b.intLaps) ivTxt = b.intText; }
      else if (!a.gapLaps && !b.gapLaps && b.gapVal != null && (a.index === 0 || a.gapVal != null)) iv = b.gapVal - (a.index === 0 ? 0 : a.gapVal);
      else if (b.gapLaps || a.gapLaps) ivTxt = 'LAPPED';
      const key = a.num + '>' + b.num;
      const title = adjacent ? `BATTLE FOR P${a.pos}` : `P${a.pos} VS P${b.pos} · NOT ADJACENT`;
      const html = `<div class="bt-title"><span class="lbl">${title}</span><span class="bt-trend bt-trend--${trend.split(' ')[0].toLowerCase()}">${trend}</span></div>
        <div class="bt-main">${side(a, true)}<div class="bt-mid"><span class="lbl">${ivLbl}</span><strong class="mono bt-iv">${ivTxt || (iv != null ? iv.toFixed(3) : '—')}</strong><span class="bt-unit">${ivTxt ? '' : 'seconds · '}${b.code} behind ${a.code}</span></div>${side(b, false)}</div>
        <div class="bt-low">
          <div class="bt-panel"><span class="lbl">GAP AT EACH LAP</span><div class="bt-spark">${hist.length >= 2 ? spark(hist, 300, 70, { r: tv ? 4 : 3 }) : '<span class="bt-nohist">Not racing each other on recent laps</span>'}</div><span class="bt-cap">${hist.length >= 2 ? `laps ${hist[0].lap}–${hist[hist.length - 1].lap}${swapped ? ' · below zero = the other way round' : ''}` : 'Appears after two completed laps together'}</span></div>
          <div class="bt-panel"><span class="lbl">LAP TIMES</span>${laps.length ? `<table class="bt-laps"><thead><tr><th></th><th>${a.code}</th><th>${b.code}</th><th>FASTER</th></tr></thead><tbody>${lapRows}</tbody></table>` : '<span class="bt-nohist">No common completed laps yet</span>'}</div>
        </div>`;
      if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
      if (key !== this._key && this.root.animate && this._key && !document.documentElement.classList.contains('reduced-motion')) this.root.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: 380 });
      this._key = key;
    }
  }
  SS.BattleView = BattleView;

  class DriverCard {
    constructor(root, o) { this.root = root; this.o = o; this.s = o.session; root.classList.add('dcard', 'dcard--' + o.posture); }
    render(vm, num, now) {
      const r = vm.byNum[num];
      if (!r) { this.root.innerHTML = ''; return; }
      const i = r.index;
      const ahead = vm.rows[i - 1], behind = vm.rows[i + 1];
      const race = vm.kind === 'race';
      const gapAhead = race ? (i === 0 ? 'LEADING' : r.intVal != null ? '+' + r.intVal.toFixed(3) : r.intText || '—') : r.qGap != null ? '+' + r.qGap.toFixed(3) : r.pGap != null ? '+' + r.pGap.toFixed(3) : '—';
      const gapBehind = race && behind ? (behind.intVal != null ? '+' + behind.intVal.toFixed(3) : behind.intText || '—') : '';
      const evs = this.s.events.filter((e) => SS.avail(e) <= now && e.priority >= SS.PRIORITY.FEED && e.drivers.includes(num)).slice(-3).reverse();
      const html = `<div class="dc-top" style="--team:${r.colour}"><span class="dc-pos mono">P${r.pos}</span><div class="dc-id"><b>${r.code}</b><span>${U.titleCase(r.surname)} · ${r.team}</span></div>${r.inPit ? '<span class="chip-pit">PIT</span>' : r.out ? `<span class="chip-out">${r.out}</span>` : ''}</div>
        <div class="dc-grid">
          <div><span class="lbl">${race ? 'TO CAR AHEAD' : 'GAP TO P1'}</span><b class="mono">${gapAhead}</b><em>${race && ahead ? ahead.code : ''}</em></div>
          ${race ? `<div><span class="lbl">CAR BEHIND</span><b class="mono">${gapBehind || '—'}</b><em>${behind ? behind.code : ''}</em></div>` : `<div><span class="lbl">BEST</span><b class="mono">${vm.kind === 'qualifying' ? U.fmtLap(r.qTime) : r.best || '—'}</b><em></em></div>`}
          <div><span class="lbl">TYRE</span><b>${SS.compoundBadge(r.compound, r.age)}</b><em>${r.usage === 'NEW' ? 'new set' : r.usage === 'USED' ? 'used set' : ''}</em></div>
          <div><span class="lbl">${race ? 'STOPS' : 'STINT'}</span><b class="mono">${race ? r.pits : r.stint != null ? r.stint + ' laps' : '—'}</b><em></em></div>
          <div><span class="lbl">LAST LAP</span><b class="mono ${r.lastIsPB ? 't-green' : ''}">${r.last || '—'}</b><em></em></div>
          <div><span class="lbl">BEST LAP</span><b class="mono ${r.bestIsFastest ? 't-purple' : ''}">${r.best || '—'}</b><em></em></div>
          ${SS.stints ? (() => {
            const st = SS.stints(this.s, num, now);
            const dr = SS.dryRule(st);
            const lp = st.stops[st.stops.length - 1];
            return `<div><span class="lbl">SECTORS · LAST LAP</span><b class="mono dc-sec">${[r.s1, r.s2, r.s3].map((x) => (x == null || x === '' ? '—' : (+x).toFixed(3))).join(' ')}</b><em></em></div>
              <div><span class="lbl">${race ? 'TYRE STRATEGY' : 'STINT LAPS'}</span><b>${race ? SS.compoundSeq(st.list.map((x) => x.c)) : `<span class="mono">${r.stint != null ? r.stint : '—'}</span>`}</b><em>${race && vm.lap > 1 ? dr.text : ''}</em></div>
              ${race ? `<div><span class="lbl">LATEST PIT</span><b class="mono">${lp ? 'L' + lp.lap + (lp.lane ? ' · ' + lp.lane.toFixed(1) + 's' : '') : '—'}</b><em>${lp ? 'pit lane · stationary not in timing' : ''}</em></div>` : ''}`;
          })() : ''}
        </div>
        <ol class="dc-events">${evs.map((e) => { const d = SS.describe(this.s, e, now); return `<li class="tone-${d.tone}"><span class="mono">${SS.stamp(this.s, e)}</span><b>${d.title}</b><em>${d.detail}</em></li>`; }).join('') || '<li class="dim">No events yet for this driver.</li>'}</ol>`;
      if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
    }
  }
  SS.DriverCard = DriverCard;

  /* Race: what the pit lane is doing (facts only — no projections). */
  class PitBoard {
    constructor(root, o) { this.root = root; this.o = o; this.s = o.session; root.classList.add('pitboard', 'pitboard--' + o.posture); }
    render(vm, now) {
      const rows = vm.rows.filter((r) => !r.out);
      const stops = {};
      const tyres = {};
      for (const r of rows) { const k = Math.min(3, r.pits || 0); stops[k] = (stops[k] || 0) + 1; const c = SS.compoundLetter(r.compound) || '?'; tyres[c] = (tyres[c] || 0) + 1; }
      const total = rows.length || 1;
      const recent = this.s.events.filter((e) => e.type === 'PIT_IN' && SS.avail(e) <= now).slice(-(this.o.posture === 'tv' ? 6 : 5)).reverse();
      const inLane = rows.filter((r) => r.inPit);
      const bar = (obj, keys, cls) => keys.filter((k) => obj[k]).map((k) => `<i class="${cls(k)}" style="flex:${obj[k]}"><b>${obj[k]}</b><em>${typeof k === 'number' || /^\d$/.test(k) ? (k == 3 ? '3+' : k) + (k == 1 ? ' STOP' : ' STOPS') : { S: 'SOFT', M: 'MEDIUM', H: 'HARD', I: 'INTER', W: 'WET' }[k] || k}</em></i>`).join('');
      const html = `<div class="pb-sec"><span class="lbl">STOPS COMPLETED</span><div class="pb-bar">${bar(stops, [0, 1, 2, 3], (k) => 'pb-s' + k)}</div></div>
        <div class="pb-sec"><span class="lbl">TYRES ON CAR NOW</span><div class="pb-bar">${bar(tyres, ['S', 'M', 'H', 'I', 'W'], (k) => 'pb-c' + k)}</div></div>
        <div class="pb-sec pb-lane"><span class="lbl">IN THE PIT LANE NOW</span><div>${inLane.length ? inLane.map((r) => `<span class="pb-drv" style="--team:${r.colour}"><i></i>${r.code}</span>`).join('') : '<span class="dim">Empty</span>'}</div></div>
        <div class="pb-sec"><span class="lbl">LATEST STOPS</span><ol class="pb-list">${recent.map((e) => { const D = this.s.drivers[e.drivers[0]]; const known = e.rejoinAt != null && now >= e.rejoinAt; return `<li style="--team:${D.colour}"><span class="mono dim">L${e.lap}</span><b>${D.code}</b><span>${SS.compoundBadge(e.from, null, { noAge: true })}<em>→</em>${known ? SS.compoundBadge(e.compound, null, { noAge: true }) : '<span class="dim">…</span>'}</span><span class="mono">${known && e.lane ? e.lane.toFixed(1) + 's' : ''}</span><span class="dim">P${e.pos}${known && e.rejoin ? ' → P' + e.rejoin : ''}</span></li>`; }).join('') || '<li class="dim">No stops yet</li>'}</ol></div>
        <p class="pb-note">Pit-lane time is the full lane transit from timing, not stationary time.</p>`;
      if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
    }
  }
  SS.PitBoard = PitBoard;

  /* Race result: classification facts once the flag has fallen. */
  class RaceResult {
    constructor(root, o) { this.root = root; this.o = o; this.s = o.session; root.classList.add('result', 'result--' + o.posture); }
    render(vm, now) {
      const s = this.s;
      if (!this._grid) {
        const snap = s.snapshot(s.begin);
        this._grid = {};
        for (const [n, d] of Object.entries(snap.drivers)) if (d && d.p) this._grid[n] = d.p;
      }
      const grid = this._grid;
      const rows = vm.rows;
      // A result only exists after the chequered flag (pinning this view earlier must not crown anyone).
      const rs = SS.resultState ? SS.resultState(s, now) : { state: vm.finished ? 'provisional' : 'none' };
      if (rs.state === 'none') {
        const html = `<div class="rs-head"><span class="lbl">RESULT</span><span class="rs-sub">race in progress</span></div><div class="rs-wait"><b>No result yet</b><span>The classification appears when the leader takes the chequered flag${vm.lap && vm.totalLaps ? ` · ${Math.max(0, vm.totalLaps - vm.lap)} laps to go` : ''}. Running order now: ${rows.slice(0, 3).map((r) => `P${r.pos} ${r.code}`).join(' · ')} — not a result.</span></div>`;
        if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
        return;
      }
      const pod = rows.slice(0, 3).map((r, i) => `<div class="rs-pod rs-pod--${i + 1}" style="--team:${r.colour}"><span class="rs-p mono">P${i + 1}</span><b>${r.code}</b><span class="rs-n">${U.titleCase(r.surname)} · ${r.team}</span><span class="rs-g mono">${i === 0 ? 'WINNER' : r.gapLaps ? r.gapText : r.gapVal != null ? '+' + r.gapVal.toFixed(3) : ''}</span></div>`).join('');
      const gains = rows.filter((r) => !r.out && grid[r.num] != null).map((r) => ({ r, d: grid[r.num] - r.pos })).filter((x) => x.d > 0).sort((a, b) => b.d - a.d || a.r.pos - b.r.pos).slice(0, this.o.posture === 'phone' ? 3 : 4);
      let fl = null;
      if (vm.fastest) {
        const h = s.lapHistory(vm.fastest.num).find((x) => Math.abs(x.time - vm.fastest.time) < 0.0005);
        fl = { r: vm.byNum[vm.fastest.num], time: vm.fastest.time, lap: h ? h.lap : null };
      }
      const pens = s.events.filter((e) => e.type === 'PENALTY' && SS.avail(e) <= now && e.drivers[0]);
      const outs = rows.filter((r) => r.out);
      const drv = (r, extra = '') => `<span class="rs-drv" style="--team:${r.colour}"><b>${r.code}</b>${extra}</span>`;
      const html = `<div class="rs-head"><span class="lbl">${rs.state === 'final' ? 'FINAL CLASSIFICATION' : 'PROVISIONAL CLASSIFICATION'}</span><span class="rs-sub">after the chequered flag · penalties applied as published${rs.state === 'final' ? '' : ' · may still change'}</span></div>
        <div class="rs-podium">${pod}</div>
        <div class="rs-facts">
          <div class="rs-box"><span class="lbl">PLACES GAINED SINCE THE START</span><ol>${gains.map((x) => `<li>${drv(x.r)}<span class="mono dim">P${grid[x.r.num]} → P${x.r.pos}</span><em class="mono">▲${x.d}</em></li>`).join('') || '<li class="dim">No gains</li>'}</ol></div>
          <div class="rs-box"><span class="lbl">FASTEST LAP</span>${fl && fl.r ? `<div class="rs-fl">${drv(fl.r)}<strong class="mono t-purple">${U.fmtLap(fl.time)}</strong><span class="dim">${fl.lap ? 'lap ' + fl.lap : ''}</span></div>` : '<span class="dim">—</span>'}</div>
          <div class="rs-box"><span class="lbl">PENALTIES · NOT CLASSIFIED</span><ol>${pens.map((e) => { const r = vm.byNum[e.drivers[0]]; return r ? `<li>${drv(r)}<span class="mono rs-pen">${e.penalty}</span><span class="dim rs-why">${U.titleCase(e.reason || '')}</span></li>` : ''; }).join('')}${outs.map((r) => `<li>${drv(r)}<span class="rs-out">${r.out}</span></li>`).join('')}</ol></div>
        </div>`;
      if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
    }
  }
  SS.RaceResult = RaceResult;

  /* Timed sessions: who is on track right now, and what they are on. */
  class OnTrack {
    constructor(root, o) { this.root = root; this.o = o; this.s = o.session; root.classList.add('ontrack', 'ontrack--' + o.posture); }
    render(vm) {
      const on = vm.rows.filter((r) => r.activity === 'ON_TRACK' && !r.qe && !r.out);
      const quali = vm.kind === 'qualifying';
      // Best time, not last lap: in practice the last lap often includes the out-lap from the garage.
      const html = `<div class="ot-head"><span class="lbl">ON TRACK NOW · ${quali ? 'BEST THIS SEGMENT' : 'SESSION BEST'}</span><b class="mono">${on.length}</b></div><ol class="ot-list">${on.slice(0, this.o.max || 12).map((r) => `<li style="--team:${r.colour}"><span class="mono ot-p">P${r.pos}</span><i></i><b>${r.code}</b>${SS.compoundBadge(r.compound, r.age)}<span class="mono ot-t">${quali ? (r.qTime != null ? U.fmtLap(r.qTime) : '<span class="dim">no time</span>') : r.best || '<span class="dim">no time</span>'}</span>${quali && vm.advance && r.index >= vm.advance && !vm.finished ? '<span class="chip-drop">AT RISK</span>' : ''}</li>`).join('') || '<li class="dim">All cars in the pits</li>'}</ol>`;
      if (html !== this._html) { this.root.innerHTML = html; this._html = html; }
    }
  }
  SS.OnTrack = OnTrack;
})();

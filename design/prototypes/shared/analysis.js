/* Analysis panels carried over from the current app, restyled — nothing dropped.
 * Conditions, Race control, Strategy (Pirelli + Race now), Driver landscape, Stint chart,
 * Driver page, Battle page. Every figure is either read from timing or derived from it;
 * server-only analytics (battle score, pace fade, projections) are labelled as such. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;
  const DRY = ['SOFT', 'MEDIUM', 'HARD'];
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cmpL = (c) => SS.compoundLetter(c) || '?';
  const seq = (list) => `<span class="cseq">${list.map((c, i) => `${i ? '<em>›</em>' : ''}${SS.compoundBadge(c, null, { noAge: true })}`).join('')}</span>`;
  SS.compoundSeq = seq;

  /* ---------------------------------------------------------- clocks */
  const offsetMs = (s) => {
    const m = /^(-)?(\d{1,2}):(\d{2})/.exec(s.meta.gmt_offset || '');
    return m ? (m[1] ? -1 : 1) * (+m[2] * 60 + +m[3]) * 60000 : 0;
  };
  SS.offsetLabel = (s) => {
    const m = /^(-)?(\d{1,2}):(\d{2})/.exec(s.meta.gmt_offset || '');
    return m ? `UTC${m[1] ? '−' : '+'}${m[2].padStart(2, '0')}:${m[3]}` : 'UTC';
  };
  /** Track-local wall clock at session time t. */
  SS.localClock = (s, t) => {
    const d = new Date((s.d.t0 + t) * 1000 + offsetMs(s));
    return d.toISOString().slice(11, 19);
  };
  SS.sessionDate = (s) => {
    const d = new Date(Date.parse(s.meta.started_at || 0) + offsetMs(s));
    return d.toUTCString().slice(0, 16).toUpperCase().replace(',', '');
  };

  /* ---------------------------------------------------------- stints (from timing: compound changes + pit observations) */
  SS.stints = function (s, num, now) {
    s._stintCache = s._stintCache || {};
    if (!s._stintCache[num]) {
      const changes = [];
      let c = s.d.init && s.d.init[num] ? s.d.init[num].c : null;
      let lap = 0;
      if (c) changes.push({ t: s.begin, c, lap: 0 });
      for (const [sec, fr] of s.frames) {
        const ch = fr[num];
        if (!ch) continue;
        if (ch.lp != null) lap = ch.lp;
        if (ch.c && ch.c !== c) { c = ch.c; changes.push({ t: sec, c, lap }); }
      }
      // pit observations: one record per stop carries the lane time, another the compounds
      const stops = {};
      for (const [t, n, plap, prev, next, lane, ord] of s.d.pits) {
        if (n !== num) continue;
        const k = ord || plap;
        const st = (stops[k] = stops[k] || { ord, lap: plap, t, prev: null, next: null, lane: null });
        st.t = Math.min(st.t, t);
        if (prev) st.prev = prev;
        if (next) st.next = next;
        if (lane != null) st.lane = lane;
      }
      s._stintCache[num] = { changes, stops: Object.values(stops).sort((a, b) => a.t - b.t) };
    }
    const { changes, stops } = s._stintCache[num];
    const seenStops = stops.filter((x) => x.t <= now);
    const list = [];
    const first = changes.find((x) => x.t <= now) || changes[0];
    if (!first) return { list, stops: seenStops };
    list.push({ c: first.c, from: 0, to: null });
    for (const st of seenStops) {
      const after = changes.find((x) => x.t >= st.t - 5 && x.t <= now && x.c && x.t <= st.t + 120);
      list[list.length - 1].to = st.lap;
      list.push({ c: st.next || (after ? after.c : list[list.length - 1].c), from: st.lap, to: null, stop: st });
    }
    // a compound change without a pit observation (e.g. data correction) updates the last stint
    const lastCh = changes.filter((x) => x.t <= now).slice(-1)[0];
    if (lastCh && list.length && list[list.length - 1].c !== lastCh.c && !seenStops.length) list[list.length - 1].c = lastCh.c;
    return { list, stops: seenStops };
  };

  SS.dryRule = function (stints) {
    const used = new Set(stints.list.map((x) => x.c));
    if ([...used].some((c) => c === 'INTERMEDIATE' || c === 'WET')) return { key: 'waived', text: 'Wet tyres used · two-compound rule waived' };
    const dry = [...used].filter((c) => DRY.includes(c));
    return dry.length >= 2 ? { key: 'ok', text: 'Dry tyre requirement satisfied' } : { key: 'needs', text: 'Still needs another dry compound' };
  };

  /* ---------------------------------------------------------- race now (facts derived from timing) */
  SS.raceNow = function (s, vm) {
    const rows = vm.rows;
    const out = rows.filter((r) => r.out), inPit = rows.filter((r) => r.inPit), running = rows.filter((r) => !r.out && !r.inPit);
    const active = rows.filter((r) => !r.out);
    const tyres = {};
    for (const r of active) { const l = cmpL(r.compound); tyres[l] = (tyres[l] || 0) + 1; }
    const stopsDist = {};
    for (const r of active) stopsDist[r.pits] = (stopsDist[r.pits] || 0) + 1;
    const seqs = {};
    let needs = 0;
    const completed = {};
    for (const r of active) {
      const st = SS.stints(s, r.num, vm.t);
      const key = st.list.map((x) => cmpL(x.c)).join(' ');
      (seqs[key] = seqs[key] || { list: st.list.map((x) => x.c), n: 0 }).n++;
      if (vm.kind === 'race' && SS.dryRule(st).key === 'needs') needs++;
      for (const x of st.list) if (x.to != null) (completed[cmpL(x.c)] = completed[cmpL(x.c)] || []).push(x.to - x.from);
    }
    const median = (a) => { const b = a.slice().sort((x, y) => x - y); const m = b.length >> 1; return b.length ? (b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2) : null; };
    const recent = s.events.filter((e) => e.type === 'PIT_IN' && e.t <= vm.t).slice(-3).reverse();
    const topStops = Object.entries(stopsDist).sort((a, b) => b[1] - a[1])[0];
    const facts = [];
    if (topStops) facts.push(`${topStops[1]} of ${active.length} running or in-pit drivers have exactly ${topStops[0]} completed stop${topStops[0] === '1' ? '' : 's'}.`);
    if (vm.kind === 'race' && vm.lap > 1) facts.push(`${needs} of ${active.length} running or in-pit drivers still need another dry compound.`);
    if (out.length) facts.push(`${out.length} car${out.length === 1 ? '' : 's'} out: ${out.map((r) => r.code).join(', ')}.`);
    return {
      running: running.length, inPit: inPit.length, out: out.length, active: active.length,
      tyres, stopsDist, needs,
      seqs: Object.values(seqs).sort((a, b) => b.n - a.n),
      stintCtx: Object.entries(completed).map(([c, a]) => ({ c, n: a.length, med: median(a) })),
      recent, facts,
    };
  };

  /* ---------------------------------------------------------- panels */
  const panel = (eyebrow, title, action, body, cls = '') => `<section class="pnl ${cls}"><header class="pnl-h"><div><span class="pnl-eb">${eyebrow}</span><b class="pnl-t">${title}</b></div>${action ? `<div class="pnl-a">${action}</div>` : ''}</header><div class="pnl-b">${body}</div></section>`;
  SS.panel = panel;

  SS.conditionsHTML = function (s, vm) {
    const w = vm.weather;
    const v = (x, unit, d = 1) => (x == null ? '<span class="dim">—</span>' : `${(+x).toFixed(d)}${unit}`);
    const rain = w ? (w.rain ? '<span class="pill-rain">RAIN DETECTED</span>' : '<span class="pill-dry">NO RAIN</span>') : '';
    const body = `<div class="cond-grid">
      <div><span>TRACK</span><b class="mono">${v(w && w.track, ' °C')}</b></div>
      <div><span>AIR</span><b class="mono">${v(w && w.air, ' °C')}</b></div>
      <div><span>HUMIDITY</span><b class="mono">${v(w && w.hum, '%', 0)}</b></div>
      <div><span>WIND</span><b class="mono">${v(w && w.wind, ' m/s')}${w && w.dir != null ? ` <small>${Math.round(w.dir)}°</small>` : ''}</b></div>
      <div><span>PRESSURE</span><b class="mono">${v(w && w.pressure, ' hPa')}</b></div>
      <div><span>TRACK LOCAL</span><b class="mono">${SS.localClock(s, vm.t)} <small>${SS.offsetLabel(s)}</small></b></div>
    </div><footer class="pnl-foot">Rain is a sensor observation · surface grip is not inferred</footer>`;
    return panel('WEATHER FEED', 'Conditions', rain, body, 'pnl-cond');
  };

  SS.raceControlHTML = function (s, vm, max = 6) {
    const msgs = s.rc.filter((m) => m.t <= vm.t);
    const recent = msgs.slice(-max).reverse();
    const tone = (m) => {
      const f = (m.flag || '').toUpperCase();
      if (/RED/.test(f)) return 'red';
      if (/YELLOW|SC|VSC|SAFETY/.test(f) || /SAFETY CAR|VSC/.test(m.message)) return 'yellow';
      if (/GREEN|CLEAR/.test(f)) return 'green';
      if (/CHEQUERED/.test(f)) return 'chequered';
      if (/BLUE/.test(f)) return 'blue';
      if (/PENALTY|INVESTIGAT|DELETED|NOTED/.test(m.message)) return 'amber';
      return 'neutral';
    };
    const stamp = (m) => (s.kind === 'race' ? (m.lap ? 'L' + m.lap + ' · ' : '') : '') + SS.localClock(s, m.t);
    const body = recent.length ? `<ol class="rc-list">${recent.map((m) => `<li class="rc-${tone(m)}"><time class="mono">${stamp(m)}</time><span class="rc-tag">${esc(m.flag && m.flag !== 'CLEAR' ? m.flag : m.category || '')}</span><p>${esc(m.message)}</p></li>`).join('')}</ol>` : '<div class="pnl-empty">No messages at this session time</div>';
    return panel('LATEST', 'Race control', `<span class="pnl-count mono">${msgs.length}</span>`, body, 'pnl-rc');
  };

  /* Pirelli context as published by the server (captured from the current app for this race). */
  SS.pirelliHTML = function (s, compact) {
    const P = (window.SLIPSTREAM_SERVER || {})[s.d.label];
    const p = P && P.pirelli;
    if (!p) return `<div class="pir-none"><b>No official Pirelli strategy available for this session.</b><span>Current race facts remain available.</span></div>`;
    const nom = p.compounds ? `<div class="pir-nom"><span class="lbl">TYRE COMPOUNDS</span><b>${SS.compoundBadge('HARD', null, { noAge: true })}<em class="mono">${p.compounds.hard}</em>${SS.compoundBadge('MEDIUM', null, { noAge: true })}<em class="mono">${p.compounds.medium}</em>${SS.compoundBadge('SOFT', null, { noAge: true })}<em class="mono">${p.compounds.soft}</em></b></div>` : '';
    const opts = p.options && p.options.length ? p.options.map((o) => `<article class="pir-opt"><span>${o.rank}</span><b>${o.stops}-STOP</b>${seq(o.compounds)}<small>${o.window || ''}</small></article>`).join('') : '<div class="pir-noopt">No specific Pirelli tyre strategy published.</div>';
    const facts = (p.facts || []).slice(0, compact ? 1 : 5).map((f) => `<p class="pir-fact"><span>${f.category}</span>${esc(f.text)}</p>`).join('');
    return `<div class="pir"><div class="pir-src"><span class="lbl">PIRELLI · PRE-RACE PUBLICATION</span>${p.source ? `<a href="${p.source}" target="_blank" rel="noreferrer">SOURCE ↗</a>` : ''}</div>${opts}${nom}${facts}</div>`;
  };

  SS.raceNowHTML = function (s, vm, compact) {
    const n = SS.raceNow(s, vm);
    const counts = (obj, order) => order.filter((k) => obj[k]).map((k) => `<span>${SS.compoundBadge({ S: 'SOFT', M: 'MEDIUM', H: 'HARD', I: 'INTERMEDIATE', W: 'WET' }[k], null, { noAge: true })}<b class="mono">${obj[k]}</b></span>`).join('') || '—';
    const stops = Object.entries(n.stopsDist).sort((a, b) => a[0] - b[0]).map(([k, v]) => `${k} ${k === '1' ? 'stop' : 'stops'}: ${v}`).join(' · ') || '—';
    const cells = [
      ['RUNNING / STATUS', `<b>${n.running} RUNNING</b>`, [n.inPit ? `${n.inPit} in pit` : '', n.out ? `${n.out} stopped / out` : ''].filter(Boolean).join(' · ') || 'all cars running'],
      ['CURRENT TYRES', `<span class="rn-cmp">${counts(n.tyres, ['S', 'M', 'H', 'I', 'W'])}</span>`, 'running or in-pit drivers'],
      ['COMPLETED STOPS', `<b>${stops}</b>`, 'observed stop-count distribution'],
    ];
    if (vm.kind === 'race') cells.push(['DRY RULE', `<b>${n.needs} driver${n.needs === 1 ? '' : 's'} still need another dry compound</b>`, `${n.active} running or in pit`]);
    if (!compact) {
      cells.push(['COMPOUND SEQUENCES', `<span class="rn-seqs">${n.seqs.slice(0, 5).map((x) => `<span><b class="mono">${x.n}</b>${seq(x.list)}</span>`).join('')}</span>`, 'consecutive repeats kept, as observed']);
      cells.push(['STINT CONTEXT', `<span class="rn-cmp">${n.stintCtx.map((x) => `<span>${SS.compoundBadge({ S: 'SOFT', M: 'MEDIUM', H: 'HARD', I: 'INTERMEDIATE', W: 'WET' }[x.c], null, { noAge: true })}<b>${x.n} stint${x.n === 1 ? '' : 's'} · median ${x.med != null ? x.med.toFixed(1) : '—'}L</b></span>`).join('') || '—'}</span>`, 'completed stints by compound']);
      cells.push(['RECENT PITS', `<span class="rn-pits">${n.recent.map((e) => { const D = s.drivers[e.drivers[0]]; const known = e.rejoinAt != null && vm.t >= e.rejoinAt; return `<span><b>${D.code} · L${e.lap}</b>${e.from ? SS.compoundBadge(e.from, null, { noAge: true }) : ''}<em>›</em>${known ? SS.compoundBadge(e.compound, null, { noAge: true }) : '<span class="dim">…</span>'}</span>`; }).join('') || '—'}</span>`, 'latest factual pit activity']);
      cells.push(['PACE CONTEXT', '<b class="dim">server analytics</b>', 'fade trends come from the server Race Read — not in this prototype']);
    }
    return `<div class="rn-grid">${cells.map(([l, v, sub]) => `<div><span class="lbl">${l}</span>${v}<small>${sub}</small></div>`).join('')}<div class="rn-facts"><span class="lbl">NOW</span>${n.facts.slice(0, compact ? 1 : 3).map((f) => `<p>${f}</p>`).join('')}</div></div>`;
  };

  SS.strategySnapshotHTML = function (s, vm) {
    const body = `<div class="ss-zones"><section><header><span class="lbl">PIRELLI TYRE STRATEGY</span>${(window.SLIPSTREAM_SERVER || {})[s.d.label] ? '<b class="pill-pub">PUBLISHED</b>' : ''}</header>${SS.pirelliHTML(s, true)}</section><section><header><span class="lbl">RACE NOW</span><b>${vm.finished ? 'COMPLETE' : 'IN PROGRESS'}</b></header>${SS.raceNowHTML(s, vm, true)}</section></div>`;
    return panel('STRATEGY CONTEXT', 'Pirelli tyre strategy · Race now', '<a class="pnl-btn" href="#strategy" data-view="strategy">VIEW STRATEGY →</a>', body, 'pnl-strat');
  };

  /* Driver landscape table (strategy page). */
  SS.landscapeHTML = function (s, vm) {
    const rows = vm.rows.map((r) => {
      const st = SS.stints(s, r.num, vm.t);
      const dr = SS.dryRule(st);
      const last = st.stops[st.stops.length - 1];
      const pub = (window.SLIPSTREAM_SERVER || {})[s.d.label];
      const opts = pub && pub.pirelli && pub.pirelli.options && pub.pirelli.options.length;
      return `<tr class="${r.out ? 'is-out' : ''}"><td class="mono">${r.pos}</td><td><i style="background:${r.colour}"></i><b>${r.code}</b></td><td>${SS.compoundBadge(r.compound, null, { noAge: true })}</td><td class="mono">${r.age != null ? r.age : '—'}</td><td class="mono">${r.pits}</td><td>${seq(st.list.map((x) => x.c))}</td><td class="dr dr-${dr.key}">${dr.text}</td><td class="mono">${last ? `L${last.lap}${last.lane ? ' · ' + last.lane.toFixed(1) + 's' : ''}` : '—'}</td><td class="dim">${pub ? (opts ? 'see options' : 'No specific Pirelli strategy published') : '—'}</td><td class="mono dim">${opts ? '' : '—'}</td></tr>`;
    }).join('');
    return panel('CURRENT RACE', 'Driver landscape', '', `<table class="land"><thead><tr><th>P</th><th>DRIVER</th><th>TYRE</th><th>AGE</th><th>STOPS</th><th>ACTUAL TYRE STRATEGY</th><th>DRY RULE</th><th>LAST STOP</th><th>PIRELLI STRATEGY</th><th>PUBLISHED STOP WINDOW</th></tr></thead><tbody>${rows}</tbody></table>`, 'pnl-land');
  };

  /* Stint chart: every car's stints across the race, from timing. */
  SS.stintChartHTML = function (s, vm) {
    const total = s.totalLaps || Math.max(1, vm.lap || 1);
    const now = Math.min(total, vm.lap || 0);
    const bars = vm.rows.map((r) => {
      const st = SS.stints(s, r.num, vm.t);
      const segs = st.list.map((x) => {
        const to = x.to != null ? x.to : r.out ? x.from : now;
        const w = Math.max(0, to - x.from);
        return `<i class="sc-${cmpL(x.c)}" style="left:${(x.from / total) * 100}%;width:${(w / total) * 100}%" title="${x.c} · laps ${x.from}–${to}"></i>`;
      }).join('');
      return `<div class="stc-row${r.out ? ' is-out' : ''}"><span class="mono">${r.pos}</span><b>${r.code}</b><div class="stc-bar">${segs}${st.stops.map((p) => `<s style="left:${(p.lap / total) * 100}%"></s>`).join('')}</div></div>`;
    }).join('');
    const ticks = Array.from({ length: Math.floor(total / 10) + 1 }, (_, i) => `<em style="left:${((i * 10) / total) * 100}%">${i * 10}</em>`).join('');
    return panel('FROM TIMING', 'Stints by lap', `<span class="dim">lap ${now} of ${total}</span>`, `<div class="stc"><div class="stc-now" style="left:calc(84px + (100% - 84px) * ${(now / total).toFixed(4)})"></div>${bars}<div class="stc-axis"><span></span><div>${ticks}</div></div></div>`, 'pnl-stints');
  };

  /* Lap-time chart for one driver (bars, last N laps). */
  SS.lapChartHTML = function (s, num, now, n = 16, stintOnly = false) {
    let laps = s.lapHistory(num).filter((x) => x.t <= now);
    const st = SS.stints(s, num, now);
    const pitLaps = new Set(st.stops.flatMap((p) => [p.lap, p.lap + 1]));
    if (stintOnly && st.list.length) { const from = st.list[st.list.length - 1].from; laps = laps.filter((x) => x.lap > from); }
    laps = laps.slice(-n);
    if (laps.length < 2) return '<div class="pnl-empty">Lap times appear after two completed laps.</div>';
    const clean = laps.filter((x) => !pitLaps.has(x.lap) && x.time < 1.07 * Math.min(...laps.map((y) => y.time)));
    const ref = clean.length ? Math.min(...clean.map((x) => x.time)) : Math.min(...laps.map((x) => x.time));
    const worst = clean.length ? Math.max(...clean.map((x) => x.time)) : ref + 1;
    const cap = ref + Math.max(0.8, (worst - ref) * 1.25);
    return `<div class="lapc">${laps.map((x) => { const v = Math.min(x.time, cap); const h = 14 + ((cap - v) / (cap - ref || 1)) * 86; const pit = pitLaps.has(x.lap); const slow = !pit && x.time > cap; return `<div class="lapc-b${pit ? ' is-pit' : ''}${slow ? ' is-slow' : ''}${x.time === ref ? ' is-best' : ''}" title="L${x.lap} · ${U.fmtLap(x.time)}"><i style="height:${pit ? 8 : h.toFixed(1)}%"></i><em class="mono">${pit ? 'PIT' : U.fmtLap(x.time).slice(-6)}</em><span class="mono">L${x.lap}</span></div>`; }).join('')}</div><p class="pnl-note">Taller = faster, scaled from ${U.fmtLap(ref)} (best clean lap) to +${(cap - ref).toFixed(1)} s. In-laps and out-laps marked PIT.</p>`;
  };
})();

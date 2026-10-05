/* Where are the cars? Four honest answers, chosen by capability:
 *  1. TrackMap   — circuit outline + approximate positions (interpolated between mini-sector crossings)
 *  2. TrackLine  — no outline, positions known: the lap straightened into a line
 *  3. GapRibbon  — race order in time (gap to leader); always available in a race
 *  4. Ladder     — timed sessions: best-lap spread with the cut line
 * Labels never overlap. Cars that share a spot become one marker with a count,
 * and a label that cannot be placed is dropped: the tower already names everyone.
 */
(function () {
  'use strict';
  const SS = window.SS;
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };

  /* Same normalisation as web/domain/trackGeometry.ts (rotation, 1000×650, padding 58). */
  SS.buildGeometry = function (path, rotation = 0) {
    if (!path || path.length < 3) return null;
    const c = path.reduce((v, p) => ({ x: v.x + p[0] / path.length, y: v.y + p[1] / path.length }), { x: 0, y: 0 });
    const a = (rotation * Math.PI) / 180;
    const rot = path.map(([x, y]) => { const dx = x - c.x, dy = y - c.y; return { x: dx * Math.cos(a) - dy * Math.sin(a), y: dx * Math.sin(a) + dy * Math.cos(a) }; });
    const minX = Math.min(...rot.map((p) => p.x)), maxX = Math.max(...rot.map((p) => p.x));
    const minY = Math.min(...rot.map((p) => p.y)), maxY = Math.max(...rot.map((p) => p.y));
    const W = 1000, H = 650, pad = 58;
    const s = Math.min((W - pad * 2) / Math.max(maxX - minX, 1), (H - pad * 2) / Math.max(maxY - minY, 1));
    const xo = (W - (maxX - minX) * s) / 2, yo = (H - (maxY - minY) * s) / 2;
    const pts = rot.map((p) => ({ x: xo + (p.x - minX) * s, y: yo + (maxY - p.y) * s }));
    const closed = [...pts, pts[0]];
    const dist = [0];
    for (let i = 1; i < closed.length; i++) dist.push(dist[i - 1] + Math.hypot(closed[i].x - closed[i - 1].x, closed[i].y - closed[i - 1].y));
    const total = dist[dist.length - 1];
    const pointAt = (f) => {
      const target = (((f % 1) + 1) % 1) * total;
      let lo = 1, hi = dist.length - 1;
      while (lo < hi) { const m = (lo + hi) >> 1; if (dist[m] >= target) hi = m; else lo = m + 1; }
      const i = lo, p0 = closed[i - 1], p1 = closed[i];
      const len = dist[i] - dist[i - 1] || 1;
      const mix = (target - dist[i - 1]) / len;
      return { x: p0.x + (p1.x - p0.x) * mix, y: p0.y + (p1.y - p0.y) * mix, nx: -(p1.y - p0.y) / len, ny: (p1.x - p0.x) / len };
    };
    return { pts, poly: closed.map((p) => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' '), pointAt, total };
  };

  /* ---------------------------------------------------------- 1-D label packing */
  const D1 = {
    tv: { font: 17, dot: 18, laneH: 27, lanes: 4 },
    desktop: { font: 11, dot: 12, laneH: 17, lanes: 3 },
    phone: { font: 10, dot: 10, laneH: 15, lanes: 3 },
  };
  /**
   * items: [{ key, x (px), prio (lower = more important), focus, label }]
   * returns Map key -> { show, count, lane (-1 = no label), shift (px) }
   */
  function pack1D(items, post, width, lanesOverride) {
    const Z = Object.assign({}, D1[post] || D1.desktop);
    if (lanesOverride) Z.lanes = lanesOverride;
    const res = new Map();
    const sorted = items.slice().sort((a, b) => a.x - b.x);
    const groups = [];
    for (const it of sorted) {
      const g = groups[groups.length - 1];
      if (g && it.x - g.x0 < Z.dot * 0.75) g.members.push(it);
      else groups.push({ x0: it.x, members: [it] });
    }
    for (const g of groups) {
      g.rep = g.members.find((m) => m.focus) || g.members.slice().sort((a, b) => a.prio - b.prio)[0];
      g.prio = Math.min(...g.members.map((m) => (m.focus ? -1 : m.prio)));
      for (const m of g.members) res.set(m.key, { show: m === g.rep, count: m === g.rep ? g.members.length : 0, lane: -1, shift: 0 });
    }
    const lanes = Array.from({ length: Z.lanes }, () => []);
    const pad = Z.font * 0.4;
    for (const g of groups.slice().sort((a, b) => a.prio - b.prio)) {
      const w = Z.font * 0.7 * g.rep.label.length + Z.font * 0.7 + (g.members.length > 1 ? Z.font * 1.2 : 0);
      let l = g.rep.x - w / 2;
      const shift = width ? Math.max(0, Math.min(width - w, l)) - l : 0;
      l += shift;
      const r = l + w;
      const lane = lanes.findIndex((ivs) => ivs.every(([a, b]) => r + pad <= a || l - pad >= b));
      if (lane === -1) continue;
      lanes[lane].push([l, r]);
      const o = res.get(g.rep.key);
      o.lane = lane;
      o.shift = shift;
    }
    return res;
  }
  SS.pack1D = pack1D;

  /* A dot on an axis with its label lifted into a lane (shared by the 1-D views). */
  const makeDot = (D) => {
    const c = document.createElement('div');
    c.className = 'd1';
    c.style.setProperty('--team', D.colour);
    c.innerHTML = `<i></i><s></s><b>${D.code}<em></em></b>`;
    return c;
  };
  const placeDot = (c, x01, p, extra = {}) => {
    if (!p || !p.show) { c.style.display = 'none'; return; }
    c.style.display = '';
    c.style.left = (x01 * 100).toFixed(3) + '%';
    c.style.setProperty('--lane', Math.max(0, p.lane));
    c.style.setProperty('--shift', p.shift.toFixed(1) + 'px');
    c.classList.toggle('no-lbl', p.lane < 0);
    const em = c.lastChild.lastChild;
    const n = p.count > 1 ? String(p.count) : '';
    if (em.textContent !== n) em.textContent = n;
    for (const [k, v] of Object.entries(extra)) c.classList.toggle(k, !!v);
  };

  /* ---------------------------------------------------------- TrackMap */
  class TrackMap {
    /** o: { session, posture, labels: n } */
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      this.geo = SS.buildGeometry(this.s.circuit.path, this.s.circuit.rotation || 0);
      root.classList.add('tmap', 'tmap--' + o.posture);
      root.innerHTML = '<svg viewBox="0 0 1000 650" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Circuit map with approximate car positions"></svg><div class="tmap-boxes"><div class="tmap-box tmap-pit" hidden><b>PIT LANE</b><span></span></div><div class="tmap-box tmap-out" hidden><b>OUT</b><span></span></div></div><div class="tmap-foot"></div>';
      const svg = (this.svg = root.querySelector('svg'));
      el('polyline', { points: this.geo.poly, class: 'trk-edge' }, svg);
      el('polyline', { points: this.geo.poly, class: 'trk-surface' }, svg);
      el('polyline', { points: this.geo.poly, class: 'trk-center' }, svg);
      const sf = this.geo.pointAt(0);
      el('line', { x1: sf.x - sf.nx * 16, y1: sf.y - sf.ny * 16, x2: sf.x + sf.nx * 16, y2: sf.y + sf.ny * 16, class: 'trk-sf' }, svg);
      this.layer = el('g', { class: 'cars' }, svg);
      this.cars = {};
      for (const num of Object.keys(this.s.drivers)) {
        const D = this.s.drivers[num];
        const g = el('g', { class: 'car', 'data-num': num }, this.layer);
        g.style.setProperty('--team', D.colour);
        el('circle', { r: 9, class: 'car-dot' }, g);
        const n = el('g', { class: 'car-n' }, g);
        el('circle', { class: 'car-n-bg' }, n);
        el('text', { class: 'car-n-t', 'text-anchor': 'middle', 'dominant-baseline': 'central' }, n);
        const t = el('text', { class: 'car-lbl', 'text-anchor': 'middle', 'dominant-baseline': 'central' }, g);
        t.textContent = D.code;
        this.cars[num] = g;
      }
      this.focus = new Set();
      this.mode = 'replay';
      this.foot = root.querySelector('.tmap-foot');
      const step = this.s.tpStep ? Math.round(1 / this.s.tpStep) : null;
      this.foot.innerHTML = `<span>CIRCUIT SHAPE · OBSERVED</span><span>POSITIONS · APPROXIMATE${step ? ` · ${step} TIMING POINTS PER LAP` : ''}</span><span class="tmap-cov"></span>`;
      this._resize = () => { const w = this.svg.clientWidth || this.svg.getBoundingClientRect().width || 1000; const h = this.svg.clientHeight || 650; this.unit = Math.max(1000 / w, 650 / h); };
      this._resize();
      // Re-measure whenever the map box changes (window, layout preset, map size, TV scale): marker and
      // label sizes are kept constant on screen by this unit.
      if (window.ResizeObserver) new ResizeObserver(() => this._resize()).observe(this.svg);
      else window.addEventListener('resize', this._resize);
    }
    setFocus(nums) { this.focus = new Set(nums || []); }
    setMode(m) { this.mode = m; }

    render(vm, t) {
      if (!this.unit || this.unit === 1) this._resize();
      const u = this.unit || 1;
      const post = this.o.posture;
      const R = (post === 'tv' ? 12 : post === 'phone' ? 7 : 8) * u;
      const fs = (post === 'tv' ? 18 : post === 'phone' ? 10.5 : 12) * u;
      const topN = this.o.labels || (post === 'phone' ? 3 : post === 'tv' ? 10 : 6);
      const pit = [], out = [], pts = [];
      for (const r of vm.rows) {
        const g = this.cars[r.num];
        if (r.out) { g.style.display = 'none'; out.push(r); continue; }
        if (r.inPit || (vm.kind !== 'race' && r.activity === 'IN_PIT')) { g.style.display = 'none'; pit.push(r); continue; }
        if (r.qe) { g.style.display = 'none'; continue; }
        const f = this.s.progressAt(r.num, t, this.mode);
        if (f == null) { g.style.display = 'none'; continue; }
        pts.push({ r, g, p: this.geo.pointAt(f), focus: this.focus.has(r.num) });
      }
      // 1. cars that share a spot become one marker with a count
      const groups = [];
      for (const it of pts) {
        const k = groups.find((q) => Math.hypot(q.p.x - it.p.x, q.p.y - it.p.y) < R * 1.3);
        if (k) k.members.push(it);
        else groups.push({ p: it.p, members: [it] });
      }
      const prio = (k) => Math.min(...k.members.map((m) => (m.focus ? -1 : m.r.index)));
      // 2. labels, most important first; never over another label or marker
      const boxes = groups.map((k) => ({ x0: k.p.x - R * 1.15, x1: k.p.x + R * (k.members.length > 1 ? 1.9 : 1.15), y0: k.p.y - R * (k.members.length > 1 ? 1.9 : 1.15), y1: k.p.y + R * 1.15 }));
      const hit = (b) => boxes.some((q) => b.x0 < q.x1 && b.x1 > q.x0 && b.y0 < q.y1 && b.y1 > q.y0);
      for (const k of groups.slice().sort((a, b) => prio(a) - prio(b))) {
        k.rep = k.members.find((m) => m.focus) || k.members[0];
        k.lbl = null;
        if (prio(k) >= topN) continue;
        const w = fs * 0.68 * k.rep.r.code.length + fs * 0.3, h = fs * 1.02;
        const p = k.p;
        const tries = [[1, 1], [-1, 1], [1, 1.8], [-1, 1.8], [1, 2.6], [-1, 2.6]];
        for (const [side, mult] of tries) {
          const off = (R + fs * 0.75) * mult;
          const cx = p.x + p.nx * off * side, cy = p.y + p.ny * off * side;
          const b = { x0: cx - w / 2, x1: cx + w / 2, y0: cy - h / 2, y1: cy + h / 2 };
          if (!hit(b)) { boxes.push(b); k.lbl = { x: cx - p.x, y: cy - p.y }; break; }
        }
        if (!k.lbl && k.rep.focus) { const off = R + fs * 0.75; k.lbl = { x: p.nx * off, y: p.ny * off }; }
      }
      // 3. draw
      const top = [];
      for (const k of groups) {
        for (const m of k.members) {
          const g = m.g;
          if (m !== k.rep) { g.style.display = 'none'; continue; }
          g.style.display = '';
          const r = m.r;
          const [c, n, tx] = g.children;
          c.setAttribute('r', (m.focus ? R * 1.3 : r.index === 0 ? R * 1.12 : R).toFixed(1));
          if (k.members.length > 1) {
            n.style.display = '';
            n.setAttribute('transform', `translate(${(R * 0.95).toFixed(1)} ${(-R * 0.95).toFixed(1)})`);
            n.firstChild.setAttribute('r', (R * 0.78).toFixed(1));
            n.lastChild.setAttribute('font-size', (fs * 0.72).toFixed(1));
            n.lastChild.textContent = k.members.length;
          } else n.style.display = 'none';
          if (k.lbl) {
            tx.style.display = '';
            tx.setAttribute('x', k.lbl.x.toFixed(1));
            tx.setAttribute('y', k.lbl.y.toFixed(1));
            tx.setAttribute('font-size', (m.focus ? fs * 1.12 : fs).toFixed(1));
          } else tx.style.display = 'none';
          g.setAttribute('transform', `translate(${k.p.x.toFixed(1)} ${k.p.y.toFixed(1)})`);
          g.classList.toggle('is-focus', m.focus);
          g.classList.toggle('is-leader', r.index === 0);
          g.classList.toggle('is-dim', this.focus.size > 0 && !m.focus);
          if (m.focus || r.index === 0) top.push(g);
        }
      }
      for (const g of top) this.layer.appendChild(g);
      const pitBox = this.root.querySelector('.tmap-pit');
      pitBox.hidden = !pit.length;
      const ph = pit.map((r) => `<em style="--team:${r.colour}">${r.code}</em>`).join('');
      if (pitBox.lastChild._v !== ph) { pitBox.lastChild.innerHTML = ph; pitBox.lastChild._v = ph; }
      // coverage, as the current app shows it: cars with a position / cars still running
      const active = vm.rows.filter((r) => !r.out && !r.qe).length;
      const cov = `COVERAGE · ${pts.length + pit.length}/${active}`;
      if (this._cov !== cov) { this._cov = cov; const f = this.foot.querySelector('.tmap-cov'); if (f) f.textContent = cov; }
      const outBox = this.root.querySelector('.tmap-out');
      outBox.hidden = !out.length;
      const oh = out.map((r) => `<em>${r.code}</em>`).join('');
      if (outBox.lastChild._v !== oh) { outBox.lastChild.innerHTML = oh; outBox.lastChild._v = oh; }
    }
  }
  SS.TrackMap = TrackMap;

  /* ---------------------------------------------------------- TrackLine */
  class TrackLine {
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('tline', 'tline--' + o.posture);
      const n = this.s.tpStep ? Math.round(1 / this.s.tpStep) : 0;
      root.innerHTML = `<div class="tline-head"><b>LAP PROGRESS</b><span>start line → start line${n ? ` · ticks are the ${n} timing points where position is known` : ''}</span></div>
        <div class="tline-track"><i class="tline-rail"></i><div class="tline-ticks">${n ? Array.from({ length: n + 1 }, (_, i) => `<i style="left:${((i / n) * 100).toFixed(3)}%"></i>`).join('') : ''}</div><div class="tline-cars"></div></div>
        <div class="tline-axis"><span>START / FINISH</span><span>FINISH</span></div>
        <div class="tline-pit"><b>PIT LANE</b><span></span></div>
        <div class="tline-foot"><span>CIRCUIT OUTLINE NOT AVAILABLE FOR ${(this.s.meta.circuit || 'THIS VENUE').toUpperCase()}</span><span>POSITIONS · APPROXIMATE · TIMING-DERIVED</span></div>`;
      this.carsEl = root.querySelector('.tline-cars');
      this.cars = {};
      for (const num of Object.keys(this.s.drivers)) {
        const c = makeDot(this.s.drivers[num]);
        c.classList.add('d1--' + o.posture);
        this.carsEl.appendChild(c);
        this.cars[num] = c;
      }
      this.focus = new Set();
      this.mode = 'replay';
    }
    setFocus(n) { this.focus = new Set(n || []); }
    setMode(m) { this.mode = m; }
    render(vm, t) {
      const pit = [];
      const items = [];
      const W = this.carsEl.offsetWidth || 800;
      const fpos = {};
      for (const r of vm.rows) {
        if (r.out || r.qe) continue;
        if (r.inPit || (vm.kind !== 'race' && r.activity === 'IN_PIT')) { pit.push(r); continue; }
        const f = this.s.progressAt(r.num, t, this.mode);
        if (f == null) continue;
        fpos[r.num] = f;
        items.push({ key: r.num, x: f * W, prio: r.index, focus: this.focus.has(r.num), label: r.code });
      }
      const res = pack1D(items, this.o.posture, W, this.o.lanes);
      for (const [num, c] of Object.entries(this.cars)) {
        const r = vm.byNum ? vm.byNum[num] : vm.rows.find((x) => x.num === num);
        placeDot(c, fpos[num] || 0, fpos[num] != null ? res.get(num) : null, { 'is-focus': this.focus.has(num), 'is-lead': r && r.index === 0 });
      }
      const ph = pit.length ? pit.map((r) => `<em style="--team:${r.colour}">${r.code}</em>`).join('') : '<em class="dim">—</em>';
      const span = this.root.querySelector('.tline-pit span');
      if (span._v !== ph) { span.innerHTML = ph; span._v = ph; }
    }
  }
  SS.TrackLine = TrackLine;

  /* ---------------------------------------------------------- GapRibbon */
  class GapRibbon {
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('ribbon', 'ribbon--' + o.posture);
      root.innerHTML = '<div class="rb-head"><b>RACE ORDER IN TIME</b><span>gap to the leader, from timing</span><span class="rb-lapped" hidden><b>LAPPED</b><span></span></span></div><div class="rb-plot"><div class="rb-axis"></div><div class="rb-links"></div><div class="rb-cars"></div><div class="rb-empty" hidden>Gaps appear once the cars cross the first timing line.</div></div>';
      this.plot = root.querySelector('.rb-plot');
      this.carsEl = root.querySelector('.rb-cars');
      this.links = root.querySelector('.rb-links');
      this.axis = root.querySelector('.rb-axis');
      this.cars = {};
      for (const num of Object.keys(this.s.drivers)) {
        const c = makeDot(this.s.drivers[num]);
        c.classList.add('d1--' + o.posture);
        this.carsEl.appendChild(c);
        this.cars[num] = c;
      }
      this.scale = null;
      this.focus = new Set();
    }
    setFocus(n) { this.focus = new Set(n || []); }
    render(vm, jumped) {
      const rows = vm.rows.filter((r) => !r.out);
      let maxGap = 0, known = 0;
      for (const r of rows) if (r.gapVal != null && !r.gapLaps) { maxGap = Math.max(maxGap, r.gapVal); known++; }
      const steps = [3, 5, 10, 20, 30, 45, 60, 90, 120, 180];
      const want = steps.find((s) => s >= maxGap * 1.05) || 180;
      if (this.scale == null || want > this.scale || (want < this.scale && maxGap * 1.05 < want * 0.85)) {
        if (want !== this.scale) {
          this.scale = want;
          const tick = want <= 5 ? 1 : want <= 20 ? 5 : want <= 45 ? 10 : want <= 90 ? 15 : 30;
          let h = '';
          for (let v = 0; v <= want + 1e-9; v += tick) h += `<span style="left:${(v / want) * 100}%"><em class="mono">${v === 0 ? 'LEADER' : '+' + v + 's'}</em></span>`;
          this.axis.innerHTML = h;
        }
      }
      this.root.classList.toggle('is-jump', !!jumped);
      const W = this.carsEl.offsetWidth || 800;
      const lapped = [];
      const items = [];
      const xs = {};
      for (const r of rows) {
        const v = r.index === 0 ? 0 : r.gapVal;
        if (r.gapLaps) { lapped.push(r); continue; }
        if (v == null) continue;
        xs[r.num] = Math.min(1, v / this.scale);
        items.push({ key: r.num, x: xs[r.num] * W, prio: r.index, focus: this.focus.has(r.num), label: r.code });
      }
      const res = pack1D(items, this.o.posture, W);
      for (const [num, c] of Object.entries(this.cars)) {
        const r = vm.byNum ? vm.byNum[num] : null;
        placeDot(c, xs[num] || 0, xs[num] != null ? res.get(num) : null, { 'is-focus': this.focus.has(num), 'is-pit': r && r.inPit, 'is-lead': r && r.index === 0 });
      }
      this.root.querySelector('.rb-empty').hidden = known > 0;
      // battle links: consecutive cars within 1 s (from lap 3, green flag)
      let lh = '';
      vm.rows.forEach((r, i) => {
        if (!r.battle || i === 0) return;
        const a = xs[vm.rows[i - 1].num], b = xs[r.num];
        if (a == null || b == null) return;
        lh += `<i style="left:${(a * 100).toFixed(2)}%;width:${Math.max(0.5, (b - a) * 100).toFixed(2)}%"></i>`;
      });
      if (this.links._v !== lh) { this.links.innerHTML = lh; this.links._v = lh; }
      const lp = this.root.querySelector('.rb-lapped');
      lp.hidden = !lapped.length;
      const lph = lapped.map((r) => `<em style="--team:${r.colour}">${r.code}</em>`).join('');
      if (lp.lastChild._v !== lph) { lp.lastChild.innerHTML = lph; lp.lastChild._v = lph; }
    }
  }
  SS.GapRibbon = GapRibbon;

  /* ---------------------------------------------------------- Ladder */
  class Ladder {
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('ladder', 'ladder--' + o.posture);
      root.innerHTML = '<div class="ld-head"><b></b><span></span></div><div class="ld-plot"><div class="ld-axis"></div><div class="ld-zone"></div><div class="ld-cut"><span></span></div><div class="ld-cars"></div></div><div class="ld-none"></div>';
      this.carsEl = root.querySelector('.ld-cars');
      this.cars = {};
      for (const num of Object.keys(this.s.drivers)) {
        const c = makeDot(this.s.drivers[num]);
        c.classList.add('d1--' + o.posture);
        this.carsEl.appendChild(c);
        this.cars[num] = c;
      }
      this.focus = new Set();
      this.span = null;
    }
    setFocus(n) { this.focus = new Set(n || []); }
    render(vm, jumped) {
      const quali = vm.kind === 'qualifying';
      const rows = vm.rows.filter((r) => !r.qe && !r.out);
      const val = (r) => (quali ? r.qGap : r.pGap);
      const timed = rows.filter((r) => val(r) != null);
      const spread = timed.length ? Math.max(...timed.map(val)) : 1;
      const span = [0.5, 1, 1.5, 2, 3, 4, 6, 10].find((s) => s >= spread * 1.04) || 10;
      if (span !== this.span) {
        this.span = span;
        const tick = span <= 1 ? 0.25 : span <= 2 ? 0.5 : span <= 4 ? 1 : 2;
        let h = '';
        for (let v = 0; v <= span + 1e-9; v += tick) h += `<span style="left:${(v / span) * 100}%"><em class="mono">${v === 0 ? 'P1' : '+' + v.toFixed(v < 1 ? 2 : 1)}</em></span>`;
        this.root.querySelector('.ld-axis').innerHTML = h;
      }
      this.root.classList.toggle('is-jump', !!jumped);
      const head = this.root.querySelector('.ld-head');
      const ht = quali ? `${vm.phase || ''} SPREAD` : 'BEST-LAP SPREAD';
      if (head.firstChild.textContent !== ht) head.firstChild.textContent = ht;
      const hs = quali ? `best lap in this segment · gap to P1${vm.advance ? ` · top ${vm.advance} go through` : ''}` : 'best lap this session · gap to P1';
      if (head.lastChild.textContent !== hs) head.lastChild.textContent = hs;
      const W = this.root.querySelector('.ld-cars').offsetWidth || 800;
      const none = [];
      const xs = {};
      const items = [];
      for (const r of rows) {
        const v = val(r);
        if (v == null) { none.push(r); continue; }
        xs[r.num] = Math.min(1, v / span);
        items.push({ key: r.num, x: xs[r.num] * W, prio: r.index, focus: this.focus.has(r.num), label: r.code });
      }
      const res = pack1D(items, this.o.posture, W);
      for (const [num, c] of Object.entries(this.cars)) {
        const r = vm.byNum ? vm.byNum[num] : null;
        placeDot(c, xs[num] || 0, xs[num] != null ? res.get(num) : null, {
          'is-focus': this.focus.has(num),
          'is-drop': quali && r && vm.advance != null && r.index >= vm.advance,
          'is-ontrack': r && r.activity === 'ON_TRACK',
        });
      }
      const cut = this.root.querySelector('.ld-cut'), zone = this.root.querySelector('.ld-zone');
      const cutRow = quali && vm.advance ? rows[vm.advance - 1] : null;
      if (cutRow && val(cutRow) != null && vm.advance < rows.length) {
        const x = Math.min(1, val(cutRow) / span);
        cut.hidden = false; zone.hidden = false;
        cut.style.left = (x * 100).toFixed(2) + '%';
        zone.style.left = (x * 100).toFixed(2) + '%';
        const ct = 'CUT · P' + vm.advance;
        if (cut.firstChild.textContent !== ct) cut.firstChild.textContent = ct;
      } else { cut.hidden = true; zone.hidden = true; }
      const nn = this.root.querySelector('.ld-none');
      const nh = none.length ? `<b>NO TIME YET</b>${none.map((r) => `<em style="--team:${r.colour}">${r.code}</em>`).join('')}` : '';
      if (nn._v !== nh) { nn.innerHTML = nh; nn._v = nh; }
    }
  }
  SS.Ladder = Ladder;
})();

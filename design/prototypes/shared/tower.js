/* Timing tower with cause-aware motion.
 *
 * Rows are keyed per driver and positioned with transforms, so a reorder is a
 * transition, not a re-render. Every movement is classified from facts that are
 * true *now* (pit lane, stopped, classification after the flag, a new lap time)
 * and styled accordingly. A jump (seek, reset, delay change) moves nothing.
 */
(function () {
  'use strict';
  const SS = window.SS;

  const DUR = {
    pass: (d) => Math.min(1150, 520 + 70 * (d - 1)),
    passed: (d) => Math.min(1150, 520 + 70 * (d - 1)),
    start: (d) => Math.min(700, 360 + 40 * d),
    pit: (d) => Math.min(1700, 820 + 80 * d),
    promoted: () => 680,
    out: (d) => Math.min(1800, 1050 + 50 * d),
    class: () => 950,
    improve: (d) => Math.min(1200, 560 + 60 * d),
    pushed: () => 600,
    deleted: (d) => Math.min(1400, 900 + 40 * d),
    neutral: () => 700,
  };
  const EASE = {
    pass: 'cubic-bezier(.45,.05,.2,1)', passed: 'cubic-bezier(.45,.05,.2,1)', start: 'cubic-bezier(.3,.6,.3,1)',
    pit: 'cubic-bezier(.6,0,.3,1)', promoted: 'cubic-bezier(.4,0,.2,1)', out: 'cubic-bezier(.55,0,.45,1)',
    class: 'cubic-bezier(.65,0,.35,1)', improve: 'cubic-bezier(.3,.9,.25,1)', pushed: 'cubic-bezier(.4,0,.2,1)',
    deleted: 'cubic-bezier(.6,0,.4,1)', neutral: 'cubic-bezier(.4,0,.2,1)',
  };
  const Z = { pass: 6, improve: 6, class: 5, start: 4, promoted: 3, neutral: 3, passed: 2, pushed: 2, deleted: 2, pit: 1, out: 1 };

  class Tower {
    /**
     * @param {HTMLElement} root
     * @param {object} o { session, columns, rowH, posture: 'tv'|'desktop'|'phone', onRow(num, ev), dividers: true }
     */
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      this.rowH = o.rowH;
      this.rows = {};
      this.follow = new Set(o.follow || []);
      this.highlight = new Set();
      root.classList.add('tw', 'tw--' + o.posture, 'tw--' + this.s.kind);
      root.style.setProperty('--row-h', this.rowH + 'px');
      root.style.setProperty('--tw-cols', o.columns.map((c) => c.w).join(' '));
      root.innerHTML = `<div class="tw-head">${o.columns.map((c) => `<span class="tw-h ${c.cls || ''}" ${c.title ? `title="${c.title}"` : ''}>${c.label || ''}</span>`).join('')}</div><div class="tw-body"><div class="tw-cut" hidden><span></span></div><div class="tw-elim" hidden><span></span></div></div>`;
      this.body = root.querySelector('.tw-body');
      this.cutEl = root.querySelector('.tw-cut');
      this.elimEl = root.querySelector('.tw-elim');
      for (const num of Object.keys(this.s.drivers)) this._makeRow(num);
      this.body.style.height = Object.keys(this.s.drivers).length * this.rowH + 'px';
      this.motionScale = o.posture === 'tv' ? 1.35 : o.posture === 'phone' ? 0.85 : 1;
      this.reduced = false;
    }

    _makeRow(num) {
      const D = this.s.drivers[num];
      const el = document.createElement('div');
      el.className = 'tw-row';
      el.dataset.num = num;
      el.style.setProperty('--team', D.colour);
      el.innerHTML = `<div class="tw-wash"></div><div class="tw-grid">${this.o.columns.map((c) => `<span class="tw-c ${c.cls || ''}"></span>`).join('')}</div><div class="tw-delta"></div><div class="tw-chips"></div>`;
      el._cells = Array.from(el.querySelectorAll('.tw-c'));
      el._html = [];
      el.addEventListener('click', (ev) => this.o.onRow && this.o.onRow(num, ev));
      this.body.appendChild(el);
      this.rows[num] = el;
    }

    setFollow(nums) { this.follow = new Set(nums); }
    setHighlight(nums) { this.highlight = new Set(nums || []); }

    /* Vertical layout: optional gaps for the qualifying cut line and eliminated block. */
    _layout(vm) {
      const y = {};
      let gap = 0;
      const H = this.rowH;
      const cutAt = vm.advance && vm.status !== 'WAITING' ? vm.advance : null;
      let elimIndex = null;
      vm.rows.forEach((r, i) => {
        if (cutAt != null && i === cutAt) gap += Math.round(H * 0.42);
        if (r.qe && elimIndex == null) { elimIndex = i; gap += Math.round(H * 0.42); }
        y[r.num] = i * H + gap;
      });
      this.body.style.height = vm.rows.length * H + gap + 'px';
      // Divider labels
      if (cutAt != null && vm.rows[cutAt]) {
        this.cutEl.hidden = false;
        this.cutEl.style.transform = `translateY(${y[vm.rows[cutAt].num] - Math.round(H * 0.42)}px)`;
        this.cutEl.style.height = Math.round(H * 0.42) + 'px';
        const cut = vm.rows[cutAt - 1];
        this.cutEl.firstChild.innerHTML = `<b>${vm.phase} CUT · TOP ${cutAt} ADVANCE</b>${cut && cut.qTime != null ? `<em class="mono">${SS.util.fmtLap(cut.qTime)}</em>` : ''}`;
      } else this.cutEl.hidden = true;
      if (elimIndex != null) {
        this.elimEl.hidden = false;
        this.elimEl.style.transform = `translateY(${y[vm.rows[elimIndex].num] - Math.round(H * 0.42)}px)`;
        this.elimEl.style.height = Math.round(H * 0.42) + 'px';
        const ph = vm.rows[elimIndex].qp;
        this.elimEl.firstChild.innerHTML = `<b>ELIMINATED</b>`;
      } else this.elimEl.hidden = true;
      return y;
    }

    _causes(vm, ctx, idxNew, moved) {
      const res = {};
      const by = vm.byNum;
      const kind = vm.kind;
      const recentPit = (r) => r.inPit || (ctx.pitEntry[r.num] != null && vm.t - ctx.pitEntry[r.num] < 45);
      for (const n of moved) {
        const el = this.rows[n];
        const from = el._idx, to = idxNew[n];
        const up = to < from;
        const r = by[n];
        const crossed = moved.filter((m) => m !== n && (up ? this.rows[m]._idx < from && idxNew[m] > to : this.rows[m]._idx > from && idxNew[m] < to)).map((m) => by[m]);
        let cause;
        if (kind === 'race') {
          // Pass styling only in green-flag running: under yellow, VSC or SC an order change is shown
          // neutrally — the cause is not established (a slow or stopped car, a correction).
          const green = vm.status === 'GREEN';
          if (vm.finished) cause = 'class';
          else if (!up) cause = r.out ? 'out' : recentPit(r) ? 'pit' : vm.lap != null && vm.lap <= 1 ? 'start' : !green ? 'neutral' : 'passed';
          else if (r.inPit) cause = 'pit';
          else if (crossed.length && crossed.every((x) => x.out || recentPit(x))) cause = 'promoted';
          else cause = vm.lap != null && vm.lap <= 1 ? 'start' : !green ? 'neutral' : 'pass';
        } else {
          if (up) cause = ctx.improved[n] && vm.t - ctx.improved[n].t < 8 ? 'improve' : 'promoted';
          else cause = ctx.deleted[n] != null && vm.t - ctx.deleted[n] < 20 ? 'deleted' : 'pushed';
        }
        res[n] = { cause, dist: Math.abs(to - from), up, crossesCut: vm.advance != null && ((from < vm.advance && to >= vm.advance) || (from >= vm.advance && to < vm.advance)) };
      }
      return res;
    }

    _chip(el, html, cls, ms) {
      const c = document.createElement('span');
      c.className = 'tw-chip ' + cls;
      c.innerHTML = html;
      el.querySelector('.tw-chips').appendChild(c);
      if (ms) setTimeout(() => { c.classList.add('is-leaving'); setTimeout(() => c.remove(), 320); }, ms);
      return c;
    }
    _delta(el, up, n, ms) {
      const d = el.querySelector('.tw-delta');
      d.className = 'tw-delta ' + (up ? 'is-up' : 'is-down');
      d.textContent = (up ? '▲' : '▼') + n;
      clearTimeout(el._deltaT);
      el._deltaT = setTimeout(() => (d.className = 'tw-delta'), ms);
    }
    _wash(el, colour, ms, peak = 0.3) {
      const w = el.querySelector('.tw-wash');
      w.style.background = colour;
      if (this.reduced || !w.animate) { w.style.opacity = peak * 0.6; clearTimeout(el._washT); el._washT = setTimeout(() => (w.style.opacity = 0), ms); return; }
      w.animate([{ opacity: 0 }, { opacity: peak, offset: 0.12 }, { opacity: peak * 0.7, offset: 0.6 }, { opacity: 0 }], { duration: ms * this.motionScale, easing: 'linear' });
    }
    _flashCell(el, key, cls) {
      let i = this.o.columns.findIndex((c) => c.key === key);
      if (i < 0 && key === 'time' && this._phaseKey) i = this.o.columns.findIndex((c) => c.key === this._phaseKey);
      if (i < 0) return;
      const cell = el._cells[i];
      cell.classList.remove(cls);
      void cell.offsetWidth;
      cell.classList.add(cls);
      clearTimeout(cell._t);
      cell._t = setTimeout(() => cell.classList.remove(cls), 2600 * this.motionScale);
    }

    /**
     * @param vm  view model
     * @param ctx { jumped, recent (SS.recentContext), reduced }
     */
    render(vm, ctx) {
      this.reduced = !!ctx.reduced;
      this._phaseKey = vm.phase && SS.PHASE_INDEX[vm.phase] != null ? 'q' + SS.PHASE_INDEX[vm.phase] : null;
      vm.byNum = vm.byNum || Object.fromEntries(vm.rows.map((r) => [r.num, r]));
      const idxNew = {};
      vm.rows.forEach((r, i) => (idxNew[r.num] = i));
      const jumped = ctx.jumped || this._first !== false;
      this._first = false;
      const moved = jumped ? [] : vm.rows.filter((r) => this.rows[r.num]._idx != null && this.rows[r.num]._idx !== idxNew[r.num]).map((r) => r.num);
      const causes = moved.length ? this._causes(vm, ctx.recent, idxNew, moved) : {};
      const ys = this._layout(vm);
      // Fast replay: shorter moves from 5×, and from 30× rows snap without cause effects — several
      // later changes would arrive before an explanation finished. Chronology over drama.
      const sp = ctx.speed || 1;
      const fast = sp >= 30;
      const ms = this.motionScale * (sp >= 5 ? 0.6 : 1);
      for (const r of vm.rows) {
        const el = this.rows[r.num];
        // cells
        this.o.columns.forEach((c, i) => {
          const html = c.cell(r, vm, ctx);
          if (el._html[i] !== html) { el._cells[i].innerHTML = html; el._html[i] = html; }
        });
        // state classes
        el.classList.toggle('is-pit', !!r.inPit && vm.kind === 'race'); // in a timed session the garage is the normal place to be
        el.classList.toggle('is-out', !!r.out);
        el.classList.toggle('is-follow', this.follow.has(r.num));
        el.classList.toggle('is-hl', this.highlight.has(r.num));
        el.classList.toggle('is-battle', !!r.battle);
        el.classList.toggle('is-elim', !!r.qe);
        el.classList.toggle('is-ontrack', vm.kind !== 'race' && r.activity === 'ON_TRACK' && !r.qe);
        el.classList.toggle('is-drop', vm.kind === 'qualifying' && vm.advance != null && r.index >= vm.advance && !r.qe && vm.status === 'GREEN');
        // pit exit → fresh tyre chip (fact: activity left the pit lane)
        if (el._wasPit && !r.inPit && !r.out && !jumped && vm.kind === 'race') {
          el._exitChip = this._chip(el, `PIT EXIT ${SS.compoundBadge(r.compound, null, { noAge: true })}`, 'chip-fresh', 7000 * ms);
          el._exitCmp = r.compound;
        }
        // the compound can arrive a moment after the car leaves the lane: keep the chip truthful
        if (el._exitChip && el._exitChip.isConnected && el._exitCmp !== r.compound) {
          el._exitCmp = r.compound;
          el._exitChip.innerHTML = `PIT EXIT ${SS.compoundBadge(r.compound, null, { noAge: true })}`;
        }
        el._wasPit = r.inPit;
        // penalty pending
        const pen = ctx.recent && ctx.recent.penalty[r.num];
        if (pen && !el._penChip && !vm.finished) el._penChip = this._chip(el, pen, 'chip-pen', 0);
        if ((!pen || vm.finished) && el._penChip) { el._penChip.remove(); el._penChip = null; }

        // lap-time improvement without a position change
        const imp = ctx.recent && ctx.recent.improved[r.num];
        if (imp && el._impT !== imp.t && !jumped && vm.t - imp.t < 3) {
          el._impT = imp.t;
          const purple = imp.type === 'SEGMENT_P1' || imp.type === 'PROVISIONAL_POLE' || imp.type === 'SESSION_BEST';
          this._flashCell(el, 'time', purple ? 'flash-purple' : 'flash-green');
          if (!causes[r.num]) this._wash(el, purple ? 'var(--time-session-best)' : 'var(--time-personal-best)', 1800, 0.16);
        } else if (imp && jumped) el._impT = imp.t;

        // movement
        const i = idxNew[r.num];
        const y = ys[r.num];
        if (jumped || el._idx == null) {
          el.style.transition = 'none';
          el.style.zIndex = '';
        } else if (el._idx !== i && fast) {
          el.style.transition = 'none';
          el.style.zIndex = '';
        } else if (el._idx !== i) {
          const c = causes[r.num];
          const dur = this.reduced ? 1 : Math.round(DUR[c.cause](c.dist) * ms);
          el.style.transition = `transform ${dur}ms ${EASE[c.cause]}`;
          el.style.zIndex = Z[c.cause];
          el.dataset.cause = c.cause;
          clearTimeout(el._causeT);
          el._causeT = setTimeout(() => { delete el.dataset.cause; el.style.zIndex = ''; }, dur + 1400 * ms);
          this._applyCause(el, r, c, vm);
        } else if (el._y !== y) {
          el.style.transition = `transform ${Math.round(400 * ms)}ms var(--ease-out)`;
        }
        if (el._y !== y) el.style.transform = `translate3d(0,${y}px,0)`;
        el._y = y;
        el._idx = i;
      }
      if (jumped) {
        this.root.classList.add('tw-jump');
        void this.root.offsetWidth;
        requestAnimationFrame(() => this.root.classList.remove('tw-jump'));
      }
    }

    _applyCause(el, r, c, vm) {
      const ms = this.motionScale;
      switch (c.cause) {
        case 'pass':
          this._wash(el, 'var(--team)', 2600, 0.3);
          this._delta(el, true, c.dist, 3600 * ms);
          el.classList.remove('pos-pulse'); void el.offsetWidth; el.classList.add('pos-pulse');
          break;
        case 'passed':
          this._delta(el, false, c.dist, 2400 * ms);
          break;
        case 'improve': {
          const purple = r.index === 0;
          this._wash(el, purple ? 'var(--time-session-best)' : 'var(--time-personal-best)', 2600, 0.26);
          this._delta(el, true, c.dist, 3600 * ms);
          el.classList.remove('pos-pulse'); void el.offsetWidth; el.classList.add('pos-pulse');
          if (c.crossesCut) this._chip(el, 'ABOVE CUT', 'chip-safe', 3500 * ms); // provisional: a later lap can still push them back
          break;
        }
        case 'pushed':
          if (c.crossesCut) { this._chip(el, 'DROP ZONE', 'chip-drop', 4200 * ms); this._wash(el, 'var(--loss)', 2200, 0.18); }
          else this._delta(el, false, c.dist, 1800 * ms);
          break;
        case 'deleted':
          this._chip(el, 'LAP DELETED', 'chip-amber', 4200 * ms);
          this._wash(el, 'var(--amber)', 2400, 0.2);
          this._flashCell(el, 'time', 'flash-strike');
          break;
        case 'class':
          this._wash(el, 'var(--amber)', 2600, 0.22);
          this._delta(el, c.up, c.dist, 5000 * ms);
          break;
        case 'out':
          this._chip(el, r.out || 'OUT', 'chip-out', 5000 * ms);
          break;
        case 'pit':
        case 'promoted':
        case 'start':
        case 'neutral':
        default:
          break;
      }
    }
  }
  SS.Tower = Tower;

  /* ---------------------------------------------------------- columns */
  const fmtNum = (v, d = 3) => (v == null ? '—' : v.toFixed(d));
  const C = {};
  C.pos = (w = '40px') => ({ key: 'pos', label: 'P', w, cls: 'c-pos', cell: (r) => `<span class="tw-pos mono">${r.pos}</span>` });
  C.driver = (w = '1fr', withName = true) => ({
    key: 'driver', label: 'DRIVER', w, cls: 'c-drv',
    cell: (r) => `<i class="tw-team"></i><b class="tw-code">${r.code}</b>${withName ? `<span class="tw-name">${SS.util.titleCase(r.surname)}</span>` : ''}`,
  });
  C.int = (w = '84px') => ({
    key: 'int', label: 'INT', w, cls: 'c-num c-int', title: 'Interval to the car ahead',
    cell: (r, vm) => {
      if (r.out) return '';
      if (r.inPit) return '<span class="pill-pit">IN PIT</span>';
      if (r.index === 0) return vm.kind === 'race' ? '<span class="dim">—</span>' : '';
      if (r.intLaps) return `<span class="dim">${r.intText}</span>`;
      const v = r.intVal;
      if (v == null) return '<span class="dim">—</span>';
      const pct = Math.max(0, Math.min(1, 1 - v / 1.0));
      return `${r.battle ? `<i class="int-bar" style="--p:${pct.toFixed(2)}"></i>` : ''}<span class="mono">+${v.toFixed(3)}</span>`;
    },
  });
  C.gap = (w = '96px') => ({
    key: 'gap', label: 'GAP', w, cls: 'c-num c-gap', title: 'Gap to the leader',
    cell: (r) => {
      if (r.out) return `<span class="st-out">${r.out}</span>`;
      if (r.index === 0) return '<span class="st-leader">LEADER</span>';
      if (r.gapLaps) return `<span class="dim mono">${r.gapText}</span>`;
      return r.gapVal == null ? '<span class="dim">—</span>' : `<span class="mono">+${r.gapVal.toFixed(3)}</span>`;
    },
  });
  C.driverTeam = (w = '1fr') => ({
    key: 'driver', label: 'DRIVER / TEAM', w, cls: 'c-drv c-drvteam',
    cell: (r) => `<i class="tw-team"></i><b class="tw-code">${r.code}</b><span class="tw-nt"><span class="tw-name">${SS.util.titleCase(r.surname)}</span><em class="tw-tm">${r.team}</em></span>`,
  });
  C.tyre = (w = '86px') => ({ key: 'tyre', label: 'TYRE', w, cls: 'c-tyre', cell: (r) => SS.compoundBadge(r.compound, r.age) });
  C.sector = (i, w = '64px') => ({
    key: 's' + i, label: 'S' + i, w, cls: 'c-num c-sec', title: 'Sector time from the latest lap (no sector colours: the feed does not grade sectors)',
    cell: (r) => { const v = r['s' + i]; return v == null || v === '' ? '<span class="dim">—</span>' : `<span class="mono">${(+v).toFixed(3)}</span>`; },
  });
  C.tyreSeq = (s, w = '1fr') => ({ key: 'tseq', label: 'TYRE STRATEGY', w, cls: 'c-tseq', cell: (r, vm) => SS.compoundSeq(SS.stints(s, r.num, vm.t).list.map((x) => x.c)) });
  C.lastStop = (s, w = '96px') => ({
    key: 'lstop', label: 'LAST STOP', w, cls: 'c-num',
    cell: (r, vm) => { const st = SS.stints(s, r.num, vm.t).stops; const p = st[st.length - 1]; return p ? `<span class="mono">L${p.lap}${p.lane ? ' · ' + p.lane.toFixed(1) + 's' : ''}</span>` : '<span class="dim">—</span>'; },
  });
  C.stops = (w = '48px') => ({ key: 'pits', label: 'STOPS', w, cls: 'c-num c-pits', cell: (r) => `<span class="mono dim">${r.pits || 0}</span>` });
  C.pits = (w = '40px') => ({ key: 'pits', label: 'PIT', w, cls: 'c-num c-pits', cell: (r) => `<span class="mono dim">${r.pits || 0}</span>` });
  C.last = (w = '104px') => ({
    key: 'time', label: 'LAST LAP', w, cls: 'c-num c-last',
    // laps far off the driver's best (out-laps, garage time in practice) stay visible but are dimmed
    cell: (r) => (r.out || !r.last ? '<span class="dim">—</span>' : `<span class="mono ${r.lastIsFastest ? 't-purple' : r.lastIsPB ? 't-green' : r.lastSec && r.bestSec && r.lastSec > r.bestSec * 1.2 ? 'dim' : ''}">${r.last}</span>`),
  });
  C.best = (w = '104px', key = 'best') => ({
    key, label: 'BEST', w, cls: 'c-num c-best',
    cell: (r) => (!r.best ? '<span class="dim">—</span>' : `<span class="mono ${r.bestIsFastest ? 't-purple' : ''}">${r.best}</span>`),
  });
  C.status = (w = '96px') => ({
    key: 'status', label: '', w, cls: 'c-status',
    cell: (r, vm) => {
      if (r.out) return `<span class="st-out">${r.out}</span>`;
      if (vm.kind !== 'race') {
        if (r.qe) return `<span class="st-elim">OUT ${r.qp || ''}</span>`;
        return r.activity === 'ON_TRACK' ? '<span class="st-track">ON TRACK</span>' : '<span class="st-pit">PIT</span>';
      }
      if (r.finished) return '<span class="st-fin">FIN</span>';
      return '';
    },
  });
  // Qualifying
  C.qtime = (w = '110px') => ({
    key: 'time', label: 'BEST', w, cls: 'c-num c-qtime',
    cell: (r, vm) => (r.qTime == null ? `<span class="dim">${r.qe ? '' : 'NO TIME'}</span>` : `<span class="mono ${r.index === 0 ? 't-purple' : ''}">${SS.util.fmtLap(r.qTime)}</span>`),
  });
  C.qgap = (w = '86px') => ({
    key: 'qgap', label: 'GAP', w, cls: 'c-num',
    cell: (r) => (r.qGap == null ? '' : r.qGap === 0 ? '<span class="dim">—</span>' : `<span class="mono">+${r.qGap.toFixed(3)}</span>`),
  });
  C.qint = (w = '80px') => ({ key: 'qint', label: 'INT', w, cls: 'c-num', cell: (r) => (r.qInt == null ? '' : `<span class="mono dim">+${r.qInt.toFixed(3)}</span>`) });
  C.qseg = (idx, w = '96px') => ({
    key: 'q' + idx, label: ['Q1', 'Q2', 'Q3'][idx], w, cls: 'c-num c-qseg',
    cell: (r, vm) => {
      const v = r.qr && r.qr[idx];
      const cur = SS.PHASE_INDEX[vm.phase] === idx;
      return v == null ? '<span class="dim">—</span>' : `<span class="mono ${cur ? '' : 'dim'}">${SS.util.fmtLap(v)}</span>`;
    },
  });
  // Practice
  C.pgap = (w = '86px') => ({ key: 'pgap', label: 'GAP', w, cls: 'c-num', cell: (r) => (r.pGap == null ? '' : r.pGap === 0 ? '<span class="dim">—</span>' : `<span class="mono">+${r.pGap.toFixed(3)}</span>`) });
  C.stint = (w = '64px', label = 'LAPS') => ({ key: 'stint', label, w, cls: 'c-num', title: 'Laps in this stint', cell: (r) => `<span class="mono dim">${r.stint != null ? r.stint : '—'}</span>` });
  C.pint = (w = '72px') => ({ key: 'pint', label: 'INT', w, cls: 'c-num', title: 'Best-lap difference to the driver above', cell: (r) => (r.pInt == null ? '' : `<span class="mono dim">+${r.pInt.toFixed(3)}</span>`) });
  SS.cols = C;
})();

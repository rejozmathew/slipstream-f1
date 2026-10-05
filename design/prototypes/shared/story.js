/* The story layer: feed (memory), ticker (TV memory), takeovers (moments).
 * Rules shared by every surface:
 *  - An event is shown only once it is available at the viewer cursor (SS.avail: `at`, not `t`).
 *  - A jump (seek, delay change, reconnect, mode change) re-reads the past silently, and so does a
 *    panel that was hidden and is revealed again: navigation is never presented as news.
 *  - Inspecting an event and replaying it are separate actions; replay remembers where you were.
 *  - At fast replay speeds explanations are coalesced instead of queued. */
(function () {
  'use strict';
  const SS = window.SS;
  const P = SS.PRIORITY;
  const avail = (e) => (SS.avail ? SS.avail(e) : e.t);

  const stamp = (s, e) => {
    if (s.kind === 'race') return e.lap != null ? 'L' + e.lap : '';
    const clock = s.clockAt(e.t);
    const ph = s.snapshot(Math.floor(e.t)).session.qualifying_phase;
    return (s.kind === 'qualifying' && ph ? ph + ' ' : '') + (clock != null ? SS.util.fmtClock(clock) : '');
  };
  SS.stamp = stamp;

  class Feed {
    /** o: { session, min: priority, max: count, posture, onPick(e) → replay, live() → bool } */
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('feed', 'feed--' + (o.posture || 'desktop'));
      root.innerHTML = '<button class="fd-newpill" type="button" hidden></button><ol class="fd-list"></ol>';
      this.list = root.querySelector('.fd-list');
      this.pill = root.querySelector('.fd-newpill');
      this.lastT = null;
      this.gen = null;
      this.lastWall = 0;
      this.open = null;      // id of the expanded (inspected) item
      this.unseen = 0;
      root.addEventListener('click', (ev) => {
        if (ev.target.closest('.fd-newpill')) { root.scrollTop = 0; this.unseen = 0; this.pill.hidden = true; return; }
        const act = ev.target.closest('[data-fdact]');
        if (act) {
          ev.stopPropagation();
          const e = this.s.events.find((x) => x.id === +act.dataset.id);
          if (act.dataset.fdact === 'replay' && e && o.onPick) o.onPick(e);
          return;
        }
        const li = ev.target.closest('[data-id]');
        if (!li) return;
        this.open = this.open === +li.dataset.id ? null : +li.dataset.id;
        this._sig = null;
        this.render(this._now, true, this.gen);
      });
      root.addEventListener('keydown', (ev) => { if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches('[data-id]')) { ev.preventDefault(); ev.target.click(); } });
      root.addEventListener('scroll', () => { if (root.scrollTop < 8 && this.unseen) { this.unseen = 0; this.pill.hidden = true; } }, { passive: true });
    }
    setMin(p) { this.o.min = p; this.lastT = null; this._sig = null; }
    render(now, jumped, gen) {
      this._now = now;
      const wall = performance.now();
      // Silent when navigating, when the generation changed while hidden, or when re-revealed.
      const silent = jumped || (gen != null && gen !== this.gen) || wall - this.lastWall > 1500 || this.lastT == null;
      this.gen = gen;
      this.lastWall = wall;
      const min = this.o.min == null ? P.FEED : this.o.min;
      const evs = this.s.events.filter((e) => avail(e) <= now && e.priority >= min).slice(-(this.o.max || 40)).reverse();
      const lapNow = this.s.kind === 'race' ? this.s.lapAt(now) : null;
      const sig = evs.map((e) => e.id).join(',') + '|' + Math.floor(now / 5) + '|' + this.open;
      if (sig === this._sig) { this.lastT = now; return; }
      this._sig = sig;
      const live = this.o.live ? this.o.live() : false;
      let added = 0;
      const html = evs.map((e) => {
        const d = SS.describe(this.s, e, now);
        const isNew = !silent && avail(e) > this.lastT;
        if (isNew) added++;
        const D = e.drivers[0] && this.s.drivers[e.drivers[0]];
        // An old battle observation is history, not a recommendation.
        const past = e.type === 'BATTLE' && lapNow != null && e.lap != null && e.lap < lapNow - 1;
        const open = this.open === e.id;
        return `<li data-id="${e.id}" tabindex="0" role="button" aria-expanded="${open}" class="fd-item tone-${d.tone}${isNew ? ' is-new' : ''}${e.priority >= P.HIGHLIGHT ? ' is-hl' : ''}${past ? ' is-past' : ''}${open ? ' is-open' : ''}" style="${D ? '--team:' + D.colour : ''}">
          <span class="fd-time mono">${stamp(this.s, e)}</span>
          <span class="fd-tag">${d.tag}${past ? ' <i class="fd-pastlbl">EARLIER</i>' : ''}${e.state === 'provisional' ? ' <i class="fd-prov">PROVISIONAL</i>' : ''}</span>
          <span class="fd-text"><b>${d.title}</b>${d.detail ? `<em>${d.detail}</em>` : ''}</span>
          ${open ? this._details(e, live) : ''}</li>`;
      }).join('');
      const keep = this.root.scrollTop > 8 && !silent;
      const oldH = this.list.scrollHeight;
      this.list.innerHTML = html || '<li class="fd-empty">Nothing yet — events appear here as they become known.</li>';
      if (keep && added) {
        // Reading older items: hold the position and say how many arrived above.
        this.root.scrollTop += this.list.scrollHeight - oldH;
        this.unseen += added;
        this.pill.textContent = `${this.unseen} new ↑`;
        this.pill.hidden = false;
      }
      if (silent) { this.unseen = 0; this.pill.hidden = true; }
      this.lastT = now;
    }
    _details(e, live) {
      const s = this.s;
      const at = avail(e);
      const clock = (t) => (SS.localClock ? SS.localClock(s, t) : SS.util.fmtClock(t));
      const rows = [`<span>Happened</span><b class="mono">${clock(e.t)}</b>`];
      if (at - e.t >= 1) rows.push(`<span>Known</span><b class="mono">${clock(at)} · ${Math.round(at - e.t)} s later</b>`);
      if (e.state) rows.push(`<span>Status</span><b>${e.state.toUpperCase()}</b>`);
      const who = (e.drivers || []).filter((n) => s.drivers[n]).slice(0, 6).map((n) => `<span class="fd-drv" style="--team:${s.drivers[n].colour}"><i></i>${s.drivers[n].code}</span>`).join('');
      const action = live
        ? '<span class="fd-livenote">Live has no rewind. This moment becomes replayable once the session is recorded.</span>'
        : `<button class="fd-act" type="button" data-fdact="replay" data-id="${e.id}">REPLAY FROM ${stamp(s, e) || 'HERE'} ▸</button>`;
      return `<div class="fd-more"><div class="fd-facts">${rows.map((r) => `<div>${r}</div>`).join('')}</div>${who ? `<div class="fd-who">${who}</div>` : ''}${action}</div>`;
    }
  }
  SS.Feed = Feed;

  /* Bottom ticker for TV: the last few things that mattered. */
  class Ticker {
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('ticker');
      root.innerHTML = '<span class="tk-lbl">LAST</span><ol class="tk-list"></ol>';
      this.list = root.querySelector('.tk-list');
      this.lastT = null;
      this.gen = null;
    }
    render(now, jumped, gen) {
      const silent = jumped || (gen != null && gen !== this.gen) || this.lastT == null;
      this.gen = gen;
      const min = this.o.min || P.HIGHLIGHT;
      const evs = this.s.events.filter((e) => avail(e) <= now && e.priority >= min && e.type !== 'BATTLE').slice(-(this.o.count || 4)).reverse();
      const sig = evs.map((e) => e.id).join(',');
      if (sig === this._sig) { this.lastT = now; return; }
      this._sig = sig;
      this.list.innerHTML = evs.map((e, i) => {
        const d = SS.describe(this.s, e, now);
        const D = e.drivers[0] && this.s.drivers[e.drivers[0]];
        const isNew = !silent && avail(e) > this.lastT;
        return `<li class="tk-item tone-${d.tone}${isNew ? ' is-new' : ''}${i === 0 ? ' is-latest' : ''}" style="${D ? '--team:' + D.colour : ''}"><span class="tk-time mono">${stamp(this.s, e)}</span><span class="tk-tag">${d.tag}${e.state === 'provisional' ? ' · PROVISIONAL' : ''}</span><b>${d.title}</b><em>${d.detail || ''}</em></li>`;
      }).join('');
      this.lastT = now;
    }
  }
  SS.Ticker = Ticker;

  /* Takeovers: one moment at a time, never covering the order.
   * Fast replay: at 5–10× holds shorten and only the newest pending card survives; from 20× only
   * results and red flags get a card; the rail, tower and ticker still carry everything. */
  const RANK = { WINNER: 5, POLE: 5, SESSION_END: 4, ELIMINATED: 4, FLAG: 3, LEAD_CHANGE: 3, STOPPED: 2, PHASE: 2 };
  class Takeover {
    /** o: { session, posture, onShow(e) } */
    constructor(root, o) {
      this.root = root;
      this.o = o;
      this.s = o.session;
      root.classList.add('to-layer', 'to-layer--' + (o.posture || 'tv'));
      this.queue = [];
      this.current = null;
      this.enabled = true;
      this.reduced = false;
      this.speed = 1;
      this._timer = null;
    }
    clear() { this.queue = []; clearTimeout(this._timer); if (this.current) this._hide(true); }
    /** Feed newly available events (forward playback only). */
    offer(events, now) {
      if (!this.enabled) return;
      const fast = this.speed >= 20, brisk = this.speed >= 5;
      for (const e of events) {
        if (e.priority < P.TAKEOVER) continue;
        if (e.type === 'LEAD_CHANGE' && e.cause !== 'ON_TRACK' && e.cause !== 'START') continue;
        if (e.type === 'FLAG' && !['VSC', 'SAFETY_CAR', 'RED_FLAG', 'RED', 'CHEQUERED'].includes(e.status)) continue;
        if (fast && !(e.type === 'WINNER' || e.type === 'POLE' || (e.type === 'FLAG' && /RED/.test(e.status)))) continue;
        // a newer explanation of the same kind supersedes a pending or showing one
        this.queue = this.queue.filter((q) => q.type !== e.type);
        if (this.current && this.current.e.type === e.type && !/WINNER|POLE|ELIMINATED/.test(e.type)) this._hide(true);
        this.queue.push(e);
      }
      if (brisk && this.queue.length > 1) this.queue = [this.queue.sort((a, b) => (RANK[b.type] || 0) - (RANK[a.type] || 0))[0]];
      if (this.queue.length > 3) this.queue = this.queue.slice(-3);
      this._pump(now);
    }
    _pump(now) {
      const wall = performance.now();
      if (this.current && wall - this.current.at < this.current.minHold) return;
      if (this.current && this.queue.length === 0) {
        if (wall - this.current.at >= this.current.hold) this._hide();
        return;
      }
      if (!this.queue.length) return;
      this._show(this.queue.shift(), now);
    }
    tick(now) { this._pump(now); }
    _show(e, now) {
      if (this.current) this._hide(true);
      const card = document.createElement('div');
      card.className = 'to-card to--' + e.type.toLowerCase() + (e.status ? ' to-flag--' + e.status.toLowerCase() : '');
      card.setAttribute('role', 'status');
      card.innerHTML = SS.takeoverHTML(this.s, e, now);
      const D = e.drivers && e.drivers[0] && this.s.drivers[e.drivers[0]];
      if (D) card.style.setProperty('--team', D.colour);
      this.root.appendChild(card);
      const scale = this.speed >= 5 ? 0.6 : 1;
      const hold = (e.type === 'WINNER' || e.type === 'POLE' || e.type === 'ELIMINATED' ? 9000 : e.type === 'FLAG' ? 4200 : 5600) * scale;
      this.current = { e, card, at: performance.now(), hold, minHold: 2600 * scale };
      if (!this.reduced && card.animate) card.animate([{ opacity: 0, transform: 'translateY(22px) scale(.985)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.22,1,.36,1)' });
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this._pump(now), hold + 30);
      if (this.o.onShow) this.o.onShow(e);
    }
    _hide(instant) {
      const cur = this.current;
      if (!cur) return;
      this.current = null;
      if (this.o.onHide) this.o.onHide(cur.e);
      if (instant || this.reduced || !cur.card.animate) { cur.card.remove(); return; }
      const a = cur.card.animate([{ opacity: 1 }, { opacity: 0, transform: 'translateY(-10px)' }], { duration: 280, easing: 'ease-in', fill: 'forwards' });
      a.onfinish = () => cur.card.remove();
    }
  }
  SS.Takeover = Takeover;

  /* Card markup per event type. Uses only what is known at the viewer cursor (now). */
  SS.takeoverHTML = function (s, e, now) {
    const D = s.drivers;
    const d = SS.describe(s, e, now);
    const name = (n) => (D[n] ? `<span class="to-first">${(D[n].name || '').split(' ')[0]}</span> ${SS.util.titleCase(D[n].surname)}` : n);
    const chip = (n, extra = '') => (D[n] ? `<span class="to-drv" style="--team:${D[n].colour}"><i></i><b>${D[n].code}</b>${extra}</span>` : '');
    const prov = e.state === 'provisional' ? ' · PROVISIONAL' : '';
    switch (e.type) {
      case 'FLAG':
        return `<div class="to-flagbox"><span class="to-tag">${s.kind === 'race' && e.lap ? 'LAP ' + e.lap : SS.stamp(s, e)}</span><strong>${d.title}</strong><em>${d.detail || ''}</em></div>`;
      case 'WINNER': {
        // Podium as known at the viewer's moment: gaps only for cars that have already taken the flag.
        const snap = s.snapshot(Math.floor(now));
        const cards = e.drivers.map((n, i) => {
          const dd = snap.drivers[n] || {};
          const gap = i === 0 ? 'WINNER' : dd.cl === 'FINISHED' ? SS.util.parseGap(dd.g).text || '' : 'ON FINAL LAP';
          return `<div class="to-pod to-pod--${i + 1}" style="--team:${D[n].colour}"><span class="to-pod-p">P${i + 1}</span><b>${D[n].code}</b><span class="to-pod-n">${SS.util.titleCase(D[n].surname)}</span><span class="to-pod-g mono">${gap}</span></div>`;
        }).join('');
        return `<div class="to-head"><span class="to-tag">CHEQUERED FLAG · LAP ${e.lap}${prov || ' · PROVISIONAL'}</span><strong>${name(e.drivers[0])} wins</strong></div><div class="to-podium">${cards}</div>`;
      }
      case 'ELIMINATED':
        return `<div class="to-head"><span class="to-tag">${d.tag}${prov}</span><strong>${e.drivers.length} drivers eliminated</strong></div><div class="to-list">${e.drivers.map((n) => chip(n)).join('')}</div>`;
      case 'POLE': {
        const top = (e.top || []).slice(0, 2);
        return `<div class="to-head"><span class="to-tag">POLE POSITION · ${(s.meta.meeting_name || '').toUpperCase()}${prov}</span><strong>${name(e.drivers[0])}</strong><em class="mono">${SS.util.fmtLap(e.time)}</em></div><div class="to-list">${top.map((n, i) => chip(n, `<small>${i === 0 ? 'POLE' : 'P2'}</small>`)).join('')}</div>`;
      }
      case 'SESSION_END':
        return `<div class="to-head"><span class="to-tag">SESSION COMPLETE${prov}</span><strong>${name(e.drivers[0])} fastest</strong></div><div class="to-list">${e.drivers.map((n, i) => chip(n, `<small>P${i + 1}</small>`)).join('')}</div>`;
      case 'PHASE': {
        const pol = SS.qualiPolicy ? SS.qualiPolicy(s) : null;
        const field = Object.keys(D).length, el = field >= 22 ? 6 : 5;
        const n2 = pol && pol.q2 ? pol.q2 : field - el, n3 = pol && pol.q3 ? pol.q3 : field - 2 * el;
        return `<div class="to-head"><span class="to-tag">SEGMENT CHANGE</span><strong>${e.phase} is next</strong><em>${e.phase === 'Q2' ? `${n2} cars · top ${n3} advance` : e.phase === 'Q3' ? `${n3} cars · fight for pole` : ''}</em></div>`;
      }
      case 'LEAD_CHANGE':
        return `<div class="to-slab"></div><div class="to-head"><span class="to-tag">${d.tag}</span><strong>${name(e.drivers[0])}</strong><em>${d.detail}</em></div><div class="to-list">${chip(e.drivers[0], '<small>P1</small>')}${chip(e.drivers[1], '<small>P2</small>')}</div>`;
      case 'STOPPED':
        return `<div class="to-slab"></div><div class="to-head"><span class="to-tag">${d.tag}</span><strong>${name(e.drivers[0])}</strong><em>${d.detail}</em></div>`;
      default:
        return `<div class="to-slab"></div><div class="to-head"><span class="to-tag">${d.tag}</span><strong>${e.drivers && e.drivers[0] ? name(e.drivers[0]) : d.title}</strong><em>${d.detail}</em></div>`;
    }
  };
})();

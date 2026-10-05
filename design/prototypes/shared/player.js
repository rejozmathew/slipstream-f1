/* Playback controller + transport UI.
 * Replay: play/pause, speed, seek (a seek is a jump: no motion, no callouts), sync offset.
 * Live (simulated from the recording for review): the live edge advances in real time. The viewer
 * sits `delay` seconds behind it. Pausing holds the cursor while the edge moves on, so the delay
 * grows (like pausing a TV); resuming keeps the new delay. No seek and no speed in live: ←/→ change
 * the delay instead. Every command passes the same capability check (pointer, keyboard, remote).
 * Stale/reconnect: the cursor freezes, then catches up silently (a jump, not news). */
(function () {
  'use strict';
  const SS = window.SS;
  const MAX_LIVE_DELAY = 300; // 5:00 — the server's per-viewer delay buffer in this prototype

  class Player {
    constructor(session, o = {}) {
      this.s = session;
      this.o = o;
      this.cursor = new SS.Cursor(session);
      this.t = o.startAt != null ? o.startAt : session.begin;
      this.cursor.reset(this.t);
      this.speed = o.speed || 1;
      this.playing = false;
      this.mode = o.mode || 'replay';
      this.delay = 0;            // effective seconds behind the live edge (live) / sync offset (replay)
      this.requestedDelay = 0;   // what the viewer asked for; may exceed what the buffer holds
      this.edge = null;          // live edge in source time
      this.liveState = 'LIVE';
      this.staleSince = null;
      this.gen = 0;              // navigation generation: bumps on every jump (seek, delay, reconnect, mode)
      this.horizon = this.t;     // furthest point this viewer has reached (spoiler policy)
      this.returnPoint = null;   // where to go back to after replaying a moment
      this._listeners = [];
      this._pendingJump = true;
      this._last = performance.now();
      this._raf = requestAnimationFrame(this._tick.bind(this));
    }
    on(fn) { this._listeners.push(fn); }
    /** Capability check shared by every input path. */
    can(cmd) {
      if (this.mode !== 'live') return true;
      return ['play', 'pause', 'toggle', 'delay', 'golive'].includes(cmd);
    }
    play() {
      if (this.mode !== 'live' && this.t >= this.s.end) this._jump(this.s.begin);
      this.playing = true; this._last = performance.now();
      if (this.mode === 'live') this.requestedDelay = this.delay;
      this._emitState();
    }
    pause() { this.playing = false; this._emitState(); }
    toggle() { this.playing ? this.pause() : this.play(); }
    seek(t) { if (!this.can('seek')) return false; return this._jump(t); }
    skip(dt) { return this.seek(this.t + dt); }
    setSpeed(x) { if (!this.can('speed')) return false; this.speed = x; this._emitState(); return true; }
    _jump(t) {
      this.t = Math.max(this.s.begin, Math.min(this.s.end, t));
      this.cursor.reset(this.t);
      this._pendingJump = true;
      this.gen++;
      this._emitState();
      return true;
    }
    setMode(m) {
      this.mode = m;
      if (m === 'live') {
        this.speed = 1; this.liveState = 'LIVE';
        this.edge = Math.min(this.s.end, this.t + this.delay);
        this.playing = true; this._last = performance.now();
      } else {
        this.edge = null;
      }
      this._pendingJump = true; this.gen++;
      this._emitState();
    }
    /** Live: seconds behind the live edge, limited by the buffer. Replay: a sync offset (moves the cursor). */
    setDelay(sec) {
      sec = Math.max(0, Math.round(sec));
      if (this.mode === 'live') {
        this.requestedDelay = Math.min(sec, MAX_LIVE_DELAY);
        const available = Math.max(0, this.edge - this.s.begin);
        this.delay = Math.min(this.requestedDelay, available);
        return this._jump(this.edge - this.delay);
      }
      const d = sec - this.delay;
      this.delay = sec; this.requestedDelay = sec;
      return this._jump(this.t - d);
    }
    nudgeDelay(d) { return this.setDelay(Math.max(0, Math.min(MAX_LIVE_DELAY, Math.round(this.delay) + d))); }
    goLive() { this.setDelay(0); this.playing = true; this._emitState(); }
    /** Remember where the viewer was before replaying a moment, so they can return. */
    markReturn() { this.returnPoint = { t: this.t, playing: this.playing, speed: this.speed }; this._emitState(); }
    goReturn() {
      const r = this.returnPoint; if (!r) return;
      this.returnPoint = null; this._jump(r.t); this.speed = r.speed; this.playing = r.playing; this._emitState();
    }
    simulateStale(seconds = 9) {
      if (this.mode !== 'live') return;
      this.liveState = 'STALE';
      this.staleSince = performance.now();
      this._staleFor = seconds;
      this._emitState();
    }
    _emitState() { if (this.o.onState) this.o.onState(this); }
    _tick(now) {
      const dt = Math.min(0.25, (now - this._last) / 1000);
      this._last = now;
      let jumped = this._pendingJump;
      this._pendingJump = false;
      let crossed = [];
      const prevT = this.t;
      if (this.mode === 'live') {
        this.edge = Math.min(this.s.end, this.edge + dt); // the world keeps going
        if (this.liveState !== 'LIVE') {
          // Stale feed freezes the cursor; reconnect catches up silently to the same delay.
          const el = (now - this.staleSince) / 1000;
          if (this.liveState === 'STALE' && el > this._staleFor) this.liveState = 'RECONNECTING';
          if (this.liveState === 'RECONNECTING' && el > this._staleFor + 2.2) {
            this.liveState = 'LIVE';
            this._jump(this.edge - this.delay);
            jumped = true;
            this._pendingJump = false;
          }
          this._emitState();
        } else if (this.playing) {
          this.t = Math.max(this.s.begin, this.edge - this.delay);
        } else {
          // Paused in live: the delay grows while the edge moves on, up to the buffer limit.
          this.delay = this.edge - this.t;
          this.requestedDelay = this.delay;
          if (this.delay >= MAX_LIVE_DELAY) { this.delay = MAX_LIVE_DELAY; this.playing = true; this._limitHit = performance.now(); this._emitState(); }
        }
      } else if (this.playing) {
        this.t = Math.min(this.s.end, this.t + dt * this.speed);
        if (this.t >= this.s.end) { this.playing = false; this._emitState(); }
      }
      if (this.t > this.horizon) this.horizon = this.t;
      const r = this.cursor.advanceTo(this.t);
      if (r.jumped) { jumped = true; }
      if (!jumped && this.t > prevT) crossed = this.s.eventsBetween(prevT, this.t);
      for (const fn of this._listeners) fn({ now: this.t, jumped, crossed, cursor: this.cursor, player: this, gen: this.gen });
      this._raf = requestAnimationFrame(this._tick.bind(this));
    }
    staleSeconds() { return this.staleSince ? Math.floor((performance.now() - this.staleSince) / 1000) : 0; }
    /** Seconds the viewer is behind the live edge (live only). */
    behind() { return this.mode === 'live' ? Math.max(0, this.edge - this.t) : 0; }
  }
  Player.MAX_LIVE_DELAY = MAX_LIVE_DELAY;
  SS.Player = Player;

  /* Event markers on the scrubber: where the story happened. */
  const MARK = (e) => {
    if (e.type === 'LEAD_CHANGE') return 'mk-lead';
    if (e.type === 'FLAG' && ['VSC', 'SAFETY_CAR', 'VSC_ENDING', 'YELLOW'].includes(e.status)) return 'mk-yellow';
    if (e.type === 'FLAG' && ['RED', 'RED_FLAG'].includes(e.status)) return 'mk-red';
    if (e.type === 'FLAG' && e.status === 'CHEQUERED') return 'mk-cheq';
    if (e.type === 'STOPPED') return 'mk-out';
    if (e.type === 'PIT_IN' && e.priority >= SS.PRIORITY.HIGHLIGHT) return 'mk-pit';
    if (['PROVISIONAL_POLE', 'SEGMENT_P1', 'SESSION_BEST', 'POLE'].includes(e.type)) return 'mk-purple';
    if (['ELIMINATED', 'PHASE'].includes(e.type)) return 'mk-phase';
    if (e.type === 'PENALTY') return 'mk-amber';
    return null;
  };

  const SPEEDS = [0.5, 1, 2, 5, 10, 30, 60, 120];
  const DELAYS = [0, 5, 10, 30, 60, 120, 180, 300];
  const fmtDelay = (sec) => { sec = Math.max(0, Math.round(sec)); return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`; };
  const parseDelay = (txt) => {
    const m = /^\s*(\d{1,2})(?::(\d{1,2}))?\s*$/.exec(txt || '');
    if (!m) return null;
    const v = m[2] != null ? +m[1] * 60 + +m[2] : +m[1];
    return v >= 0 && v <= 300 ? v : null;
  };
  const presetLbl = (x, live) => (x === 0 ? (live ? 'LIVE' : '0s') : x < 60 ? x + 's' : x / 60 + 'm');
  SS.fmtDelay = fmtDelay;
  SS.parseDelay = parseDelay;
  SS.SPEEDS = SPEEDS;
  SS.DELAYS = DELAYS;
  /** Spoiler policy for timeline markers and the moments list: 'safe' shows only what this viewer
   * has already reached; 'all' shows the whole session (completed-session review only). */
  SS.spoilers = { get() { return SS.prefs ? SS.prefs.get('spoilers', 'safe') : 'safe'; }, set(v) { if (SS.prefs) SS.prefs.set('spoilers', v); } };

  class Transport {
    /** o: { posture: 'desktop'|'phone', moments: true } */
    constructor(root, player, o = {}) {
      this.root = root;
      this.p = player;
      this.s = player.s;
      this.o = o;
      const phone = o.posture === 'phone';
      root.classList.add('tp', 'tp--' + (o.posture || 'desktop'));
      const span = this.s.end - this.s.begin;
      const marks = this.s.events.map((e) => [e, MARK(e)]).filter(([, m]) => m).map(([e, m]) => `<i class="tp-mk ${m}" data-at="${SS.avail ? SS.avail(e) : e.t}" style="left:${(((e.t - this.s.begin) / span) * 100).toFixed(2)}%" title="${SS.describe(this.s, e).title}"></i>`).join('');
      const delayPresets = DELAYS.map((x) => `<button class="tp-d" data-d="${x}" type="button">${presetLbl(x, true)}</button>`).join('');
      root.innerHTML = `
        <div class="tp-replay">
          <div class="tp-btns">
            <button class="tp-b" data-a="start" type="button" title="Return to session start">|&lt;</button>
            <button class="tp-b" data-a="back" type="button" title="Back 30 s (←)">−30s</button>
            <button class="tp-b tp-play" data-a="play" type="button" title="Play / pause (space)"><span class="i-play">PLAY</span><span class="i-pause">PAUSE</span></button>
            <button class="tp-b" data-a="fwd" type="button" title="Forward 30 s (→)">+30s</button>
          </div>
          <div class="tp-scrubwrap"><div class="tp-scrub"><div class="tp-marks">${marks}</div><input type="range" min="${this.s.begin}" max="${this.s.end}" step="1" value="${player.t}" aria-label="Replay position"><div class="tp-fill"></div></div>
            <div class="tp-meta"><time class="mono tp-el"></time><span class="mono tp-sess"></span><time class="mono tp-total"></time></div></div>
          <button class="tp-b tp-return" data-a="return" type="button" hidden title="Go back to where you were before replaying a moment"></button>
          <label class="tp-field"><span class="lbl">SPEED</span><select class="tp-speed" aria-label="Replay speed">${SPEEDS.map((x) => `<option value="${x}">${x}×</option>`).join('')}</select></label>
          <form class="tp-field tp-sync" title="Shift this replay to line up with a recorded broadcast"><span class="lbl">SYNC OFFSET</span><span class="tp-num"><input class="mono" type="number" min="0" max="300" step="1" value="0" aria-label="Sync offset, seconds"><em>SEC</em></span><button class="tp-b" type="submit">APPLY</button></form>
          ${o.moments !== false ? `<div class="tp-moments"><button class="tp-b tp-mbtn" data-a="moments" type="button" aria-haspopup="true">MOMENTS ▾</button><div class="tp-menu" hidden><div class="tp-mlist"></div><label class="tp-spoil"><input type="checkbox" class="tp-spoilchk"> Show the whole session (spoilers)</label></div></div>` : ''}
        </div>
        <div class="tp-live">
          <span class="tp-livebadge"></span>
          <button class="tp-b tp-lpause" data-a="play" type="button" title="Pause: the timing holds and your delay grows, like pausing your TV (space)"><span class="i-play">RESUME</span><span class="i-pause">PAUSE</span></button>
          <div class="tp-delay" role="group" aria-label="Live delay"><span class="lbl">DELAY</span>${delayPresets}</div>
          <form class="tp-field tp-custom"><span class="lbl">M:SS</span><input class="mono" maxlength="4" placeholder="0:00" aria-label="Custom live delay M:SS"><button class="tp-b" type="submit">APPLY</button></form>
          <button class="tp-b tp-golive" data-a="golive" type="button" title="Back to the live edge (0 s)">GO LIVE</button>
          <span class="tp-behind mono"></span>
          <span class="tp-err" role="alert" hidden></span>
          <button class="tp-b tp-stale" data-a="stale" type="button" title="Prototype only: demonstrate a stale feed">SIMULATE FEED DROP</button>
        </div>
        ${phone ? `<button class="tp-b tp-delaybtn" data-a="delaysheet" type="button"><span class="lbl">DELAY</span><b class="mono tp-delayval">0:00</b> ▾</button>
        <div class="tp-sheet" hidden><header><b class="tp-sheet-t">Delay</b><span class="tp-sheet-s"></span></header><div class="tp-sheetp">${DELAYS.map((x) => `<button class="tp-d" data-d="${x}" type="button">${presetLbl(x, false)}</button>`).join('')}</div><form class="tp-field tp-custom"><span class="lbl">CUSTOM M:SS</span><input class="mono" maxlength="4" placeholder="0:00"><button class="tp-b" type="submit">APPLY</button></form><button class="tp-b" data-a="closesheet" type="button">DONE</button></div>` : ''}`;
      this.range = root.querySelector('input[type=range]');
      this.speedSel = root.querySelector('.tp-speed');
      this.marks = [...root.querySelectorAll('.tp-mk')];
      const err = root.querySelector('.tp-err');
      const showErr = (m) => { err.textContent = m; err.hidden = !m; };
      this.showErr = showErr;
      root.addEventListener('click', (ev) => {
        const b = ev.target.closest('button');
        if (!b) return;
        const a = b.dataset.a;
        if (a === 'play') player.toggle();
        else if (a === 'back') player.skip(-30);
        else if (a === 'fwd') player.skip(30);
        else if (a === 'start') player.seek(this.s.begin);
        else if (a === 'return') player.goReturn();
        else if (a === 'moments') { const m = root.querySelector('.tp-menu'); m.hidden = !m.hidden; if (!m.hidden) this._renderMoments(); }
        else if (a === 'stale') player.simulateStale(8);
        else if (a === 'golive') { player.goLive(); showErr(''); }
        else if (a === 'delaysheet') root.querySelector('.tp-sheet').hidden = !root.querySelector('.tp-sheet').hidden;
        else if (a === 'closesheet') root.querySelector('.tp-sheet').hidden = true;
        if (b.dataset.m != null) { const m = this.s.moments[+b.dataset.m]; player.markReturn(); player.seek(m.t); player.play(); root.querySelector('.tp-menu').hidden = true; }
        if (b.dataset.d != null) { player.setDelay(+b.dataset.d); showErr(''); }
      });
      const chk = root.querySelector('.tp-spoilchk');
      if (chk) { chk.checked = SS.spoilers.get() === 'all'; chk.addEventListener('change', () => { SS.spoilers.set(chk.checked ? 'all' : 'safe'); this._renderMoments(); this._hz = -1; }); }
      document.addEventListener('click', (ev) => { const m = root.querySelector('.tp-menu'); if (m && !m.hidden && !ev.target.closest('.tp-moments')) m.hidden = true; });
      root.querySelector('.tp-sync').addEventListener('submit', (ev) => { ev.preventDefault(); const v = Math.max(0, Math.min(300, Math.round(+ev.target.querySelector('input').value || 0))); player.setDelay(v); });
      root.querySelectorAll('.tp-custom').forEach((f) => f.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const v = parseDelay(f.querySelector('input').value);
        if (v == null) { showErr('Enter M:SS from 0:00 to 5:00.'); return; }
        showErr('');
        player.setDelay(v);
      }));
      this.range.addEventListener('input', () => player.seek(+this.range.value));
      this.speedSel.addEventListener('change', () => player.setSpeed(+this.speedSel.value));
      this.speedSel.value = String(player.speed);
      this._hz = -1;
    }
    _renderMoments() {
      const list = this.root.querySelector('.tp-mlist');
      if (!list) return;
      const all = SS.spoilers.get() === 'all';
      const items = this.s.moments.map((m, i) => [m, i]).filter(([m]) => all || m.t <= this.p.horizon);
      const hiddenN = this.s.moments.length - items.length;
      list.innerHTML = items.map(([m, i]) => `<button data-m="${i}" type="button"><b>${m.label}</b><em>${m.note || ''}</em></button>`).join('')
        + (hiddenN ? `<p class="tp-mnote">${hiddenN} later moment${hiddenN === 1 ? '' : 's'} hidden until you reach ${hiddenN === 1 ? 'it' : 'them'}.</p>` : '')
        + (!items.length ? '<p class="tp-mnote">Nothing yet — moments appear here once you have watched them.</p>' : '');
    }
    update() {
      const p = this.p, s = this.s;
      this.root.dataset.mode = p.mode;
      this.root.classList.toggle('is-playing', p.playing);
      if (document.activeElement !== this.range) this.range.value = String(Math.floor(p.t));
      const span = s.end - s.begin;
      this.root.querySelector('.tp-fill').style.transform = `scaleX(${((p.t - s.begin) / span).toFixed(4)})`;
      // spoiler-safe markers: only what this viewer has reached (re-evaluated as the horizon moves)
      const hz = SS.spoilers.get() === 'all' ? Infinity : Math.floor(p.horizon / 5);
      if (hz !== this._hz) { this._hz = hz; const lim = hz === Infinity ? Infinity : p.horizon; for (const m of this.marks) m.hidden = +m.dataset.at > lim; }
      const el = Math.max(0, p.t - s.begin);
      const set = (sel, v) => { const e = this.root.querySelector(sel); if (e && e.textContent !== v) e.textContent = v; };
      set('.tp-el', 'ELAPSED ' + SS.util.fmtClock(el, true));
      set('.tp-sess', s.kind === 'race' ? `LAP ${s.lapAt(p.t) || '—'}/${s.totalLaps || '—'} · ${SS.localClock ? SS.localClock(s, p.t) + ' LOCAL' : ''}` : (s.clockAt(p.t) != null ? SS.util.fmtClock(s.clockAt(p.t)) + ' LEFT · ' : '') + (SS.localClock ? SS.localClock(s, p.t) + ' LOCAL' : ''));
      set('.tp-total', 'TOTAL ' + SS.util.fmtClock(span, true));
      if (this.speedSel.value !== String(p.speed)) this.speedSel.value = String(p.speed);
      const sync = this.root.querySelector('.tp-sync input');
      if (sync && document.activeElement !== sync && +sync.value !== p.delay) sync.value = String(p.mode === 'live' ? 0 : p.delay);
      const ret = this.root.querySelector('.tp-return');
      const rp = p.returnPoint;
      ret.hidden = !rp || p.mode === 'live';
      if (rp) set('.tp-return', `↩ BACK TO ${s.kind === 'race' ? 'L' + (s.lapAt(rp.t) || '—') + ' · ' : ''}${SS.localClock ? SS.localClock(s, rp.t) : ''}`);
      this.root.querySelector('.tp-livebadge').innerHTML = SS.modeBadge({ kind: 'live', state: p.liveState, delay: p.delay, paused: p.mode === 'live' && !p.playing, staleFor: p.staleSeconds() + 's' });
      const live = p.mode === 'live';
      const d = Math.round(live ? p.requestedDelay : p.delay);
      this.root.querySelectorAll('.tp-d').forEach((b) => b.classList.toggle('is-on', +b.dataset.d === d));
      this.root.querySelectorAll('.tp-custom input').forEach((i) => { if (document.activeElement !== i) i.value = SS.fmtDelay(live ? p.delay : p.delay); });
      let behind = '';
      if (live) {
        if (p.liveState !== 'LIVE') behind = 'HOLDING YOUR DELAY';
        else if (!p.playing) behind = `PAUSED · ${fmtDelay(p.delay)} BEHIND LIVE ▲`;
        else if (p.requestedDelay - p.delay > 1) behind = `ASKED ${fmtDelay(p.requestedDelay)} · BUFFER HOLDS ${fmtDelay(p.delay)}`;
        else behind = p.delay >= 1 ? `${fmtDelay(p.delay)} BEHIND LIVE` : 'AT THE LIVE EDGE';
        if (p._limitHit && performance.now() - p._limitHit < 4000) behind = 'REACHED THE 5:00 DELAY LIMIT · RESUMED';
      }
      set('.tp-behind', behind);
      set('.tp-delayval', live ? (p.delay >= 1 ? '−' + SS.fmtDelay(p.delay) : 'LIVE') : (p.delay ? '+' + SS.fmtDelay(p.delay) : '0:00'));
      const st = this.root.querySelector('.tp-sheet-t'); if (st) { set('.tp-sheet-t', live ? 'Live delay' : 'Sync offset'); set('.tp-sheet-s', live ? 'Match your TV broadcast. 0–5 min behind live.' : 'Shift this replay to line up with a recorded broadcast.'); }
    }
  }
  SS.Transport = Transport;
})();

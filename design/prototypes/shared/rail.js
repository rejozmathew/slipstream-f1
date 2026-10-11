/* Status rail: the one element you read first, on every posture.
 * Calm when green, loud when not. Escalations wipe in and blink three times;
 * de-escalations cross-fade quietly. Unknown status is omitted, not shouted. */
(function () {
  'use strict';
  const SS = window.SS;

  const WORD = {
    GREEN: 'GREEN', YELLOW: 'YELLOW', VSC: 'VIRTUAL SAFETY CAR', VSC_ENDING: 'VSC ENDING', SAFETY_CAR: 'SAFETY CAR',
    RED_FLAG: 'RED FLAG', RED: 'RED FLAG', CHEQUERED: 'CHEQUERED FLAG', FINISHED: 'FINISHED', WAITING: 'STARTING SOON',
  };
  const SHORT = { VSC: 'VSC', VSC_ENDING: 'VSC ENDING', SAFETY_CAR: 'SAFETY CAR', CHEQUERED: 'CHEQUERED', RED_FLAG: 'RED FLAG', RED: 'RED FLAG', WAITING: 'NEXT' };
  const SEVERITY = { null: 0, FINISHED: 0, WAITING: 0, GREEN: 1, YELLOW: 2, VSC_ENDING: 2, VSC: 3, SAFETY_CAR: 3, CHEQUERED: 3, RED: 4, RED_FLAG: 4 };

  class StatusRail {
    /** @param o { posture: 'tv'|'desktop'|'phone', intensity: 'calm'|'bold' } */
    constructor(root, o = {}) {
      this.root = root;
      this.o = o;
      root.classList.add('rail', 'rail--' + (o.posture || 'desktop'));
      root.dataset.intensity = o.intensity || 'calm';
      root.innerHTML = `
        <div class="rail-flag"><span class="rail-word"></span><span class="rail-sub"></span></div>
        <div class="rail-mid">
          <div class="rail-session"><b class="rail-meeting"></b><span class="rail-name"></span></div>
          <div class="rail-progress-txt"><span class="rail-big mono"></span><span class="rail-small"></span></div>
          <div class="rail-chips"></div>
          <div class="rail-clock"></div>
        </div>
        <div class="rail-mode"></div>
        <div class="rail-wipe" aria-hidden="true"></div>
        <div class="rail-line" aria-hidden="true"><i></i></div>`;
      this.$ = (s) => root.querySelector(s);
      this.status = undefined;
      this.reduced = false;
    }
    setIntensity(v) { this.root.dataset.intensity = v; }

    /**
     * @param d { status, phaseLabel, meeting, session, big, small, chips:[{cls,html}], mode:{kind:'live'|'replay', ...}, progress (0..1) , jumped }
     */
    update(d) {
      const st = d.status || null;
      if (st !== this.status) {
        const prev = this.status;
        this.status = st;
        const escalate = prev !== undefined && (SEVERITY[st] || 0) > (SEVERITY[prev] || 0) && (SEVERITY[st] || 0) >= 2;
        this._transition(st, escalate && !d.jumped, prev === undefined || d.jumped);
      }
      const word = st ? (this.o.posture === 'phone' ? SHORT[st] || WORD[st] : WORD[st]) || st : '';
      this._text('.rail-word', word);
      this._text('.rail-sub', d.flagSub || '');
      this._text('.rail-meeting', d.meeting || '');
      this._text('.rail-name', d.session || '');
      this._html('.rail-big', d.big || '');
      this._html('.rail-small', d.small || '');
      this._html('.rail-chips', (d.chips || []).map((c) => `<span class="rchip ${c.cls || ''}">${c.html}</span>`).join(''));
      this._html('.rail-clock', d.clock || '');
      this._html('.rail-mode', d.modeHtml || '');
      const line = this.$('.rail-line i');
      if (d.progress != null) { this.$('.rail-line').hidden = false; line.style.transform = `scaleX(${Math.max(0, Math.min(1, d.progress))})`; }
      else this.$('.rail-line').hidden = true;
    }
    _text(sel, v) { const e = this.$(sel); if (e.textContent !== v) e.textContent = v; }
    _html(sel, v) { const e = this.$(sel); if (e._v !== v) { e.innerHTML = v; e._v = v; } }

    _transition(st, escalate, instant) {
      const root = this.root;
      const wipe = this.$('.rail-wipe');
      // Every transition supersedes the previous one: cancel in-flight wipes, blinks and their
      // callbacks so a stale colour can never land after a seek (generation token).
      const gen = (this._gen = (this._gen || 0) + 1);
      if (wipe.getAnimations) wipe.getAnimations().forEach((x) => x.cancel());
      clearTimeout(this._blinkT); clearTimeout(this._changedT);
      root.classList.remove('rail-blink', 'rail-changed');
      const apply = () => { root.dataset.status = st || 'NONE'; };
      if (instant || this.reduced || !wipe.animate) {
        apply();
        if (escalate && this.reduced) { root.classList.add('rail-changed'); this._changedT = setTimeout(() => { if (gen === this._gen) root.classList.remove('rail-changed'); }, 4000); }
        return;
      }
      wipe.dataset.status = st || 'NONE';
      const dur = this.o.posture === 'tv' ? 700 : 520;
      const a = wipe.animate(
        escalate
          ? [{ clipPath: 'inset(0 100% 0 0)', opacity: 1 }, { clipPath: 'inset(0 0% 0 0)', opacity: 1 }]
          : [{ opacity: 0 }, { opacity: 1 }],
        { duration: escalate ? dur : 600, easing: escalate ? 'cubic-bezier(.65,0,.35,1)' : 'ease-out', fill: 'forwards' },
      );
      a.onfinish = () => {
        if (gen !== this._gen) return; // superseded
        apply();
        wipe.getAnimations().forEach((x) => x.cancel());
        if (escalate) {
          void root.offsetWidth;
          root.classList.add('rail-blink');
          this._blinkT = setTimeout(() => { if (gen === this._gen) root.classList.remove('rail-blink'); }, 1500);
        }
      };
    }
  }
  SS.StatusRail = StatusRail;

  /**
   * What the rail says, for any posture. One model so TV, desktop and phone never disagree.
   * Returns (vm, player) => rail data. Keeps a little memory (when the track last went green).
   */
  SS.railModel = function (session) {
    const kind = session.kind;
    let lastStatus = null, clearAt = null;
    const purple = (t) => `<span style="color:var(--time-session-best)">${t}</span>`;
    return function (vm, player) {
      const S = vm.S;
      let status = vm.status;
      if (status !== lastStatus) { if (status === 'GREEN' && lastStatus && lastStatus !== 'WAITING') clearAt = vm.t; lastStatus = status; }
      let flagSub = '', big = '', small = '', compact = '';
      const chips = [];
      if (kind === 'race') {
        if (S.status === 'FINISHED') status = 'CHEQUERED';
        if (S.status === 'SCHEDULED' || status === 'WAITING') { big = `${vm.totalLaps || '—'}<small> LAPS</small>`; compact = `${vm.totalLaps || '—'} LAPS`; }
        else {
          big = vm.lap ? `LAP ${Math.min(vm.lap, vm.totalLaps || vm.lap)}<small>/${vm.totalLaps || '—'}</small>` : '';
          compact = vm.lap ? `L${Math.min(vm.lap, vm.totalLaps || vm.lap)}/${vm.totalLaps || '—'}` : '';
          small = S.status === 'FINISHED' ? 'FINAL CLASSIFICATION' : vm.lap && vm.totalLaps ? (vm.lap >= vm.totalLaps ? 'FINAL LAP' : `${vm.totalLaps - vm.lap} TO GO`) : '';
        }
        if (vm.overtakeMode != null && !vm.finished && !['VSC', 'VSC_ENDING', 'SAFETY_CAR', 'RED', 'RED_FLAG'].includes(status)) chips.push({ cls: vm.overtakeMode ? 'is-on' : '', html: vm.overtakeMode ? 'OVERTAKE ON' : 'OVERTAKE OFF' });
        if (vm.fastest && vm.lap >= 3) chips.push({ cls: '', html: `${purple('FASTEST')} ${session.drivers[vm.fastest.num].code} <span class="mono">${SS.util.fmtLap(vm.fastest.time)}</span>` });
      } else {
        const clock = vm.clock != null ? SS.util.fmtClock(vm.clock) : '—';
        if (kind === 'qualifying') {
          const finishedSeg = S.status === 'FINISHED' || S.control_status === 'CHEQUERED';
          const settled = session.events.some((e) => (e.type === 'ELIMINATED' || e.type === 'POLE') && e.phase === vm.phase && SS.avail(e) <= vm.t && e.state !== 'provisional');
          if (S.status === 'SCHEDULED') { status = 'WAITING'; flagSub = `${vm.phase} STARTS SOON`; }
          else if (finishedSeg && !settled) status = 'CHEQUERED';
          else if (finishedSeg && settled) { status = 'FINISHED'; flagSub = vm.phase === 'Q3' ? 'QUALIFYING COMPLETE' : `${vm.phase} COMPLETE`; }
          big = `${vm.phase || ''} <span>${clock}</span>`;
          compact = `${vm.phase || ''} ${clock}`;
          const active = vm.rows.filter((r) => !r.qe).length;
          small = vm.advance ? `${active} CARS · TOP ${vm.advance} ADVANCE` : 'POLE SHOOTOUT · 10 CARS';
          const p1 = vm.rows[0];
          if (p1 && p1.qTime != null) chips.push({ cls: '', html: `${purple('P1')} ${p1.code} <span class="mono">${SS.util.fmtLap(p1.qTime)}</span>` });
          if (vm.clock != null && vm.clock <= 120 && S.status === 'RUNNING') chips.push({ cls: 'is-warn', html: 'FINAL MINUTES' });
        } else {
          if (S.status === 'FINISHED') status = 'FINISHED';
          big = `<span>${clock}</span>`;
          compact = clock;
          small = S.status === 'FINISHED' ? 'SESSION COMPLETE' : 'REMAINING';
          const p1 = vm.rows[0];
          if (p1 && p1.best) chips.push({ cls: '', html: `${purple('FASTEST')} ${p1.code} <span class="mono">${p1.best}</span>` });
        }
      }
      // Weather from the weather feed: rain is the only reading that changes how you watch, so it gets colour.
      const w = vm.weather;
      if (w && w.rain) chips.unshift({ cls: 'is-rain', html: 'RAIN' });
      if (w && w.track != null && w.air != null) chips.push({ cls: 'is-wx', html: `TRACK <span class="mono">${Math.round(w.track)}°</span> AIR <span class="mono">${Math.round(w.air)}°</span>` });
      if (vm.sectorFlag && (status === 'YELLOW' || status === 'GREEN')) flagSub = `${vm.sectorFlag.flag === 'DOUBLE YELLOW' ? 'DOUBLE · ' : ''}SECTOR ${vm.sectorFlag.sector}`;
      if (status === 'GREEN' && clearAt != null && vm.t - clearAt < 6 && vm.t >= clearAt) flagSub = 'TRACK CLEAR';
      const clock = SS.localClock ? `<span>${SS.sessionDate(session)}</span><b>${SS.localClock(session, vm.t)}</b><span>LOCAL · ${SS.offsetLabel(session)}</span>` : '';
      return {
        status, flagSub, compact, clock,
        meeting: session.meta.meeting_name,
        session: `${session.meta.name.toUpperCase()} · ${(session.meta.circuit || '').toUpperCase()}`,
        big, small, chips,
        modeHtml: SS.modeBadge(player.mode === 'live' ? { kind: 'live', state: player.liveState, delay: player.delay, paused: !player.playing, staleFor: player.staleSeconds() + 's' } : { kind: 'replay', speed: player.speed, paused: !player.playing, delay: player.delay }),
        progress: player.mode === 'live' ? null : (player.t - session.begin) / (session.end - session.begin),
      };
    };
  };

  /* Mode badge HTML (shared): LIVE is the accent; REPLAY is deliberately neutral. */
  SS.modeBadge = (m) => {
    const fmt = (sec) => (SS.fmtDelay ? SS.fmtDelay(sec) : Math.round(sec) + 's');
    if (m.kind === 'live') {
      const st = m.state || 'LIVE';
      if (st === 'STALE') return `<span class="mode mode--stale"><i></i>STALE <em class="mono">${m.staleFor || ''}</em></span>`;
      if (st === 'RECONNECTING') return `<span class="mode mode--stale"><i></i>RECONNECTING</span>`;
      if (st === 'CONNECTING') return `<span class="mode mode--stale"><i></i>CONNECTING</span>`;
      if (st === 'FINALIZING') return `<span class="mode mode--final">FINALIZING RESULTS</span>`;
      // LIVE stays LIVE when delayed or paused: the badge says how far behind the edge you are.
      return `<span class="mode mode--live${m.paused ? ' is-paused' : ''}"><i></i>LIVE${m.paused ? '<em>PAUSED</em>' : ''}${m.delay >= 1 ? `<em class="mono">−${fmt(m.delay)}</em>` : ''}</span>`;
    }
    return `<span class="mode mode--replay"><svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1.5v7l6-3.5z"/></svg>REPLAY${m.speed && m.speed !== 1 ? `<em class="mono">${m.speed}×</em>` : ''}${m.delay ? `<em class="mono">SYNC ${fmt(m.delay)}</em>` : ''}${m.paused ? '<em>PAUSED</em>' : ''}</span>`;
  };
})();

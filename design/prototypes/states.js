/* States & flows: the real components, rendered at fixed moments or with fixed inputs. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;
  const $ = (s) => document.querySelector(s);
  const race = new SS.Session('hungaroring-2026-race');
  const quali = new SS.Session('kl-2026-qualifying');

  const vmAt = (s, t) => {
    const cur = new SS.Cursor(s);
    cur.reset(t);
    const vm = SS.vm(s, cur, { now: t });
    vm.byNum = Object.fromEntries(vm.rows.map((r) => [r.num, r]));
    return vm;
  };

  /* ---------------------------------------------------------- countdown to the next live session (real date from the catalog) */
  const RACE_START = Date.parse('2026-10-04T07:00:00Z');
  const cdText = () => {
    const d = Math.floor((RACE_START - Date.now()) / 1000);
    if (d <= 0) return 'NOW';
    const h = Math.floor(d / 3600), m = Math.floor((d % 3600) / 60), s = d % 60;
    return (h ? h + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  };
  const tickCd = () => document.querySelectorAll('[data-cd], #cd').forEach((e) => (e.textContent = cdText()));
  setInterval(tickCd, 1000);

  /* ---------------------------------------------------------- rails with fixed inputs */
  const makeRail = (host, posture, d, word) => {
    const r = new SS.StatusRail(host, { posture });
    r.update(Object.assign({ chips: [], jumped: true }, d));
    if (word != null) host.querySelector('.rail-word').textContent = word;
    return r;
  };
  const base = { meeting: 'Bahrain Grand Prix', session: 'RACE · KUALA LUMPUR' };
  const live = (state, extra = {}) => SS.modeBadge(Object.assign({ kind: 'live', state }, extra));

  /* opening */
  makeRail($('#railOpen'), 'desktop', { status: null, meeting: 'Hungarian Grand Prix', session: 'RACE · HUNGARORING', big: '', small: '', modeHtml: SS.modeBadge({ kind: 'replay', speed: 1, paused: true }), progress: 0 });
  $('#skel').innerHTML = Array.from({ length: 14 }, (_, i) => `<i style="--d:${(i * 0.06).toFixed(2)}s"></i>`).join('');

  /* live lifecycle */
  const LIVE_STATES = [
    { id: 'PRE_EVENT', title: 'Before the session', rail: { status: 'WAITING', flagSub: 'SUN 15:00 LOCAL', big: 'STARTS IN <span data-cd>—</span>', small: '', modeHtml: '<span class="mode mode--final">NOT STARTED</span>' }, body: '<b>Waiting for the public timing feed.</b> The tower fills when the first timing arrives. Your default delay applies when you go live.', note: 'Countdown uses the real start time from your catalog.' },
    { id: 'CONNECTING', title: 'Connecting', rail: { status: null, big: '', small: '', modeHtml: live('CONNECTING') }, body: '<b>Connecting to live timing…</b> Nothing is shown until real data arrives — no placeholder order.', note: 'Unknown track status is omitted from the flag block.' },
    { id: 'LIVE', title: 'Live', rail: { status: 'GREEN', big: 'LAP 12<small>/56</small>', small: '44 TO GO', modeHtml: live('LIVE') }, body: '<b>Live.</b> Solid red badge, no progress line, no seek. The order animates; moments are announced.', note: '' },
    { id: 'LIVE_DELAY', title: 'Live with a delay', rail: { status: 'GREEN', big: 'LAP 12<small>/56</small>', small: '44 TO GO', modeHtml: live('LIVE', { delay: 30 }) }, body: '<b>Live, 30 s behind.</b> Set to match the TV broadcast so the screen never spoils the pictures.', note: 'Per viewer, 0–300 s.' },
    { id: 'STALE', title: 'Feed stale', rail: { status: 'GREEN', big: 'LAP 12<small>/56</small>', small: '44 TO GO', modeHtml: live('STALE', { staleFor: '12s' }) }, body: '<span class="amber"><b>TIMING PAUSED</b> no update for 12 s — holding the last known order.</span> Tower and map dim so a frozen screen never looks current.', note: '' },
    { id: 'RECONNECTING', title: 'Reconnecting', rail: { status: 'GREEN', big: 'LAP 12<small>/56</small>', small: '44 TO GO', modeHtml: live('RECONNECTING') }, body: '<span class="amber"><b>RECONNECTING</b></span> When the feed returns the screen catches up in one silent jump, then says “Back live”.', note: 'Catch-up is never animated as racing.' },
    { id: 'FINALIZING', title: 'Finalizing', rail: { status: 'CHEQUERED', big: 'LAP 56<small>/56</small>', small: 'FINAL CLASSIFICATION', modeHtml: live('FINALIZING') }, body: '<b>The chequered flag has fallen.</b> Penalties and investigations can still change the order; those changes are shown as classification, not overtakes.', note: '' },
    { id: 'COMPLETE', title: 'Complete', rail: { status: 'FINISHED', flagSub: 'RACE COMPLETE', big: 'LAP 56<small>/56</small>', small: 'FINAL CLASSIFICATION', modeHtml: '<span class="mode mode--final">COMPLETE</span>' }, body: '<b>Session complete.</b> The replay is being prepared from the live recording.', note: '' },
    { id: 'REPLAY_READY', title: 'Replay ready', rail: { status: 'FINISHED', flagSub: 'RACE COMPLETE', big: 'LAP 56<small>/56</small>', small: 'FINAL CLASSIFICATION', modeHtml: '<span class="mode mode--final">REPLAY READY</span>' }, body: '<b>Replay ready.</b> <button class="btn btn--primary">WATCH REPLAY</button> Opens at the start; the story list jumps to any moment.', note: '' },
    { id: 'UNAVAILABLE', title: 'Unavailable', rail: { status: null, big: '', small: '', modeHtml: '<span class="mode mode--off">LIVE UNAVAILABLE</span>' }, body: '<b>The public timing feed isn’t available.</b> Nothing has been substituted. Replays still open from the library.', note: '' },
  ];
  $('#liveGrid').innerHTML = LIVE_STATES.map((x) => `<div class="lg-item${x.id === 'STALE' || x.id === 'RECONNECTING' ? ' is-amber' : ''}"><div class="lg-title"><span class="mono">${x.id}</span><b>${x.title}</b>${x.note ? `<em>${x.note}</em>` : ''}</div><div class="lg-rail" data-id="${x.id}"></div><div class="lg-body">${x.body}</div></div>`).join('');
  for (const x of LIVE_STATES) makeRail(document.querySelector(`.lg-rail[data-id="${x.id}"]`), 'desktop', Object.assign({}, base, x.rail, { progress: null }));
  tickCd();

  /* live vs replay */
  const modesEl = $('#modes');
  const MODES = [
    { t: 'LIVE', d: { status: 'GREEN', big: 'LAP 46<small>/70</small>', small: '24 TO GO', modeHtml: live('LIVE'), progress: null } },
    { t: 'LIVE · 30 s DELAY', d: { status: 'GREEN', big: 'LAP 46<small>/70</small>', small: '24 TO GO', modeHtml: live('LIVE', { delay: 30 }), progress: null } },
    { t: 'REPLAY · 10×', d: { status: 'GREEN', big: 'LAP 46<small>/70</small>', small: '24 TO GO', modeHtml: SS.modeBadge({ kind: 'replay', speed: 10 }), progress: 0.63 } },
    { t: 'REPLAY · PAUSED', d: { status: 'VSC', big: 'LAP 56<small>/70</small>', small: '14 TO GO', modeHtml: SS.modeBadge({ kind: 'replay', speed: 1, paused: true }), progress: 0.77 } },
  ];
  modesEl.innerHTML = MODES.map((m, i) => `<div class="md-item"><span class="lbl">${m.t}</span><div class="md-rail" data-i="${i}"></div></div>`).join('') + '<div class="md-item"><span class="lbl">REPLAY TRANSPORT · markers are real events: lead changes, flags, pit stops, retirements</span><div class="md-tp" id="tpReplay"></div></div><div class="md-item"><span class="lbl">LIVE BAR · delay only</span><div class="md-tp" id="tpLive"></div></div>';
  MODES.forEach((m, i) => makeRail(modesEl.querySelector(`.md-rail[data-i="${i}"]`), 'desktop', Object.assign({ meeting: 'Hungarian Grand Prix', session: 'RACE · HUNGARORING' }, m.d)));
  const pr = new SS.Player(race, { startAt: 3897, speed: 10 });
  const tpr = new SS.Transport($('#tpReplay'), pr, { posture: 'desktop' });
  const pl = new SS.Player(race, { startAt: 3897, speed: 1 });
  pl.mode = 'live';
  pl.delay = 30;
  const tpl = new SS.Transport($('#tpLive'), pl, { posture: 'desktop' });
  pr.on(() => tpr.update());
  pl.on(() => tpl.update());

  /* missing data */
  requestAnimationFrame(() => {
    const t = 1500;
    const vm = vmAt(race, t);
    const map = new SS.TrackMap($('#missOutline'), { session: race, posture: 'desktop' });
    map.render(vm, t);
    const qt = 1180;
    const qvm = vmAt(quali, qt);
    const line = new SS.TrackLine($('#missLine'), { session: quali, posture: 'desktop', lanes: 3 });
    line.render(qvm, qt);
    const rb = new SS.GapRibbon($('#missRibbon'), { session: race, posture: 'desktop' });
    rb.render(vm, true);
    const C = SS.cols;
    const tw = new SS.Tower($('#missRows'), { session: race, columns: [C.pos('34px'), C.driver('1fr'), C.int('80px'), C.gap('90px'), C.tyre('70px'), C.last('92px')], rowH: 30, posture: 'desktop' });
    const svm = vmAt(race, 4);
    tw.render(svm, { jumped: true, recent: SS.recentContext(race, 4) });
  });

  /* results */
  requestAnimationFrame(() => {
    const t = 6150;
    const vm = vmAt(race, t);
    const rm = SS.railModel(race);
    const fake = { mode: 'replay', speed: 1, playing: false, t, liveState: 'LIVE', delay: 0, staleSeconds: () => 0 };
    const rd = rm(vm, fake);
    makeRail($('#railRes'), 'phone', Object.assign(rd, { big: `<span>${rd.compact}</span>`, small: '', modeHtml: SS.modeBadge({ kind: 'replay', speed: 1, paused: true }) }));
    new SS.RaceResult($('#resRace'), { session: race, posture: 'desktop' }).render(vm, t);
    const qt2 = quali.end - 4;
    const qvm = vmAt(quali, qt2);
    const qrm = SS.railModel(quali);
    const qd = qrm(qvm, Object.assign({}, fake, { t: qt2 }));
    makeRail($('#railQ'), 'phone', Object.assign(qd, { big: `<span>${qd.compact}</span>`, small: '', modeHtml: SS.modeBadge({ kind: 'replay', speed: 1, paused: true }) }));
    const pole = quali.events.find((e) => e.type === 'POLE');
    const C = SS.cols;
    const host = $('#resQuali');
    host.innerHTML = `<div class="to-layer to-layer--desktop res-pole"><div class="to-card to--pole">${pole ? SS.takeoverHTML(quali, pole, qt2) : ''}</div></div><div class="res-grid-list" id="qGrid"></div>`;
    const grid = new SS.Tower(host.querySelector('#qGrid'), { session: quali, columns: [C.pos('34px'), C.driver('1fr'), C.qseg(0, '84px'), C.qseg(1, '84px'), C.qseg(2, '84px')], rowH: 26, posture: 'desktop' });
    grid.render(qvm, { jumped: true, recent: SS.recentContext(quali, qt2) });
  });

  /* ---------------------------------------------------------- cold open (inline, looping) */
  const cold = document.getElementById('coldOpen');
  if (cold) {
    cold.innerHTML = `<div class="brand-open"><div class="bo-mark"><img src="shared/brand/mark-192.png" alt="" draggable="false"><i class="bo-sweep" aria-hidden="true"></i></div><b class="bo-word">SLIPSTREAM</b><span class="bo-what">Hungarian Grand Prix · Race</span><span class="kerb" aria-hidden="true"></span><span class="bo-phase">Reading the timing history</span></div>`;
    const phases = ['Connecting to Slipstream', 'Reading the timing history', 'Building the race state'];
    let i = 0;
    setInterval(() => { i = (i + 1) % phases.length; cold.querySelector('.bo-phase').textContent = phases[i]; }, 1600);
  }

  /* ---------------------------------------------------------- settings: real for display size, motion, spoilers */
  if (SS.motion) SS.motion.init(new URLSearchParams(location.search).get('reduced'));
  const prefRead = { density: () => String(SS.density.get()), motion: () => SS.motion.choice, spoilers: () => SS.spoilers.get() };
  const prefWrite = { density: (v) => SS.density.set(+v), motion: (v) => SS.motion.set(v), spoilers: (v) => SS.spoilers.set(v) };
  document.querySelectorAll('.seg').forEach((seg) => {
    const pref = seg.dataset.pref;
    if (pref && prefRead[pref]) { const cur = prefRead[pref](); seg.querySelectorAll('button').forEach((b) => b.classList.toggle('is-on', b.dataset.v === cur)); }
    seg.addEventListener('click', (ev) => {
      const b = ev.target.closest('button');
      if (!b || /EDIT|CHOOSE/.test(b.textContent)) return;
      seg.querySelectorAll('button').forEach((x) => x.classList.toggle('is-on', x === b));
      if (pref && prefWrite[pref]) prefWrite[pref](b.dataset.v);
    });
  });
  document.querySelectorAll('.tgl').forEach((t) => t.addEventListener('click', () => t.classList.toggle('is-on')));
  if (SS.density) SS.density.apply(1); // this page is a document: always 100%
})();

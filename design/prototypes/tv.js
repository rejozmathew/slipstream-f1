/* TV Mode prototype — lean-back posture, operable as a product.
 * Persistent: status rail, timing tower (code + team), story ticker with the brand bug.
 * Rotating: one feature chosen by a director, or pinned by the viewer.
 * TIMING (T) widens the tower into the full timing table: every column the old TV views had.
 * Product controls: a toolbar that appears on any key or pointer move — exit, feature, follow,
 * sync/delay, play/pause, settings. Every input path goes through the player's capability check:
 * live allows pause (delay grows) and delay changes only; replay has seek, speed and sync offset.
 * Moments: takeovers over the feature area — never over the order; coalesced at fast replay speeds.
 * Fluid: the 1920×1080 composition scales to the screen and fills any aspect ratio. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;
  const $ = (s) => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  const label = params.get('s') || 'hungaroring-2026-race';
  const session = new SS.Session(label);
  const kind = session.kind;
  const race = kind === 'race';
  const C = SS.cols;
  document.body.dataset.kind = kind;
  SS.motion.init(params.get('reduced'));
  const caps = SS.capabilities(session, { map: params.get('map'), live: params.get('live') === '1' });
  const canvas = $('#canvas');
  const opening = SS.brand.opening({ posture: 'tv', title: `${session.meta.meeting_name} · ${session.meta.name}`, phases: ['Connecting to Slipstream', 'Reading the timing history', 'Building the race state'], hold: params.get('opening') === '1' ? 3200 : 0 });

  /* ---------------------------------------------------------- state */
  const state = {
    module: params.get('module') || 'auto',
    current: null,
    since: performance.now(),
    holdUntil: 0,
    why: '',
    follow: session.drivers[params.get('follow')] ? params.get('follow') : '',
    pinnedPair: params.get('pair') ? params.get('pair').split(',') : null,
    pinnedUntil: params.get('pair') ? Infinity : 0,
    map: caps.positions,
    live: params.get('live') === '1',
    battleMode: params.get('pair') ? 'pinned' : params.get('battle') || 'recommended',
    names: params.get('names') === 'surname' ? 'surname' : 'team',
    text: +(params.get('text') || SS.prefs.get('tv.text', 1)) || 1,
    wide: false,
    guardOff: params.get('guard') === '0',
    app: params.get('app') === '1',           // standalone TV app (e.g. Android TV): no desktop to go back to
    safe: +(params.get('safe') || SS.prefs.get('tv.safe', 0)) || 0, // overscan-safe margin, % of each side
  };

  /* ---------------------------------------------------------- tower: code + team by default; TIMING widens it */
  const TEAM_SHORT = { 'Red Bull Racing': 'Red Bull', 'Haas F1 Team': 'Haas' };
  const teamShort = (t) => TEAM_SHORT[t] || (t || '').replace(/ F1 Team$/, '');
  const drvTV = { key: 'driver', label: 'DRIVER', w: '1fr', cls: 'c-drv c-drvtv', cell: (r) => `<i class="tw-team"></i><b class="tw-code">${r.code}</b>${state.names === 'surname' ? `<span class="tw-name">${U.titleCase(r.surname)}</span>` : `<em class="tw-tm">${teamShort(r.team)}</em>`}` };
  const drvWide = { key: 'driver', label: 'DRIVER / TEAM', w: 'minmax(330px, 1fr)', cls: 'c-drv c-drvtv', cell: (r) => `<i class="tw-team"></i><b class="tw-code">${r.code}</b><span class="tw-name">${U.titleCase(r.surname)}</span><em class="tw-tm">${r.team}</em>` };
  const COLS = {
    race: { compact: () => [C.pos('56px'), drvTV, C.int('136px'), C.gap('156px'), C.tyre('108px'), C.pits('46px')],
      wide: () => [C.pos('56px'), drvWide, C.gap('150px'), C.int('136px'), C.last('150px'), C.best('150px'), C.sector(1, '108px'), C.sector(2, '108px'), C.sector(3, '108px'), C.tyre('112px'), C.stint('86px', 'STINT'), C.pits('56px')] },
    qualifying: { compact: () => [C.pos('56px'), drvTV, C.qtime('160px'), C.qgap('124px'), C.tyre('108px'), C.status('126px')],
      wide: () => [C.pos('56px'), drvWide, C.qseg(0, '150px'), C.qseg(1, '150px'), C.qseg(2, '150px'), C.qgap('124px'), C.qint('112px'), C.last('150px'), C.sector(1, '104px'), C.sector(2, '104px'), C.sector(3, '104px'), C.tyre('108px'), C.status('126px')] },
    practice: { compact: () => [C.pos('56px'), drvTV, C.best('160px', 'time'), C.pgap('124px'), C.tyre('108px'), C.status('120px')],
      wide: () => [C.pos('56px'), drvWide, C.best('150px', 'time'), C.pgap('124px'), C.pint('112px'), C.last('150px'), C.sector(1, '104px'), C.sector(2, '104px'), C.sector(3, '104px'), C.tyre('108px'), C.stint('86px', 'STINT'), C.stops('86px'), C.status('120px')] },
  };
  let tower = null, towerKey = '';
  function buildTower() {
    const host = $('#tower');
    const n = Object.keys(session.drivers).length;
    const avail = (host.clientHeight || 886) - 34;
    const dividers = kind === 'qualifying' && !state.wide ? 1 : 0; // cut line + eliminated block take ~0.84 of a row
    const rowH = Math.max(32, Math.min(46, Math.floor(avail / (n + dividers))));
    const key = (state.wide ? 'wide' : 'compact') + '@' + rowH + state.names;
    if (key === towerKey) return;
    towerKey = key;
    host.innerHTML = ''; host.className = 'tv-tower';
    if (!race) host.style.setProperty('--chips-right', state.wide ? '128px' : '128px');
    tower = new SS.Tower(host, { session, columns: COLS[kind][state.wide ? 'wide' : 'compact'](), rowH, posture: 'tv', onRow: (num) => setFollow(state.follow === num ? '' : num) });
    tower.setFollow(state.follow ? [state.follow] : []);
    forceJump = true;
  }

  /* ---------------------------------------------------------- fit: scale with the screen, fill any aspect */
  function fit() {
    const vw = innerWidth, vh = innerHeight;
    const small = vw < 900 && !state.guardOff;
    $('#guard').hidden = !small;
    const k = Math.max(0.5, Math.min(vw / 1920, vh / 1080)) * state.text;
    canvas.style.setProperty('--k', k.toFixed(4));
    // Safe area for TVs that overscan (and TV-app guidelines): content moves in; backgrounds stay full-bleed.
    const sx = Math.round((vw / k) * state.safe / 100), sy = Math.round((vh / k) * state.safe / 100);
    canvas.style.setProperty('--safe-x', sx + 'px');
    canvas.style.setProperty('--safe-y', sy + 'px');
    canvas.classList.toggle('has-safe', state.safe > 0);
    requestAnimationFrame(() => buildTower());
  }
  window.addEventListener('resize', fit);
  $('#guardAnyway').addEventListener('click', () => { state.guardOff = true; fit(); });

  /* ---------------------------------------------------------- components */
  const rail = new SS.StatusRail($('#rail'), { posture: 'tv', intensity: params.get('bold') === '1' ? 'bold' : 'calm' });
  const ticker = new SS.Ticker($('#ticker'), { session, min: SS.PRIORITY.HIGHLIGHT, count: 4 });
  $('#ticker').insertAdjacentHTML('afterbegin', SS.brand.mark({ h: 34 }));
  const takeover = new SS.Takeover($('#takeover'), { session, posture: 'tv', onHide: (e) => afterTakeover(e) });

  /* feature modules */
  const body = $('#stageBody');
  const mk = (cls) => { const d = document.createElement('div'); d.className = 'mod ' + cls; body.appendChild(d); return d; };
  const modules = [];
  let trackView = null, lineView = null, ribbon = null, ladder = null, onTrack = null, battle = null, pits = null, dcard = null, zone = null, result = null, stratRight = null, dMap = null, dLine = null, dLaps = null;
  const resultState = (t) => (SS.resultState ? SS.resultState(session, t) : { state: lastVm && lastVm.finished ? 'provisional' : 'none' });

  if (race) {
    const m = mk('mod-track');
    m.innerHTML = '<div class="mt-map"></div><div class="mt-note" hidden></div><div class="mt-ribbon"></div>';
    ribbon = new SS.GapRibbon(m.querySelector('.mt-ribbon'), { session, posture: 'tv' });
    modules.push({ id: 'track', label: 'TRACK', el: m, dwell: 26 });
    const b = mk('mod-battle');
    battle = new SS.BattleView(b, { session, posture: 'tv' });
    modules.push({ id: 'battle', label: 'BATTLE', el: b, dwell: 20, available: (vm) => !!battlePair(vm), why: 'No two cars within 1.0 s in green-flag running' });
    const p = mk('mod-pits');
    p.innerHTML = '<div class="msx-l"></div><div class="msx-r"></div>';
    pits = new SS.PitBoard(p.querySelector('.msx-l'), { session, posture: 'tv' });
    stratRight = p.querySelector('.msx-r');
    modules.push({ id: 'pits', label: 'STRATEGY', el: p, dwell: 18, available: (vm) => !vm.finished && (vm.lap >= 4 || vm.rows.some((r) => r.inPit)), why: 'From lap 4, or when a car pits' });
    const rs = mk('mod-result');
    result = new SS.RaceResult(rs, { session, posture: 'tv' });
    modules.push({ id: 'result', label: 'RESULT', el: rs, dwell: 40, available: (vm) => resultState(vm.t).state !== 'none', why: 'Appears after the chequered flag' });
  } else {
    const s = mk('mod-spread');
    s.innerHTML = '<div class="ms-ladder"></div><div class="ms-cols"><div class="ms-ontrack"></div><div class="ms-zone"></div></div>';
    ladder = new SS.Ladder(s.querySelector('.ms-ladder'), { session, posture: 'tv' });
    onTrack = new SS.OnTrack(s.querySelector('.ms-ontrack'), { session, posture: 'tv', max: 9 });
    zone = s.querySelector('.ms-zone');
    modules.push({ id: 'spread', label: kind === 'qualifying' ? 'CUT LINE' : 'SPREAD', el: s, dwell: 28 });
    const m = mk('mod-track');
    m.innerHTML = '<div class="mt-map"></div><div class="mt-note" hidden></div>';
    modules.push({ id: 'track', label: 'TRACK', el: m, dwell: 18, available: () => state.map !== 'none', why: 'No car positions for this session' });
  }
  const d = mk('mod-driver');
  d.innerHTML = '<div class="mdv-l"></div><div class="mdv-r"><div class="mdv-map"></div><div class="mdv-laps"></div></div>';
  dcard = new SS.DriverCard(d.querySelector('.mdv-l'), { session, posture: 'tv' });
  modules.push({ id: 'driver', label: 'FOLLOWING', el: d, dwell: 14, available: () => !!state.follow, why: 'Choose a driver to follow' });
  // TIMING is a viewer choice, never part of the rotation: it widens the tower over the stage.
  modules.push({ id: 'timing', label: 'TIMING', el: null, dwell: Infinity, manualOnly: true });

  function buildDriverMap() {
    const host = d.querySelector('.mdv-map');
    host.innerHTML = '';
    dMap = dLine = null;
    // One capability object for every feature: no positions here means none in Following either.
    if (state.map === 'outline') dMap = new SS.TrackMap(host, { session, posture: 'tv', labels: 3 });
    else if (state.map === 'line') dLine = new SS.TrackLine(host, { session, posture: 'tv', lanes: 3 });
    else host.innerHTML = '<div class="mt-note"><b>No car positions</b><span>Order and gaps from timing only.</span></div>';
  }
  dLaps = d.querySelector('.mdv-laps');

  const trackMod = modules.find((m) => m.id === 'track');
  function buildMap() {
    const host = trackMod.el.querySelector('.mt-map');
    host.innerHTML = '';
    trackView = lineView = null;
    const note = trackMod.el.querySelector('.mt-note');
    note.hidden = true;
    trackMod.el.dataset.map = state.map;
    if (state.map === 'outline') trackView = new SS.TrackMap(host, { session, posture: 'tv' });
    else if (state.map === 'line') lineView = new SS.TrackLine(host, { session, posture: 'tv', lanes: race ? 4 : 6 });
    else { note.hidden = false; note.innerHTML = `<b>Car positions are not available for this ${state.live ? 'live feed' : 'replay'}.</b><span>${race ? 'The order and gaps come straight from timing — shown here as race order in time.' : 'The order and lap times come straight from timing.'}</span>`; }
    buildDriverMap();
  }
  buildMap();

  /* ---------------------------------------------------------- feature selection (stage header + toolbar) */
  const isAvail = (m, vm) => !m.available || !vm || m.available(vm);
  const modsEl = $('#stageMods');
  const chipHtml = (vm, cls) => modules.map((m, i) => {
    const av = isAvail(m, vm);
    return `<button type="button" class="${cls}${m.id === state.current || (m.id === 'timing' && state.wide) ? ' is-on' : ''}${av ? '' : ' is-na'}" data-mod="${m.id}" aria-pressed="${m.id === state.current}" ${av ? '' : `aria-disabled="true" title="${m.why || 'Not available yet'}"`}>${cls === 'smod' ? `<em class="mono">${m.id === 'timing' ? 'T' : i + 1}</em>` : ''}${m.label}</button>`;
  }).join('') + `<button type="button" class="${cls} ${cls === 'smod' ? 'smod-auto' : ''}${state.module === 'auto' ? ' is-on' : ''}" data-mod="auto" aria-pressed="${state.module === 'auto'}">${cls === 'smod' ? '<em class="mono">A</em>' : ''}AUTO${cls === 'smod' ? `<i style="--p:${dwellProgress()}"></i>` : ''}</button>`;
  const dwellProgress = () => {
    const m = modules.find((x) => x.id === state.current);
    if (!m || state.module !== 'auto' || !isFinite(m.dwell)) return 0;
    return Math.min(1, (performance.now() - state.since) / 1000 / Math.max(m.dwell, (state.holdUntil - state.since) / 1000)).toFixed(3);
  };
  function renderModChips(vm) {
    const html = chipHtml(vm, 'smod');
    if (modsEl._v !== html && !modsEl.contains(document.activeElement)) { modsEl.innerHTML = html; modsEl._v = html; }
    const tb = $('#tbMods');
    const h2 = chipHtml(vm, 'tb-b');
    if (tb._v !== h2 && !tb.contains(document.activeElement)) { tb.innerHTML = h2; tb._v = h2; }
  }
  function pin(id) {
    if (id === 'auto') { state.module = 'auto'; state.holdUntil = 0; setWide(false); return; }
    if (id === 'timing') { setWide(!state.wide); return; }
    const m = modules.find((x) => x.id === id);
    if (!m) return;
    if (!isAvail(m, lastVm)) { flashWhy(m.why || 'not available yet'); return; }
    setWide(false);
    state.module = id;
    show(id, 'pinned');
  }
  const flashWhy = (txt) => { state.whyFlash = { txt, until: performance.now() + 2600 }; };
  [modsEl, $('#tbMods')].forEach((el) => el.addEventListener('click', (ev) => { const b = ev.target.closest('[data-mod]'); if (b) pin(b.dataset.mod); }));
  function setWide(on) {
    if (state.wide === on) return;
    state.wide = on;
    canvas.classList.toggle('is-wide', on);
    takeover.enabled = !on && $('#optTakeovers').checked;
    if (on) takeover.clear();
    towerKey = '';
    buildTower();
  }

  function show(id, why) {
    if (state.current === id) { state.why = why || state.why; return; }
    state.current = id;
    state.since = performance.now();
    state.why = why || '';
    for (const m of modules) if (m.el) m.el.classList.toggle('is-active', m.id === id);
  }
  function request(id, holdSec, why) {
    if (state.module !== 'auto' || state.wide) return;
    const m = modules.find((x) => x.id === id);
    if (!m) return;
    show(id, why);
    state.holdUntil = performance.now() + holdSec * 1000;
  }
  const livePinnedPair = () => (state.pinnedPair && performance.now() < state.pinnedUntil ? state.pinnedPair : null);
  const leaderPair = (vm) => { const live = vm.rows.filter((r) => !r.out); return live.length > 1 ? [live[0], live[1]] : null; };
  const battlePair = (vm) => (!race ? null : state.battleMode === 'leader' ? leaderPair(vm) : SS.pickBattle(vm, livePinnedPair()));
  let slowAt = 0;
  const slowTick = () => { const n = performance.now(); if (n > slowAt) { slowAt = n + 500; return true; } return false; };
  function renderStrategyRight(vm) {
    if (!stratRight || !slowTick()) return;
    const n = SS.raceNow(session, vm);
    const P = (window.SLIPSTREAM_SERVER || {})[label];
    const pir = P && P.pirelli;
    const html = `<div class="msx-block"><span class="lbl">DRY RULE</span><b>${n.needs} driver${n.needs === 1 ? '' : 's'} still need another dry compound</b></div>
      <div class="msx-block"><span class="lbl">COMPOUND SEQUENCES</span><div class="msx-seqs">${n.seqs.slice(0, 4).map((x) => `<span><b class="mono">${x.n}</b>${SS.compoundSeq(x.list)}</span>`).join('')}</div></div>
      <div class="msx-block"><span class="lbl">STINT CONTEXT · COMPLETED</span><div class="msx-seqs">${n.stintCtx.map((x) => `<span>${SS.compoundBadge({ S: 'SOFT', M: 'MEDIUM', H: 'HARD', I: 'INTERMEDIATE', W: 'WET' }[x.c], null, { noAge: true })}<b>${x.n} · median ${x.med != null ? x.med.toFixed(1) : '—'}L</b></span>`).join('') || '<span class="dim">no completed stints yet</span>'}</div></div>
      ${pir ? `<div class="msx-block msx-pir"><span class="lbl">PIRELLI · PRE-RACE</span><div class="pir-nom">${SS.compoundBadge('HARD', null, { noAge: true })}<em class="mono">${pir.compounds.hard}</em>${SS.compoundBadge('MEDIUM', null, { noAge: true })}<em class="mono">${pir.compounds.medium}</em>${SS.compoundBadge('SOFT', null, { noAge: true })}<em class="mono">${pir.compounds.soft}</em></div><p>${pir.facts[0].text}</p></div>` : ''}`;
    if (stratRight._v !== html) { stratRight.innerHTML = html; stratRight._v = html; }
  }

  /* director: rotation + event-driven switches (TIMING and pins are the viewer's) */
  function direct(vm) {
    if (state.wide) return;
    if (state.module !== 'auto') { show(state.module, 'pinned'); return; }
    const avail = modules.filter((m) => !m.manualOnly && isAvail(m, vm));
    const cur = modules.find((m) => m.id === state.current);
    const now = performance.now();
    if (race && avail.some((m) => m.id === 'result')) { if (state.current !== 'result') show('result', 'provisional result'); return; }
    if (!cur || !avail.includes(cur)) return show(avail[0].id, 'rotation');
    const elapsed = (now - state.since) / 1000;
    if (now > state.holdUntil && elapsed > cur.dwell) show(avail[(avail.indexOf(cur) + 1) % avail.length].id, 'rotation');
  }
  function onEvents(events) {
    if (player.speed >= 20) return; // fast replay: the director keeps its rotation instead of chasing events
    for (const e of events) {
      if (e.priority < SS.PRIORITY.HIGHLIGHT) continue;
      if (race) {
        if ((e.type === 'PASS' || e.type === 'BATTLE') && e.pos <= 12) { if (state.battleMode !== 'pinned') { state.pinnedPair = e.type === 'PASS' ? [e.drivers[0], e.drivers[1]] : [e.drivers[1], e.drivers[0]]; state.pinnedUntil = performance.now() + 30000; } request('battle', 18, e.type === 'PASS' ? 'just happened' : 'close battle'); }
        else if (e.type === 'PIT_IN' && e.pos <= 8) request('pits', 14, 'pit stop');
        else if (e.type === 'FLAG' && e.status === 'CHEQUERED') { /* result module takes over once there is a result */ }
        else if (e.type === 'FLAG' || e.type === 'STOPPED') request('track', 22, e.type === 'STOPPED' ? 'car stopped' : 'flag');
      } else if (['INTO_DROP_ZONE', 'OUT_OF_DROP_ZONE', 'IMPROVEMENT', 'SEGMENT_P1', 'PROVISIONAL_POLE', 'SESSION_BEST', 'LAP_DELETED'].includes(e.type)) request('spread', 16, 'lap time');
    }
  }
  function afterTakeover(e) {
    if (e.type === 'LEAD_CHANGE' && e.cause === 'ON_TRACK' && state.battleMode !== 'pinned') { state.pinnedPair = [e.drivers[0], e.drivers[1]]; state.pinnedUntil = performance.now() + 30000; request('battle', 18, 'lead change'); }
  }

  /* ---------------------------------------------------------- follow */
  const followOpts = '<option value="">— nobody —</option>' + Object.values(session.drivers).sort((a, b) => a.code.localeCompare(b.code)).map((D) => `<option value="${D.num}">${D.code} · ${U.titleCase(D.surname)}</option>`).join('');
  $('#optFollow').innerHTML = followOpts;
  $('#tbFollow').innerHTML = followOpts;
  function setFollow(n) {
    state.follow = n || '';
    $('#optFollow').value = state.follow;
    $('#tbFollow').value = state.follow;
    if (tower) tower.setFollow(state.follow ? [state.follow] : []);
    if (state.follow && state.module === 'auto') request('driver', 12, 'following');
  }
  $('#optFollow').addEventListener('change', (ev) => setFollow(ev.target.value));
  $('#tbFollow').addEventListener('change', (ev) => setFollow(ev.target.value));

  /* ---------------------------------------------------------- player (viewer context from the URL) */
  const startAt = params.get('t') != null ? +params.get('t') : session.moments.length ? session.moments[0].t : session.begin;
  const player = new SS.Player(session, { startAt, speed: +(params.get('speed') || 10) });
  SS.viewer.apply(player, params);
  if (params.get('play') !== '0') player.play(); else if (player.mode === 'live') player.pause();
  const railModel = SS.railModel(session);

  /* ---------------------------------------------------------- toolbar + sync panel */
  const bar = $('#tvbar'), syncEl = $('#syncPanel');
  let barT = null;
  function showBar() {
    bar.hidden = false;
    clearTimeout(barT);
    barT = setTimeout(() => { if (syncEl.hidden && !bar.matches(':hover')) { if (bar.contains(document.activeElement)) document.activeElement.blur(); bar.hidden = true; } }, 6000);
  }
  let lastMove = 0;
  document.addEventListener('pointermove', () => { const n = performance.now(); if (n - lastMove > 250) { lastMove = n; showBar(); } });
  bar.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-a]'); if (!b) return;
    const a = b.dataset.a;
    if (a === 'exit') exitTv();
    else if (a === 'sync') toggleSync();
    else if (a === 'play') player.toggle();
    showBar();
  });
  function exitTv() {
    if (state.app) { openSessions(); return; }
    const to = params.get('from') === 'phone' ? 'phone' : 'web';
    location.href = `${to}.html?` + SS.viewer.query(SS.viewer.fromPlayer(player, { follow: state.follow, reduced: SS.motion.choice === 'reduced' ? 1 : SS.motion.choice === 'full' ? 0 : '' }));
  }
  function updateBar() {
    const live = player.mode === 'live';
    const sync = live ? `<span>⏱ DELAY</span><em>${player.delay >= 1 ? '−' + SS.fmtDelay(player.delay) : 'LIVE'}</em>` : `<span>⏱ SYNC</span><em>${player.speed}× · ${SS.fmtDelay(player.delay)}</em>`;
    const tb = $('#tbSync'); if (tb._v !== sync) { tb.innerHTML = sync; tb._v = sync; }
    const pl = live ? (player.playing ? '❚❚ PAUSE' : '▶ RESUME') : (player.playing ? '❚❚ PAUSE' : '▶ PLAY');
    const tp = $('#tbPlay'); if (tp.textContent !== pl) tp.textContent = pl;
  }
  const DLBL = (x) => (x === 0 ? 'LIVE' : x < 60 ? x + 's' : x / 60 + 'm');
  function toggleSync(on) {
    const open = on === undefined ? syncEl.hidden : on;
    if (!open) { syncEl.hidden = true; $('#tbSync').focus({ preventScroll: true }); showBar(); return; }
    renderSync();
    syncEl.hidden = false;
    showBar();
    const first = syncEl.querySelector('.ts-b.is-on') || syncEl.querySelector('button');
    if (first) first.focus({ preventScroll: true });
  }
  function renderSync() {
    const live = player.mode === 'live';
    syncEl.dataset.mode = player.mode;
    syncEl.innerHTML = live
      ? `<div class="ts-head"><span class="lbl">LIVE DELAY</span><b id="tsVal"></b><span id="tsSub"></span></div>
        <div class="ts-row"><span class="lbl">PRESETS</span>${SS.DELAYS.map((x) => `<button class="ts-b" type="button" data-d="${x}">${DLBL(x)}</button>`).join('')}</div>
        <div class="ts-row"><span class="lbl">NUDGE</span><button class="ts-b" type="button" data-n="5">+5 s</button><button class="ts-b" type="button" data-n="1">+1 s</button><button class="ts-b" type="button" data-n="-1">−1 s</button><button class="ts-b" type="button" data-n="-5">−5 s</button></div>
        <div class="ts-row"><span class="lbl">EXACT</span><form><input class="mono" maxlength="4" placeholder="M:SS" aria-label="Delay M:SS"><button class="ts-b ts-wide" type="submit">APPLY</button><span class="ts-err" role="alert" hidden></span></form></div>
        <div class="ts-row"><button class="ts-b ts-wide" type="button" data-a="play" id="tsPlay"></button><button class="ts-b ts-golive" type="button" data-a="golive">GO LIVE</button><button class="ts-b ts-wide" type="button" data-a="close">CLOSE</button></div>
        <p class="ts-note">Pausing holds the timing while the session carries on — the delay grows, like pausing your TV, up to 5:00. ←/→ nudge by 1 s while this panel is open.</p>`
      : `<div class="ts-head"><span class="lbl">REPLAY</span><b id="tsVal"></b><span id="tsSub"></span></div>
        <div class="ts-row"><span class="lbl">SPEED</span>${SS.SPEEDS.map((x) => `<button class="ts-b" type="button" data-speed="${x}">${x}×</button>`).join('')}</div>
        <div class="ts-row"><span class="lbl">SYNC OFFSET</span>${[0, 5, 10, 30, 60, 120].map((x) => `<button class="ts-b" type="button" data-d="${x}">${x === 0 ? '0s' : DLBL(x)}</button>`).join('')}<form><input class="mono" maxlength="4" placeholder="M:SS" aria-label="Sync offset M:SS"><button class="ts-b ts-wide" type="submit">APPLY</button><span class="ts-err" role="alert" hidden></span></form></div>
        <div class="ts-row"><span class="lbl">POSITION</span><button class="ts-b" type="button" data-skip="-30">−30 s</button><button class="ts-b ts-wide" type="button" data-a="play" id="tsPlay"></button><button class="ts-b" type="button" data-skip="30">+30 s</button>${player.returnPoint ? '<button class="ts-b ts-wide" type="button" data-a="return">↩ BACK</button>' : ''}<button class="ts-b ts-wide" type="button" data-a="close">CLOSE</button></div>
        <p class="ts-note">Sync offset lines the replay up with a recorded broadcast. ←/→ move 30 s.</p>`;
    updateSync();
  }
  function updateSync() {
    if (syncEl.hidden && !syncEl.innerHTML) return;
    const live = player.mode === 'live';
    if ((syncEl.dataset.mode || '') !== player.mode) { if (!syncEl.hidden) renderSync(); return; }
    const set = (id, v) => { const e = document.getElementById(id); if (e && e.textContent !== v) e.textContent = v; };
    if (live) {
      set('tsVal', player.delay >= 1 ? '−' + SS.fmtDelay(player.delay) : 'LIVE');
      set('tsSub', player.liveState !== 'LIVE' ? 'feed interrupted · holding your delay' : !player.playing ? 'paused · delay growing' : player.requestedDelay - player.delay > 1 ? `asked ${SS.fmtDelay(player.requestedDelay)} · the buffer holds ${SS.fmtDelay(player.delay)}` : player.delay >= 1 ? `${SS.fmtDelay(player.delay)} behind live` : 'at the live edge');
      syncEl.querySelectorAll('[data-d]').forEach((b) => b.classList.toggle('is-on', +b.dataset.d === Math.round(player.requestedDelay)));
      set('tsPlay', player.playing ? '❚❚ PAUSE' : '▶ RESUME');
    } else {
      set('tsVal', race ? `LAP ${session.lapAt(player.t) || '—'}/${session.totalLaps || '—'}` : (session.clockAt(player.t) != null ? U.fmtClock(session.clockAt(player.t)) + ' LEFT' : '—'));
      set('tsSub', `${SS.localClock(session, player.t)} local · ${player.speed}× · sync offset ${SS.fmtDelay(player.delay)}`);
      syncEl.querySelectorAll('[data-speed]').forEach((b) => b.classList.toggle('is-on', +b.dataset.speed === player.speed));
      syncEl.querySelectorAll('[data-d]').forEach((b) => b.classList.toggle('is-on', +b.dataset.d === Math.round(player.delay)));
      set('tsPlay', player.playing ? '❚❚ PAUSE' : '▶ PLAY');
    }
  }
  syncEl.addEventListener('click', (ev) => {
    const b = ev.target.closest('button'); if (!b) return;
    if (b.dataset.d != null) player.setDelay(+b.dataset.d);
    if (b.dataset.n) player.nudgeDelay(+b.dataset.n);
    if (b.dataset.speed) player.setSpeed(+b.dataset.speed);
    if (b.dataset.skip) player.skip(+b.dataset.skip);
    const a = b.dataset.a;
    if (a === 'play') player.toggle();
    else if (a === 'golive') player.goLive();
    else if (a === 'return') player.goReturn();
    else if (a === 'close') toggleSync(false);
    updateSync(); showBar();
  });
  syncEl.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const f = ev.target, v = SS.parseDelay(f.querySelector('input').value), err = f.querySelector('.ts-err');
    if (v == null) { err.textContent = 'Enter M:SS from 0:00 to 5:00'; err.hidden = false; return; }
    err.hidden = true; player.setDelay(v); updateSync();
  });
  $('#rail').addEventListener('click', (ev) => { if (ev.target.closest('.mode')) toggleSync(); });

  /* ---------------------------------------------------------- sessions (standalone TV app) */
  const sessionsEl = $('#sessions');
  const SESS = [
    { s: 'hungaroring-2026-race', t: 'Hungarian Grand Prix', n: 'Race · Hungaroring' },
    { s: 'kl-2026-qualifying', t: 'Bahrain Grand Prix', n: 'Qualifying · Kuala Lumpur' },
    { s: 'kl-2026-practice-2', t: 'Bahrain Grand Prix', n: 'Practice 2 · Kuala Lumpur' },
  ];
  $('#sessionsList').innerHTML = SESS.map((x) => `<a class="tvs-item${x.s === label ? ' is-on' : ''}" href="tv.html?s=${x.s}&app=1${state.safe ? '&safe=' + state.safe : ''}"><b>${x.t}</b><span>${x.n}</span><em>${x.s === label ? 'WATCHING' : 'REPLAY READY'}</em></a>`).join('');
  function openSessions() {
    bar.hidden = true; syncEl.hidden = true;
    sessionsEl.hidden = false;
    const on = sessionsEl.querySelector('.tvs-item.is-on') || sessionsEl.querySelector('a, button');
    if (on) on.focus({ preventScroll: true });
  }
  if (state.app) { const ex = bar.querySelector('[data-a=exit]'); ex.textContent = '‹ SESSIONS'; ex.title = 'Choose another session'; }

  /* ---------------------------------------------------------- remote / keyboard — same checks as the buttons
   * Works with a TV remote (D-pad, OK, Back, media keys) and a keyboard alike.
   * Controls hidden: ←/→ move in time (replay ±30 s) or move the delay (live ±5 s); OK, ↑ or ↓ bring up
   * the toolbar. Controls shown: the D-pad moves focus between controls, OK activates, Back closes —
   * panel first, then toolbar, then (standalone app) the session list. */
  const tgt = (ev) => (ev.target && ev.target.matches ? ev.target : document.body); // remote events may target the document
  const isBack = (ev) => ['Escape', 'GoBack', 'BrowserBack', 'Back'].includes(ev.key) || (ev.key === 'Backspace' && !tgt(ev).matches('input, textarea'));
  const focusables = () => [...document.querySelectorAll('#tvbar button, #tvbar select, #tvbar a, #syncPanel button, #syncPanel input, #sessions a')]
    .filter((el) => !el.closest('[hidden]') && el.getClientRects().length && el.getAttribute('aria-disabled') !== 'true');
  function moveFocus(dir) {
    const list = focusables();
    if (!list.length) return false;
    const cur = document.activeElement;
    if (!list.includes(cur)) { (list.find((x) => x.classList.contains('is-on')) || list[0]).focus({ preventScroll: true }); return true; }
    const a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
    let best = null, bestScore = Infinity;
    for (const el of list) {
      if (el === cur) continue;
      const b = el.getBoundingClientRect(), dx = b.left + b.width / 2 - ax, dy = b.top + b.height / 2 - ay;
      const primary = dir === 'left' ? -dx : dir === 'right' ? dx : dir === 'up' ? -dy : dy;
      if (primary <= 1) continue;
      const score = primary + (dir === 'left' || dir === 'right' ? Math.abs(dy) : Math.abs(dx)) * 2.5;
      if (score < bestScore) { bestScore = score; best = el; }
    }
    if (best) best.focus({ preventScroll: true });
    return !!best;
  }
  function step(dir) {
    const panel = !syncEl.hidden;
    if (player.mode === 'live') player.nudgeDelay(-dir * (panel ? 1 : 5)); // right = closer to live
    else player.skip(dir * 30);
    updateSync();
  }
  function back() {
    if (!sessionsEl.hidden) { sessionsEl.hidden = true; return; }
    if (!syncEl.hidden) { toggleSync(false); return; }
    if (!bar.hidden) { bar.hidden = true; if (bar.contains(document.activeElement)) document.activeElement.blur(); return; }
    if (state.app) openSessions();
  }
  const ARROW = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
  document.addEventListener('keydown', (ev) => {
    const k = ev.key;
    const typing = tgt(ev).matches('input, textarea');
    const ae = document.activeElement;
    const inUI = !!ae && ae !== document.body && (bar.contains(ae) || syncEl.contains(ae) || sessionsEl.contains(ae));
    if (isBack(ev)) { ev.preventDefault(); back(); return; }
    // remote media keys
    if (k === 'MediaPlayPause') { ev.preventDefault(); player.toggle(); showBar(); return; }
    if (k === 'MediaPlay') { ev.preventDefault(); player.play(); showBar(); return; }
    if (k === 'MediaPause' || k === 'MediaStop') { ev.preventDefault(); player.pause(); showBar(); return; }
    if (k === 'MediaFastForward' || k === 'MediaTrackNext') { ev.preventDefault(); step(1); showBar(); return; }
    if (k === 'MediaRewind' || k === 'MediaTrackPrevious') { ev.preventDefault(); step(-1); showBar(); return; }
    const dir = ARROW[k];
    if (dir) {
      if (typing && (dir === 'left' || dir === 'right')) return; // caret in the M:SS field
      ev.preventDefault();
      if (inUI || !sessionsEl.hidden) { moveFocus(dir); if (sessionsEl.hidden) showBar(); return; }
      if (dir === 'left' || dir === 'right') { step(dir === 'right' ? 1 : -1); showBar(); return; }
      showBar(); moveFocus(dir); return; // ↑/↓ with nothing focused: bring the controls up, focused
    }
    if ((k === 'Enter' || k === ' ') && inUI) { showBar(); return; } // let the focused control act
    if (k === 'Enter' && !inUI) { ev.preventDefault(); showBar(); moveFocus('down'); return; }
    if (typing) return;
    showBar();
    const lk = k.toLowerCase();
    if (lk === ' ' || lk === 'k') { ev.preventDefault(); player.toggle(); }
    else if (lk === 'd' || lk === 's') toggleSync();
    else if (lk === 't') pin('timing');
    else if (lk === 'a' || lk === '0') pin('auto');
    else if (/^[1-9]$/.test(lk) && modules[+lk - 1] && !modules[+lk - 1].manualOnly) pin(modules[+lk - 1].id);
    else if (lk === '[' || lk === ']') { if (player.can('speed')) { const sp = SS.SPEEDS, i = sp.indexOf(player.speed); player.setSpeed(sp[Math.max(0, Math.min(sp.length - 1, (i < 0 ? 4 : i) + (lk === ']' ? 1 : -1)))]); } }
    else if (lk === 'h') toggleReview(review.hidden);
    else if (lk === 'r') { optReduced.checked = !optReduced.checked; optReduced.dispatchEvent(new Event('change')); }
    else if (lk === 'b') { optBold.checked = !optBold.checked; optBold.dispatchEvent(new Event('change')); }
    else if (lk === 'l') { optLive.checked = !optLive.checked; optLive.dispatchEvent(new Event('change')); }
  });

  /* ---------------------------------------------------------- frame */
  const prov = $('#prov');
  const provText = () => `${player.mode === 'live' ? 'SIMULATED LIVE FROM RECORDING' : 'REPLAY'} · ${session.meta.meeting_name.toUpperCase()} ${session.meta.name.toUpperCase()} 2026 · ${session.d.source === 'f1-static-public' ? 'OFFICIAL TIMING ARCHIVE' : 'PUBLIC LIVE TIMING (RECORDED)'}`;
  let forceJump = true, lastVm = null, opened = false;
  fit();
  buildTower();
  setFollow(state.follow);
  if (state.module === 'timing') { state.module = 'auto'; setWide(true); }

  player.on(({ now, jumped, crossed, cursor, gen }) => {
    jumped = jumped || forceJump;
    forceJump = false;
    const vm = SS.vm(session, cursor, { now });
    vm.byNum = Object.fromEntries(vm.rows.map((r) => [r.num, r]));
    lastVm = vm;
    const reduced = SS.motion.reduced;
    const rd = railModel(vm, player);
    rd.jumped = jumped;
    rail.reduced = reduced;
    rail.update(rd);
    tower.render(vm, { jumped, recent: SS.recentContext(session, now), reduced, speed: player.speed });
    ticker.render(now, jumped, gen);
    takeover.reduced = reduced;
    takeover.speed = player.speed;
    if (jumped) takeover.clear();
    else if (crossed.length) { takeover.offer(crossed, now); onEvents(crossed); }
    takeover.tick(now);
    if (!opened) { opened = true; opening.done(); }
    direct(vm);
    renderModChips(vm);
    const cur = modules.find((m) => m.id === state.current) || {};
    const ttl = state.wide ? 'TIMING' : cur.label || '';
    if ($('#stageTitle').textContent !== ttl) $('#stageTitle').textContent = ttl;
    const why = state.whyFlash && performance.now() < state.whyFlash.until ? '· ' + state.whyFlash.txt : state.module === 'auto' ? (state.why && state.why !== 'rotation' ? '· ' + state.why : '') : '· pinned';
    if ($('#stageWhy').textContent !== why) $('#stageWhy').textContent = why;
    const focus = [];
    if (state.follow) focus.push(state.follow);
    const bp = battlePair(vm);
    if (state.current === 'battle' && bp && !state.wide) focus.push(bp[0].num, bp[1].num);
    tower.setHighlight(state.current === 'battle' && bp && !state.wide ? [bp[0].num, bp[1].num] : []);
    if (!state.wide) {
      switch (state.current) {
        case 'track':
          if (trackView) { trackView.setFocus(focus); trackView.setMode(player.mode); trackView.render(vm, now); }
          if (lineView) { lineView.setFocus(focus); lineView.setMode(player.mode); lineView.render(vm, now); }
          if (ribbon) { ribbon.setFocus(focus); ribbon.render(vm, jumped); }
          break;
        case 'battle': battle.render(vm, bp, now); break;
        case 'pits': pits.render(vm, now); renderStrategyRight(vm); break;
        case 'driver':
          if (!state.follow) break;
          dcard.render(vm, state.follow, now);
          if (dMap) { dMap.setFocus([state.follow]); dMap.setMode(player.mode); dMap.render(vm, now); }
          if (dLine) { dLine.setFocus([state.follow]); dLine.setMode(player.mode); dLine.render(vm, now); }
          if (slowTick()) { const h = `<div class="lbl">${race ? 'LAP TIMES THIS STINT' : 'LAP TIMES'}</div>${SS.lapChartHTML(session, state.follow, now, 14, race)}`; if (dLaps._v !== h) { dLaps.innerHTML = h; dLaps._v = h; } }
          break;
        case 'result': result.render(vm, now); break;
        case 'spread': ladder.setFocus(focus); ladder.render(vm, jumped); onTrack.render(vm); renderZone(vm); break;
      }
    }
    if (prov.textContent !== provText()) prov.textContent = provText();
    updateBar();
    if (!syncEl.hidden) updateSync();
    renderStale();
    if (reviewReady) syncReview();
  });

  /* Live feed health: a frozen screen must say it is frozen. */
  const staleEl = $('#stale');
  let wasStale = false, recoveredAt = 0;
  function renderStale() {
    const stale = player.mode === 'live' && player.liveState !== 'LIVE';
    canvas.classList.toggle('is-stale', stale);
    if (stale) {
      wasStale = true;
      staleEl.hidden = false;
      staleEl.className = 'tv-stale';
      const html = player.liveState === 'RECONNECTING'
        ? '<b>RECONNECTING</b><span>Timing feed interrupted — holding the last known order</span>'
        : `<b>TIMING PAUSED</b><span>No update for <em class="mono">${player.staleSeconds()} s</em> — holding the last known order</span>`;
      if (staleEl._v !== html) { staleEl.innerHTML = html; staleEl._v = html; }
    } else if (wasStale) {
      wasStale = false;
      recoveredAt = performance.now();
      staleEl.className = 'tv-stale is-ok';
      staleEl.innerHTML = `<b>BACK LIVE</b><span>Caught up${player.delay >= 1 ? ' to your ' + SS.fmtDelay(player.delay) + ' delay' : ' to the live edge'} — changes while paused are in the ticker</span>`;
      staleEl._v = '';
    } else if (recoveredAt && performance.now() - recoveredAt > 3500) {
      recoveredAt = 0;
      staleEl.hidden = true;
    }
  }

  function renderZone(vm) {
    let html;
    if (kind === 'qualifying' && vm.advance) {
      const active = vm.rows.filter((r) => !r.qe);
      const cut = active[vm.advance - 1];
      const at = active.slice(vm.advance - 2, vm.advance + 4);
      html = `<div class="ot-head"><span class="lbl">AROUND THE CUT</span><b class="mono">${cut && cut.qTime != null ? U.fmtLap(cut.qTime) : '—'}</b></div><ol class="zone-list">${at.map((r) => {
        const delta = r.qTime != null && cut && cut.qTime != null ? r.qTime - cut.qTime : null;
        return `<li class="${r.index < vm.advance ? 'is-safe' : 'is-risk'}${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${delta == null ? '' : delta === 0 ? 'SETS CUT' : U.fmtDelta(delta)}</em></li>`;
      }).join('')}</ol>`;
    } else if (kind === 'qualifying') {
      html = `<div class="ot-head"><span class="lbl">FIGHT FOR POLE</span></div><ol class="zone-list">${vm.rows.slice(0, 6).map((r) => `<li class="is-top${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${r.qGap ? '+' + r.qGap.toFixed(3) : r.qTime != null ? 'POLE TIME' : ''}</em></li>`).join('')}</ol>`;
    } else {
      const ev = session.events.filter((e) => SS.avail(e) <= vm.t && (e.type === 'SESSION_BEST' || e.type === 'FLAG' || e.type === 'STOPPED' || (e.type === 'IMPROVEMENT' && session.drivers[e.drivers[0]] && (e.pos || 99) <= 10))).slice(-7).reverse();
      html = `<div class="ot-head"><span class="lbl">SESSION LOG</span></div><ol class="zone-list zone-log">${ev.map((e) => { const dd = SS.describe(session, e, vm.t); return `<li class="tone-${dd.tone}"><span class="mono">${SS.stamp(session, e)}</span><i></i><b>${dd.tag}</b><span>${dd.title}</span></li>`; }).join('') || '<li class="dim">Quiet so far</li>'}</ol>`;
    }
    if (zone._v !== html) { zone.innerHTML = html; zone._v = html; }
  }

  /* ---------------------------------------------------------- review drawer (prototype only, not the product UI) */
  const review = $('#review');
  const playBtn = $('#rvPlay');
  let reviewReady = false;
  document.querySelectorAll('#rvSession button').forEach((b) => b.classList.toggle('is-on', b.dataset.s === label));
  $('#rvSession').addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) { const q = new URLSearchParams(location.search); q.set('s', b.dataset.s); ['t', 'follow', 'map', 'pair'].forEach((x) => q.delete(x)); location.search = q.toString(); } });
  $('#rvMoments').innerHTML = session.moments.map((m, i) => `<button class="rv-m" data-m="${i}" title="${m.note}">${m.label}</button>`).join('');
  $('#rvMoments').addEventListener('click', (ev) => { const b = ev.target.closest('[data-m]'); if (b) { player.markReturn(); player.seek(session.moments[+b.dataset.m].t); player.play(); } });
  playBtn.addEventListener('click', () => player.toggle());
  review.querySelectorAll('[data-skip]').forEach((b) => b.addEventListener('click', () => player.skip(+b.dataset.skip)));
  const speedSel = $('#rvSpeed');
  speedSel.value = String(player.speed);
  speedSel.addEventListener('change', () => player.setSpeed(+speedSel.value));
  const optLive = $('#optLive');
  optLive.checked = player.mode === 'live';
  optLive.addEventListener('change', () => { state.live = optLive.checked; player.setMode(state.live ? 'live' : 'replay'); if (!state.live) { player.delay = 0; player.setSpeed(+speedSel.value); } $('#optStale').hidden = !state.live; if (!syncEl.hidden) renderSync(); });
  $('#optStale').hidden = player.mode !== 'live';
  $('#optStale').addEventListener('click', () => player.simulateStale(8));
  const optBold = $('#optBold');
  optBold.checked = params.get('bold') === '1';
  optBold.addEventListener('change', () => rail.setIntensity(optBold.checked ? 'bold' : 'calm'));
  const optReduced = $('#optReduced');
  optReduced.checked = SS.motion.reduced;
  optReduced.addEventListener('change', () => SS.motion.set(optReduced.checked ? 'reduced' : 'full'));
  SS.motion.onChange((r) => { optReduced.checked = r; });
  const optTO = $('#optTakeovers');
  optTO.addEventListener('change', () => { takeover.enabled = optTO.checked && !state.wide; if (!optTO.checked) takeover.clear(); });
  const modSel = $('#optModule');
  modSel.innerHTML = '<option value="auto">Director (auto)</option>' + modules.map((m) => `<option value="${m.id}">${m.label}</option>`).join('');
  modSel.value = state.module;
  modSel.addEventListener('change', () => pin(modSel.value));
  const mapSel = $('#optMap');
  if (!caps.outline) { mapSel.querySelector('[value=outline]').disabled = true; mapSel.querySelector('[value=outline]').textContent = 'Outline (not available here)'; }
  mapSel.value = state.map;
  mapSel.addEventListener('change', () => { state.map = mapSel.value; buildMap(); request('track', 15, 'map view'); });
  const optBattle = $('#optBattle');
  optBattle.value = state.battleMode === 'pinned' ? 'recommended' : state.battleMode;
  optBattle.addEventListener('change', () => { state.battleMode = optBattle.value; state.pinnedUntil = 0; });
  if (!race) optBattle.closest('label').hidden = true;
  const optSafe = $('#optSafe');
  optSafe.value = String(state.safe);
  optSafe.addEventListener('change', () => { state.safe = +optSafe.value; SS.prefs.set('tv.safe', state.safe); towerKey = ''; fit(); });
  const optText = $('#optText');
  optText.value = String(state.text);
  optText.addEventListener('change', () => { state.text = +optText.value; SS.prefs.set('tv.text', state.text); towerKey = ''; fit(); });
  $('#rvHide').addEventListener('click', () => toggleReview(false));
  $('#rvShow').addEventListener('click', () => toggleReview(true));
  function toggleReview(on) { review.hidden = !on; $('#rvShow').hidden = on; }
  if (params.get('clean') === '1') toggleReview(false);
  function syncReview() {
    const pt = player.playing ? '❚❚ Pause' : '▶ Play';
    if (playBtn.textContent !== pt) playBtn.textContent = pt;
    if (speedSel.value !== String(player.speed) && player.mode !== 'live') speedSel.value = String(player.speed);
    speedSel.disabled = player.mode === 'live';
    review.querySelectorAll('[data-skip]').forEach((b) => (b.disabled = player.mode === 'live'));
    if (modSel.value !== (state.wide ? 'timing' : state.module) && document.activeElement !== modSel) modSel.value = state.wide ? 'timing' : state.module;
  }
  reviewReady = true;
  if (params.get('bar') === '1') showBar();
  if (params.get('sync') === '1') toggleSync(true);
  if (params.get('sessions') === '1') openSessions();
  window.__tv = { session, player, state, rail, takeover, show, pin, toggleSync, showBar, openSessions };
})();

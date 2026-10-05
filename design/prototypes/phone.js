/* Phone prototype — its own hierarchy, not a shrunken desktop.
 * Primary task: find (or follow) my driver and understand the latest change.
 *  - App bar: brand, the session being watched (tap to change), menu.
 *  - Rail: flag, lap or clock, live/replay.
 *  - Session-aware tabs. Race: TIMING · TRACK · STRATEGY · ACTIVITY. Qualifying: TIMING · CUT LINE · TRACK ·
 *    ACTIVITY. Practice: TIMING · RUNS · TRACK · ACTIVITY. Race-only concepts never appear elsewhere.
 *  - Row tap opens Driver Focus; following is an explicit action there; Compare picks any two drivers.
 *  - Minimal transport; speed, exact position, sync offset and live delay live in one sheet.
 *  - Moments are a compact banner at the bottom of the content: the leaders are never covered.
 *  - Landscape: timing on the left, the chosen panel on the right. */
(function () {
  'use strict';
  const SS = window.SS;
  const U = SS.util;
  const P = SS.PRIORITY;
  const $ = (s) => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  const label = params.get('s') || 'hungaroring-2026-race';
  const session = new SS.Session(label);
  const kind = session.kind;
  const race = kind === 'race';
  const C = SS.cols;
  const ph = $('#ph');
  document.body.dataset.kind = kind;
  SS.motion.init(params.get('reduced'));
  const caps = SS.capabilities(session, { map: params.get('map'), live: params.get('live') === '1' });

  const SESSIONS = [
    { s: 'hungaroring-2026-race', meeting: 'Hungarian Grand Prix', short: 'Hungarian GP', name: 'Race', where: 'Hungaroring' },
    { s: 'kl-2026-qualifying', meeting: 'Bahrain Grand Prix', short: 'Bahrain GP', name: 'Qualifying', where: 'Kuala Lumpur' },
    { s: 'kl-2026-practice-2', meeting: 'Bahrain Grand Prix', short: 'Bahrain GP', name: 'Practice 2', where: 'Kuala Lumpur' },
  ];
  const cur = SESSIONS.find((x) => x.s === label) || SESSIONS[0];
  $('#sessMeeting').textContent = cur.short;
  $('#sessName').textContent = cur.name;
  const opening = SS.brand.opening({ posture: 'phone', title: `${cur.meeting} · ${cur.name}`, phases: ['Connecting to Slipstream', 'Reading the timing history', 'Building the race state'], hold: params.get('opening') === '1' ? 3000 : 0 });

  const TEAM_SHORT = { 'Red Bull Racing': 'Red Bull', 'Haas F1 Team': 'Haas', 'Kick Sauber': 'Sauber', 'Aston Martin': 'Aston Martin' };
  const teamShort = (t) => TEAM_SHORT[t] || (t || '').replace(/ F1 Team$/, '');

  const ico = (d) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const ICON = {
    timing: ico('<path d="M4 6h16M4 12h16M4 18h16"/><path d="M2 6h0M2 12h0M2 18h0"/>'),
    track: ico('<path d="M5 17c-2-3 0-8 3-10s6-3 9-1 3 6 0 8-6 0-8 2-2 4-4 1z"/>'),
    strategy: ico('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>'),
    activity: ico('<path d="M3 12h4l3-7 4 14 3-7h4"/>'),
    cut: ico('<path d="M3 8h18"/><path d="M3 16h4M10 16h4M17 16h4"/>'),
    runs: ico('<circle cx="12" cy="13" r="7"/><path d="M12 13V9M10 3h4"/>'),
  };
  const TABS = race
    ? [['timing', 'TIMING', ICON.timing], ['track', 'TRACK', ICON.track], ['strategy', 'STRATEGY', ICON.strategy], ['activity', 'ACTIVITY', ICON.activity]]
    : [['timing', 'TIMING', ICON.timing], ['session', kind === 'qualifying' ? 'CUT LINE' : 'RUNS', kind === 'qualifying' ? ICON.cut : ICON.runs], ['track', 'TRACK', ICON.track], ['activity', 'ACTIVITY', ICON.activity]];
  const tabIds = TABS.map((t) => t[0]);

  const state = {
    tab: tabIds.includes(params.get('tab')) ? params.get('tab') : 'timing',
    ctx: 'track',                    // landscape: the panel beside the timing
    metric: params.get('metric') || (race ? 'int' : 'time'),
    follow: session.drivers[params.get('follow')] ? params.get('follow') : (SS.prefs.get('follow.' + label, '') || ''),
    focus: null, compare: null, result: false,
    act: params.get('act') === 'rc' ? 'rc' : 'story',
    storyMin: P.HIGHLIGHT,
    sheet: null,
    land: false,
  };
  if (!session.drivers[state.follow]) state.follow = '';

  /* ---------------------------------------------------------- rail */
  const rail = new SS.StatusRail($('#rail'), { posture: 'phone' });
  const railModel = SS.railModel(session);

  /* ---------------------------------------------------------- timing */
  // Row anatomy: position · identity (code + team, never squeezed out) · one primary value · tyre.
  // Transient chips take the team line instead of overlapping values.
  const drvCol = { key: 'driver', label: 'DRIVER', w: 'minmax(84px, 1fr)', cls: 'c-drv c-drvp', cell: (r) => `<i class="tw-team"></i><span class="tw-nt"><b class="tw-code">${r.code}</b><em class="tw-tm">${teamShort(r.team)}</em></span>` };
  const outFirst = (col) => Object.assign({}, col, { cell: (r, vm) => (r.out ? `<span class="st-out">${r.out}</span>` : col.cell(r, vm)) });
  const METRICS = race
    ? { int: ['INT', () => outFirst(C.int('78px'))], gap: ['GAP', () => outFirst(C.gap('82px'))] }
    : kind === 'qualifying'
      ? { time: ['TIME', () => C.qtime('76px')], gap: ['GAP', () => C.qgap('70px')] }
      : { time: ['BEST', () => C.best('76px', 'time')], gap: ['GAP', () => C.pgap('70px')], last: ['LAST', () => C.last('76px')] };
  if (!METRICS[state.metric]) state.metric = Object.keys(METRICS)[0];
  let tower = null;
  function buildTower() {
    const host = $('#tower');
    host.innerHTML = '';
    host.className = '';
    const cols = [C.pos('26px'), drvCol, METRICS[state.metric][1](), C.tyre('54px')];
    // Timed sessions show both time and gap when there is room (landscape / wide phones).
    if (!race && (state.land || window.innerWidth >= 400)) cols.splice(3, 0, state.metric === 'gap' ? METRICS.time[1]() : METRICS.gap[1]());
    tower = new SS.Tower(host, { session, columns: cols, rowH: state.land ? 30 : 36, posture: 'phone', onRow: (n) => openFocus(n) });
    tower.setFollow(state.follow ? [state.follow] : []);
    forceJump = true;
  }
  const metricEl = $('#metric');
  metricEl.innerHTML = Object.entries(METRICS).map(([k, [lbl]]) => `<button type="button" data-m="${k}">${lbl}</button>`).join('');
  metricEl.addEventListener('click', (ev) => { const b = ev.target.closest('[data-m]'); if (!b) return; state.metric = b.dataset.m; syncMetric(); buildTower(); });
  const syncMetric = () => metricEl.querySelectorAll('[data-m]').forEach((b) => { b.classList.toggle('is-on', b.dataset.m === state.metric); b.setAttribute('aria-pressed', b.dataset.m === state.metric); });
  syncMetric();
  $('#timingHint').textContent = 'tap a driver';

  /* ---------------------------------------------------------- track */
  let trackView = null, lineView = null, ribbon = null, ladder = null;
  const trackHost = $('#track');
  if (caps.positions === 'outline') trackView = new SS.TrackMap(trackHost, { session, posture: 'phone' });
  else if (caps.positions === 'line') lineView = new SS.TrackLine(trackHost, { session, posture: 'phone', lanes: 3 });
  else trackHost.innerHTML = '<div class="ph-note"><b>Car positions are not available.</b><span>Order and gaps come straight from timing — shown below in time.</span></div>';
  if (race) ribbon = new SS.GapRibbon($('#ribbon'), { session, posture: 'phone' });
  else ladder = new SS.Ladder($('#ribbon'), { session, posture: 'phone' });

  /* ---------------------------------------------------------- strategy (race) / session (timed) */
  let pitBoard = null, onTrack = null;
  if (race) {
    $('#strategy').innerHTML = '<div id="stNow"></div><div class="ph-mod" id="stPits"></div><div id="stPir"></div><div id="stStints"></div><div id="stCond"></div>';
    pitBoard = new SS.PitBoard($('#stPits'), { session, posture: 'phone' });
  } else {
    $('#sessionPane').innerHTML = `<div id="ssCells"></div><div class="pnl"><header class="pnl-h"><div><span class="pnl-eb">${kind === 'qualifying' ? 'QUALIFYING' : 'PRACTICE'}</span><b class="pnl-t">${kind === 'qualifying' ? 'Around the cut' : 'Session log'}</b></div></header><div class="pnl-b" id="ssZone"></div></div><div class="pnl"><div class="pnl-b" id="ssOnTrack"></div></div><div id="ssCond"></div>`;
    onTrack = new SS.OnTrack($('#ssOnTrack'), { session, posture: 'phone', max: 12 });
  }

  /* ---------------------------------------------------------- activity: story + official race control */
  const actSeg = $('#actSeg');
  actSeg.innerHTML = `<button type="button" role="tab" data-a="story">STORY</button><button type="button" role="tab" data-a="rc">RACE CONTROL <span class="mono" id="rcCount"></span></button>`;
  actSeg.addEventListener('click', (ev) => { const b = ev.target.closest('[data-a]'); if (b) { state.act = b.dataset.a; syncAct(); } });
  function syncAct() {
    actSeg.querySelectorAll('[data-a]').forEach((b) => { b.classList.toggle('is-on', b.dataset.a === state.act); b.setAttribute('aria-selected', b.dataset.a === state.act); });
    document.querySelectorAll('.ph-act').forEach((x) => (x.hidden = x.dataset.act !== state.act));
    $('#storyFilter').hidden = state.act !== 'story';
    feedSilent = true;
  }
  $('#storyFilter').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-f]'); if (!b) return;
    state.storyMin = b.dataset.f === 'hl' ? P.HIGHLIGHT : P.FEED;
    $('#storyFilter').querySelectorAll('[data-f]').forEach((x) => x.classList.toggle('is-on', x === b));
    feed.setMin(state.storyMin);
  });
  let feedSilent = true;
  const feed = new SS.Feed($('#feed'), {
    session, min: P.HIGHLIGHT, max: 50, posture: 'phone', live: () => player.mode === 'live',
    onPick: (e) => {
      if (player.mode === 'live') return;
      player.markReturn();
      player.seek(Math.max(session.begin, e.t - 10));
      player.play();
      showTab('timing');
    },
  });
  syncAct();

  /* ---------------------------------------------------------- tabs + landscape */
  const tabsEl = $('#tabs');
  tabsEl.innerHTML = TABS.map(([id, lbl, svg]) => `<button type="button" data-tab="${id}">${svg}${lbl}</button>`).join('');
  tabsEl.addEventListener('click', (ev) => { const b = ev.target.closest('[data-tab]'); if (b) showTab(b.dataset.tab); });
  const ctxbar = $('#ctxbar');
  ctxbar.innerHTML = TABS.filter(([id]) => id !== 'timing').map(([id, lbl]) => `<button type="button" data-ctx="${id}">${lbl}</button>`).join('');
  ctxbar.addEventListener('click', (ev) => { const b = ev.target.closest('[data-ctx]'); if (b) showTab(b.dataset.ctx); });
  function showTab(id) {
    closePage();
    if (id !== 'timing') state.ctx = id;
    state.tab = id;
    const visible = state.land ? ['timing', state.ctx] : [id];
    document.querySelectorAll('.ph-pane').forEach((p) => p.classList.toggle('is-on', visible.includes(p.dataset.pane)));
    document.querySelectorAll('.ph-pane').forEach((p) => p.classList.toggle('is-ctx', state.land && p.dataset.pane === state.ctx));
    tabsEl.querySelectorAll('[data-tab]').forEach((b) => { const on = b.dataset.tab === id; b.classList.toggle('is-on', on); b.setAttribute('aria-current', on ? 'page' : 'false'); });
    ctxbar.querySelectorAll('[data-ctx]').forEach((b) => b.classList.toggle('is-on', b.dataset.ctx === state.ctx));
    if (id === 'activity') feedSilent = true;
    slowNext = 0;
  }
  const landMq = matchMedia('(orientation: landscape) and (max-height: 540px)');
  function applyLand() {
    state.land = landMq.matches;
    ph.classList.toggle('is-land', state.land);
    buildTower();
    showTab(state.land && state.tab === 'timing' ? state.ctx : state.tab);
  }
  landMq.addEventListener ? landMq.addEventListener('change', applyLand) : landMq.addListener(applyLand);

  /* ---------------------------------------------------------- follow (explicit) */
  const followEl = $('#follow');
  function setFollow(n) {
    state.follow = n || '';
    SS.prefs.set('follow.' + label, state.follow);
    if (tower) tower.setFollow(state.follow ? [state.follow] : []);
    slowNext = 0;
  }
  followEl.addEventListener('click', (ev) => {
    if (ev.target.closest('[data-a=unfollow]')) { setFollow(''); return; }
    if (state.follow) openFocus(state.follow);
  });
  function renderFollow(vm) {
    // Not shown while that driver's own page is open: the same summary twice adds nothing.
    const show = !!state.follow && state.focus !== state.follow && !state.land;
    followEl.hidden = !show;
    if (!show) return;
    const r = vm.byNum[state.follow];
    if (!r) return;
    const ahead = vm.rows[r.index - 1];
    let rel = '';
    if (race) rel = r.out ? r.out : r.inPit ? 'IN PIT' : r.index === 0 ? 'LEADING' : r.intLaps ? r.intText : r.intVal != null ? `+${r.intVal.toFixed(3)} to ${ahead ? ahead.code : ''}` : '';
    else if (kind === 'qualifying') rel = (r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME') + (r.qGap ? ` · +${r.qGap.toFixed(3)}` : '');
    else rel = (r.best || 'NO TIME') + (r.pGap ? ` · +${r.pGap.toFixed(3)}` : '');
    const drop = kind === 'qualifying' && vm.advance && !r.qe && r.index >= vm.advance;
    const html = `<i style="background:${r.colour}"></i><span class="pfw-l"><span class="lbl">FOLLOWING</span><span><b class="mono">P${r.pos}</b> <strong>${r.code}</strong> <span class="mono">${rel}</span>${drop ? ' <em class="chip-drop">DROP ZONE</em>' : ''}</span></span><span class="ph-follow-t">${SS.compoundBadge(r.compound, r.age)}</span><span class="pfw-x" data-a="unfollow" role="button" aria-label="Stop following" title="Stop following">×</span>`;
    if (followEl._v !== html) { followEl.innerHTML = html; followEl._v = html; }
  }

  /* ---------------------------------------------------------- driver focus page */
  const focusPage = $('#focusPage'), comparePage = $('#comparePage');
  let battle = null;
  function openFocus(n) { state.focus = n; state.compare = null; state.result = false; comparePage.hidden = true; focusPage.hidden = false; focusPage.scrollTop = 0; focusPage._v = ''; slowNext = 0; }
  function closePage() { state.focus = null; state.compare = null; state.result = false; focusPage.hidden = true; comparePage.hidden = true; }
  focusPage.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-a]'); if (!b) return;
    if (b.dataset.a === 'back') closePage();
    else if (b.dataset.a === 'follow') { setFollow(state.follow === state.focus ? '' : state.focus); focusPage._v = ''; }
    else if (b.dataset.a === 'compare') openCompare(state.focus);
  });
  const cell = (l, v, sub = '') => `<div><span class="lbl">${l}</span><b>${v}</b>${sub ? `<small>${sub}</small>` : ''}</div>`;
  const secTxt = (r) => [r.s1, r.s2, r.s3].map((x) => (x == null || x === '' ? '—' : (+x).toFixed(3))).join(' · ');
  function renderFocus(vm, now) {
    const r = vm.byNum[state.focus];
    if (!r) return;
    const D = session.drivers[r.num];
    const ahead = vm.rows[r.index - 1], behind = vm.rows[r.index + 1];
    const following = state.follow === r.num;
    const posSub = r.out ? r.out : race ? (r.index === 0 ? 'LEADER' : r.gapLaps ? r.gapText : r.gapVal != null ? '+' + r.gapVal.toFixed(3) : '') : kind === 'qualifying' ? (r.qGap ? '+' + r.qGap.toFixed(3) : r.qTime != null ? 'FASTEST' : '') : (r.pGap ? '+' + r.pGap.toFixed(3) : r.best ? 'FASTEST' : '');
    const st = SS.stints(session, r.num, now);
    const dr = SS.dryRule(st);
    let cells = [];
    if (race) {
      cells = [
        cell('AHEAD', ahead ? `${ahead.code} · P${ahead.pos}` : '—', ahead && r.intVal != null && !r.intLaps ? `<span class="mono">+${r.intVal.toFixed(3)} s</span>` : r.intLaps ? r.intText : ''),
        cell('BEHIND', behind ? `${behind.code} · P${behind.pos}` : '—', behind && behind.intVal != null && !behind.intLaps ? `<span class="mono">+${behind.intVal.toFixed(3)} s</span>` : ''),
        cell('TYRE', `${SS.compoundBadge(r.compound, r.age)}`, r.usage ? r.usage.toLowerCase() + ' set' : ''),
        cell('STINT', `<span class="mono">${r.stint != null ? r.stint : '—'}</span> laps`),
        cell('STOPS', `<span class="mono">${r.pits}</span>`, r.inPit ? 'in the pit lane now' : ''),
        cell('LAST LAP', `<span class="mono ${r.lastIsPB ? 't-green' : ''}">${r.last || '—'}</span>`),
        cell('BEST LAP', `<span class="mono ${r.bestIsFastest ? 't-purple' : ''}">${r.best || '—'}</span>`),
        cell('SECTORS · LAST', `<span class="mono">${secTxt(r)}</span>`),
      ];
    } else if (kind === 'qualifying') {
      const cutTxt = r.qe ? 'ELIMINATED' : vm.advance ? (r.index < vm.advance ? 'ABOVE CUT' : 'BELOW CUT') : vm.phase === 'Q3' ? 'POLE SHOOTOUT' : '—';
      cells = [
        cell('SEGMENT', vm.phase || '—', cutTxt),
        cell('THIS SEGMENT', `<span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span>`),
        ...['Q1', 'Q2', 'Q3'].map((q, i) => cell(q, `<span class="mono">${r.qr && r.qr[i] != null ? U.fmtLap(r.qr[i]) : '—'}</span>`)),
        cell('TYRE', `${SS.compoundBadge(r.compound, r.age)}`, r.usage ? r.usage.toLowerCase() + ' set' : ''),
        cell('NOW', r.activity === 'ON_TRACK' ? 'ON TRACK' : r.inPit || r.activity === 'IN_PIT' ? 'IN PIT' : '—'),
        cell('SECTORS · LAST', `<span class="mono">${secTxt(r)}</span>`),
      ];
    } else {
      cells = [
        cell('BEST', `<span class="mono">${r.best || '—'}</span>`), cell('LAST', `<span class="mono">${r.last || '—'}</span>`),
        cell('TYRE', `${SS.compoundBadge(r.compound, r.age)}`, r.usage ? r.usage.toLowerCase() + ' set' : ''),
        cell('STINT', `<span class="mono">${r.stint != null ? r.stint : '—'}</span> laps`), cell('STOPS', `<span class="mono">${r.pits}</span>`),
        cell('NOW', r.activity === 'ON_TRACK' ? 'ON TRACK' : r.inPit || r.activity === 'IN_PIT' ? 'IN PIT' : '—'),
        cell('SECTORS · LAST', `<span class="mono">${secTxt(r)}</span>`),
      ];
    }
    const evs = session.events.filter((e) => SS.avail(e) <= now && e.priority >= P.FEED && e.drivers.includes(r.num)).slice(-6).reverse();
    const pits = race && st.stops.length ? `<ol class="dp-pits">${st.stops.map((p, i) => `<li><span class="lbl">STOP ${i + 1}</span><b class="mono">LAP ${p.lap}</b><span>${p.prev ? SS.compoundBadge(p.prev, null, { noAge: true }) : ''}<em>›</em>${p.next ? SS.compoundBadge(p.next, null, { noAge: true }) : '<span class="dim">?</span>'}</span><span class="mono">LANE ${p.lane ? p.lane.toFixed(1) + 's' : '—'}</span></li>`).join('')}</ol><p class="pnl-note">Pit-lane time is the full lane transit, not stationary time.</p>` : '';
    const extra = SS.Focus && kind === 'qualifying' && SS.Focus.qualifying ? SS.Focus.qualifying(session, r.num, now) : SS.Focus && kind === 'practice' && SS.Focus.practice ? SS.Focus.practice(session, r.num, now) : '';
    const html = `<header class="pf-head" style="--team:${r.colour}">
        <button class="pf-back" type="button" data-a="back" aria-label="Back">‹</button>
        <div class="pf-id"><span class="pf-num">#${r.num} · ${D.team}</span><h2>${(D.name || '').split(' ')[0]} <b>${U.titleCase(D.surname)}</b></h2></div>
        <div class="pf-pos"><b class="mono">P${r.pos}</b><em class="mono">${posSub}</em></div>
      </header>
      <div class="pf-actions"><button type="button" data-a="follow" class="${following ? 'is-on' : ''}" aria-pressed="${following}">${following ? '★ FOLLOWING' : '☆ FOLLOW'}</button>${race ? '<button type="button" data-a="compare">COMPARE WITH…</button>' : ''}</div>
      <div class="pf-body">
        <div class="dp-cells pf-cells">${cells.join('')}</div>
        ${race ? SS.panel('TYRES', 'Strategy so far', '', `<div class="pf-seq">${SS.compoundSeq(st.list.map((x) => x.c))}<span class="dr-${dr.key}">${dr.text}</span></div>${pits}`, 'pnl-pf') : ''}
        ${extra}
        ${SS.panel(race ? 'CURRENT STINT' : 'THIS SESSION', 'Lap times', '', SS.lapChartHTML(session, r.num, now, 12, race), 'pnl-laps')}
        ${SS.panel('MOMENTS', `${r.code} so far`, '', evs.length ? `<ol class="dp-evs">${evs.map((e) => { const d = SS.describe(session, e, now); return `<li class="tone-${d.tone}"><span class="mono">${SS.stamp(session, e)}</span><b>${d.title}</b><em>${d.detail || ''}</em></li>`; }).join('')}</ol>` : '<div class="pnl-empty">Nothing yet for this driver</div>', 'pnl-dev')}
        ${race ? '<p class="pnl-note">Pace trend and outlook come from the server’s driver model in production; not reproduced from timing here.</p>' : ''}
      </div>`;
    if (focusPage._v !== html) { focusPage.innerHTML = html; focusPage._v = html; }
  }

  /* ---------------------------------------------------------- compare (race) + result */
  function openCompare(a) {
    const vm = lastVm;
    const r = vm && vm.byNum[a];
    const other = r ? (vm.rows[r.index - 1] || vm.rows[r.index + 1]) : null;
    state.compare = [a, other ? other.num : null];
    state.focus = null; state.result = false;
    focusPage.hidden = true; comparePage.hidden = false; comparePage._v = ''; comparePage.scrollTop = 0;
    buildCompare();
  }
  function openResult() { state.result = true; state.compare = null; state.focus = null; focusPage.hidden = true; comparePage.hidden = false; comparePage._v = ''; buildResult(); }
  const optList = (sel) => Object.values(session.drivers).sort((x, y) => x.code.localeCompare(y.code)).map((D) => `<option value="${D.num}"${D.num === sel ? ' selected' : ''}>${D.code} · ${U.titleCase(D.surname)}</option>`).join('');
  function buildCompare() {
    comparePage.innerHTML = `<header class="pf-head pf-head--plain"><button class="pf-back" type="button" data-a="back" aria-label="Back">‹</button><div class="pf-id"><span class="pf-num">RACE INTELLIGENCE</span><h2><b>Compare</b></h2></div></header>
      <div class="pc-pick"><select id="cmpA" aria-label="Driver A">${optList(state.compare[0])}</select><span>VS</span><select id="cmpB" aria-label="Driver B"><option value="">CHOOSE</option>${optList(state.compare[1])}</select></div>
      <div class="pc-body" id="cmpBody"></div><p class="pnl-note pc-note">Interval when the two run next to each other; otherwise the gap between them from timing. Battle score is server analytics and is not reproduced here.</p>`;
    battle = new SS.BattleView($('#cmpBody'), { session, posture: 'phone' });
    comparePage.querySelectorAll('select').forEach((s) => s.addEventListener('change', () => { state.compare = [$('#cmpA').value, $('#cmpB').value || null]; slowNext = 0; }));
  }
  function buildResult() {
    comparePage.innerHTML = `<header class="pf-head pf-head--plain"><button class="pf-back" type="button" data-a="back" aria-label="Back">‹</button><div class="pf-id"><span class="pf-num">${cur.meeting.toUpperCase()}</span><h2><b>Result</b></h2></div></header><div class="ph-pad" id="resBody"></div>`;
    resultMod = new SS.RaceResult($('#resBody'), { session, posture: 'phone' });
  }
  let resultMod = null;
  comparePage.addEventListener('click', (ev) => { const b = ev.target.closest('[data-a=back]'); if (b) closePage(); });
  $('#resultBanner').addEventListener('click', () => openResult());

  /* ---------------------------------------------------------- takeovers: compact, at the bottom of the content */
  const takeover = new SS.Takeover($('#takeover'), { session, posture: 'phone' });

  /* ---------------------------------------------------------- player + transport */
  const startAt = params.get('t') != null ? +params.get('t') : session.moments.length ? session.moments[0].t : session.begin;
  const player = new SS.Player(session, { startAt, speed: +(params.get('speed') || 5) });
  SS.viewer.apply(player, params);
  if (params.get('play') !== '0') player.play(); else if (player.mode === 'live') player.pause();

  const tpEl = $('#transport');
  const span = session.end - session.begin;
  const MARK = { LEAD_CHANGE: 'mk-lead', STOPPED: 'mk-out', PENALTY: 'mk-amber' };
  const marks = session.events.filter((e) => MARK[e.type] || (e.type === 'FLAG' && /VSC|SAFETY|RED|CHEQ/.test(e.status)) || /POLE|SEGMENT_P1|SESSION_BEST|ELIMINATED/.test(e.type)).map((e) => `<i class="tp-mk ${MARK[e.type] || (e.type === 'FLAG' ? (/RED/.test(e.status) ? 'mk-red' : /CHEQ/.test(e.status) ? 'mk-cheq' : 'mk-yellow') : /ELIM/.test(e.type) ? 'mk-phase' : 'mk-purple')}" data-at="${SS.avail(e)}" style="left:${(((e.t - session.begin) / span) * 100).toFixed(2)}%"></i>`).join('');
  tpEl.innerHTML = `
    <div class="pt-replay">
      <button class="pt-b pt-play" type="button" data-a="play" aria-label="Play or pause"><span class="i-play">▶</span><span class="i-pause">❚❚</span></button>
      <div class="pt-scrub"><div class="tp-marks">${marks}</div><input type="range" min="${session.begin}" max="${session.end}" step="1" aria-label="Replay position"><div class="tp-fill"></div></div>
      <button class="pt-b pt-ret" type="button" data-a="return" hidden aria-label="Back to where you were">↩</button>
      <button class="pt-pos" type="button" data-a="sheet" aria-label="Playback options"><b class="mono" id="ptPos"></b><span id="ptSub"></span></button>
    </div>
    <div class="pt-live">
      <button class="pt-b pt-play" type="button" data-a="play" aria-label="Pause or resume live"><span class="i-play">▶</span><span class="i-pause">❚❚</span></button>
      <button class="pt-delay" type="button" data-a="sheet"><span class="lbl">DELAY</span><b class="mono" id="ptDelay"></b><i aria-hidden="true">▾</i></button>
      <span class="pt-behind" id="ptBehind"></span>
      <button class="pt-b pt-golive" type="button" data-a="golive">GO LIVE</button>
    </div>`;
  const range = tpEl.querySelector('input[type=range]');
  const markEls = [...tpEl.querySelectorAll('.tp-mk')];
  range.addEventListener('input', () => player.seek(+range.value));
  tpEl.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-a]'); if (!b) return;
    const a = b.dataset.a;
    if (a === 'play') player.toggle();
    else if (a === 'return') player.goReturn();
    else if (a === 'golive') player.goLive();
    else if (a === 'sheet') openSheet(player.mode === 'live' ? 'delay' : 'playback');
  });
  let hz = -1;
  function updateTransport() {
    const live = player.mode === 'live';
    tpEl.dataset.mode = player.mode;
    tpEl.classList.toggle('is-playing', player.playing);
    if (document.activeElement !== range) range.value = String(Math.floor(player.t));
    tpEl.querySelector('.tp-fill').style.transform = `scaleX(${((player.t - session.begin) / span).toFixed(4)})`;
    const h = SS.spoilers.get() === 'all' ? Infinity : Math.floor(player.horizon / 5);
    if (h !== hz) { hz = h; for (const m of markEls) m.hidden = h !== Infinity && +m.dataset.at > player.horizon; }
    const set = (id, v) => { const e = document.getElementById(id); if (e && e.textContent !== v) e.textContent = v; };
    set('ptPos', race ? `L${session.lapAt(player.t) || '—'}/${session.totalLaps || '—'}` : (session.clockAt(player.t) != null ? U.fmtClock(session.clockAt(player.t)) : '—'));
    set('ptSub', `${player.speed}× · ${SS.localClock(session, player.t)}`);
    tpEl.querySelector('.pt-ret').hidden = !player.returnPoint || live;
    set('ptDelay', player.delay >= 1 ? '−' + SS.fmtDelay(player.delay) : 'LIVE');
    set('ptBehind', player.liveState !== 'LIVE' ? 'HOLDING' : !player.playing ? 'PAUSED ▲' : '');
  }

  /* ---------------------------------------------------------- sheets: playback, delay, session, menu */
  const sheet = $('#sheet'), scrim = $('#scrim');
  let lastFocus = null;
  function openSheet(id) {
    state.sheet = id;
    lastFocus = document.activeElement;
    sheet.innerHTML = SHEETS[id]();
    sheet.dataset.sheet = id;
    sheet.hidden = false; scrim.hidden = false;
    const first = sheet.querySelector('button, select, input');
    if (first) first.focus({ preventScroll: true });
    updateSheet();
  }
  function closeSheet() {
    state.sheet = null; sheet.hidden = true; scrim.hidden = true; sheet.innerHTML = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }
  scrim.addEventListener('click', closeSheet);
  const sheetHead = (t, s) => `<header class="sh-h"><div><b>${t}</b>${s ? `<span>${s}</span>` : ''}</div><button class="sh-x" type="button" data-a="close" aria-label="Close">DONE</button></header>`;
  const SHEETS = {
    playback: () => `${sheetHead('Playback', 'Replay · nothing here changes what the timing says')}
      <div class="sh-sec"><div class="sh-pos"><b class="mono" id="shPos"></b><span id="shPosSub"></span></div>
        <div class="sh-row"><button class="sh-b" type="button" data-a="start">|‹</button><button class="sh-b" type="button" data-a="back">−30 s</button><button class="sh-b sh-b--main" type="button" data-a="play"><span class="i-play">PLAY</span><span class="i-pause">PAUSE</span></button><button class="sh-b" type="button" data-a="fwd">+30 s</button></div>
        <button class="sh-b sh-ret" type="button" data-a="return" hidden></button></div>
      <div class="sh-sec"><span class="lbl">SPEED</span><div class="sh-chips">${SS.SPEEDS.map((x) => `<button type="button" data-speed="${x}">${x}×</button>`).join('')}</div></div>
      <div class="sh-sec"><span class="lbl">SYNC OFFSET</span><p class="sh-note">Shift the replay to line up with a recorded broadcast.</p><div class="sh-chips">${[0, 5, 10, 30, 60, 120].map((x) => `<button type="button" data-d="${x}">${x === 0 ? '0 s' : x < 60 ? x + ' s' : x / 60 + ' min'}</button>`).join('')}</div>
        <form class="sh-form" data-f="delay"><input class="mono" maxlength="4" placeholder="M:SS" aria-label="Sync offset M:SS"><button class="sh-b" type="submit">APPLY</button><span class="sh-err" role="alert" hidden></span></form></div>
      <div class="sh-sec"><span class="lbl">MOMENTS</span><div class="sh-moments" id="shMoments"></div><label class="sh-chk"><input type="checkbox" id="shSpoil"${SS.spoilers.get() === 'all' ? ' checked' : ''}> Show the whole session (spoilers)</label></div>`,
    delay: () => `${sheetHead('Live delay', 'Match your TV broadcast · 0–5 min behind live')}
      <div class="sh-sec"><div class="sh-pos"><b class="mono" id="shDelay"></b><span id="shDelaySub"></span></div>
        <div class="sh-row"><button class="sh-b sh-b--main" type="button" data-a="play"><span class="i-play">RESUME</span><span class="i-pause">PAUSE</span></button><button class="sh-b sh-golive" type="button" data-a="golive">GO LIVE</button></div>
        <p class="sh-note">Pausing holds the timing while the session carries on, so your delay grows — like pausing your TV. Resume keeps the new delay.</p></div>
      <div class="sh-sec"><span class="lbl">SET DELAY</span><div class="sh-chips">${SS.DELAYS.map((x) => `<button type="button" data-d="${x}">${x === 0 ? 'LIVE' : x < 60 ? x + ' s' : x / 60 + ' min'}</button>`).join('')}</div>
        <div class="sh-row"><button class="sh-b" type="button" data-nudge="5">+5 s behind</button><button class="sh-b" type="button" data-nudge="-5">−5 s</button></div>
        <form class="sh-form" data-f="delay"><input class="mono" maxlength="4" placeholder="M:SS" aria-label="Live delay M:SS"><button class="sh-b" type="submit">APPLY</button><span class="sh-err" role="alert" hidden></span></form></div>
      <div class="sh-sec sh-proto"><span class="lbl">PROTOTYPE</span><button class="sh-b" type="button" data-a="stale">Simulate a feed drop</button></div>`,
    session: () => `${sheetHead('Sessions', 'Season 2026 · on this server')}
      <div class="sh-list">${SESSIONS.map((x) => `<a class="sh-item${x.s === label ? ' is-on' : ''}" href="phone.html?s=${x.s}"><b>${x.meeting}</b><span>${x.name} · ${x.where}</span><em>REPLAY READY</em></a>`).join('')}</div>
      <a class="sh-link" href="states.html#library">Full library: weekends, downloads, live →</a>`,
    menu: () => `${sheetHead('Slipstream', `${cur.meeting} · ${cur.name}`)}
      <div class="sh-list">
        <a class="sh-item" href="#" data-go="web"><b>Open on desktop</b><span>Same moment, mode and delay</span></a>
        <a class="sh-item" href="#" data-go="tv"><b>TV mode</b><span>For a big screen · same moment</span></a>
        <a class="sh-item" href="states.html#settings"><b>Settings</b><span>Display, motion, TV, live, layouts</span></a>
      </div>
      <div class="sh-sec"><span class="lbl">MOTION</span><div class="sh-chips" data-motion>${['system', 'full', 'reduced'].map((m) => `<button type="button" data-mo="${m}">${m.toUpperCase()}</button>`).join('')}</div><p class="sh-note">Reduced: rows snap, changes are outlined, the banner does not slide.</p></div>
      <div class="sh-sec sh-proto"><span class="lbl">PROTOTYPE</span><label class="sh-chk"><input type="checkbox" id="shLive"${player.mode === 'live' ? ' checked' : ''}> Live chrome (simulated)</label>
        <label class="sh-sel">Map <select id="shMap"><option value="outline"${caps.positions === 'outline' ? ' selected' : ''}${caps.outline ? '' : ' disabled'}>Outline + positions</option><option value="line"${caps.positions === 'line' ? ' selected' : ''}>No outline</option><option value="none"${caps.positions === 'none' ? ' selected' : ''}>No positions</option></select></label></div>`,
  };
  const go = (page) => { location.href = `${page}.html?` + SS.viewer.query(SS.viewer.fromPlayer(player, { follow: state.follow, reduced: SS.motion.choice === 'reduced' ? 1 : SS.motion.choice === 'full' ? 0 : '', from: 'phone' })); };
  sheet.addEventListener('click', (ev) => {
    const t = ev.target;
    const g = t.closest('[data-go]'); if (g) { ev.preventDefault(); go(g.dataset.go); return; }
    const b = t.closest('button'); if (!b) return;
    const a = b.dataset.a;
    if (a === 'close') closeSheet();
    else if (a === 'play') player.toggle();
    else if (a === 'start') player.seek(session.begin);
    else if (a === 'back') player.skip(-30);
    else if (a === 'fwd') player.skip(30);
    else if (a === 'return') { player.goReturn(); closeSheet(); }
    else if (a === 'golive') player.goLive();
    else if (a === 'stale') { player.simulateStale(8); closeSheet(); }
    if (b.dataset.speed) player.setSpeed(+b.dataset.speed);
    if (b.dataset.d != null) player.setDelay(+b.dataset.d);
    if (b.dataset.nudge) player.nudgeDelay(+b.dataset.nudge);
    if (b.dataset.m != null) { const m = session.moments[+b.dataset.m]; player.markReturn(); player.seek(m.t); player.play(); closeSheet(); }
    if (b.dataset.mo) SS.motion.set(b.dataset.mo);
    updateSheet();
  });
  sheet.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const f = ev.target; const v = SS.parseDelay(f.querySelector('input').value); const err = f.querySelector('.sh-err');
    if (v == null) { err.textContent = 'Enter M:SS from 0:00 to 5:00.'; err.hidden = false; return; }
    err.hidden = true; player.setDelay(v); updateSheet();
  });
  sheet.addEventListener('change', (ev) => {
    if (ev.target.id === 'shSpoil') { SS.spoilers.set(ev.target.checked ? 'all' : 'safe'); hz = -1; renderMoments(); }
    if (ev.target.id === 'shLive') { player.setMode(ev.target.checked ? 'live' : 'replay'); if (!ev.target.checked) { player.delay = 0; player.setSpeed(5); } closeSheet(); }
    if (ev.target.id === 'shMap') { const q = new URLSearchParams(location.search); q.set('map', ev.target.value); q.set('t', Math.round(player.t)); location.search = q.toString(); }
  });
  function renderMoments() {
    const host = document.getElementById('shMoments'); if (!host) return;
    const all = SS.spoilers.get() === 'all';
    const items = session.moments.map((m, i) => [m, i]).filter(([m]) => all || m.t <= player.horizon);
    const hidden = session.moments.length - items.length;
    host.innerHTML = items.map(([m, i]) => `<button type="button" data-m="${i}"><b>${m.label}</b><em>${m.note || ''}</em></button>`).join('') + (hidden ? `<p class="sh-note">${hidden} later moment${hidden === 1 ? '' : 's'} hidden until you reach ${hidden === 1 ? 'it' : 'them'}.</p>` : '') + (!items.length ? '<p class="sh-note">Moments appear here once you have watched them.</p>' : '');
  }
  function updateSheet() {
    if (!state.sheet) return;
    const set = (id, v) => { const e = document.getElementById(id); if (e && e.textContent !== v) e.textContent = v; };
    sheet.classList.toggle('is-playing', player.playing);
    if (state.sheet === 'playback') {
      set('shPos', race ? `LAP ${session.lapAt(player.t) || '—'} / ${session.totalLaps || '—'}` : (session.clockAt(player.t) != null ? U.fmtClock(session.clockAt(player.t)) + ' LEFT' : '—'));
      set('shPosSub', `${SS.localClock(session, player.t)} local · elapsed ${U.fmtClock(Math.max(0, player.t - session.begin), true)}`);
      sheet.querySelectorAll('[data-speed]').forEach((b) => b.classList.toggle('is-on', +b.dataset.speed === player.speed));
      sheet.querySelectorAll('[data-d]').forEach((b) => b.classList.toggle('is-on', +b.dataset.d === Math.round(player.delay)));
      const ret = sheet.querySelector('.sh-ret');
      if (ret) { ret.hidden = !player.returnPoint; if (player.returnPoint) ret.textContent = `↩ Back to ${race ? 'L' + (session.lapAt(player.returnPoint.t) || '—') + ' · ' : ''}${SS.localClock(session, player.returnPoint.t)}`; }
      if (!sheet._mom) { renderMoments(); sheet._mom = true; }
    } else if (state.sheet === 'delay') {
      set('shDelay', player.delay >= 1 ? `${SS.fmtDelay(player.delay)} behind live` : 'At the live edge');
      set('shDelaySub', player.liveState !== 'LIVE' ? 'Feed interrupted · holding your delay' : !player.playing ? 'Paused · delay growing' : player.requestedDelay - player.delay > 1 ? `Asked ${SS.fmtDelay(player.requestedDelay)} · buffer holds ${SS.fmtDelay(player.delay)}` : 'Timing follows the live feed at this delay');
      sheet.querySelectorAll('[data-d]').forEach((b) => b.classList.toggle('is-on', +b.dataset.d === Math.round(player.requestedDelay)));
    } else if (state.sheet === 'menu') {
      sheet.querySelectorAll('[data-mo]').forEach((b) => b.classList.toggle('is-on', b.dataset.mo === SS.motion.choice));
    }
  }
  $('#sessBtn').addEventListener('click', () => openSheet('session'));
  $('#menuBtn').addEventListener('click', () => openSheet('menu'));
  sheet.addEventListener('transitionend', () => { sheet._mom = false; });

  /* ---------------------------------------------------------- frame */
  let forceJump = true, lastVm = null, slowNext = 0, opened = false;
  applyLand();
  if (params.get('focus') && session.drivers[params.get('focus')]) openFocus(params.get('focus'));
  if (params.get('compare')) { const [a, b] = params.get('compare').split(','); if (session.drivers[a]) { lastVm = null; state.compare = [a, session.drivers[b] ? b : null]; focusPage.hidden = true; comparePage.hidden = false; buildCompare(); } }
  if (params.get('sheet') && SHEETS[params.get('sheet')]) openSheet(params.get('sheet'));

  player.on(({ now, jumped, crossed, cursor, gen }) => {
    jumped = jumped || forceJump;
    forceJump = false;
    const vm = SS.vm(session, cursor, { now });
    vm.byNum = Object.fromEntries(vm.rows.map((r) => [r.num, r]));
    lastVm = vm;
    const reduced = SS.motion.reduced;
    const rd = railModel(vm, player);
    rd.jumped = jumped;
    rd.big = rd.compact ? `<span>${rd.compact}</span>` : rd.big;
    rd.small = '';
    rail.reduced = reduced;
    rail.update(rd);
    tower.render(vm, { jumped, recent: SS.recentContext(session, now), reduced, speed: player.speed });
    takeover.reduced = reduced;
    takeover.speed = player.speed;
    if (jumped) takeover.clear();
    else if (crossed.length) takeover.offer(crossed, now);
    takeover.tick(now);
    if (!opened) { opened = true; opening.done(); }
    const slow = jumped || performance.now() > slowNext;
    if (slow) slowNext = performance.now() + 450;
    const visible = (id) => !state.focus && !state.compare && !state.result && (state.land ? id === state.ctx || id === 'timing' : state.tab === id);

    // timing: result banner after the flag (a provisional classification, not a final one)
    const rs = race ? (SS.resultState ? SS.resultState(session, now) : { state: vm.finished ? 'provisional' : 'none' }) : { state: 'none' };
    const rb = $('#resultBanner');
    rb.hidden = rs.state === 'none';
    if (!rb.hidden) { const t = `<b>${rs.state === 'final' ? 'FINAL' : 'PROVISIONAL'} CLASSIFICATION</b><span>${vm.rows[0] ? vm.rows[0].code + ' wins on the road' : ''} · places gained, fastest lap, penalties</span><i>›</i>`; if (rb._v !== t) { rb.innerHTML = t; rb._v = t; } }

    if (visible('track')) {
      const nearby = [];
      if (state.follow && vm.byNum[state.follow]) { const r = vm.byNum[state.follow]; nearby.push(state.follow); if (vm.rows[r.index - 1]) nearby.push(vm.rows[r.index - 1].num); if (vm.rows[r.index + 1]) nearby.push(vm.rows[r.index + 1].num); }
      if (trackView) { trackView.setFocus(nearby); trackView.setMode(player.mode); trackView.render(vm, now); }
      if (lineView) { lineView.setFocus(nearby); lineView.setMode(player.mode); lineView.render(vm, now); }
      if (ribbon) { ribbon.setFocus(nearby); ribbon.render(vm, jumped); }
      if (ladder) { ladder.setFocus(nearby); ladder.render(vm, jumped); }
      if (race && slow) renderBattleCard(vm);
    }
    if (visible('strategy') && slow) {
      setHTML($('#stNow'), SS.panel('CURRENT RACE', 'Race now', '', SS.raceNowHTML(session, vm, true), 'pnl-rn'));
      pitBoard.render(vm, now);
      setHTML($('#stPir'), SS.panel('OFFICIAL PRE-RACE', 'Pirelli strategy', '', SS.pirelliHTML(session, true), 'pnl-pir'));
      setHTML($('#stStints'), SS.stintChartHTML(session, vm));
      setHTML($('#stCond'), SS.conditionsHTML(session, vm));
    }
    if (visible('session') && slow) renderSession(vm);
    if (visible('activity')) {
      if (state.act === 'story') { feed.render(now, jumped || feedSilent, gen); feedSilent = false; }
      else if (slow) setHTML($('#rcLog'), SS.raceControlHTML(session, vm, 60));
      const note = player.mode === 'live' ? 'Tap a moment for details. Replay unlocks once the session is recorded.' : 'Tap a moment for details, then REPLAY to watch it. ↩ in the transport brings you back.';
      if ($('#storyNote').textContent !== note) $('#storyNote').textContent = note;
    }
    if (slow) { const n = session.rc.filter((m) => m.t <= now).length; const t = n ? String(n) : ''; if ($('#rcCount').textContent !== t) $('#rcCount').textContent = t; }
    if (state.focus && slow) renderFocus(vm, now);
    if (state.compare && slow && battle) {
      const a = vm.byNum[state.compare[0]], b = state.compare[1] && vm.byNum[state.compare[1]];
      battle.render(vm, a && b ? (a.index < b.index ? [a, b] : [b, a]) : null, now);
    }
    if (state.result && slow && resultMod) resultMod.render(vm, now);
    renderFollow(vm);
    updateTransport();
    if (state.sheet) updateSheet();
    const health = $('#health');
    const stale = player.mode === 'live' && player.liveState !== 'LIVE';
    health.hidden = !stale;
    if (stale) { const t = player.liveState === 'RECONNECTING' ? '<b>RECONNECTING</b> holding the last known order' : `<b>TIMING PAUSED</b> no update for ${player.staleSeconds()} s · the order may be behind`; if (health._v !== t) { health.innerHTML = t; health._v = t; } }
    document.body.classList.toggle('is-stale', stale);
  });
  const setHTML = (el, html) => { if (el && el._v !== html) { el.innerHTML = html; el._v = html; } };

  function renderBattleCard(vm) {
    const pair = SS.pickBattle(vm, null);
    let html;
    if (!pair) html = `<div class="ph-bcard is-empty"><span class="lbl">CLOSEST FIGHT</span><span>No two cars within 1.0 s in green-flag running.</span></div>`;
    else {
      const [a, b] = pair;
      html = `<button class="ph-bcard" type="button" data-cmp="${b.num},${a.num}"><span class="lbl">CLOSEST FIGHT · P${a.pos}</span><span class="pb-pair"><i style="background:${b.colour}"></i><b>${b.code}</b><span class="mono">+${b.intVal.toFixed(3)}</span><span class="dim">behind</span><i style="background:${a.colour}"></i><b>${a.code}</b></span><em>COMPARE ›</em></button>`;
    }
    setHTML($('#battleCard'), html);
  }
  $('#battleCard').addEventListener('click', (ev) => { const b = ev.target.closest('[data-cmp]'); if (!b) return; const [x, y] = b.dataset.cmp.split(','); openCompare(x); state.compare = [x, y]; buildCompare(); });

  function renderSession(vm) {
    if (kind === 'qualifying') {
      const p1 = vm.rows[0];
      const cells = [['SEGMENT', vm.phase || '—'], ['TIME LEFT', vm.clock != null ? U.fmtClock(vm.clock) : '—'], ['FASTEST', p1 && p1.qTime != null ? `${p1.code} ${U.fmtLap(p1.qTime)}` : '—'], ['ADVANCE', vm.advance ? `TOP ${vm.advance}` : vm.phase === 'Q3' ? 'POLE SHOOTOUT' : '—']];
      setHTML($('#ssCells'), `<div class="cond-grid q-grid">${cells.map(([l, v]) => `<div><span>${l}</span><b class="mono">${v}</b></div>`).join('')}</div>`);
      let html;
      if (vm.advance) {
        const active = vm.rows.filter((r) => !r.qe);
        const cut = active[vm.advance - 1];
        const at = active.slice(Math.max(0, vm.advance - 3), vm.advance + 3);
        html = `<div class="ot-head"><span class="lbl">TOP ${vm.advance} GO THROUGH</span><b class="mono">${cut && cut.qTime != null ? U.fmtLap(cut.qTime) : '—'}</b></div><ol class="zone-list">${at.map((r) => { const d = r.qTime != null && cut && cut.qTime != null ? r.qTime - cut.qTime : null; return `<li class="${r.index < vm.advance ? 'is-safe' : 'is-risk'}${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${d == null ? '' : d === 0 ? 'SETS CUT' : U.fmtDelta(d)}</em></li>`; }).join('')}</ol>`;
      } else {
        html = `<div class="ot-head"><span class="lbl">FIGHT FOR POLE</span></div><ol class="zone-list">${vm.rows.slice(0, 10).map((r) => `<li class="is-top${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${r.qGap ? '+' + r.qGap.toFixed(3) : ''}</em></li>`).join('')}</ol>`;
      }
      setHTML($('#ssZone'), html);
    } else {
      setHTML($('#ssCells'), `<div class="cond-grid q-grid">${[['REMAINING', vm.clock != null ? U.fmtClock(vm.clock) : '—'], ['FASTEST', vm.rows[0] && vm.rows[0].best ? `${vm.rows[0].code} ${vm.rows[0].best}` : '—'], ['ON TRACK', String(vm.rows.filter((r) => r.activity === 'ON_TRACK').length)]].map(([l, v]) => `<div><span>${l}</span><b class="mono">${v}</b></div>`).join('')}</div>`);
      const ev = session.events.filter((e) => SS.avail(e) <= vm.t && (e.type === 'SESSION_BEST' || e.type === 'FLAG' || e.type === 'STOPPED' || (e.type === 'IMPROVEMENT' && (e.pos || 99) <= 10))).slice(-10).reverse();
      setHTML($('#ssZone'), `<ol class="zone-list zone-log">${ev.map((e) => { const d = SS.describe(session, e, vm.t); return `<li class="tone-${d.tone}"><span class="mono">${SS.stamp(session, e)}</span><i></i><b>${d.tag}</b><span>${d.title}</span></li>`; }).join('') || '<li class="dim">Quiet so far</li>'}</ol>`);
    }
    onTrack.render(vm);
    setHTML($('#ssCond'), SS.conditionsHTML(session, vm));
  }

  /* ---------------------------------------------------------- keyboard (desktop testing; same capability checks) */
  document.addEventListener('keydown', (ev) => {
    if (ev.target && ev.target.matches && ev.target.matches('input, select, textarea')) return;
    const k = ev.key.toLowerCase();
    if (k === 'escape') { if (state.sheet) closeSheet(); else if (state.focus || state.compare || state.result) closePage(); return; }
    if (state.sheet) return;
    const live = player.mode === 'live';
    if (k === ' ') { ev.preventDefault(); player.toggle(); }
    else if (k === 'arrowleft') live ? player.nudgeDelay(5) : player.skip(-30);
    else if (k === 'arrowright') live ? player.nudgeDelay(-5) : player.skip(30);
  });
  window.__ph = { session, player, state, showTab, openFocus, openCompare, openResult, setFollow, openSheet, closeSheet };
})();

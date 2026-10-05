/* Desktop prototype — the current app's pages, kept whole, in the new language.
 * SESSION: tower (standard / timing / strategy views) + analysis stack (track, story, strategy,
 * conditions, race control). DRIVER, BATTLE, STRATEGY: deep pages with a compact tower beside them,
 * so the order never leaves the screen. Replay transport keeps speed and sync delay; live keeps
 * the delay presets, the M:SS field and GO LIVE. */
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
  const hasOutline = !!(session.circuit && session.circuit.path && session.circuit.path.length > 2);
  const C = SS.cols;
  document.body.dataset.kind = kind;
  SS.density.apply(SS.density.get(params.get('density')));
  SS.motion.init(params.get('reduced'));

  const state = {
    view: params.get('view') || 'session',
    towerView: params.get('tower') || 'standard',
    split: params.get('split') || 'balanced',
    driver: params.get('driver') || '',
    battleMode: params.get('battle') || 'recommended',
    pinned: params.get('pair') ? params.get('pair').split(',') : null,
    map: params.get('map') || (hasOutline ? 'outline' : 'line'),
    live: params.get('live') === '1',
    layout: params.get('layout') || SS.prefs.get('layout.' + kind, 'brief'),
    mapSize: params.get('mapsize') || null,
    filter: 'hl',
    recentPair: null, recentUntil: 0,
  };
  Object.defineProperty(state, 'reduced', { get: () => SS.motion.reduced });
  if (!race && (state.view === 'battle' || state.view === 'strategy')) state.view = 'session';

  /* ---------------------------------------------------------- header */
  const SESSIONS = [
    { s: 'hungaroring-2026-race', meeting: 'Hungarian Grand Prix', name: 'Race', where: 'Hungaroring' },
    { s: 'kl-2026-qualifying', meeting: 'Bahrain Grand Prix', name: 'Qualifying', where: 'Kuala Lumpur' },
    { s: 'kl-2026-practice-2', meeting: 'Bahrain Grand Prix', name: 'Practice 2', where: 'Kuala Lumpur' },
  ];
  const cur = SESSIONS.find((x) => x.s === label) || SESSIONS[0];
  $('#pickerTitle').textContent = `2026 / ${cur.meeting}`;
  $('#pickerSub').textContent = `${cur.name} · ${cur.where}`;
  const pop = $('#pickerPop');
  pop.innerHTML = `<header><b>SESSIONS</b><span>season 2026 · on this server</span></header>
    ${SESSIONS.map((x) => `<a class="pk-item${x.s === label ? ' is-on' : ''}" href="?s=${x.s}"><b>${x.meeting}</b><span>${x.name} · ${x.where}</span><em class="pk-state">REPLAY READY</em></a>`).join('')}
    <a class="pk-more" href="states.html#library">Full library: weekends, downloads, live →</a>`;
  $('#pickerBtn').addEventListener('click', () => { pop.hidden = !pop.hidden; $('#protoPop').hidden = true; });
  $('#protoBtn').addEventListener('click', () => { $('#protoPop').hidden = !$('#protoPop').hidden; pop.hidden = true; });
  document.addEventListener('click', (ev) => {
    if (!ev.target.closest('#picker')) pop.hidden = true;
    if (!ev.target.closest('#proto')) $('#protoPop').hidden = true;
    if (!ev.target.closest('#splitMenu')) $('#splitPop').hidden = true;
  });
  // Presentation changes keep the viewer's moment, mode, delay and focus (one viewer, three postures).
  const ctxNow = (extra = {}) => SS.viewer.fromPlayer(player, Object.assign({
    follow: state.view === 'driver' ? state.driver : '',
    pair: state.battleMode === 'pinned' && state.pinned ? state.pinned.join(',') : '',
    reduced: SS.motion.choice === 'reduced' ? 1 : SS.motion.choice === 'full' ? 0 : '',
    from: 'web',
  }, extra));
  $('#navTv').addEventListener('click', (ev) => { ev.preventDefault(); location.href = 'tv.html?' + SS.viewer.query(ctxNow()); });
  $('#openPhone').addEventListener('click', (ev) => { ev.preventDefault(); location.href = 'phone.html?' + SS.viewer.query(ctxNow()); });
  const opening = SS.brand.opening({ title: `${cur.meeting} · ${cur.name}`, phases: ['Connecting to Slipstream', 'Reading the timing history', 'Building the race state', 'Ready'], hold: params.get('opening') === '1' ? 3400 : 0 });
  document.querySelectorAll('[data-race]').forEach((a) => (a.hidden = !race));
  document.addEventListener('click', (ev) => {
    const a = ev.target.closest('a[data-view], button[data-view]');
    if (!a) return;
    ev.preventDefault();
    setView(a.dataset.view);
  });

  /* ---------------------------------------------------------- rail */
  const rail = new SS.StatusRail($('#rail'), { posture: 'desktop' });
  const railModel = SS.railModel(session);

  /* ---------------------------------------------------------- tower */
  // [column, drop priority]: 0 never drops; when the tower is narrow the highest numbers go first,
  // so driver identity (code, name, team) is never the thing that disappears.
  const IDENT = 'minmax(140px, 1fr)', IDENT_MIN = 140;
  const COLS = {
    race: {
      standard: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.gap('92px'), 0], [C.int('84px'), 2], [C.tyre('78px'), 1], [C.last('96px'), 3], [C.pits('34px'), 4]],
      timing: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.gap('86px'), 3], [C.int('78px'), 4], [C.tyre('66px'), 5], [C.sector(1, '60px'), 0], [C.sector(2, '60px'), 0], [C.sector(3, '60px'), 0], [C.last('90px'), 0], [C.best('90px'), 2]],
      strategy: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.gap('86px'), 2], [C.int('78px'), 4], [C.tyre('70px'), 0], [C.stint('48px', 'STINT'), 3], [C.pits('34px'), 1], [C.tyreSeq(session, '128px'), 0], [C.lastStop(session, '104px'), 5]],
    },
    qualifying: {
      standard: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.qseg(0, '80px'), 0], [C.qseg(1, '80px'), 0], [C.qseg(2, '80px'), 0], [C.qgap('72px'), 2], [C.qint('70px'), 4], [C.tyre('66px'), 3], [C.status('80px'), 5]],
      timing: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.qtime('88px'), 0], [C.sector(1, '60px'), 0], [C.sector(2, '60px'), 0], [C.sector(3, '60px'), 0], [C.qgap('72px'), 0], [C.qint('70px'), 3], [C.tyre('66px'), 4], [C.status('80px'), 5]],
    },
    practice: {
      standard: () => [[C.pos('38px'), 0], [C.driverTeam(IDENT), 0], [C.tyre('66px'), 2], [C.last('86px'), 1], [C.best('86px', 'time'), 0], [C.pgap('72px'), 0], [C.pint('68px'), 3], [C.stint('46px', 'STINT'), 4], [C.stops('46px'), 5], [C.status('80px'), 6]],
    },
  };
  const compactCols = () => [C.pos('30px'), C.driver('minmax(60px, 1fr)', false), race ? C.int('70px') : kind === 'qualifying' ? C.qgap('70px') : C.pgap('70px'), C.tyre('56px')];
  const pxOf = (w) => (/^\d+(\.\d+)?px$/.test(w) ? parseFloat(w) : 0);
  function fitCols(spec, avail) {
    let list = spec.slice();
    const need = (l) => l.reduce((a, [c]) => a + pxOf(c.w), 0) + IDENT_MIN + 24;
    while (need(list) > avail) {
      const cand = list.filter(([, pr]) => pr > 0).sort((a, b) => b[1] - a[1])[0];
      if (!cand) break;
      list = list.filter((x) => x !== cand);
    }
    return { cols: list.map(([c]) => c), hidden: spec.filter((x) => !list.includes(x)).map(([c]) => c.label || c.key), min: need(list) };
  }
  const towerViews = Object.keys(COLS[kind]);
  if (!towerViews.includes(state.towerView)) state.towerView = 'standard';
  let tower = null, towerKey = '';
  function buildTower() {
    const compact = state.view !== 'session';
    const host = $('#tower');
    const avail = host.clientWidth || 600;
    const fit = compact ? { cols: compactCols(), hidden: [], min: 0 } : fitCols(COLS[kind][state.towerView](), avail);
    // Rows fill the available height (28–36 px) so the tower never ends in a void.
    const nDrivers = Object.keys(session.drivers).length;
    const rowH = compact ? 28 : Math.max(28, Math.min(38, Math.floor(((host.clientHeight || 700) - 28) / nDrivers)));
    const key = (compact ? 'compact' : state.towerView + ':' + fit.cols.map((c) => c.key + (c.label || '')).join(',')) + '@' + rowH;
    const hiddenEl = $('#colsHidden');
    hiddenEl.hidden = compact || !fit.hidden.length;
    hiddenEl.textContent = fit.hidden.length ? `+${fit.hidden.length} HIDDEN` : '';
    hiddenEl.title = fit.hidden.length ? 'Hidden to keep driver names readable: ' + fit.hidden.join(', ') : '';
    if (key === towerKey) return;
    towerKey = key;
    host.innerHTML = '';
    host.className = '';
    host.style.setProperty('--chips-right', compact ? '0px' : kind === 'race' ? '0px' : '84px');
    host.style.setProperty('--tw-min', fit.min + 'px');
    tower = new SS.Tower(host, { session, columns: fit.cols, rowH, posture: 'desktop', onRow: (n) => openDriver(n) });
    tower.setFollow(state.driver && state.view === 'driver' ? [state.driver] : []);
    forceJump = true;
  }
  // Re-fit when the tower's width changes (window, split preset, display size).
  let fitT = null;
  new ResizeObserver(() => { clearTimeout(fitT); fitT = setTimeout(() => { if (tower) buildTower(); }, 140); }).observe($('#tower'));
  const tvEl = $('#towerViews');
  tvEl.innerHTML = towerViews.length > 1 ? `<span class="lbl">TOWER VIEW</span>${towerViews.map((v) => `<button data-tv="${v}">${v.toUpperCase()}</button>`).join('')}` : '';
  tvEl.addEventListener('click', (ev) => { const b = ev.target.closest('[data-tv]'); if (b) { state.towerView = b.dataset.tv; syncTowerViews(); buildTower(); } });
  const syncTowerViews = () => tvEl.querySelectorAll('[data-tv]').forEach((b) => b.classList.toggle('is-on', b.dataset.tv === state.towerView));
  syncTowerViews();
  $('#towerCount').textContent = `${Object.keys(session.drivers).length} DRIVERS`;

  /* split presets (as today: balanced / tower wide / analysis wide) */
  const SPLITS = { balanced: '50%', tower: '62%', analysis: '40%' };
  const SPLIT_NAMES = { balanced: 'BALANCED', tower: 'TOWER WIDE', analysis: 'ANALYSIS WIDE' };
  $('#splitBtn').addEventListener('click', () => ($('#splitPop').hidden = !$('#splitPop').hidden));
  $('#splitPop').addEventListener('click', (ev) => { const b = ev.target.closest('[data-split]'); if (b) { state.split = b.dataset.split; applySplit(); $('#splitPop').hidden = true; } });
  function applySplit() {
    $('#ws').style.setProperty('--tower-w', state.view === 'session' ? SPLITS[state.split] : '300px');
    $('#splitBtn').textContent = `SPLIT · ${SPLIT_NAMES[state.split]} ▾`;
    $('#ws').dataset.view = state.view;
  }

  /* ---------------------------------------------------------- session view: analysis stack */
  const stack = $('#stack');
  const M = {};
  const mod = (id) => { const d = document.createElement('div'); d.className = 'stack-m'; d.dataset.m = id; stack.appendChild(d); M[id] = d; return d; };
  let trackView = null, lineView = null, ribbon = null, ladder = null, onTrack = null;
  const circuitName = (session.meta.circuit || session.meta.location || 'Circuit');
  // Track
  const mTrack = mod('track');
  mTrack.innerHTML = SS.panel('CIRCUIT', circuitName, '<span class="mono mt-lap"></span>', `<div class="mt-map"></div><div class="mt-note" hidden></div>${race ? '<div class="mt-ribbon"></div>' : ''}`, 'pnl-track');
  const mapHost = mTrack.querySelector('.mt-map');
  if (race) ribbon = new SS.GapRibbon(mTrack.querySelector('.mt-ribbon'), { session, posture: 'desktop' });
  function buildMap() {
    mapHost.innerHTML = '';
    mapHost.className = 'mt-map';
    trackView = lineView = null;
    const note = mTrack.querySelector('.mt-note');
    note.hidden = true;
    mTrack.dataset.map = state.map;
    if (state.map === 'outline' && hasOutline) trackView = new SS.TrackMap(mapHost, { session, posture: 'desktop' });
    else if (state.map === 'line' || (state.map === 'outline' && !hasOutline)) lineView = new SS.TrackLine(mapHost, { session, posture: 'desktop', lanes: race ? 3 : 4 });
    else { note.hidden = false; note.innerHTML = `<b>Car positions are not available for this ${state.live ? 'live feed' : 'replay'}.</b><span>${race ? 'Order and gaps come straight from timing — shown below as race order in time.' : 'Order and lap times come straight from timing.'}</span>`; }
  }
  buildMap();
  // Timed sessions: session facts + cut line / spread
  let mSession = null, mCut = null, zone = null;
  if (!race) {
    if (kind === 'qualifying') mSession = mod('session');
    mCut = mod('cut');
    mCut.innerHTML = SS.panel(kind === 'qualifying' ? 'QUALIFYING' : 'PRACTICE', kind === 'qualifying' ? 'Cut line' : 'Best-lap spread', '', '<div class="ms-ladder"></div><div class="ms-cols"><div class="ms-zone"></div><div class="ms-ontrack"></div></div>', 'pnl-cut');
    ladder = new SS.Ladder(mCut.querySelector('.ms-ladder'), { session, posture: 'desktop' });
    onTrack = new SS.OnTrack(mCut.querySelector('.ms-ontrack'), { session, posture: 'desktop', max: 10 });
    zone = mCut.querySelector('.ms-zone');
  }
  // Story (new) — feed with replay-this-moment and a way back
  const mStory = mod('story');
  mStory.innerHTML = SS.panel('NEW · WHAT CHANGED', 'Story', '<div class="ws-seg" id="storyFilter"><button data-f="hl" class="is-on">HIGHLIGHTS</button><button data-f="all">EVERYTHING</button></div>', '<div class="story-feed"></div><button class="story-more" type="button">SHOW MORE</button>', 'pnl-story');
  const feed = new SS.Feed(mStory.querySelector('.story-feed'), {
    session, min: P.HIGHLIGHT, max: 60, posture: 'desktop', live: () => player.mode === 'live',
    onPick: (e) => {
      if (!e) return;
      if (player.mode === 'live') { toast('Live has no rewind. Moments become replayable once the session is recorded.'); return; }
      player.markReturn();
      player.seek(Math.max(session.begin, e.t - 10));
      player.play();
      toast(`Replaying from ${SS.stamp(session, e)} · ${SS.describe(session, e).title} · ↩ in the transport takes you back`);
    },
  });
  mStory.querySelector('#storyFilter').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-f]');
    if (!b) return;
    state.filter = b.dataset.f;
    mStory.querySelectorAll('[data-f]').forEach((x) => x.classList.toggle('is-on', x === b));
    feed.setMin(state.filter === 'hl' ? P.HIGHLIGHT : P.FEED);
  });
  mStory.querySelector('.story-more').addEventListener('click', (ev) => { const on = mStory.classList.toggle('is-expanded'); ev.target.textContent = on ? 'SHOW LESS' : 'SHOW MORE'; });
  const mStrat = race ? mod('strategy') : null;
  const mCond = mod('conditions');
  const mRc = mod('rc');

  /* Layout presets — a good default is not a replacement for layout control: split, preset, map size
   * and (in settings) module order/hide all remain. Rows are one wide module or a pair of columns. */
  const PRESETS = {
    race: {
      brief: { label: 'BRIEF', map: 'm', rows: [['pair', ['track'], ['strategy']], ['pair', ['story'], ['conditions', 'rc']]] },
      map: { label: 'MAP', map: 'l', rows: [['wide', 'track'], ['pair', ['strategy'], ['conditions', 'rc']], ['wide', 'story']] },
      story: { label: 'STORY', map: 's', tall: true, rows: [['pair', ['story'], ['conditions', 'rc']], ['pair', ['track'], ['strategy']]] },
    },
    qualifying: {
      brief: { label: 'BRIEF', map: 'm', rows: [['pair', ['session', 'conditions'], ['rc']], ['wide', 'cut'], ['pair', ['track'], ['story']]] },
      map: { label: 'MAP', map: 'l', rows: [['wide', 'track'], ['wide', 'cut'], ['pair', ['session', 'conditions'], ['rc']], ['wide', 'story']] },
      story: { label: 'STORY', map: 's', tall: true, rows: [['pair', ['story'], ['session', 'rc']], ['wide', 'cut'], ['pair', ['track'], ['conditions']]] },
    },
    practice: {
      brief: { label: 'BRIEF', map: 'm', rows: [['wide', 'cut'], ['pair', ['track'], ['conditions', 'rc']], ['wide', 'story']] },
      map: { label: 'MAP', map: 'l', rows: [['wide', 'track'], ['wide', 'cut'], ['pair', ['conditions'], ['rc']], ['wide', 'story']] },
      story: { label: 'STORY', map: 's', tall: true, rows: [['pair', ['story'], ['conditions', 'rc']], ['wide', 'cut'], ['wide', 'track']] },
    },
  };
  const presets = PRESETS[kind];
  if (!presets[state.layout]) state.layout = 'brief';
  $('#anaPreset').innerHTML = `<span class="lbl">PRESET</span>${Object.entries(presets).map(([k, v]) => `<button data-lp="${k}">${v.label}</button>`).join('')}`;
  function applyLayout() {
    const pr = presets[state.layout];
    stack.textContent = '';
    for (const row of pr.rows) {
      const r = document.createElement('div');
      r.className = 'st-row' + (row[0] === 'pair' ? ' is-pair' : '');
      for (const ids of row[0] === 'pair' ? row.slice(1) : [[row[1]]]) {
        const c = document.createElement('div');
        c.className = 'st-col';
        for (const id of ids) if (M[id]) c.appendChild(M[id]);
        r.appendChild(c);
      }
      stack.appendChild(r);
    }
    mStory.toggleAttribute('data-tall', !!pr.tall);
    setMapSize(state.mapSize || pr.map, true);
    $('#anaPreset').querySelectorAll('[data-lp]').forEach((b) => b.classList.toggle('is-on', b.dataset.lp === state.layout));
  }
  function setMapSize(sz, fromPreset) {
    if (!fromPreset) state.mapSize = sz;
    mTrack.dataset.size = sz;
    $('#mapSize').querySelectorAll('[data-ms]').forEach((b) => b.classList.toggle('is-on', b.dataset.ms === sz));
    setTimeout(() => window.dispatchEvent(new Event('resize')), 340);
  }
  $('#anaPreset').addEventListener('click', (ev) => { const b = ev.target.closest('[data-lp]'); if (!b) return; state.layout = b.dataset.lp; state.mapSize = null; SS.prefs.set('layout.' + kind, state.layout); applyLayout(); });
  $('#mapSize').addEventListener('click', (ev) => { const b = ev.target.closest('[data-ms]'); if (b) setMapSize(b.dataset.ms); });
  $('#mapSize').hidden = state.map === 'none';
  applyLayout();

  /* ---------------------------------------------------------- deep pages */
  const driverPage = $('#driverPage'), battlePage = $('#battlePage'), strategyPage = $('#strategyPage');
  driverPage.innerHTML = `<div class="dp-head" id="dpHead"></div><div class="dp-grid"><div class="dp-col" id="dpLeft"></div><div class="dp-col"><div class="pnl"><header class="pnl-h"><div><span class="pnl-eb">CIRCUIT</span><b class="pnl-t">${circuitName}</b></div><div class="pnl-a"><span class="dim dp-focus"></span></div></header><div class="pnl-b"><div class="dp-map"></div></div></div><div id="dpRight"></div></div></div>`;
  let dpMap = null, dpLine = null;
  const dpMapHost = driverPage.querySelector('.dp-map');
  if (hasOutline && state.map !== 'none') dpMap = new SS.TrackMap(dpMapHost, { session, posture: 'desktop', labels: 3 });
  else if (state.map !== 'none') dpLine = new SS.TrackLine(dpMapHost, { session, posture: 'desktop', lanes: 3 });
  let bMap = null, bLine = null, battleView = null;
  if (race) {
    battlePage.innerHTML = `<div class="bp-head"><div><span class="pnl-eb">RACE INTELLIGENCE</span><h2>Battle</h2><p>Recommended uses completed-lap history from timing; Leader and Pinned are your choice. Choosing never changes what the timing says.</p></div><div class="bp-ctl"><div class="ws-seg" id="bMode"><button data-bm="recommended">RECOMMENDED</button><button data-bm="leader">LEADER</button><button data-bm="pinned">PINNED</button></div><label class="bp-sel"><span class="lbl">DRIVER A</span><select id="bA"></select></label><label class="bp-sel"><span class="lbl">DRIVER B</span><select id="bB"></select></label></div></div>
      <div class="bp-main" id="bMain"></div>
      <div class="bp-grid"><div class="bp-card" id="bCardA"></div><div class="pnl bp-mapp"><header class="pnl-h"><div><span class="pnl-eb">CIRCUIT</span><b class="pnl-t">Pair on track</b></div></header><div class="pnl-b"><div class="bp-map"></div></div></div><div class="bp-card" id="bCardB"></div></div>
      <div class="bp-score pnl"><header class="pnl-h"><div><span class="pnl-eb">SERVER ANALYTICS</span><b class="pnl-t">Battle score</b></div></header><div class="pnl-b"><p class="dim">The server’s battle score (gap, relative degradation and representative pace contributions) is kept on this page in production. It is not reproduced in the prototype because it is computed by AnalyticsSnapshot, not from timing alone.</p></div></div>`;
    battleView = new SS.BattleView($('#bMain'), { session, posture: 'desktop' });
    const bMapHost = battlePage.querySelector('.bp-map');
    if (hasOutline && state.map !== 'none') bMap = new SS.TrackMap(bMapHost, { session, posture: 'desktop', labels: 2 });
    else if (state.map !== 'none') bLine = new SS.TrackLine(bMapHost, { session, posture: 'desktop', lanes: 2 });
    const opts = '<option value="">SELECT</option>' + Object.values(session.drivers).sort((a, b) => a.code.localeCompare(b.code)).map((D) => `<option value="${D.num}">${D.code}</option>`).join('');
    $('#bA').innerHTML = opts; $('#bB').innerHTML = opts;
    $('#bMode').addEventListener('click', (ev) => { const b = ev.target.closest('[data-bm]'); if (b) { state.battleMode = b.dataset.bm; slowNext = 0; } });
    const pick = () => { const a = $('#bA').value, b = $('#bB').value; if (a && b && a !== b) { state.pinned = [a, b]; state.battleMode = 'pinned'; slowNext = 0; } };
    $('#bA').addEventListener('change', pick); $('#bB').addEventListener('change', pick);
    strategyPage.innerHTML = `<div class="bp-head"><div><span class="pnl-eb">RACE INTELLIGENCE</span><h2>Strategy</h2><p>Pirelli’s published pre-race strategy, alongside the current race as timing records it.</p></div></div><div class="sp-top" id="spTop"></div><div id="spStints"></div><div id="spLand"></div>`;
  }

  /* ---------------------------------------------------------- views */
  function setView(v) {
    if (!race && (v === 'battle' || v === 'strategy')) v = 'session';
    if (v === 'driver' && !state.driver) state.driver = (lastVm && lastVm.rows[0] && lastVm.rows[0].num) || Object.keys(session.drivers)[0];
    state.view = v;
    document.querySelectorAll('#nav [data-view]').forEach((a) => a.classList.toggle('is-on', a.dataset.view === v));
    document.querySelectorAll('#side .view').forEach((x) => x.classList.toggle('is-on', x.dataset.view === v));
    applySplit();
    buildTower();
    tower.setFollow(v === 'driver' && state.driver ? [state.driver] : []);
    slowNext = 0;
  }
  function openDriver(n) {
    state.driver = n;
    setView('driver');
  }

  /* ---------------------------------------------------------- takeovers + toast */
  const takeover = new SS.Takeover($('#takeover'), { session, posture: 'desktop' });
  const toastEl = document.createElement('div');
  toastEl.className = 'ws-toast';
  toastEl.hidden = true;
  document.body.appendChild(toastEl);
  let toastT = null;
  function toast(msg) { toastEl.textContent = msg; toastEl.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (toastEl.hidden = true), 2600); }
  function onEvents(events) {
    for (const e of events) if (race && (e.type === 'PASS' || e.type === 'BATTLE') && e.priority >= P.HIGHLIGHT) { state.recentPair = e.type === 'PASS' ? [e.drivers[0], e.drivers[1]] : [e.drivers[1], e.drivers[0]]; state.recentUntil = performance.now() + 30000; }
  }

  /* ---------------------------------------------------------- player + transport */
  const startAt = params.get('t') != null ? +params.get('t') : session.moments.length ? session.moments[0].t : session.begin;
  const player = new SS.Player(session, { startAt, speed: +(params.get('speed') || 10) });
  const transport = new SS.Transport($('#transport'), player, { posture: 'desktop' });
  SS.viewer.apply(player, params);
  if (params.get('follow') && session.drivers[params.get('follow')]) { state.driver = params.get('follow'); if (!params.get('view')) state.view = 'driver'; }
  if (params.get('play') !== '0') player.play(); else if (player.mode === 'live') player.pause();

  let forceJump = true, lastVm = null, slowNext = 0, opened = false;
  setView(state.view);

  function battlePair(vm) {
    if (state.battleMode === 'leader') { const live = vm.rows.filter((r) => !r.out); return live.length > 1 ? [live[0], live[1]] : null; }
    if (state.battleMode === 'pinned' && state.pinned) { const a = vm.byNum[state.pinned[0]], b = vm.byNum[state.pinned[1]]; if (a && b) return a.index < b.index ? [a, b] : [b, a]; }
    return SS.pickBattle(vm, state.recentPair && performance.now() < state.recentUntil ? state.recentPair : null);
  }

  player.on(({ now, jumped, crossed, cursor }) => {
    jumped = jumped || forceJump;
    forceJump = false;
    const vm = SS.vm(session, cursor, { now });
    vm.byNum = Object.fromEntries(vm.rows.map((r) => [r.num, r]));
    lastVm = vm;
    const rd = railModel(vm, player);
    rd.jumped = jumped;
    rail.reduced = state.reduced;
    rail.update(rd);
    tower.render(vm, { jumped, recent: SS.recentContext(session, now), reduced: state.reduced, speed: player.speed });
    takeover.reduced = state.reduced;
    takeover.speed = player.speed;
    if (jumped) takeover.clear();
    else if (crossed.length) { takeover.offer(crossed, now); onEvents(crossed); }
    takeover.tick(now);
    if (!opened) { opened = true; opening.done(); }
    const conn = player.mode === 'live' ? (player.liveState === 'LIVE' ? '<i class="ok"></i>LIVE CONNECTED' : `<i class="warn"></i>${player.liveState}`) : '<i class="ok"></i>REPLAY CONNECTED';
    if ($('#conn')._v !== conn) { $('#conn').innerHTML = conn; $('#conn')._v = conn; }
    const slow = jumped || performance.now() > slowNext;
    if (slow) slowNext = performance.now() + 450;

    if (state.view === 'session') {
      const lapTxt = race ? `LAP ${vm.lap || '—'} / ${vm.totalLaps || '—'}` : vm.clock != null ? `${vm.phase ? vm.phase + ' · ' : ''}${U.fmtClock(vm.clock)} LEFT` : '';
      const lt = mTrack.querySelector('.mt-lap'); if (lt.textContent !== lapTxt) lt.textContent = lapTxt;
      if (trackView) { trackView.setFocus([]); trackView.setMode(player.mode); trackView.render(vm, now); }
      if (lineView) { lineView.setFocus([]); lineView.setMode(player.mode); lineView.render(vm, now); }
      if (ribbon) { ribbon.setFocus([]); ribbon.render(vm, jumped); }
      if (ladder) { ladder.setFocus([]); ladder.render(vm, jumped); onTrack.render(vm); }
      feed.render(now, jumped, player.gen);
      if (slow) {
        if (zone) renderZone(vm);
        if (mSession) setHTML(mSession, sessionPanel(vm));
        if (mStrat) setHTML(mStrat, SS.strategySnapshotHTML(session, vm));
        setHTML(mCond, SS.conditionsHTML(session, vm));
        setHTML(mRc, SS.raceControlHTML(session, vm, state.layout === 'brief' ? 4 : 6));
      }
    } else if (state.view === 'driver') {
      renderDriver(vm, now, slow);
    } else if (state.view === 'battle') {
      const pair = battlePair(vm);
      tower.setHighlight(pair ? [pair[0].num, pair[1].num] : []);
      if (slow) renderBattle(vm, now, pair);
      if (bMap) { bMap.setFocus(pair ? [pair[0].num, pair[1].num] : []); bMap.setMode(player.mode); bMap.render(vm, now); }
      if (bLine) { bLine.setFocus(pair ? [pair[0].num, pair[1].num] : []); bLine.setMode(player.mode); bLine.render(vm, now); }
    } else if (state.view === 'strategy' && slow) {
      setHTML($('#spTop'), `<div class="sp-col">${SS.panel('OFFICIAL PRE-RACE', 'Pirelli tyre strategy', (window.SLIPSTREAM_SERVER || {})[label] ? '<span class="pill-pub">PUBLISHED · MODEL-ADMISSIBLE</span>' : '', SS.pirelliHTML(session, false), 'pnl-pir')}</div><div class="sp-col">${SS.panel('CURRENT SESSION', 'Race now', '', SS.raceNowHTML(session, vm, false), 'pnl-rn')}${SS.conditionsHTML(session, vm)}</div>`);
      setHTML($('#spStints'), SS.stintChartHTML(session, vm));
      setHTML($('#spLand'), SS.landscapeHTML(session, vm));
    }
    if (state.view !== 'battle') tower.setHighlight([]);
    transport.update();
    document.body.classList.toggle('is-stale', player.mode === 'live' && player.liveState !== 'LIVE');
    document.body.classList.toggle('is-live', player.mode === 'live');
  });

  const setHTML = (el, html) => { if (el._v !== html) { el.innerHTML = html; el._v = html; } };

  function sessionPanel(vm) {
    const p1 = vm.rows[0];
    const cells = [
      ['SEGMENT', vm.phase || '—'],
      ['TIME LEFT', vm.clock != null ? U.fmtClock(vm.clock) : '—'],
      ['FASTEST', p1 && p1.qTime != null ? `${p1.code} ${U.fmtLap(p1.qTime)}` : '—'],
      ['ADVANCE', vm.advance ? `TOP ${vm.advance}` : vm.phase === 'Q3' ? 'POLE SHOOTOUT' : '—'],
    ];
    return SS.panel('QUALIFYING', 'Session', '', `<div class="cond-grid q-grid">${cells.map(([l, v]) => `<div><span>${l}</span><b class="mono">${v}</b></div>`).join('')}</div>`, 'pnl-qs');
  }

  function renderZone(vm) {
    let html;
    if (kind === 'qualifying' && vm.advance) {
      const active = vm.rows.filter((r) => !r.qe);
      const cut = active[vm.advance - 1];
      const at = active.slice(Math.max(0, vm.advance - 3), vm.advance + 3);
      html = `<div class="ot-head"><span class="lbl">AROUND THE CUT · TOP ${vm.advance} GO THROUGH</span><b class="mono">${cut && cut.qTime != null ? U.fmtLap(cut.qTime) : '—'}</b></div><ol class="zone-list">${at.map((r) => {
        const delta = r.qTime != null && cut && cut.qTime != null ? r.qTime - cut.qTime : null;
        return `<li class="${r.index < vm.advance ? 'is-safe' : 'is-risk'}${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${delta == null ? '' : delta === 0 ? 'SETS CUT' : U.fmtDelta(delta)}</em></li>`;
      }).join('')}</ol>`;
    } else if (kind === 'qualifying') {
      html = `<div class="ot-head"><span class="lbl">FIGHT FOR POLE</span></div><ol class="zone-list">${vm.rows.slice(0, 6).map((r) => `<li class="is-top${r.activity === 'ON_TRACK' ? ' is-ontrack' : ''}" style="--team:${r.colour}"><span class="mono">P${r.pos}</span><i></i><b>${r.code}</b><span class="mono">${r.qTime != null ? U.fmtLap(r.qTime) : 'NO TIME'}</span><em class="mono">${r.qGap ? '+' + r.qGap.toFixed(3) : r.qTime != null ? 'POLE TIME' : ''}</em></li>`).join('')}</ol>`;
    } else {
      const ev = session.events.filter((e) => SS.avail(e) <= vm.t && (e.type === 'SESSION_BEST' || e.type === 'FLAG' || e.type === 'STOPPED' || (e.type === 'IMPROVEMENT' && (e.pos || 99) <= 10))).slice(-7).reverse();
      html = `<div class="ot-head"><span class="lbl">SESSION LOG</span></div><ol class="zone-list zone-log">${ev.map((e) => { const d = SS.describe(session, e, vm.t); return `<li class="tone-${d.tone}"><span class="mono">${SS.stamp(session, e)}</span><i></i><b>${d.tag}</b><span>${d.title}</span></li>`; }).join('') || '<li class="dim">Quiet so far</li>'}</ol>`;
    }
    setHTML(zone, html);
  }

  /* ---------------------------------------------------------- driver page */
  function renderDriver(vm, now, slow) {
    const r = vm.byNum[state.driver];
    if (dpMap) { dpMap.setFocus([state.driver]); dpMap.setMode(player.mode); dpMap.render(vm, now); }
    if (dpLine) { dpLine.setFocus([state.driver]); dpLine.setMode(player.mode); dpLine.render(vm, now); }
    if (!slow || !r) return;
    const D = session.drivers[r.num];
    const ahead = vm.rows[r.index - 1], behind = vm.rows[r.index + 1];
    const lapLabel = race ? `LAP ${vm.lap || '—'}` : vm.phase ? `${vm.phase} · ${U.fmtClock(vm.clock)} LEFT` : `${U.fmtClock(vm.clock)} LEFT`;
    setHTML($('#dpHead'), `<button class="tp-b" data-view="session">← BACK</button><div class="dp-id" style="--team:${r.colour}"><span class="pnl-eb">#${r.num} DRIVER FOCUS · ${lapLabel}</span><h2>${(D.name || '').split(' ')[0]} <b>${U.titleCase(D.surname)}</b></h2><p>${D.team}</p></div><div class="dp-pos"><span class="lbl">CURRENT POSITION</span><b class="mono">P${r.pos}</b><em>${r.out ? r.out : race ? (r.index === 0 ? 'LEADER' : r.gapLaps ? r.gapText : r.gapVal != null ? '+' + r.gapVal.toFixed(3) + ' to leader' : '') : r.qGap ? '+' + r.qGap.toFixed(3) : r.pGap ? '+' + r.pGap.toFixed(3) : r.index === 0 ? 'FASTEST' : ''}</em></div><span class="dp-hint dim">Click any row in the tower to change driver</span>`);
    const st = SS.stints(session, r.num, now);
    const dr = SS.dryRule(st);
    const cell = (l, v, sub = '') => `<div><span class="lbl">${l}</span><b>${v}</b>${sub ? `<small>${sub}</small>` : ''}</div>`;
    const stintCells = [
      cell('COMPOUND', `${SS.compoundBadge(r.compound, null, { noAge: true })} ${r.compound || '—'}`, r.usage ? r.usage.toLowerCase() + ' set' : ''),
      cell('TYRE AGE', r.age != null ? `<span class="mono">${r.age}</span> laps` : '—'),
      cell('STINT LAPS', `<span class="mono">${r.stint != null ? r.stint : '—'}</span>`),
      cell(race ? 'PIT STOPS' : 'STOPS', `<span class="mono">${r.pits}</span>`),
      cell('LAST LAP', `<span class="mono ${r.lastIsPB ? 't-green' : ''}">${r.last || '—'}</span>`),
      cell('BEST LAP', `<span class="mono ${r.bestIsFastest ? 't-purple' : ''}">${r.best || '—'}</span>`),
      cell('SECTORS · LAST LAP', `<span class="mono">${[r.s1, r.s2, r.s3].map((x) => (x == null || x === '' ? '—' : (+x).toFixed(3))).join('  ')}</span>`),
    ];
    if (race) {
      stintCells.push(cell('AHEAD', ahead ? `${ahead.code} · P${ahead.pos}` : '—', ahead && r.intVal != null ? `<span class="mono">${r.intVal.toFixed(3)} s</span>` : ''));
      stintCells.push(cell('BEHIND', behind ? `${behind.code} · P${behind.pos}` : '—', behind && behind.intVal != null ? `<span class="mono">${behind.intVal.toFixed(3)} s</span>` : ''));
    } else if (kind === 'qualifying') {
      stintCells.push(cell('SEGMENT TIMES', `<span class="mono">${['Q1', 'Q2', 'Q3'].map((q, i) => `${q} ${r.qr && r.qr[i] != null ? U.fmtLap(r.qr[i]) : '—'}`).join(' · ')}</span>`));
    }
    const facts = [];
    facts.push(r.out ? `${r.code} is ${r.out.toLowerCase()}.` : `${r.code} is running P${r.pos}${r.inPit ? ', in the pit lane' : ''}.`);
    if (r.compound) facts.push(`Current stint: ${r.compound} at ${r.age != null ? r.age : '—'} laps of tyre age.`);
    if (race) facts.push(`Observed completed pit stops: ${r.pits}.`);
    if (race && vm.lap > 1) facts.push(dr.text + '.');
    const left = SS.panel('CURRENT STINT', 'Driver state', '', `<div class="dp-cells">${stintCells.join('')}</div>`, 'pnl-ds')
      + SS.panel('FROM TIMING', 'Driver read', '', `<ul class="dp-facts">${facts.map((f) => `<li>${f}</li>`).join('')}</ul><p class="pnl-note">Pace trend and outlook come from the server’s driver model in production; they are not reproduced from timing here.</p>`, 'pnl-read')
      + SS.panel('DRIVER STRATEGY', 'Tyre strategy', '', `<div class="dp-cells">${cell('CURRENT TYRE', `${SS.compoundBadge(r.compound, r.age)}`)}${cell('STOPS', `<span class="mono">${r.pits}</span>`)}${cell('ACTUAL TYRE STRATEGY', SS.compoundSeq(st.list.map((x) => x.c)))}${race ? cell('DRY RULE', `<span class="dr-${dr.key}">${dr.text}</span>`) : ''}</div>${race ? SS.pirelliHTML(session, true) : ''}`, 'pnl-dstrat');
    setHTML($('#dpLeft'), left);
    const evs = session.events.filter((e) => SS.avail(e) <= now && e.priority >= P.FEED && e.drivers.includes(r.num)).slice(-8).reverse();
    const right = SS.panel(race ? 'CURRENT STINT' : 'THIS SESSION', race ? 'Lap times this stint' : 'Lap times', '', SS.lapChartHTML(session, r.num, now, 18, race), 'pnl-laps')
      + (race ? SS.panel('FACTUAL', 'Pit history', `<span class="pnl-count mono">${st.stops.length}</span>`, st.stops.length ? `<ol class="dp-pits">${st.stops.map((p, i) => `<li><span class="lbl">STOP ${i + 1}</span><b class="mono">LAP ${p.lap}</b><span>${p.prev ? SS.compoundBadge(p.prev, null, { noAge: true }) : ''}<em>›</em>${p.next ? SS.compoundBadge(p.next, null, { noAge: true }) : ''}</span><span class="mono">PIT LANE ${p.lane ? p.lane.toFixed(1) + 's' : '—'}</span><span class="dim">STATIONARY — <small>(not in the timing feed)</small></span></li>`).join('')}</ol>` : '<div class="pnl-empty">No stops yet</div>', 'pnl-pits') : '')
      + SS.panel('NEW', 'Moments', '', evs.length ? `<ol class="dp-evs">${evs.map((e) => { const d = SS.describe(session, e, now); return `<li class="tone-${d.tone}"><span class="mono">${SS.stamp(session, e)}</span><b>${d.title}</b><em>${d.detail || ''}</em></li>`; }).join('')}</ol>` : '<div class="pnl-empty">No moments yet for this driver</div>', 'pnl-dev');
    setHTML($('#dpRight'), right);
    const fl = driverPage.querySelector('.dp-focus'); if (fl) fl.textContent = `${r.code} · FOCUS`;
  }

  /* ---------------------------------------------------------- battle page */
  function renderBattle(vm, now, pair) {
    $('#bMode').querySelectorAll('[data-bm]').forEach((b) => b.classList.toggle('is-on', b.dataset.bm === state.battleMode));
    if (pair) { if (document.activeElement !== $('#bA')) $('#bA').value = pair[0].num; if (document.activeElement !== $('#bB')) $('#bB').value = pair[1].num; }
    battleView.render(vm, pair, now);
    const card = (r) => {
      if (!r) return '';
      const D = session.drivers[r.num];
      const st = SS.stints(session, r.num, now);
      const dr = SS.dryRule(st);
      return `<div class="pnl" style="--team:${r.colour}"><header class="pnl-h bc-h"><div><span class="pnl-eb">P${r.pos}</span><b class="pnl-t">${r.code} <small>${D.name} · #${r.num}</small></b></div><span class="dim">${D.team}</span></header><div class="pnl-b"><div class="dp-cells">
        <div><span class="lbl">GAP TO LEADER</span><b class="mono">${r.index === 0 ? 'LEADER' : r.gapLaps ? r.gapText : r.gapVal != null ? '+' + r.gapVal.toFixed(3) : '—'}</b></div>
        <div><span class="lbl">TYRE / AGE</span><b>${SS.compoundBadge(r.compound, r.age)}</b></div>
        <div><span class="lbl">LAST LAP</span><b class="mono">${r.last || '—'}</b></div>
        <div><span class="lbl">BEST LAP</span><b class="mono">${r.best || '—'}</b></div>
        <div><span class="lbl">S1 · S2 · S3</span><b class="mono">${[r.s1, r.s2, r.s3].map((x) => (x == null || x === '' ? '—' : (+x).toFixed(3))).join(' · ')}</b></div>
        <div><span class="lbl">STOPS</span><b class="mono">${r.pits}</b></div>
        <div><span class="lbl">ACTUAL TYRE STRATEGY</span><b>${SS.compoundSeq(st.list.map((x) => x.c))}</b></div>
        <div><span class="lbl">DRY RULE</span><b class="dr-${dr.key}">${dr.text}</b></div>
      </div></div></div>`;
    };
    setHTML($('#bCardA'), pair ? card(pair[0]) : '');
    setHTML($('#bCardB'), pair ? card(pair[1]) : '');
  }

  /* ---------------------------------------------------------- prototype options */
  const optLive = $('#optLive');
  optLive.checked = state.live;
  optLive.addEventListener('change', () => { state.live = optLive.checked; player.setMode(state.live ? 'live' : 'replay'); if (!state.live) { player.delay = 0; player.setSpeed(10); } });
  const optReduced = $('#optReduced');
  optReduced.checked = SS.motion.reduced;
  optReduced.addEventListener('change', () => SS.motion.set(optReduced.checked ? 'reduced' : 'full'));
  SS.motion.onChange((r) => { optReduced.checked = r; });
  const optDensity = $('#optDensity');
  optDensity.value = String(SS.density.get(params.get('density')));
  optDensity.addEventListener('change', () => SS.density.set(+optDensity.value));
  const optSpoil = $('#optSpoil');
  optSpoil.value = SS.spoilers.get();
  optSpoil.addEventListener('change', () => { SS.spoilers.set(optSpoil.value); transport._hz = -1; });
  $('#optTakeovers').addEventListener('change', (ev) => { takeover.enabled = ev.target.checked; if (!ev.target.checked) takeover.clear(); });
  const mapSel = $('#optMap');
  if (!hasOutline) { mapSel.querySelector('[value=outline]').disabled = true; mapSel.querySelector('[value=outline]').textContent = 'Outline (not available here)'; }
  mapSel.value = state.map;
  mapSel.addEventListener('change', () => { state.map = mapSel.value; buildMap(); setView('session'); });

  // Keyboard goes through the same capability checks as the buttons. Live: Space pauses (the delay
  // grows), ←/→ move the delay by 5 s. Replay: Space play/pause, ←/→ 30 s.
  document.addEventListener('keydown', (ev) => {
    if (ev.target && ev.target.matches && ev.target.matches('input, select, textarea')) return;
    const k = ev.key.toLowerCase();
    const live = player.mode === 'live';
    if (k === ' ') { ev.preventDefault(); player.toggle(); }
    else if (k === 'arrowleft') { ev.preventDefault(); live ? player.nudgeDelay(5) : player.skip(-30); }
    else if (k === 'arrowright') { ev.preventDefault(); live ? player.nudgeDelay(-5) : player.skip(30); }
    else if (k === 'escape') { if (!$('#protoPop').hidden || !$('#pickerPop').hidden) { $('#protoPop').hidden = true; $('#pickerPop').hidden = true; } else setView('session'); }
  });
  window.__web = { session, player, state, setView, openDriver };
})();

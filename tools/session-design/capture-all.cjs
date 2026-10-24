// Reusable live/replay visual audit. Uses the real API and browser, without mocked data.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const args = Object.fromEntries(process.argv.slice(2).reduce((rows, value, i, all) => value.startsWith('--') ? [...rows, [value.slice(2), all[i + 1]]] : rows, []));
const deps = process.env.SLIPSTREAM_BROWSER_DEPS || 'C:/Users/rejoz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = require(require.resolve('playwright', { paths: [deps] }));
const base = args.url || 'http://127.0.0.1:3344';
const mode = args.mode || 'live';
const repoRoot = path.resolve(__dirname, '../..');
const out = path.resolve(args.out || path.join(repoRoot, 'output/playwright', new Date().toISOString().replace(/[:.]/g, '-') + '-session-capture'));
if (!out.toLowerCase().startsWith('c:' + path.sep + 'gitclone' + path.sep)) throw new Error('Capture output must stay under C:/GitClone.');
const label = args.label || 'session-' + mode;
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g,'');
const report = {startedAt:new Date().toISOString(),base,mode,label,source:repoRoot.replace(/\\/g,'/'),commit:args.commit || null,profiles:[{id:'desktop',width:1440,height:900},{id:'phone',width:390,height:844}],captures:[],checks:[],issues:[],errors:[],networkFailures:[],websockets:[]};
let sequence = 0;
async function saveReport() { await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(report,null,2)); }
async function check(name, fn, profile) {
  try { const detail = await fn(); report.checks.push({name,profile,status:'pass',detail}); console.log('PASS',profile || '',name); }
  catch(e) { report.checks.push({name,profile,status:'fail',error:e.message}); report.issues.push({name,profile,detail:e.message}); console.log('FAIL',profile || '',name,e.message); }
}
async function capture(page, profile, screen, note, scroll = null) {
  await page.waitForTimeout(180);
  const filename = `${String(++sequence).padStart(3,'0')}-${slug(label)}-${slug(screen)}-${profile.id}-${profile.width}x${profile.height}.png`;
  const info = await page.evaluate(() => ({title:document.title,layout:document.querySelector('.app-shell')?.dataset.sessionLayout,connection:document.querySelector('.connection-state')?.textContent,session:document.querySelector('.session-strip')?.textContent || null,viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,driverPanelWidth:document.querySelector('.driver-current')?.getBoundingClientRect().width || null,driverGridWidth:document.querySelector('.driver-focus-grid')?.getBoundingClientRect().width || null}));
  await page.screenshot({path:path.join(out,filename),animations:'disabled'});
  const shot={file:filename,profile:profile.id,width:profile.width,height:profile.height,screen,note,capturedAt:new Date().toISOString(),mode,sessionKey:report.session.sessionKey,latestSequence:page._frames.at(-1)?.seq || null,scroll,info};
  report.captures.push(shot);
  await fs.writeFile(path.join(out,filename.replace('.png','.txt')),await page.locator('body').ariaSnapshot());
  if(info.documentWidth > profile.width + 1 || info.bodyWidth > profile.width + 1) report.issues.push({name:'Document horizontal overflow',profile:profile.id,screen,detail:info});
  if(profile.id==='phone' && info.driverPanelWidth && info.driverPanelWidth < profile.width*.6 && !report.issues.some(i=>i.name==='Phone Driver focus content is compressed'))report.issues.push({name:'Phone Driver focus content is compressed',profile:profile.id,screen,detail:`Current stint panel is ${Math.round(info.driverPanelWidth)}px wide inside a ${profile.width}px viewport; visual inspection shows clipped values and a large empty area beside the cards.`});
  await saveReport();
  console.log('CAPTURE',filename);
}
async function screen(page, profile, name, note = '') {
  await page.evaluate(() => { document.querySelectorAll('*').forEach(el => { if(el.scrollTop) el.scrollTop=0; }); window.scrollTo(0,0); });
  await capture(page,profile,name,note);
  // Fixed-height applications scroll inside panels. Capture successive scroll positions too.
  const regions = await page.evaluate(() => Array.from(document.querySelectorAll('*')).flatMap((el,index) => {
    const style=getComputedStyle(el),box=el.getBoundingClientRect();
    return /auto|scroll/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 30 && box.width > 120 && box.height > 100 && box.top < innerHeight && box.bottom > 0 && box.right > 0 && box.left < innerWidth ? [{index,name:el.className?.baseVal ?? el.className ?? el.tagName,height:el.clientHeight,max:el.scrollHeight-el.clientHeight}] : [];
  }));
  for(const region of regions.slice(0,5)) {
    let step=0;
    for(let top=Math.min(region.max,Math.round(region.height*.8)); ; top=Math.min(region.max,top+Math.round(region.height*.8))) {
      await page.evaluate(({index,top})=>{document.querySelectorAll('*')[index].scrollTop=top;}, {index:region.index,top});
      await capture(page,profile,`${name}-scroll-${slug(String(region.name).split(' ').slice(0,2).join('-'))}-${++step}`,note,{region:region.name,top});
      if(top>=region.max || step>=8) break;
    }
    await page.evaluate(index=>{document.querySelectorAll('*')[index].scrollTop=0;},region.index);
  }
}
async function nav(page, name) { await page.getByRole('navigation',{name:'Product navigation'}).getByRole('button',{name,exact:true}).click(); }
async function session(page) { await nav(page,'SESSION'); }
async function prepare(page) {
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.locator('.app-header').waitFor({timeout:35000});
  if(mode === 'replay') {
    // Partial recordings can begin with an empty grid; seek before waiting for rows.
    await page.locator('input[aria-label="Replay position"]:enabled').waitFor({timeout:35000});
    const old=page._frames.at(-1)?.seq;
    const slider=page.getByRole('slider',{name:'Replay position'}),box=await slider.boundingBox();
    await slider.focus();
    await page.mouse.click(box.x+8+(box.width-16)*Number(args.fraction || .55),box.y+box.height/2);
    const until=Date.now()+35000;
    while(Date.now()<until && page._frames.at(-1)?.seq===old) await page.waitForTimeout(150);
    assert.notEqual(page._frames.at(-1)?.seq,old,'Replay seek must change the cursor');
  }
  await page.locator('.timing-row:visible').first().waitFor({timeout:35000});
  await page.waitForTimeout(800);
}
async function addPage(context, profile) {
  const page=await context.newPage(); page._frames=[];
  page.on('pageerror', e=>report.errors.push({profile:profile.id,message:e.message}));
  page.on('console', msg=>{if(msg.type()==='error') report.errors.push({profile:profile.id,type:'console',message:msg.text()});});
  page.on('requestfailed', request=>{if(!/ERR_ABORTED/.test(request.failure()?.errorText || '')) report.networkFailures.push({profile:profile.id,url:request.url(),error:request.failure()?.errorText});});
  page.on('response', r=>{if(r.status()>=400) report.networkFailures.push({profile:profile.id,url:r.url(),status:r.status()});});
  page.on('websocket', socket=>{
    const connection={profile:profile.id,url:socket.url(),openedAt:new Date().toISOString(),frames:0}; report.websockets.push(connection);
    socket.on('framereceived', ({payload})=>{try{const row=JSON.parse(String(payload));connection.frames++;if(row.type==='state.snapshot') {page._frames.push(row); if(page._frames.length>100)page._frames.shift();}}catch{}});
    socket.on('socketerror', error=>report.errors.push({profile:profile.id,type:'websocket',message:String(error)}));
  });
  return page;
}
async function audit(page, profile) {
  await check('Session layout and classified driver rows render',async()=>{
    const count=await page.locator('.timing-row:visible').count(); assert.ok(count>=20,`Only ${count} driver rows`);
    assert.equal(await page.locator('.app-shell').getAttribute('data-session-layout'),report.session.layoutFamily);
    return {rows:count,layout:report.session.layoutFamily,connection:await page.locator('.connection-state').textContent()};
  },profile.id);
  await screen(page,profile,'session-timing','Default session view; actual streaming data.');
  if(profile.id==='phone') {
    const tabs=await page.locator('.mobile-priority-tabs:visible button').allTextContents();
    for(const tab of tabs.filter(t=>t!=='TIMING')) {
      await check(`Mobile ${tab} tab`,async()=>{await page.locator('.mobile-priority-tabs').getByRole('button',{name:tab,exact:true}).click();await screen(page,profile,`session-${tab.toLowerCase()}`);},profile.id);
    }
    await page.locator('.mobile-priority-tabs').getByRole('button',{name:'TIMING',exact:true}).click();
  } else {
    await check('Keyboard panel resizing and reset',async()=>{
      const handle=page.getByRole('separator',{name:'Resize timing and analysis panels'}); if(!await handle.count())return 'No splitter for this session';
      const before=Number(await handle.getAttribute('aria-valuenow'));await handle.focus();await page.keyboard.press('ArrowLeft');
      const after=Number(await handle.getAttribute('aria-valuenow'));assert.ok(after<before,`${before} -> ${after}`);await handle.dblclick();return {before,after};
    },profile.id);
  }
  await check('Session selector opens with season/weekend/session fields',async()=>{
    await page.locator('.replay-library summary').click();
    for(const name of ['Season','Race weekend','Weekend session'])assert.ok(await page.getByRole('combobox',{name,exact:true}).isVisible());
    await screen(page,profile,'session-library');await page.locator('.replay-library summary').click();
  },profile.id);
  await check('Driver picker and keyboard focus navigation',async()=>{
    await nav(page,'DRIVER');await page.getByRole('heading',{name:'Choose a driver',exact:true}).waitFor();
    assert.ok(await page.locator('.driver-picker-grid button').count()>=20);
    await screen(page,profile,'driver-picker');
    await page.locator('.driver-picker-grid button').first().focus();await page.keyboard.press('Enter');
    await page.locator('.driver-hero').waitFor();await screen(page,profile,'driver-focus');
    const info=page.getByLabel('Show explanation').first();
    if(await info.count()){await info.click();await screen(page,profile,'driver-metric-explanation');await info.click();}
    await page.getByRole('button',{name:'CHANGE DRIVER',exact:true}).click();
    await page.locator('.driver-picker-grid button').nth(1).click();await screen(page,profile,'driver-focus-second-driver');
    const back=page.getByRole('button',{name:'BACK',exact:true});
    if(await back.isVisible())await back.click();else {await session(page);report.checks.push({name:'Phone uses SESSION navigation to return from Driver; BACK is CSS-hidden',profile:profile.id,status:'pass'});}
    assert.ok(await page.locator('.timing-row:visible').count()>=20);
  },profile.id);
  if(report.session.layoutFamily==='race') {
    for(const item of ['BATTLE','STRATEGY'])await check(`${item} view opens`,async()=>{
      await nav(page,item);await screen(page,profile,item.toLowerCase());
      if(item==='BATTLE')for(const battleMode of ['LEADER','PINNED','RECOMMENDED']){await page.locator('.battle-modes').getByRole('button',{name:battleMode,exact:true}).click();if(battleMode==='PINNED'){const options=await page.locator('.battle-selectors select').first().locator('option').evaluateAll(nodes=>nodes.map(n=>n.value).filter(Boolean));await page.locator('.battle-selectors select').nth(0).selectOption(options[0]);await page.locator('.battle-selectors select').nth(1).selectOption(options[1]);}await screen(page,profile,`battle-${slug(battleMode)}`);}
    },profile.id);
    await session(page);
    for(const view of ['STANDARD','TIMING','STRATEGY']) {
      const button=page.locator('.timing-panel:visible').getByRole('button',{name:view,exact:true});
      if(await button.count())await check(`Timing tower ${view} variant`,async()=>{await button.click();await screen(page,profile,`session-tower-${view.toLowerCase()}`);},profile.id);
    }
  }
  if(report.session.layoutFamily==='qualifying')for(const view of ['TIMING','STANDARD']) {
    const button=page.locator('.timing-panel:visible .tower-view-modes').getByRole('button',{name:view,exact:true});
    if(await button.count())await check(`Qualifying tower ${view} variant`,async()=>{await button.click();await screen(page,profile,`session-tower-${view.toLowerCase()}`);},profile.id);
  }
  if(args['skip-settings'] !== 'true') {
  await check('All settings sections open',async()=>{
    await nav(page,'SETTINGS');
    for(const [name,id] of [['Profile','profile'],['Appearance','appearance'],['Layouts','layouts'],['Sync & Devices','sync-devices'],['Preferences','tv-preferences']]) {
      await page.locator('.settings-nav').getByRole('button',{name:new RegExp('^'+name.replace('&','\\&'))}).click();
      await screen(page,profile,`settings-${id}`,['profile','sync-devices'].includes(id)?'Backend-dependent controls are intentionally disabled.':'');
    }
  },profile.id);
  await check('Appearance choices apply and persist through reload',async()=>{
    await page.locator('.settings-nav').getByRole('button',{name:/^Appearance/}).click();
    const before={background:await page.locator('.app-shell').getAttribute('data-background'),accent:await page.locator('.app-shell').getAttribute('data-accent')};
    const options=page.locator('.background-options button');
    for(let i=0;i<await options.count();i++){await options.nth(i).click();assert.ok(await options.nth(i).getAttribute('class').then(v=>v.includes('selected')));}
    const accents=page.locator('[data-accent-option]');
    for(let i=0;i<await accents.count();i++){const option=accents.nth(i);await option.click();assert.equal(await page.locator('.app-shell').getAttribute('data-accent'),await option.getAttribute('data-accent-option'));}
    const final=await page.locator('.app-shell').getAttribute('data-accent');
    await screen(page,profile,'settings-appearance-alternate','Alternative background and accent; isolated capture browser preferences.');
    await page.reload({waitUntil:'domcontentloaded'});await page.locator('.app-header').waitFor();assert.equal(await page.locator('.app-shell').getAttribute('data-accent'),final);
    if(mode==='replay')await prepare(page);
    await nav(page,'SETTINGS');await page.locator('.settings-nav').getByRole('button',{name:/^Appearance/}).click();
    // Reset default preferences for all remaining design references.
    await page.locator('.background-options button').first().click();await page.locator(`[data-accent-option="${before.accent}"]`).click();
    return {themes:await options.count(),accents:await accents.count(),persistence:true};
  },profile.id);
  await check('Layout presets and module controls respond',async()=>{
    await page.locator('.settings-nav').getByRole('button',{name:/^Layouts/}).click();
    for(const preset of ['TOWER WIDE','ANALYSIS WIDE','BALANCED']){await page.getByRole('button',{name:preset,exact:true}).click();await screen(page,profile,`settings-layout-${slug(preset)}`);}
    const toggle=page.locator('.visibility-toggle').first();const initial=await toggle.getAttribute('aria-pressed');await toggle.click();assert.notEqual(await toggle.getAttribute('aria-pressed'),initial);await toggle.click();
    const size=page.locator('.module-editor-row select').first();await size.selectOption('compact');assert.equal(await size.inputValue(),'compact');await size.selectOption('standard');
    const move=page.getByRole('button',{name:/^Move .* down$/}).first();await move.click();await page.getByRole('button',{name:'BALANCED',exact:true}).click();
  },profile.id);
  await check('TV preferences selected driver and pinned pair controls',async()=>{
    await page.locator('.settings-nav').getByRole('button',{name:/^Preferences/}).click();
    const modeSelect=page.locator('.tv-preferences-settings select').nth(1);await modeSelect.selectOption('pinned');assert.equal(await page.locator('.pinned-pair select').count(),2);
    const numbers=await page.locator('.pinned-pair select').first().locator('option').evaluateAll(nodes=>nodes.map(n=>n.value).filter(Boolean));
    await page.locator('.pinned-pair select').nth(0).selectOption(numbers[0]);await page.locator('.pinned-pair select').nth(1).selectOption(numbers[1]);
    await screen(page,profile,'settings-tv-pinned-pair');await modeSelect.selectOption('recommended');
    const alerts=page.getByRole('checkbox',{name:'Enable critical race-control interrupts'});const checked=await alerts.isChecked();await alerts.setChecked(!checked);assert.equal(await alerts.isChecked(),!checked);await alerts.setChecked(checked);
  },profile.id);
  }
  await session(page);
  await check('TV Mode states, rotation, and exit',async()=>{
    const tv=page.getByRole('button',{name:'TV MODE',exact:true});
    if(!await tv.isVisible()){
      report.issues.push({name:'TV navigation hidden at phone width',profile:profile.id,detail:'TV Mode is CSS-hidden at 390px. Companion screenshot enters using the desktop navigation, then resizes to phone.'});
      await page.setViewportSize({width:1440,height:900});await tv.click();await page.setViewportSize({width:profile.width,height:profile.height});
    } else await tv.click();
    const names=await page.locator('.tv-rotation > div button').allTextContents();
    for(let i=0;i<names.length;i++){await page.locator('.tv-rotation > div button').nth(i).click();await screen(page,profile,`tv-${slug(names[i].replace(/^\d+/,''))}`,profile.id==='phone'?'TV has no entry button at this width; entered before resize.':'');}
    await page.getByRole('button',{name:'AUTO ROTATION OFF',exact:true}).click();assert.ok(await page.getByRole('button',{name:'AUTO ROTATION ON',exact:true}).isVisible());await page.getByRole('button',{name:'AUTO ROTATION ON',exact:true}).click();
    await page.getByRole('button',{name:'EXIT TV',exact:true}).click();assert.ok(await page.locator('.app-header').isVisible());
  },profile.id);
  if(mode==='live') {
    await check('Live delay preset confirms, custom delay validates, and GO LIVE resets',async()=>{
      const footer=page.getByRole('contentinfo',{name:'Live sync controls'});
      await footer.getByRole('button',{name:'10s',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.live-controls-status strong')?.textContent==='DELAY 0:10',null,{timeout:15000});
      await screen(page,profile,'live-delay-10-seconds');
      const input=page.getByRole('textbox',{name:'Custom live delay M:SS'});await input.fill('6:00');await footer.getByRole('button',{name:'APPLY',exact:true}).click();assert.ok(await page.getByRole('alert').isVisible());
      await screen(page,profile,'live-delay-invalid','Validation state for an out-of-range custom delay.');
      await input.fill('0:15');await footer.getByRole('button',{name:'APPLY',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.live-controls-status strong')?.textContent==='DELAY 0:15',null,{timeout:15000});
      await footer.getByRole('button',{name:'GO LIVE',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('.live-controls-status strong')?.textContent==='LIVE',null,{timeout:15000});
      assert.equal(await page.getByRole('textbox',{name:'Custom live delay M:SS'}).inputValue(),'0:00');
      return {preset:10,custom:15,invalid:'6:00',reset:0};
    },profile.id);
  } else {
    await check('Replay play/pause and speed controls',async()=>{
      const play=page.locator('.play-button');await play.click();await page.waitForTimeout(650);await play.click();
      const select=page.locator('.replay-controls select');if(await select.count()){const options=await select.locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));if(options.length>1){await select.selectOption(options[1]);await select.selectOption(options[0]);}}
      return 'Replay cursor seek performed during setup; play/pause exercised.';
    },profile.id);
  }
  await screen(page,profile,'session-after-checks','Returned to default Session view after interaction checks.');
}
function html() {
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(label)} screenshots</title><style>body{margin:0;background:#0b111a;color:#e8edf4;font:15px system-ui}header{padding:28px 36px;border-bottom:1px solid #283648}h1{font-size:26px;margin:0 0 8px}p{color:#a9b7ca}a{color:#54d6e9}nav{position:sticky;top:0;z-index:2;background:#111b28;padding:14px 36px;display:flex;gap:12px;flex-wrap:wrap}button{background:#1f3045;border:1px solid #40526a;border-radius:5px;color:white;padding:9px 16px;cursor:pointer}button.active{border-color:#48deef}main{padding:24px 36px;display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:24px}figure{margin:0;background:#111b28;padding:16px;border-radius:8px;border:1px solid #253548}img{width:100%;height:280px;object-fit:contain;background:#06090e}figcaption{line-height:1.6;margin-top:12px}small{color:#9aabc0}section{padding:0 36px 24px}li{margin:8px 0}.badge{color:#54d6e9;font-size:12px;text-transform:uppercase}body[data-filter=desktop] figure[data-profile=phone],body[data-filter=phone] figure[data-profile=desktop]{display:none}</style><header><h1>${esc(report.session.meetingName)} · ${esc(report.session.sessionName)} · ${esc(mode.toUpperCase())}</h1><p>${report.captures.length} labeled captures · desktop 1440 × 900 · phone 390 × 844 · touch emulation · DPR 1</p><p>Source commit ${esc(report.commit)} · session ${esc(report.session.sessionKey)} · ${esc(report.startedAt)} UTC · <a href="manifest.json">Capture manifest and checks</a></p><p>Raw images preserve the viewport. Scroll companions cover content inside fixed-height panels. Open an image for full resolution.</p></header><nav><button class="active" onclick="filter('all',this)">All</button><button onclick="filter('desktop',this)">Desktop</button><button onclick="filter('phone',this)">Phone</button><button onclick="document.getElementById('qa').scrollIntoView()">QA findings</button></nav><main>${report.captures.map(c=>`<figure data-profile="${esc(c.profile)}"><a href="${esc(c.file)}"><img loading="lazy" src="${esc(c.file)}" alt="${esc(c.screen)} ${esc(c.profile)}"></a><figcaption><span class="badge">${esc(c.profile)} ${c.width} × ${c.height} · ${esc(c.mode)}</span><br><b>${esc(c.screen.replace(/-/g,' '))}</b><br><small>${esc(c.note)} ${c.scroll?`Scroll ${esc(c.scroll.region)}: ${c.scroll.top}px.`:''}<br>${esc(c.capturedAt)} · stream sequence ${esc(c.latestSequence)}<br><a href="${esc(c.file)}">PNG</a> · <a href="${esc(c.file.replace('.png','.txt'))}">Accessible screen text</a></small></figcaption></figure>`).join('')}</main><section id="qa"><h2>QA results</h2><p>${report.checks.filter(c=>c.status==='pass').length} passed · ${report.checks.filter(c=>c.status==='fail').length} failed · ${report.errors.length} browser errors · ${report.networkFailures.length} failed requests</p><ul>${report.issues.map(i=>`<li><b>${esc(i.name)} ${esc(i.profile || '')}</b>: ${esc(typeof i.detail==='string'?i.detail:JSON.stringify(i.detail))}</li>`).join('')}</ul><details><summary>All checks</summary><ul>${report.checks.map(c=>`<li>${esc(c.status.toUpperCase())} · ${esc(c.profile || '')} · ${esc(c.name)} ${esc(c.error || '')}</li>`).join('')}</ul></details></section><script>function filter(value,el){document.body.dataset.filter=value;document.querySelectorAll('nav button').forEach(b=>b.classList.remove('active'));el.classList.add('active')}</script></html>`;
}
(async()=>{
  await fs.mkdir(out,{recursive:true});
  const response=await fetch(base+'/api/v1/catalog');assert.ok(response.ok,'Catalog endpoint');const catalog=await response.json();
  report.session=catalog.sessions.find(s=>s.sessionKey===(args.session || catalog.liveSessionKey));assert.ok(report.session,'Requested session is in catalog');
  if(mode==='live' && report.session.meetingName==='Bahrain Grand Prix' && report.session.circuit==='Kuala Lumpur')report.issues.push({name:'Live catalog identity needs review',detail:'The app identifies session 11728 as Bahrain Grand Prix / Practice 2 but labels its circuit and location Kuala Lumpur. These are recorded source values; no metadata was changed.'});
  if(!report.session.circuitShapeAvailable)report.issues.push({name:'Circuit shape unavailable',detail:'The selected session has no circuit outline. Screenshots preserve the honest unavailable state; no replacement map or car positions were injected.'});
  if(mode==='live')assert.ok(report.session.liveAvailable,'Requested session has live data');
  await fs.writeFile(path.join(out,'session-metadata.json'),JSON.stringify(report.session,null,2));
  const browser=await chromium.launch({headless:true});
  try {
    if(mode==='live')await check('Viewer delay remains private across simultaneous connections',async()=>{
      const contexts=[];const pages=[];try{
        for(let i=0;i<2;i++){const context=await browser.newContext({viewport:{width:1440,height:900}});contexts.push(context);await context.addInitScript(key=>{localStorage.setItem('slipstream.selected-session.v1',key);localStorage.setItem('slipstream.viewing-intent.v2',JSON.stringify({mode:'live',followLive:true}));},report.session.sessionKey);const page=await addPage(context,{id:`isolation-${i}`});pages.push(page);await prepare(page);}
        await pages[0].getByRole('contentinfo',{name:'Live sync controls'}).getByRole('button',{name:'30s',exact:true}).click();
        await pages[0].waitForFunction(()=>document.querySelector('.live-controls-status strong')?.textContent==='DELAY 0:30',null,{timeout:15000});
        await pages[1].waitForTimeout(500);assert.equal(pages[0]._frames.at(-1).live.delaySeconds,30);assert.equal(pages[1]._frames.at(-1).live.delaySeconds,0);return {viewerA:30,viewerB:0};
      }finally{for(const context of contexts)await context.close();}
    });
    for(const profile of report.profiles){
      const context=await browser.newContext({viewport:{width:profile.width,height:profile.height},isMobile:profile.id==='phone',hasTouch:profile.id==='phone',deviceScaleFactor:1});
      await context.addInitScript(({key,mode})=>{localStorage.setItem('slipstream.selected-session.v1',key);localStorage.setItem('slipstream.viewing-intent.v2',JSON.stringify({mode,followLive:mode==='live'}));},{key:report.session.sessionKey,mode});
      const page=await addPage(context,profile);
      await check('Initial real session connection and cursor',()=>prepare(page),profile.id);
      if(page._frames.length)await fs.writeFile(path.join(out,`state-${profile.id}.json`),JSON.stringify(page._frames.at(-1),null,2));
      if(mode==='live')await check('Live stream sequence advances',async()=>{const seq=page._frames.at(-1)?.seq;const until=Date.now()+10000;while(Date.now()<until&&page._frames.at(-1)?.seq===seq)await page.waitForTimeout(250);assert.ok(page._frames.at(-1)?.seq>seq,'No live sequence advance in 10 seconds');return {before:seq,after:page._frames.at(-1)?.seq};},profile.id);
      await audit(page,profile);
      await context.close();
    }
  } finally {
    await browser.close();report.finishedAt=new Date().toISOString();await saveReport();await fs.writeFile(path.join(out,'index.html'),html());
  }
  console.log(JSON.stringify({captures:report.captures.length,passed:report.checks.filter(c=>c.status==='pass').length,failed:report.checks.filter(c=>c.status==='fail').length,browserErrors:report.errors,networkFailures:report.networkFailures,issues:report.issues,out},null,2));
})().catch(async e=>{report.fatal=e.message;console.error(e);await saveReport();if(report.session)await fs.writeFile(path.join(out,'index.html'),html());process.exitCode=1;});

// Real replay design baselines: download/opening states and chronological screens.
// Capture files stay in the GitClone worktree; Settings are deliberately omitted.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const argv=process.argv.slice(2),arg={};for(let i=0;i<argv.length;i+=2)arg[argv[i].replace(/^--/,'')]=argv[i+1];
const repo=path.resolve(__dirname,'../..'),base=arg.url||'http://127.0.0.1:3344';
const out=path.resolve(arg.out||path.join(repo,'output/playwright/replay/2026-10-02-baku-2026'));
if(!out.toLowerCase().startsWith('c:'+path.sep+'gitclone'+path.sep))throw new Error('Output must stay under C:/GitClone.');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.SLIPSTREAM_BROWSER_DEPS||'C:/Users/rejoz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules']}));
const slug=s=>String(s).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');
const profiles=[{id:'desktop',width:1440,height:900},{id:'phone',width:390,height:844}];
let report,selected,kind,browser,captureSequence=0,saveQueue=Promise.resolve();
function save(){const body=JSON.stringify(report,null,2);saveQueue=saveQueue.then(async()=>{const temporary=path.join(out,'manifest.json.tmp');await fs.writeFile(temporary,body);await fs.rename(temporary,path.join(out,'manifest.json'));});return saveQueue;}
async function recordCheck(name,fn,profile,checkpoint){try{const detail=await fn();report.checks.push({name,status:'pass',profile,sessionKey:selected.sessionKey,checkpoint,detail});console.log('PASS',kind,profile||'',checkpoint||'',name);return detail;}catch(e){report.checks.push({name,status:'fail',profile,sessionKey:selected.sessionKey,checkpoint,detail:e.message});report.issues.push({name,profile,sessionKey:selected.sessionKey,checkpoint,detail:e.message});console.log('FAIL',name,e.message);await save();return null;}}
async function capture(page,profile,checkpoint,screen,note='',scroll=null){
 const dir=path.join(kind,checkpoint),filename=`${String(++captureSequence).padStart(3,'0')}-${slug(selected.circuit)}-${selected.year}-${selected.sessionKey}-${kind}-${checkpoint}-${screen}-${profile.id}-${profile.width}x${profile.height}.png`;
 await fs.mkdir(path.join(out,dir),{recursive:true});
 const info=await page.evaluate(()=>({width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,banners:Array.from(document.querySelectorAll('.live-source-state,.service-unavailable')).map(e=>e.textContent),connection:document.querySelector('.connection-state')?.textContent,driverRows:document.querySelectorAll('.timing-row').length,map:(()=>{
 const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),clip={left:0,top:0,right:innerWidth,bottom:innerHeight};if(r.width<=0||r.height<=0)return false;for(let a=e;a;a=a.parentElement){const s=getComputedStyle(a),b=a.getBoundingClientRect();if(s.display==='none'||s.visibility==='hidden')return false;if(/auto|scroll|hidden|clip/.test(s.overflowX)){clip.left=Math.max(clip.left,b.left);clip.right=Math.min(clip.right,b.right);}if(/auto|scroll|hidden|clip/.test(s.overflowY)){clip.top=Math.max(clip.top,b.top);clip.bottom=Math.min(clip.bottom,b.bottom);}}return Math.min(r.right,clip.right)>Math.max(r.left,clip.left)&&Math.min(r.bottom,clip.bottom)>Math.max(r.top,clip.top);};
 const views=Array.from(document.querySelectorAll('.map-panel')).filter(visible).map(e=>({shapeAvailable:visible(e.querySelector('.circuit-line')),markerCount:Array.from(e.querySelectorAll('.car-marker')).filter(visible).length,positionLabel:e.querySelector('.panel-footer')?.textContent||''}));return {shapeAvailable:views.some(v=>v.shapeAvailable),markerCount:Math.max(0,...views.map(v=>v.markerCount)),positionLabel:views.map(v=>v.positionLabel).join(' | '),views,measurement:'viewport-clipped-dom'};
 })(),battleMode:document.querySelector('.battle-modes button.active')?.textContent||null,tvState:document.querySelector('[class*=tv-stage-]')?.className||null}));
 const state=page._frames.at(-1),replayTime=state?.sessionTime||null;
 await page.screenshot({path:path.join(out,dir,filename),animations:'disabled'});
 await fs.writeFile(path.join(out,dir,filename.replace('.png','.txt')),await page.locator('body').ariaSnapshot());
 const shot={file:path.join(dir,filename).replace(/\\/g,'/'),profile:profile.id,width:profile.width,height:profile.height,sessionKey:selected.sessionKey,kind,checkpoint,screen,note,capturedAt:new Date().toISOString(),replayTime,lap:state?.data?.session?.lap??null,phase:state?.data?.session?.qualifying_phase??null,status:state?.data?.session?.status??null,sequence:state?.seq??null,source:(state?.capabilities||page._capabilities)?.source??null,positionMode:(state?.capabilities||page._capabilities)?.positionMode??null,map:info.map,scroll,info};
 report.captures.push(shot);if(info.documentWidth>profile.width+1&&!report.issues.some(i=>i.name==='Document horizontal overflow'&&i.profile===profile.id&&i.screen===screen))report.issues.push({name:'Document horizontal overflow',profile:profile.id,screen,checkpoint,sessionKey:selected.sessionKey,detail:info.documentWidth});
 await save();console.log('CAPTURE',shot.file,'lap',shot.lap,'phase',shot.phase,'markers',shot.map.markerCount);
}
async function screen(page,profile,checkpoint,name,note='',scrolls=false){
 await page.evaluate(()=>{document.querySelectorAll('*').forEach(e=>{if(e.scrollTop)e.scrollTop=0;});scrollTo(0,0);});
 await capture(page,profile,checkpoint,name,note);
 if(!scrolls)return;
 const regions=await page.evaluate(()=>Array.from(document.querySelectorAll('*')).flatMap((el,index)=>{const s=getComputedStyle(el),b=el.getBoundingClientRect();return /auto|scroll/.test(s.overflowY)&&el.scrollHeight>el.clientHeight+30&&b.width>120&&b.height>100&&b.top<innerHeight&&b.bottom>0&&b.right>0&&b.left<innerWidth?[{index,name:String(el.className?.baseVal??el.className??el.tagName),height:el.clientHeight,max:el.scrollHeight-el.clientHeight}]:[];}));
 for(const r of regions.slice(0,5)){let step=0;for(let top=Math.min(r.max,Math.round(r.height*.8));;top=Math.min(r.max,top+Math.round(r.height*.8))){await page.evaluate(({i,top})=>document.querySelectorAll('*')[i].scrollTop=top,{i:r.index,top});await capture(page,profile,checkpoint,`${name}-scroll-${slug(r.name.split(' ').slice(0,2).join('-'))}-${++step}`,note,{region:r.name,top});if(top>=r.max||step>=8)break;}await page.evaluate(i=>document.querySelectorAll('*')[i].scrollTop=0,r.index);}
}
async function nav(page,name){await page.getByRole('navigation',{name:'Product navigation'}).getByRole('button',{name,exact:true}).click();}
async function createPage(profile){
 const context=await browser.newContext({viewport:{width:profile.width,height:profile.height},deviceScaleFactor:1,isMobile:profile.id==='phone',hasTouch:profile.id==='phone'});
 await context.addInitScript(key=>{localStorage.setItem('slipstream.selected-session.v1',key);localStorage.setItem('slipstream.viewing-intent.v2',JSON.stringify({mode:'replay',followLive:false}));const Original=window.WebSocket;window.WebSocket=class extends Original{constructor(...args){super(...args);window.__captureSocket=this;}};},selected.sessionKey);
 const page=await context.newPage();page._frames=[];
 page.on('pageerror',e=>report.errors.push({profile:profile.id,sessionKey:selected.sessionKey,message:e.message}));
 page.on('console',m=>{if(m.type()==='error')report.errors.push({profile:profile.id,sessionKey:selected.sessionKey,type:'console',message:m.text()});});
 page.on('requestfailed',r=>{if(!/ERR_ABORTED/.test(r.failure()?.errorText||''))report.networkFailures.push({profile:profile.id,sessionKey:selected.sessionKey,url:r.url(),error:r.failure()?.errorText});});
 page.on('response',r=>{if(r.status()>=400)report.networkFailures.push({profile:profile.id,sessionKey:selected.sessionKey,url:r.url(),status:r.status()});});
 page.on('websocket',s=>s.on('framereceived',({payload})=>{try{const row=JSON.parse(String(payload));if(row.type==='state.snapshot'){if(row.capabilities)page._capabilities=row.capabilities;page._frames.push(row);if(page._frames.length>100)page._frames.shift();}}catch{}}));
 await page.goto(base,{waitUntil:'domcontentloaded'});await page.locator('.app-header').waitFor({timeout:30000});
 return {context,page,profile};
}
async function acquire(pages){
 if(!selected.available){
  for(const p of pages){await p.page.locator('.replay-library summary').click();await p.page.getByRole('button',{name:'DOWNLOAD REPLAY',exact:true}).waitFor();await capture(p.page,p.profile,'loading','before-download','Recording is absent locally; actual download action and session selectors.');}
  await pages[0].page.getByRole('button',{name:'DOWNLOAD REPLAY',exact:true}).click();
  await Promise.all(pages.map(p=>capture(p.page,p.profile,'loading','download-requested','Actual download requested from the desktop browser. Both browsers observe the same coalesced backend job.')));
  for(const p of pages){if(await p.page.locator('.replay-library[open]').count())await p.page.locator('.replay-library summary').click();}
  const seen=new Set(),deadline=Date.now()+12*60*1000;let completed=false,lastStatus='';
  while(Date.now()<deadline){
   for(const p of pages){const texts=await p.page.locator('.live-source-state:visible,.service-unavailable:visible').allTextContents();for(const text of texts){const stage=text.includes('OPENING SESSION')?'opening-session':text.match(/REPLAY \d+: (QUEUED|DOWNLOADING|FINALIZING|FAILED)/)?.[1]?.toLowerCase();if(stage&&!seen.has(p.profile.id+stage)){seen.add(p.profile.id+stage);await capture(p.page,p.profile,'loading',stage,`Observed application state: ${text.trim()}`);}}}
   const jobs=await (await fetch(base+'/api/v1/jobs')).json(),job=(jobs.jobs||jobs).find(j=>j.sessionKey===selected.sessionKey);
   if(job?.status!==lastStatus){lastStatus=job?.status;console.log('DOWNLOAD',selected.sessionKey,job?.status,job?.error||'');report.downloads.push({...job,observedAt:new Date().toISOString()});await save();}
   if(job?.status==='FAILED')throw new Error('Replay download failed: '+job.error);
   if(job?.status==='AVAILABLE'){completed=true;break;}
   await pages[0].page.waitForTimeout(150);
  }
  assert.ok(completed,'Download must complete within 12 minutes');
 }
 const openingSeen=new Set();const deadline=Date.now()+120000;
 while(Date.now()<deadline){let ready=0;for(const p of pages){if(await p.page.locator('input[aria-label="Replay position"]:enabled').count())ready++;else if(arg.resume!=='true'&&await p.page.getByText('OPENING SESSION',{exact:true}).count()&&!openingSeen.has(p.profile.id)){openingSeen.add(p.profile.id);await capture(p.page,p.profile,'loading','opening-replay','Real session initialization before playback controls become enabled.');}}if(ready===pages.length)break;await pages[0].page.waitForTimeout(100);}
 for(const p of pages){await p.page.locator('input[aria-label="Replay position"]:enabled').waitFor({timeout:30000});if(arg.resume!=='true')await capture(p.page,p.profile,'start','replay-ready-at-initial-cursor','First usable replay cursor. Empty cells and unpositioned cars are preserved.');}
}
async function seek(page,at){
 const target=Date.parse(at);await page.evaluate(at=>{if(window.__captureSocket?.readyState!==1)throw new Error('Replay socket is not open');window.__captureSocket.send(JSON.stringify({type:'seek',at}));},at);
 const deadline=Date.now()+90000;while(Date.now()<deadline){const state=page._frames.at(-1);if(state?.sessionTime&&Math.abs(Date.parse(state.sessionTime)-target)<=1500){await page.waitForTimeout(450);return state;}await page.waitForTimeout(100);}throw new Error('Replay seek did not reach '+at);
}
function checkpoints(events,metadata){
 const first=Date.parse(metadata.startTime),last=Date.parse(metadata.endTime);let status=null,phase=null,active=null;const windows={},runs=[],laps=[];
 const close=t=>{if(active&&t>active.start){(windows[active.phase]??=[]).push({start:active.start,end:t});active=null;}};
 for(const e of events){if(e.kind!=='session')continue;const p=e.payload,t=Date.parse(e.occurred_at);
  if(p.qualifying_phase&&p.qualifying_phase!==phase){close(t);phase=p.qualifying_phase;}
  if(p.status&&p.status!==status){if(status==='RUNNING')close(t);status=p.status;if(status==='RUNNING')runs.push(t);}
  if(status==='RUNNING'&&!active)active={phase:phase||'UNKNOWN',start:t};
  if(p.lap!=null)laps.push({lap:Number(p.lap),at:t});
 }
 close(last);const running=runs.find(t=>t>=first)||first,clamp=t=>new Date(Math.min(last,Math.max(first,t))).toISOString();
 const phaseAt=p=>{const spans=windows[p]||[];let remaining=spans.reduce((n,w)=>n+w.end-w.start,0)*.65;for(const w of spans){if(remaining<=w.end-w.start)return w.start+remaining;remaining-=w.end-w.start;}return null;};
 if(kind==='qualifying')return [{id:'start',at:clamp(running+5000),note:'First RUNNING state + 5 seconds.'},...['Q1','Q2','Q3'].filter(p=>phaseAt(p)!=null).map(p=>({id:p.toLowerCase(),at:clamp(phaseAt(p)),note:`65% through cumulative source-authored RUNNING time in ${p}; interruptions excluded and phase/status validated after seek.`})),{id:'finish',at:clamp(last),note:'Replay end cursor from server metadata; settled final classification.'}];
 if(kind==='race'){
  const total=Math.max(...laps.map(l=>l.lap),0),lapAt=n=>laps.find(l=>l.lap>=n&&l.at>=running)?.at;
  return [{id:'start',at:clamp(running+5000),note:'Actual race RUNNING transition + 5 seconds; start appearance.'},{id:'early',at:clamp((lapAt(3)||running+(last-running)*.08)+10000),note:'Source lap 3 transition + 10 seconds where available.'},{id:'middle',at:clamp((lapAt(Math.ceil(total/2))||running+(last-running)*.5)+10000),note:`Mid-race, source lap ${Math.ceil(total/2)} transition + 10 seconds.`},{id:'late',at:clamp((lapAt(Math.max(total-3,1))||running+(last-running)*.9)+10000),note:'Three laps before the final observed lap, + 10 seconds.'},{id:'finish',at:clamp(last),note:'Replay end cursor from server metadata; finishing and retired states.'}];
 }
 return [{id:'start',at:clamp(running+5000),note:'Actual practice RUNNING transition + 5 seconds.'},{id:'early',at:clamp(running+(last-running)*.15),note:'Early practice, 15% of the actual RUNNING-to-replay-end window.'},{id:'middle',at:clamp(running+(last-running)*.5),note:'Middle of the actual practice running window.'},{id:'late',at:clamp(running+(last-running)*.9),note:'Late practice, 90% of the running window.'},{id:'finish',at:clamp(last),note:'Replay end cursor from server metadata.'}];
}
async function tv(page,profile,cp){
 const button=page.getByRole('button',{name:'TV MODE',exact:true});let note='All TV screens offered by this session at this cursor.';
 if(!await button.isVisible()){await page.setViewportSize({width:1440,height:900});await button.click();await page.setViewportSize({width:profile.width,height:profile.height});note+=' Phone entry is hidden; entered at desktop width then resized to the requested phone viewport.';if(!report.issues.some(i=>i.name==='Phone TV entry hidden'))report.issues.push({name:'Phone TV entry hidden',detail:note,profile:profile.id});}else await button.click();
 const rotation=page.locator('.tv-rotation > div button'),names=await rotation.allTextContents();
 for(let i=0;i<names.length;i++){await rotation.nth(i).click();await screen(page,profile,cp,`tv-${slug(names[i].replace(/^\d+/,''))}`,note,true);}
 await recordCheck('Every available TV screen captured',()=>({screens:names}),profile.id,cp);
 await page.getByRole('button',{name:'EXIT TV',exact:true}).click();
}
async function checkpointScreens(page,profile,cp){
 await nav(page,'SESSION');await seek(page,cp.at);await screen(page,profile,cp.id,'session-timing',cp.note,true);
 await recordCheck('Replay cursor matches checkpoint',async()=>{const s=page._frames.at(-1);assert.ok(Math.abs(Date.parse(s.sessionTime)-Date.parse(cp.at))<1500);if(/^q[123]$/.test(cp.id)){assert.equal(s.data.session.qualifying_phase,cp.id.toUpperCase());assert.equal(s.data.session.status,'RUNNING');}return {time:s.sessionTime,seq:s.seq,lap:s.data.session.lap,phase:s.data.session.qualifying_phase,rows:await page.locator('.timing-row:visible').count(),positionMode:(s.capabilities||page._capabilities)?.positionMode};},profile.id,cp.id);
 if(profile.id==='phone'){const tabs=await page.locator('.mobile-priority-tabs:visible button').allTextContents();for(const name of tabs.filter(n=>n!=='TIMING')){await page.locator('.mobile-priority-tabs').getByRole('button',{name,exact:true}).click();await screen(page,profile,cp.id,'session-'+slug(name),cp.note,true);}if(tabs.includes('TIMING'))await page.locator('.mobile-priority-tabs').getByRole('button',{name:'TIMING',exact:true}).click();}
 if(cp.id==='middle'||cp.id==='q2'){
  const modes=page.locator('.timing-panel:visible .tower-view-modes button'),names=await modes.allTextContents();for(let i=0;i<names.length;i++){await modes.nth(i).click();await screen(page,profile,cp.id,'session-tower-'+slug(names[i]),cp.note,true);}if(names.length)await modes.first().click();
  await page.locator('.replay-library summary').click();await screen(page,profile,cp.id,'session-library','Downloaded replay session selection; no Settings recapture.');await page.locator('.replay-library summary').click();
 }
 const driverCount=Object.keys(page._frames.at(-1)?.data?.drivers||{}).length;
 if(driverCount){
  await nav(page,'DRIVER');if(await page.getByRole('button',{name:'CHANGE DRIVER',exact:true}).isVisible())await page.getByRole('button',{name:'CHANGE DRIVER',exact:true}).click();await page.locator('.driver-picker-grid button').first().waitFor({timeout:15000});if(cp.id==='middle'||cp.id==='q2')await screen(page,profile,cp.id,'driver-picker','All driver choices in this replay.',true);
  await page.locator('.driver-picker-grid button').first().click();await page.locator('.driver-hero').waitFor();await page.waitForTimeout(400);await screen(page,profile,cp.id,'driver-focus',cp.note,true);
  if(cp.id==='middle'||cp.id==='q2'){const info=page.getByLabel('Show explanation').first();if(await info.count()){await info.click();await screen(page,profile,cp.id,'driver-metric-explanation');await info.click();}await page.getByRole('button',{name:'CHANGE DRIVER',exact:true}).click();await page.locator('.driver-picker-grid button').nth(1).click();await page.waitForTimeout(350);await screen(page,profile,cp.id,'driver-focus-second-driver',cp.note,true);}
  await nav(page,'SESSION');
 }
 if(kind==='race'){
  await nav(page,'BATTLE');await page.locator('.battle-modes').getByRole('button',{name:'RECOMMENDED',exact:true}).click();await screen(page,profile,cp.id,'battle-recommended',cp.note,true);
  if(cp.id==='middle')for(const name of ['LEADER','PINNED']){await page.locator('.battle-modes').getByRole('button',{name,exact:true}).click();if(name==='PINNED'){const options=await page.locator('.battle-selectors select').first().locator('option').evaluateAll(ns=>ns.map(n=>n.value).filter(Boolean));await page.locator('.battle-selectors select').nth(0).selectOption(options[0]);await page.locator('.battle-selectors select').nth(1).selectOption(options[1]);}await screen(page,profile,cp.id,'battle-'+slug(name),cp.note,true);}
  await nav(page,'STRATEGY');await screen(page,profile,cp.id,'strategy',cp.note,true);await nav(page,'SESSION');
 }
 await tv(page,profile,cp.id);
 if(cp.id==='middle'||cp.id==='q2')await recordCheck('Replay UI play, pause, speed and keyboard seek',async()=>{const speed=page.getByRole('combobox',{name:'Replay speed'});await speed.selectOption('2');assert.equal(await speed.inputValue(),'2');await page.locator('.play-button').click();await page.waitForTimeout(400);await page.locator('.play-button').click();await speed.selectOption('10');await page.getByRole('slider',{name:'Replay position'}).focus();await page.keyboard.press('ArrowRight');await seek(page,cp.at);return 'Actual UI controls exercised; restored checkpoint';},profile.id,cp.id);
}
(async()=>{
 await fs.mkdir(out,{recursive:true});try{report=JSON.parse(await fs.readFile(path.join(out,'manifest.json'),'utf8'));}catch{report={title:'Baku 2026 replay design baselines',mode:'replay',source:repo,commit:arg.commit||null,startedAt:new Date().toISOString(),scope:'Practice, Qualifying, Race; loading/start/chronological checkpoints; Session/Driver/Battle/Strategy/available TV screens; Settings excluded; actual replay data only.',sessions:[],captures:[],checks:[],issues:[],errors:[],networkFailures:[],downloads:[]};}
 captureSequence=report.captures.length;
 const catalog=await (await fetch(base+'/api/v1/catalog')).json();selected=catalog.sessions.find(s=>s.sessionKey===arg.session);assert.ok(selected,'Session key must be in the actual app catalog');kind=selected.layoutFamily;assert.ok(['practice','qualifying','race'].includes(kind));if(!report.sessions.some(s=>s.sessionKey===selected.sessionKey))report.sessions.push(selected);
 browser=await chromium.launch({headless:true});const pages=[];
 try{
  for(const p of profiles)pages.push(await createPage(p));await acquire(pages);
  const metadata=await (await fetch(base+'/api/v1/replay?session_key='+selected.sessionKey)).json();assert.ok(metadata.available,'Actual recording metadata');
  report.sessions.find(s=>s.sessionKey===selected.sessionKey).replayMetadata=metadata;
  if(arg['download-only']==='true'){console.log('DOWNLOAD_READY',selected.sessionKey,metadata.positionMode);return;}
  const dataRoot=arg['data-root']||'C:/GitClone/slipstream-f1/recordings',names=await fs.readdir(dataRoot),filename=names.find(n=>n===`f1-static-${selected.sessionKey}.json`);assert.ok(filename,'Checkpoint extraction needs the actual normalized static archive recording');const events=JSON.parse(await fs.readFile(path.join(dataRoot,filename),'utf8'));
  const points=checkpoints(events,metadata);report.sessions.find(s=>s.sessionKey===selected.sessionKey).checkpoints=points;console.log('CHECKPOINTS',kind,JSON.stringify(points));
  for(const p of pages)for(const cp of points){if(arg.checkpoints&&!arg.checkpoints.split(',').includes(cp.id))continue;if(arg.only==='battle'){await nav(p.page,'SESSION');await seek(p.page,cp.at);await nav(p.page,'BATTLE');await p.page.locator('.battle-modes').getByRole('button',{name:'RECOMMENDED',exact:true}).click();await screen(p.page,p.profile,cp.id,'battle-recommended',cp.note,true);continue;}const complete=report.checks.some(c=>c.sessionKey===selected.sessionKey&&c.profile===p.profile.id&&c.checkpoint===cp.id&&c.name==='Every available TV screen captured'&&c.status==='pass');if(arg.resume==='true'&&complete)continue;await checkpointScreens(p.page,p.profile,cp);}
  await recordCheck('Running map outline and car markers',async()=>{const shots=report.captures.filter(c=>c.sessionKey===selected.sessionKey&&['early','middle','late','q1','q2','q3'].includes(c.checkpoint));assert.ok(shots.some(c=>c.map.shapeAvailable),'No rendered track outline');assert.ok(shots.some(c=>c.map.markerCount>0),'No renderable car positions in this replay');return {maxMarkers:Math.max(...shots.map(c=>c.map.markerCount)),positionModes:[...new Set(shots.map(c=>c.positionMode))]};},null,'running');
 }finally{for(const p of pages)await p.context.close();await browser.close();report.updatedAt=new Date().toISOString();await save();}
 console.log('COMPLETE',kind,selected.sessionKey,'total captures',report.captures.length);if(report.checks.some(c=>c.sessionKey===selected.sessionKey&&c.status==='fail')||report.errors.some(e=>e.sessionKey===selected.sessionKey)||report.networkFailures.some(e=>e.sessionKey===selected.sessionKey))process.exitCode=1;
})().catch(async e=>{console.error(e);if(report){report.issues.push({name:'Capture interrupted',sessionKey:selected?.sessionKey,detail:e.message});await save();}process.exitCode=1;});

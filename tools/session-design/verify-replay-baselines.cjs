// Verify real replay capture artifacts and the generated review gallery.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const deps=process.env.SLIPSTREAM_BROWSER_DEPS||'C:/Users/rejoz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const sharp=require(require.resolve('sharp',{paths:[deps]})),{chromium}=require(require.resolve('playwright',{paths:[deps]}));
const root=path.resolve(process.argv[2]||path.join(__dirname,'../../output/playwright/replay/2026-10-02-baku-2026'));
if(!root.toLowerCase().startsWith('c:'+path.sep+'gitclone'+path.sep))throw new Error('Verification output must remain in GitClone.');
(async()=>{
 const data=JSON.parse(await fs.readFile(path.join(root,'manifest.json'),'utf8')),paths=new Set(),result={verifiedAt:new Date().toISOString(),screenshots:0,profiles:{},sessions:[],galleryChecks:[],browserErrors:[]};
 assert.ok(data.captures.length);assert.equal(data.errors.length,0);assert.equal(data.networkFailures.length,0);assert.equal(data.checks.filter(c=>c.status==='fail').length,0);assert.equal(data.captures.filter(c=>/settings/i.test(c.screen)).length,0);
 for(const c of data.captures){
  const file=path.resolve(root,c.file);assert.ok(file.startsWith(root+path.sep));assert.ok(!paths.has(file),'Duplicate capture path: '+c.file);paths.add(file);
  const metadata=await sharp(file).metadata();assert.equal(metadata.width,c.width,c.file);assert.equal(metadata.height,c.height,c.file);
  assert.deepEqual([c.width,c.height],c.profile==='desktop'?[1440,900]:[390,844]);assert.ok((await fs.readFile(file.replace(/\.png$/i,'.txt'),'utf8')).trim().length);
  if(c.screen.startsWith('tv-')){const state=c.info.tvState.match(/\btv-stage-([a-z]+)/)?.[1];assert.ok(c.screen.startsWith('tv-'+state),c.file+' TV state mismatch');}
  if(c.info.battleMode&&c.screen.startsWith('battle-'))assert.ok(c.screen.startsWith('battle-'+c.info.battleMode.toLowerCase()),c.file+' Battle mode mismatch');
  result.screenshots++;result.profiles[c.profile]=(result.profiles[c.profile]||0)+1;
 }
 for(const session of data.sessions){
  const shots=data.captures.filter(c=>c.sessionKey===session.sessionKey),kind=session.layoutFamily,tv=kind==='race'?['tower','track','strategy','battle','driver']:kind==='qualifying'?['tower','track']:['tower'];
  for(const profile of ['desktop','phone']){
   for(const screen of ['before-download','download-requested','downloading'])assert.ok(shots.some(c=>c.profile===profile&&c.checkpoint==='loading'&&c.screen===screen),session.sessionKey+' '+profile+' '+screen);
   assert.ok(shots.some(c=>c.profile===profile&&c.screen==='replay-ready-at-initial-cursor'));
   for(const cp of session.checkpoints){
    const primary=shots.find(c=>c.profile===profile&&c.checkpoint===cp.id&&c.screen==='session-timing');assert.ok(primary,session.sessionKey+' '+profile+' '+cp.id);assert.equal(primary.replayTime,cp.at);
    if(/^q[123]$/.test(cp.id)){assert.equal(primary.phase,cp.id.toUpperCase());assert.equal(primary.status,'RUNNING');}
    for(const mode of tv)assert.ok(shots.some(c=>c.profile===profile&&c.checkpoint===cp.id&&c.screen==='tv-'+mode),session.sessionKey+' '+profile+' '+cp.id+' tv-'+mode);
   }
  }
  assert.ok(shots.some(c=>c.map.shapeAvailable&&c.map.markerCount>0&&(c.map.measurement==='viewport-clipped-dom'||c.map.measurement==='screenshot-review')),'No screenshot-visible track/car evidence: '+session.sessionKey);
  result.sessions.push({key:session.sessionKey,kind,total:shots.length,desktop:shots.filter(c=>c.profile==='desktop').length,phone:shots.filter(c=>c.profile==='phone').length,checkpoints:session.checkpoints.map(c=>c.id),tvModes:tv});
 }
 const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',e=>result.browserErrors.push(e.message));await page.goto('http://127.0.0.1:8766/replay/2026-10-02-baku-2026/',{waitUntil:'domcontentloaded'});await page.locator('.capture').first().waitFor();assert.equal(await page.locator('.capture').count(),data.captures.length);
  await page.locator('#kind').selectOption('qualifying');await page.locator('#checkpoint').selectOption('q2');await page.locator('#profile').selectOption('phone');await page.locator('#screen').selectOption('tv-track');assert.equal(await page.locator('.capture').count(),1);await page.locator('.preview img').first().scrollIntoViewIfNeeded();await page.waitForFunction(()=>document.querySelector('.preview img')?.naturalWidth===390);result.galleryChecks.push('Combined session/checkpoint/viewport/TV filters and full-resolution image');
  await page.locator('#reset').click();assert.equal(await page.locator('.capture').count(),data.captures.length);await page.locator('#search').fill('download');assert.ok(await page.locator('.capture').count()>0);result.galleryChecks.push('Search and reset');
  const phone=await browser.newPage({viewport:{width:390,height:844}});phone.on('pageerror',e=>result.browserErrors.push(e.message));await phone.goto('http://127.0.0.1:8766/replay/2026-10-02-baku-2026/',{waitUntil:'domcontentloaded'});assert.ok(await phone.evaluate(()=>document.documentElement.scrollWidth<=390));result.galleryChecks.push('Gallery fits phone width');
  await page.goto('http://127.0.0.1:8766/',{waitUntil:'domcontentloaded'});await page.getByRole('heading',{name:'Replay captures',exact:true}).waitFor();await page.getByRole('heading',{name:'Live captures',exact:true}).waitFor();assert.ok(await page.getByRole('link',{name:/Baku 2026 replay design baselines/}).count());result.galleryChecks.push('Live and Replay library organization');assert.deepEqual(result.browserErrors,[]);
 }finally{await browser.close();}
 await fs.writeFile(path.join(root,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});

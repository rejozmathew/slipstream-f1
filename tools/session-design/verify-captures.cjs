const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const deps='C:/Users/rejoz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const sharp=require(require.resolve('sharp',{paths:[deps]}));
const {chromium}=require(require.resolve('playwright',{paths:[deps]}));
const root=path.resolve(__dirname,'../../output/playwright/2026-10-02-practice-2');
(async()=>{
  let files=0;const results={dimensions:[],browserErrors:[],filterChecks:[]};
  for(const folder of ['baseline','supplemental-qualifying-replay','supplemental-race-replay']){
    const manifest=JSON.parse(await fs.readFile(path.join(root,folder,'manifest.json'),'utf8'));
    for(const capture of manifest.captures){const metadata=await sharp(path.join(root,folder,capture.file)).metadata();assert.equal(metadata.width,capture.width,capture.file);assert.equal(metadata.height,capture.height,capture.file);await fs.access(path.join(root,folder,capture.file.replace('.png','.txt')));files++;}
    results.dimensions.push({folder,verified:manifest.captures.length});
  }
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>results.browserErrors.push(e.message));
    await page.goto('http://127.0.0.1:8766/2026-10-02-practice-2/',{waitUntil:'networkidle'});
    assert.ok(await page.locator('figure:visible').count()>10);
    await page.getByRole('combobox',{name:'Capture viewport'}).selectOption('phone');
    assert.ok(await page.locator('figure:visible').count()>10);assert.equal(await page.locator('figure:visible[data-profile="desktop"]').count(),0);results.filterChecks.push('Phone viewport filter');
    await page.getByRole('combobox',{name:'Screen category'}).selectOption('driver');assert.ok(await page.locator('figure:visible').count()>=4);results.filterChecks.push('Driver screen filter');
    await page.getByRole('checkbox',{name:'Include scroll companions'}).check();assert.ok(await page.locator('figure:visible[data-scroll="true"]').count()>0);results.filterChecks.push('Scroll companion filter');
    await page.getByRole('combobox',{name:'Capture session'}).selectOption('supplemental-race-replay');assert.ok(await page.locator('figure:visible').count()>0);assert.equal(await page.locator('figure:visible[data-folder="baseline"]').count(),0);results.filterChecks.push('Historical race filter');
    await page.getByRole('combobox',{name:'Capture session'}).selectOption('baseline');await page.getByRole('combobox',{name:'Capture viewport'}).selectOption('all');await page.getByRole('combobox',{name:'Screen category'}).selectOption('session');await page.getByRole('checkbox',{name:'Include scroll companions'}).uncheck();
    const images=page.locator('figure:visible img');for(let i=0;i<Math.min(await images.count(),6);i++){await images.nth(i).scrollIntoViewIfNeeded();assert.ok(await images.nth(i).evaluate(img=>img.complete&&img.naturalWidth>0));}results.filterChecks.push('Visible image links load');
    await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(root,'gallery-preview.png')});
    const phonePage=await browser.newPage({viewport:{width:390,height:844}});await phonePage.goto('http://127.0.0.1:8766/2026-10-02-practice-2/',{waitUntil:'networkidle'});const width=await phonePage.evaluate(()=>document.documentElement.scrollWidth);assert.ok(width<=390,`Gallery phone width ${width}`);results.filterChecks.push('Gallery fits phone width');
    assert.deepEqual(results.browserErrors,[]);
  }finally{await browser.close();}
  results.totalVerified=files;results.finishedAt=new Date().toISOString();await fs.writeFile(path.join(root,'capture-verification.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exitCode=1});

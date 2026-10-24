const fs = require('node:fs/promises');
const path = require('node:path');
const repo = path.resolve(__dirname, '../..');
const root = path.join(repo, 'output/playwright');
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const relativeUrl = value => value.split(path.sep).map(encodeURIComponent).join('/');
async function readJson(file) { try { return JSON.parse(await fs.readFile(file, 'utf8')); } catch { return undefined; } }
async function discover(folder, depth, runs) {
  if (depth > 5) return;
  const summary = await readJson(path.join(folder, 'qa-summary.json'));
  const manifest = await readJson(path.join(folder, 'manifest.json'));
  const data = summary ?? manifest;
  let hasGallery = false;
  try { await fs.access(path.join(folder, 'index.html')); hasGallery = true; } catch {}
  if (folder !== root && data && hasGallery) {
    const mode = summary ? 'legacy' : data.mode === 'live' ? 'live' : data.mode === 'replay' ? 'replay' : 'legacy';
    const count = Array.isArray(data.captures) ? data.captures.length : Number(data.captures ?? 0);
    const checks = summary ? data.uiChecks ?? {} : { passed: data.checks?.filter(check => check.status === 'pass').length ?? 0, failed: data.checks?.filter(check => check.status === 'fail').length ?? 0 };
    const title = summary ? 'Practice 2 design baseline · live and historical supplements' : data.title ?? `${data.session?.meetingName ?? 'Session'} / ${data.session?.sessionName ?? data.label ?? 'Capture set'}`;
    const profiles = Array.isArray(data.captures) ? [...new Set(data.captures.map(capture => `${capture.profile} ${capture.width} × ${capture.height}`))] : [];
    runs.push({ folder: path.relative(root, folder), title, count, checks, mode, profiles, startedAt: data.startedAt ?? data.createdAt ?? data.groups?.[0]?.startedAt ?? '', sessions: data.sessions ?? (data.session ? [data.session] : []), report: summary ? 'qa-summary.json' : 'manifest.json' });
    // The original mixed run owns its images; expose its live subgroup only as a reference.
    if (mode === 'legacy') {
      const subgroupFolder = path.join(folder, 'baseline');
      const subgroup = await readJson(path.join(subgroupFolder, 'manifest.json'));
      let subgroupGallery = false;
      try { await fs.access(path.join(subgroupFolder, 'index.html')); subgroupGallery = true; } catch {}
      if (subgroup?.mode === 'live' && Array.isArray(subgroup.captures) && subgroupGallery) {
        runs.push({ folder: path.relative(root, subgroupFolder), title: subgroup.title ?? 'Live Practice 2 · original baseline subgroup', count: subgroup.captures.length, checks: { passed: subgroup.checks?.filter(check => check.status === 'pass').length ?? 0, failed: subgroup.checks?.filter(check => check.status === 'fail').length ?? 0 }, mode: 'live', profiles: [...new Set(subgroup.captures.map(capture => `${capture.profile} ${capture.width} × ${capture.height}`))], startedAt: subgroup.startedAt ?? '', sessions: subgroup.sessions ?? (subgroup.session ? [subgroup.session] : []), report: 'manifest.json', referenceOf: path.relative(root, folder), referenceTitle: title });
      }
    }
    // A run owns its other descendant screenshots and manifests; do not list them twice.
    return;
  }
  const entries = await fs.readdir(folder, { withFileTypes: true });
  for (const entry of entries.filter(entry => entry.isDirectory() && !entry.isSymbolicLink())) await discover(path.join(folder, entry.name), depth + 1, runs);
}
(async () => {
  if (!root.toLowerCase().startsWith('c:' + path.sep + 'gitclone' + path.sep)) throw new Error('Gallery output must stay under C:/GitClone.');
  await fs.mkdir(root, { recursive: true });
  const runs = [];
  await discover(root, 0, runs);
  runs.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  const sections = [{ mode: 'replay', title: 'Replay captures', detail: 'Historical recordings, grouped by session and playback checkpoint. New replay sets exclude the shared Settings screens.' }, { mode: 'live', title: 'Live captures', detail: 'Capture runs from a verified live feed.' }, { mode: 'legacy', title: 'Original mixed baseline', detail: 'The original Practice 2 gallery combines live Practice 2 with historical qualifying and race supplements. It is preserved unchanged.' }];
  const renderRun = run => {
    const url = relativeUrl(run.folder);
    const descriptions = [run.count + ' screenshots', (run.checks.passed ?? 0) + ' checks passed / ' + (run.checks.failed ?? 0) + ' failed', ...run.profiles];
    return `<article><div class="stamp">${escapeHtml(run.startedAt)} · ${escapeHtml(run.mode === 'legacy' ? 'Mixed / legacy' : run.mode)}${run.referenceOf ? ' · Subgroup reference' : ''}</div><h3><a href="${escapeHtml(url)}/">${escapeHtml(run.title)}</a></h3><p>${descriptions.map(escapeHtml).join(' · ')}</p>${run.referenceOf ? `<p class="muted">Reference owned by <a href="${escapeHtml(relativeUrl(run.referenceOf))}/">${escapeHtml(run.referenceTitle)}</a>. These ${run.count} images are already included in the parent count.</p>` : ''}<p>${run.sessions.map(session => escapeHtml([session.kind ?? session.sessionName, session.sessionKey ?? session.key].filter(value => value != null).join(' · '))).join(' / ')}</p><p><a href="${escapeHtml(url)}/">Open labeled gallery</a> · <a href="${escapeHtml(url)}/${run.report}">Capture evidence</a></p></article>`;
  };
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Slipstream session design baselines</title><style>body{margin:0;padding:clamp(16px,4vw,42px);background:#0a1220;color:#eaf2fc;font:15px/1.65 system-ui}main{max-width:1150px;margin:auto}a{color:#78e0dc}h1{font-size:clamp(27px,4vw,43px);line-height:1.15;margin:10px 0 20px}h2{font-size:25px;margin:40px 0 6px}h3{font-size:20px;margin:4px 0 12px}article{background:#101e31;border:1px solid #283c57;border-radius:12px;padding:21px;margin:17px 0}.stamp,.muted{color:#a7b8cd;font-size:13px}code{overflow-wrap:anywhere}.eyebrow{letter-spacing:.13em;font-size:12px;color:#78e0dc;font-weight:700}.empty{border:1px dashed #283c57;padding:20px;color:#a7b8cd}nav{display:flex;gap:18px;flex-wrap:wrap}.top{padding-bottom:20px;border-bottom:1px solid #283c57}footer{margin-top:40px;color:#a7b8cd;font-size:13px}section{scroll-margin-top:20px}</style></head><body><main><div class="top"><span class="eyebrow">SLIPSTREAM · SESSION DESIGN BASELINES</span><h1>Desktop and phone capture library</h1><p>Branch <code>codex/session-design-baselines</code><br>Worktree <code>${escapeHtml(repo)}</code></p><p>${runs.filter(run => !run.referenceOf).reduce((sum, run) => sum + run.count, 0)} screenshots across ${runs.filter(run => !run.referenceOf).length} capture sets${runs.some(run => run.referenceOf) ? ' · ' + runs.filter(run => run.referenceOf).length + ' subgroup reference(s)' : ''}. Images, logs, and recording data remain local to GitClone.</p><nav>${sections.map(section => `<a href="#${section.mode}">${section.title}</a>`).join('')}<a href="http://127.0.0.1:3344/">Running app</a></nav></div>${sections.map(section => { const grouped = runs.filter(run => run.mode === section.mode); return `<section id="${section.mode}"><h2>${section.title}</h2><p class="muted">${section.detail}</p>${grouped.length ? grouped.map(renderRun).join('') : '<p class="empty">No completed gallery in this category yet.</p>'}</section>`; }).join('')}<article><h3>Upcoming live sessions</h3><p>Qualifying: October 3, 3–4 a.m. Chicago, catalog session 11730.<br>Race: October 4, 2–4 a.m. Chicago, catalog session 11731.</p><p>The scheduled follow-up verifies the actual connected live feed before capture. These are app catalog times and identities.</p><p class="muted">Capture runner: <code>tools/session-design/capture-session.ps1</code>. Output stays in this worktree's <code>output/playwright</code>.</p></article><footer><a href="migration-verification.json">Migration verification</a> · <a href="cleanup-report.json">Cleanup report</a><p>The original dated gallery is preserved. New capture runs appear here once their manifest and gallery have been generated.</p></footer></main></body></html>`;
  await fs.writeFile(path.join(root, 'index.html'), html);
  console.log(`Gallery indexed ${runs.length} capture runs under ${root}`);
})().catch(error => { console.error(error); process.exitCode = 1; });

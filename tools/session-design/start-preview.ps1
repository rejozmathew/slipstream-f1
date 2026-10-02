param([string]$DataRoot = 'C:\GitClone\slipstream-f1\recordings')
$ErrorActionPreference = 'Stop'
$previewRepo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not ([IO.Path]::GetFullPath($previewRepo)).StartsWith('C:\GitClone\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Capture worktree must stay under C:\GitClone.' }
$previewRuntime = Join-Path $previewRepo 'output\runtime'
$previewCaptures = Join-Path $previewRepo 'output\playwright'
New-Item -ItemType Directory -Force -Path $previewRuntime,$previewCaptures | Out-Null
$previewDependencies = Join-Path $previewRepo 'web\node_modules'
if (-not (Test-Path -LiteralPath $previewDependencies)) {
  $sharedDependencies = 'C:\GitClone\slipstream-f1\web\node_modules'
  if (-not (Test-Path -LiteralPath $sharedDependencies)) { throw 'Existing web dependencies are missing. Install them before starting preview.' }
  New-Item -ItemType Junction -Path $previewDependencies -Target $sharedDependencies | Out-Null
}
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$nodePath = (Get-Command node -ErrorAction Stop).Source
& $nodePath (Join-Path $PSScriptRoot 'index-captures.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Gallery indexing failed.' }
$previewServices = @{}
$priorPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = Join-Path $previewRepo 'src'
  if (-not (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)) {
    $service = Start-Process -FilePath $pythonPath -ArgumentList @('-m','slipstream','serve',$DataRoot,'--host','127.0.0.1','--port','8000','--catalog-years','3') -WorkingDirectory $previewRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewRuntime 'backend.stdout.log') -RedirectStandardError (Join-Path $previewRuntime 'backend.stderr.log') -PassThru
    $previewServices.backendPid = $service.Id
  }
  if (-not (Get-NetTCPConnection -State Listen -LocalPort 3344 -ErrorAction SilentlyContinue)) {
    $service = Start-Process -FilePath $nodePath -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','3344','--strictPort') -WorkingDirectory (Join-Path $previewRepo 'web') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewRuntime 'frontend.stdout.log') -RedirectStandardError (Join-Path $previewRuntime 'frontend.stderr.log') -PassThru
    $previewServices.frontendPid = $service.Id
  }
  if (-not (Get-NetTCPConnection -State Listen -LocalPort 8766 -ErrorAction SilentlyContinue)) {
    $service = Start-Process -FilePath $pythonPath -ArgumentList @('-m','http.server','8766','--bind','127.0.0.1','--directory',$previewCaptures) -WorkingDirectory $previewRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewRuntime 'gallery.stdout.log') -RedirectStandardError (Join-Path $previewRuntime 'gallery.stderr.log') -PassThru
    $previewServices.galleryPid = $service.Id
  }
} finally { $env:PYTHONPATH = $priorPythonPath }
$previewServices.source = $previewRepo
$previewServices.dataRoot = $DataRoot
$previewServices.startedAt = [DateTimeOffset]::UtcNow.ToString('o')
$previewServices | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $previewRuntime 'server-processes.json')
foreach ($previewUrl in @('http://127.0.0.1:8000/api/v1/catalog','http://127.0.0.1:3344','http://127.0.0.1:8766')) {
  $previewReady = $false
  for ($previewAttempt = 0; $previewAttempt -lt 30; $previewAttempt++) {
    try { if ((Invoke-WebRequest -Uri $previewUrl -TimeoutSec 2).StatusCode -eq 200) { $previewReady = $true; break } } catch {}
    Start-Sleep -Milliseconds 300
  }
  if (-not $previewReady) { throw "Preview service failed: $previewUrl. Inspect $previewRuntime logs." }
  Write-Output "Ready: $previewUrl"
}

param(
  [Parameter(Mandatory = $true)][string]$DataRoot,
  [string]$PythonExecutable = 'python',
  [ValidateRange(0, 20)][int]$CatalogYears = 3
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$web = Join-Path $repo 'web'
$data = (Resolve-Path -LiteralPath $DataRoot).Path
$runtime = Join-Path $repo '.codex-tmp/local-runtime'
$python = (Get-Command $PythonExecutable -ErrorAction Stop).Source
$node = (Get-Command node -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath (Join-Path $web 'node_modules/vite/bin/vite.js'))) {
  throw 'Run npm ci in web before starting the local app.'
}
foreach ($port in @(8000, 3344)) {
  if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    throw "Port $port is occupied. Inspect its process and source directory before stopping it; this launcher never reuses an unknown server."
  }
}
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$branch = & git -C $repo branch --show-current
$commit = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Repository Git metadata is unavailable.' }
$previousPythonPath = $env:PYTHONPATH
$backend = $null
$frontend = $null
try {
  $env:PYTHONPATH = Join-Path $repo 'src'
  $module = & $python -c 'import slipstream; print(slipstream.__file__)'
  if ($LASTEXITCODE -ne 0 -or -not $module.StartsWith((Join-Path $repo 'src'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected Python source: $module"
  }
  $backend = Start-Process -FilePath $python -ArgumentList @('-m', 'slipstream', 'serve', ('"' + $data + '"'), '--host', '127.0.0.1', '--port', '8000', '--catalog-years', $CatalogYears) -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'backend.stdout.log') -RedirectStandardError (Join-Path $runtime 'backend.stderr.log') -PassThru
  $frontend = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '3344', '--strictPort') -WorkingDirectory $web -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'frontend.stdout.log') -RedirectStandardError (Join-Path $runtime 'frontend.stderr.log') -PassThru
} catch {
  if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id }
  throw
} finally { $env:PYTHONPATH = $previousPythonPath }
@{ source = $repo; branch = $branch; commit = $commit; pythonModule = $module; dataRoot = $data; backendPid = $backend.Id; frontendPid = $frontend.Id; startedAt = [DateTimeOffset]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'processes.json')
Write-Output "Started $branch ($commit) from $repo"
Write-Output "App: http://127.0.0.1:3344 | API: http://127.0.0.1:8000 | Logs: $runtime"

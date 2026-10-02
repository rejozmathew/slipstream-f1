param(
  [ValidateSet('live','replay')][string]$Mode = 'live',
  [string]$Session,
  [string]$Label,
  [double]$Fraction = 0.55,
  [string]$Url = 'http://127.0.0.1:3344'
)
$ErrorActionPreference = 'Stop'
$captureCatalog = Invoke-RestMethod -Uri "$Url/api/v1/catalog" -TimeoutSec 15
if (-not $Session) { $Session = $captureCatalog.liveSessionKey }
$captureSession = $captureCatalog.sessions | Where-Object { $_.sessionKey -eq $Session } | Select-Object -First 1
if (-not $captureSession) { throw 'No matching session. Start Slipstream and pass a catalog session key for replay.' }
if (-not $Label) { $Label = "$($captureSession.meetingName)-$($captureSession.sessionName)-$Mode".ToLowerInvariant() -replace '[^a-z0-9]+','-' }
$Label = ($Label.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-')
if (-not $Label) { throw 'The capture label must contain letters or digits.' }
$captureStamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::UtcNow,'Central Standard Time').ToString('yyyy-MM-dd-HHmmss')
$captureRepo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not ([IO.Path]::GetFullPath($captureRepo)).StartsWith('C:\GitClone\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Capture worktree must stay under C:\GitClone.' }
$captureOutput = Join-Path $captureRepo 'output\playwright'
New-Item -ItemType Directory -Force -Path $captureOutput | Out-Null
$captureDestination = Join-Path $captureOutput "$captureStamp-$Label"
$captureCommit = git -C $captureRepo rev-parse HEAD
& node (Join-Path $PSScriptRoot 'capture-all.cjs') --url $Url --mode $Mode --session $Session --label $Label --fraction $Fraction --commit $captureCommit --out $captureDestination
if ($LASTEXITCODE -ne 0) { throw "Capture failed. Inspect $captureDestination\manifest.json" }
& node (Join-Path $PSScriptRoot 'index-captures.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Capture succeeded but gallery indexing failed.' }
Write-Output "Gallery: $captureDestination\index.html"

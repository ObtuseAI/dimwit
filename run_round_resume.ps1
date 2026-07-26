# Resume of run_next_round.ps1 from the packaged step (steps 1-5 already green; step 6 failed on
# the unity-build collision now fixed via bUseUnity=false - first compile is a full recompile).
$ErrorActionPreference = "Continue"
$root = "C:\Users\developer\Documents\Dimwit"
$logs = Join-Path $root "artifacts\next_round_logs"
New-Item -ItemType Directory -Force $logs | Out-Null
Set-Location $root
$summary = @()

function Step($name, $block) {
    $log = Join-Path $logs "$name.log"
    "=== $name started $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content $log
    & $block *>> $log
    $code = $LASTEXITCODE
    "=== $name exit=$code $(Get-Date -Format 'HH:mm:ss') ===" | Add-Content $log
    $script:summary += [pscustomobject]@{ step = $name; exit = $code; log = $log }
    $script:summary | ConvertTo-Json | Set-Content (Join-Path $logs "resume_summary.json")
    Write-Host "[$name] exit=$code"
}

Step "06b_packaged_gameplay_pipeline" { python scripts/pipeline/run_pipeline.py packaged_build_validation wanefall_win64_development timeout_seconds=7200 max_wait_seconds=180 settle_seconds=25 smoke_seconds=2 smoke_fps=4 }
Step "07b_domain_packaged" { python scripts/pipeline/run_validation.py --domain packaged_build --no-ue }
Step "08b_full_suite" { python scripts/pipeline/run_validation.py }
Write-Host "RESUME SEQUENCE COMPLETE"

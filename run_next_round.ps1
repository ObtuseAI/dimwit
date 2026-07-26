# WANEFALL/Dimwit next-round orchestrator (2026-07-01) - runs the queued sequence with per-step
# logs under artifacts\next_round_logs so progress/results are fully inspectable. Fail-fast on the
# build steps; validation gates always run (their red/green IS the result).
$ErrorActionPreference = "Continue"
$root = "C:\Users\developer\Documents\Dimwit"
$logs = Join-Path $root "artifacts\next_round_logs"
New-Item -ItemType Directory -Force $logs | Out-Null
Set-Location $root
$summary = @()

function Step($name, $block, [switch]$FailFast) {
    $log = Join-Path $logs "$name.log"
    "=== $name started $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content $log
    & $block *>> $log
    $code = $LASTEXITCODE
    "=== $name exit=$code $(Get-Date -Format 'HH:mm:ss') ===" | Add-Content $log
    $script:summary += [pscustomobject]@{ step = $name; exit = $code; log = $log }
    $script:summary | ConvertTo-Json | Set-Content (Join-Path $logs "summary.json")
    Write-Host "[$name] exit=$code"
    if ($FailFast -and $code -ne 0) {
        Write-Host "FAIL-FAST at $name - see $log"
        exit 1
    }
}

Step "01_tests_gameplay_motion" { python -m dimwit.tests.test_packaged_gameplay_motion } -FailFast
Step "02_tests_packaged_regression" { python -m dimwit.tests.test_packaged_build_validation } -FailFast
Step "03_tests_identity_regression" { python -m dimwit.tests.test_runtime_process_identity } -FailFast
Step "04_import_zythan_4k_textures" { & "C:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "C:\Users\developer\Documents\Unreal Projects\WanefallGreybox\WanefallGreybox.uproject" -ExecutePythonScript="C:\Users\developer\Documents\Dimwit\scripts\ue\ue_import_zythan_rebaked_textures.py" -stdout -unattended -nosplash } -FailFast
Step "05_domain_rigged_recapture" { python scripts/pipeline/run_validation.py --domain rigged_skeletal_meshes }
Step "06_packaged_gameplay_pipeline" { python scripts/pipeline/run_pipeline.py packaged_build_validation wanefall_win64_development timeout_seconds=7200 max_wait_seconds=180 settle_seconds=25 smoke_seconds=2 smoke_fps=4 }
Step "07_domain_packaged" { python scripts/pipeline/run_validation.py --domain packaged_build --no-ue }
Step "08_full_suite" { python scripts/pipeline/run_validation.py }

Write-Host "NEXT ROUND SEQUENCE COMPLETE - summary at $logs\summary.json"

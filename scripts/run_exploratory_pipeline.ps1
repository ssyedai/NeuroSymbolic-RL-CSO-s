param(
    [ValidateSet("smoke", "full")]
    [string]$Mode = "smoke",
    [int]$Workers = 4,
    [int]$Seed = 0,
    [string]$RunName = "exploratory_v8_smoke_s0"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv-win\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing Python environment: $python"
}
Set-Location -LiteralPath $repo

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PythonArgs)
    & $python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($PythonArgs -join ' ')"
    }
}

$rainSource = "data/useful/rain_real_full"
$onset = "runs/exploratory/onset_table.csv"
$scenarios = "data/useful/exploratory/rain_scenarios"
$splits = "$scenarios/splits.json"
$g2 = "runs/exploratory/controllability_${Mode}_v2.csv"
$theta = "runs/exploratory/theta_$Mode.json"

Write-Warning "EXPLORATORY ONLY: the native hydraulic reference has not passed the fixed step-size gate."
Invoke-Python -m pytest -q

Invoke-Python -m research.onset_parallel `
    --rain-dir $rainSource --events "$rainSource/events.csv" `
    --min-year 2010 --workers $Workers --out $onset --exploratory

Invoke-Python -m research.build_scaled_storms `
    --rain-dir $rainSource --events "$rainSource/events.csv" `
    --onset $onset --atlas configs/atlas14_detroit_city_ams_mm.csv `
    --out $scenarios --val-years 2021,2022 --test-years 2023,2024,2025,2026 `
    --min-year 2010 --ladder-train 5,10,25,50,100 `
    --ladder-test 200,500,1000 --mults 1,1.5,2,3 `
    --flat-factors 2 --exploratory

$g2Args = @(
    "-m", "research.run_controllability",
    "--rain-dir", $scenarios, "--split-manifest", $splits,
    "--out", $g2, "--cache", "runs/exploratory/baseline_cache_$Mode.json",
    "--exploratory"
)
if ($Mode -eq "smoke") {
    $g2Args += @("--max-storms", "12", "--static-n", "8",
                 "--cma-iters", "2", "--cma-pop", "4")
}
Invoke-Python @g2Args

$thetaArgs = @(
    "-m", "research.run_optimize_rules",
    "--rain-dir", $scenarios, "--split-manifest", $splits,
    "--out", $theta, "--cache", "runs/exploratory/baseline_cache_$Mode.json",
    "--seed", "$Seed", "--exploratory"
)
if ($Mode -eq "smoke") {
    $thetaArgs += @("--max-train", "4", "--max-val", "4",
                    "--iters", "2", "--pop", "4", "--patience", "2")
}
Invoke-Python @thetaArgs

$which = "b0,b1,b2"
$thetaResult = Get-Content -LiteralPath $theta -Raw | ConvertFrom-Json
if ($thetaResult.b3_beats_b2_on_val -eq $true) {
    $which = "$which,b3"
}
$baselineArgs = @(
    "-m", "research.run_baselines_eval",
    "--rain-dir", $scenarios, "--split-manifest", $splits,
    "--theta-path", $theta, "--out-dir", "runs/exploratory/baselines_tier1_$Mode",
    "--which", $which, "--splits", "val", "--exploratory"
)
if ($Mode -eq "smoke") {
    $baselineArgs += @("--max-storms", "12")
}
Invoke-Python @baselineArgs

$episodes = if ($Mode -eq "full") { 300 } else { 20 }
$warmup = if ($Mode -eq "full") { 2000 } else { 500 }
$evalEvery = if ($Mode -eq "full") { 25 } else { 10 }
$maxVal = if ($Mode -eq "full") { 0 } else { 6 }
$trainArgs = @(
    "-m", "multistorm.train_multi",
    "--rain-dir", $scenarios, "--split-manifest", $splits,
    "--variant", "v8", "--diet", "D2_ladder100",
    "--physical-rain", "--real-only", "--episodes", "$episodes",
    "--warmup-steps", "$warmup", "--eval-every", "$evalEvery",
    "--updates-per-step", "0.25", "--max-val-eval", "$maxVal",
    "--seed", "$Seed", "--out-dir", "runs/exploratory",
    "--run-name", $RunName, "--controllability-summary", "$g2.summary.json",
    "--exploratory"
)
if ($Mode -eq "smoke") {
    $trainArgs += @("--max-final-val-eval", "6")
}
if ($thetaResult.b3_beats_b2_on_val -eq $true) {
    $trainArgs += @("--theta-path", $theta)
}
Invoke-Python @trainArgs

$evalArgs = @(
    "-m", "multistorm.evaluate_checkpoint",
    "--run", "runs/exploratory/$RunName", "--splits", "val",
    "--repeat-check", "--exploratory"
)
if ($Mode -eq "smoke") {
    $evalArgs += @("--max-storms", "6")
}
Invoke-Python @evalArgs

Write-Host "Exploratory $Mode pipeline complete. No test split was evaluated."
Write-Host "These outputs are pipeline diagnostics, not verified performance evidence."

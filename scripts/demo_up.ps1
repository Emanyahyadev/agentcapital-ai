# One-command demo bring-up (Windows): detached API + Cloudflare tunnel +
# Vercel frontend repointed at the fresh tunnel URL.
#
# Processes start detached (Start-Process), so they survive the terminal
# that launched them. Quick tunnels rotate URLs per session, hence the
# Vercel env refresh on every run.
#
# Usage:  $env:VERCEL_TOKEN = "..." ; powershell -File scripts\demo_up.ps1

param([string]$VercelToken = $env:VERCEL_TOKEN)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = Join-Path $env:TEMP "polaris_tunnel.log"

Write-Host "[1/4] starting API (detached)..."
$apiUp = $false
try {
    $r = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 2
    if ($r.status -eq "ok") { $apiUp = $true; Write-Host "      already running" }
} catch {}
if (-not $apiUp) {
    $uv = (Get-Command uv).Source
    Start-Process -WindowStyle Hidden -WorkingDirectory (Join-Path $root "backend") `
        -FilePath $uv -ArgumentList "run", "uvicorn", "src.api.main:app", "--port", "8000"
    foreach ($i in 1..30) {
        Start-Sleep 1
        try {
            $r = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 2
            if ($r.status -eq "ok") { $apiUp = $true; break }
        } catch {}
    }
}
if (-not $apiUp) { Write-Host "API failed to start"; exit 1 }
Write-Host "      API healthy"

Write-Host "[2/4] opening Cloudflare tunnel (detached)..."
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item $log -Force -ErrorAction SilentlyContinue
Start-Process -WindowStyle Hidden -FilePath $cloudflared `
    -ArgumentList "tunnel", "--url", "http://localhost:8000" `
    -RedirectStandardError $log

$url = $null
foreach ($i in 1..30) {
    Start-Sleep 2
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Matches.Value } |
            Where-Object { $_ -ne "https://api.trycloudflare.com" } |
            Select-Object -First 1
        if ($m) { $url = $m; break }
    }
}
if (-not $url) { Write-Host "tunnel failed - see $log"; exit 1 }
Write-Host "      backend public URL: $url"

Write-Host "[3/4] pointing Vercel frontend at the tunnel..."
Push-Location (Join-Path $root "frontend")
npx -y vercel env rm NEXT_PUBLIC_API_URL production --yes --token $VercelToken | Out-Null
$url | npx -y vercel env add NEXT_PUBLIC_API_URL production --token $VercelToken | Out-Null

Write-Host "[4/4] redeploying frontend..."
npx -y vercel deploy --prod --yes --token $VercelToken | Out-Null
Pop-Location

Write-Host ""
Write-Host "demo ready:"
Write-Host "  dashboard : https://polaris-omega-taupe.vercel.app"
Write-Host "  api       : $url"

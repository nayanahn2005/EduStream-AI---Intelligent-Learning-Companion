# =============================================================================
# EduStream AI — Quick Redeploy Script
# =============================================================================
# Run this every time you make code changes and want to redeploy to AWS.
# Usage: .\redeploy.ps1
# =============================================================================

$region    = "ap-south-1"
$accountId = "686953641284"
$ecrUri    = "$accountId.dkr.ecr.$region.amazonaws.com/edustream-ai"
$serviceArn = "arn:aws:apprunner:ap-south-1:686953641284:service/edustream-ai/d7afc81aa3154c7aad868504d86e5b02"
$appUrl    = "https://tsktirkd27.ap-south-1.awsapprunner.com"
$aws       = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"

Write-Host "`n======================================" -ForegroundColor Magenta
Write-Host "  EduStream AI — Quick Redeploy" -ForegroundColor Magenta
Write-Host "======================================`n" -ForegroundColor Magenta

# --- Step 1: Ensure Docker is running ---
Write-Host "[1/4] Checking Docker..." -ForegroundColor Cyan
$dockerTest = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "     Docker not running. Starting Docker Desktop..." -ForegroundColor Yellow
    Stop-Process -Name "Docker Desktop","com.docker.backend","com.docker.build" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "     Waiting for Docker engine..." -ForegroundColor Gray
    for ($i = 1; $i -le 18; $i++) {
        Start-Sleep -Seconds 10
        if ((docker ps 2>&1 | Out-String) -notmatch "error") { 
            Write-Host "     Docker ready!" -ForegroundColor Green
            break 
        }
        Write-Host "     [$i/18] waiting..." -ForegroundColor Gray
    }
} else {
    Write-Host "     Docker is running." -ForegroundColor Green
}

# --- Step 2: Build ---
Write-Host "`n[2/4] Building Docker image..." -ForegroundColor Cyan
docker build -t "edustream-ai:latest" . 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "     Build complete!" -ForegroundColor Green

# --- Step 3: Push to ECR ---
Write-Host "`n[3/4] Pushing to Amazon ECR..." -ForegroundColor Cyan
& $aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$accountId.dkr.ecr.$region.amazonaws.com" 2>&1 | Out-Null
docker tag "edustream-ai:latest" "${ecrUri}:latest"
docker push "${ecrUri}:latest" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: ECR push failed!" -ForegroundColor Red
    exit 1
}
Write-Host "     Image pushed to ECR!" -ForegroundColor Green

# --- Step 4: Wait for App Runner to redeploy ---
Write-Host "`n[4/4] Waiting for App Runner to redeploy..." -ForegroundColor Cyan
Write-Host "     (App Runner auto-detects the new image and redeploys)" -ForegroundColor Gray
Start-Sleep -Seconds 15

for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 20
    $status = & $aws apprunner describe-service `
        --service-arn $serviceArn `
        --region $region `
        --query "Service.Status" `
        --output text 2>&1
    Write-Host "     [$i/20] Status: $status" -ForegroundColor Gray

    if ($status -eq "RUNNING") {
        Write-Host "`n======================================" -ForegroundColor Green
        Write-Host "  REDEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
        Write-Host "======================================" -ForegroundColor Green
        Write-Host "  Live URL: $appUrl/app" -ForegroundColor Cyan

        # Health check
        try {
            $h = Invoke-RestMethod -Uri "$appUrl/api/capabilities" -TimeoutSec 15
            Write-Host "  Health:   OK (v$($h.version))" -ForegroundColor Green
        } catch {
            Write-Host "  Health:   Warming up, check in 30 seconds" -ForegroundColor Yellow
        }
        Write-Host ""
        break
    }
}

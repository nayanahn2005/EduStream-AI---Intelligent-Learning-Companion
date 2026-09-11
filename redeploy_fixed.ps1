# EduStream AI - Fixed Redeploy Script
$region     = "ap-south-1"
$accountId  = "686953641284"
$ecrUri     = "$accountId.dkr.ecr.$region.amazonaws.com/edustream-ai"
$serviceArn = "arn:aws:apprunner:ap-south-1:686953641284:service/edustream-ai/d7afc81aa3154c7aad868504d86e5b02"
$appUrl     = "https://tsktirkd27.ap-south-1.awsapprunner.com"
$aws        = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"

Write-Host "`n======================================" -ForegroundColor Magenta
Write-Host "  EduStream AI - Quick Redeploy" -ForegroundColor Magenta
Write-Host "======================================`n" -ForegroundColor Magenta

# Step 1: Check Docker
Write-Host "[1/5] Checking Docker..." -ForegroundColor Cyan
$dockerTest = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Docker not running. Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Write-Host "  Waiting 60s for Docker to start..." -ForegroundColor Gray
    Start-Sleep -Seconds 60
    $dockerTest = docker ps 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Docker still not ready. Please start Docker Desktop manually." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  Docker is running." -ForegroundColor Green

# Step 2: Build Docker image
Write-Host "`n[2/5] Building Docker image..." -ForegroundColor Cyan
docker build -t "edustream-ai:latest" "E:\Edu_Stream_AI"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Docker build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  Build complete!" -ForegroundColor Green

# Step 3: Login to ECR
Write-Host "`n[3/5] Logging in to Amazon ECR..." -ForegroundColor Cyan
& $aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$accountId.dkr.ecr.$region.amazonaws.com" 2>&1 | Out-Null
Write-Host "  ECR login done." -ForegroundColor Green

# Step 4: Tag and Push
Write-Host "`n[4/5] Pushing image to ECR..." -ForegroundColor Cyan
docker tag "edustream-ai:latest" "${ecrUri}:latest"
docker push "${ecrUri}:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: ECR push failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  Image pushed successfully!" -ForegroundColor Green

# Step 5: Trigger redeploy
Write-Host "`n[5/5] Triggering App Runner redeployment..." -ForegroundColor Cyan
& $aws apprunner start-deployment --service-arn $serviceArn --region $region | Out-Null
Write-Host "  Redeployment triggered!" -ForegroundColor Green

Write-Host "`n======================================" -ForegroundColor Green
Write-Host "  REDEPLOY INITIATED!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Live URL: $appUrl/app" -ForegroundColor Cyan
Write-Host "  App Runner will update in ~3-5 minutes." -ForegroundColor Gray
Write-Host "  Check health: $appUrl/api/health`n" -ForegroundColor Gray

# Wait and poll for completion
Write-Host "Polling App Runner status..." -ForegroundColor Yellow
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 20
    $status = & $aws apprunner describe-service `
        --service-arn $serviceArn `
        --region $region `
        --query "Service.Status" `
        --output text 2>&1
    Write-Host "  [$i/20] Status: $status" -ForegroundColor Gray
    if ($status -eq "RUNNING") {
        Write-Host "`n  DEPLOYMENT COMPLETE!" -ForegroundColor Green
        Write-Host "  Live at: $appUrl/app" -ForegroundColor Cyan
        break
    }
}

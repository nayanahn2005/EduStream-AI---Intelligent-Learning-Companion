# =============================================================================
# EduStream AI — AWS Deployment Script (PowerShell)
# =============================================================================
# Run this script after installing and configuring the AWS CLI.
# Usage: .\deploy-aws.ps1
#
# Prerequisites:
#   1. AWS CLI v2 installed and configured (aws configure)
#   2. Docker Desktop running
#   3. Your GROQ_API_KEYS ready
# =============================================================================

param(
    [string]$Region = "ap-south-1",
    [string]$AppName = "edustream-ai",
    [string]$EcrRepoName = "edustream-ai",
    [string]$GroqApiKeys = ""  # Pass as: .\deploy-aws.ps1 -GroqApiKeys "key1,key2"
)

# --- Colors for output ---
function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Success($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

Write-Host "`n========================================" -ForegroundColor Magenta
Write-Host "  EduStream AI — AWS Deployment Script" -ForegroundColor Magenta
Write-Host "========================================`n" -ForegroundColor Magenta

# --- Step 1: Validate prerequisites ---
Write-Step "Validating prerequisites..."

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Fail "AWS CLI not found. Please install it first: https://awscli.amazonaws.com/AWSCLIV2.msi"
}
Write-Success "AWS CLI found: $(aws --version)"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker not found. Please install Docker Desktop."
}

$dockerStatus = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker is not running. Please start Docker Desktop."
}
Write-Success "Docker is running."

# --- Step 2: Get AWS Account ID ---
Write-Step "Fetching AWS account information..."
$AccountId = aws sts get-caller-identity --query Account --output text --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Fail "AWS CLI not configured. Please run: aws configure"
}
Write-Success "AWS Account ID: $AccountId | Region: $Region"

# --- Step 3: Create ECR Repository ---
Write-Step "Creating ECR repository: $EcrRepoName..."
$EcrUri = aws ecr describe-repositories --repository-names $EcrRepoName --region $Region --query "repositories[0].repositoryUri" --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Repository does not exist, creating it..." -ForegroundColor Yellow
    $EcrUri = aws ecr create-repository `
        --repository-name $EcrRepoName `
        --region $Region `
        --image-scanning-configuration scanOnPush=true `
        --query "repository.repositoryUri" `
        --output text
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create ECR repository." }
    Write-Success "ECR repository created: $EcrUri"
} else {
    Write-Success "ECR repository already exists: $EcrUri"
}

$ImageTag = "latest"
$FullImageUri = "${EcrUri}:${ImageTag}"

# --- Step 4: Build Docker image ---
Write-Step "Building Docker image (this may take a few minutes)..."
docker build -t "${EcrRepoName}:${ImageTag}" .
if ($LASTEXITCODE -ne 0) { Write-Fail "Docker build failed." }
Write-Success "Docker image built successfully."

# --- Step 5: Authenticate Docker to ECR ---
Write-Step "Authenticating Docker to Amazon ECR..."
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "${AccountId}.dkr.ecr.${Region}.amazonaws.com"
if ($LASTEXITCODE -ne 0) { Write-Fail "ECR authentication failed." }
Write-Success "Docker authenticated to ECR."

# --- Step 6: Tag and push image ---
Write-Step "Tagging and pushing image to ECR..."
docker tag "${EcrRepoName}:${ImageTag}" $FullImageUri
docker push $FullImageUri
if ($LASTEXITCODE -ne 0) { Write-Fail "Docker push failed." }
Write-Success "Image pushed to ECR: $FullImageUri"

# --- Step 7: Create IAM Role for App Runner ---
Write-Step "Setting up IAM role for App Runner ECR access..."
$RoleName = "AppRunnerECRAccessRole"
$RoleArn = aws iam get-role --role-name $RoleName --query "Role.Arn" --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating IAM role: $RoleName..." -ForegroundColor Yellow
    $TrustPolicy = @'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "build.apprunner.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
'@
    $TrustPolicyFile = "$env:TEMP\apprunner-trust-policy.json"
    $TrustPolicy | Out-File -FilePath $TrustPolicyFile -Encoding utf8

    $RoleArn = aws iam create-role `
        --role-name $RoleName `
        --assume-role-policy-document "file://$TrustPolicyFile" `
        --description "Allows App Runner to pull images from ECR" `
        --query "Role.Arn" `
        --output text

    aws iam attach-role-policy `
        --role-name $RoleName `
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"

    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create IAM role." }
    Write-Success "IAM role created: $RoleArn"
    Start-Sleep -Seconds 10  # Wait for IAM propagation
} else {
    Write-Success "IAM role already exists: $RoleArn"
}

# --- Step 8: Prompt for Groq API Keys if not provided ---
if (-not $GroqApiKeys) {
    Write-Step "Groq API Keys Setup"
    Write-Host "Enter your Groq API keys (comma-separated for multiple keys):" -ForegroundColor Yellow
    Write-Host "Example: gsk_key1,gsk_key2,gsk_key3" -ForegroundColor Gray
    $GroqApiKeys = Read-Host "GROQ_API_KEYS"
}

# --- Step 9: Create App Runner Service Configuration ---
Write-Step "Creating App Runner service configuration..."
$ServiceConfig = @{
    ServiceName = $AppName
    SourceConfiguration = @{
        AuthenticationConfiguration = @{
            AccessRoleArn = $RoleArn
        }
        AutoDeploymentsEnabled = $true
        ImageRepository = @{
            ImageIdentifier = $FullImageUri
            ImageRepositoryType = "ECR"
            ImageConfiguration = @{
                Port = "8000"
                RuntimeEnvironmentVariables = @{
                    GROQ_API_KEYS = $GroqApiKeys
                    LOG_LEVEL = "info"
                    WORKERS = "1"
                }
            }
        }
    }
    InstanceConfiguration = @{
        Cpu = "0.25 vCPU"
        Memory = "0.5 GB"
    }
    HealthCheckConfiguration = @{
        Protocol = "HTTP"
        Path = "/api/capabilities"
        Interval = 10
        Timeout = 5
        HealthyThreshold = 1
        UnhealthyThreshold = 5
    }
    ObservabilityConfiguration = @{
        ObservabilityEnabled = $true
    }
}

$ConfigJson = $ServiceConfig | ConvertTo-Json -Depth 10
$ConfigFile = "$env:TEMP\apprunner-service.json"
$ConfigJson | Out-File -FilePath $ConfigFile -Encoding utf8

Write-Host "Deploying to AWS App Runner in $Region..." -ForegroundColor Yellow
Write-Host "This will take 5-8 minutes. Please wait..." -ForegroundColor Gray

# Check if service already exists
$ExistingService = aws apprunner list-services --region $Region --query "ServiceSummaryList[?ServiceName=='$AppName'].ServiceArn" --output text 2>$null
if ($ExistingService) {
    Write-Warn "Service '$AppName' already exists. Updating..."
    # Trigger a new deployment
    aws apprunner start-deployment `
        --service-arn $ExistingService `
        --region $Region | Out-Null
    Write-Success "Deployment triggered for existing service."
    $ServiceArn = $ExistingService
} else {
    # Create new service
    $CreateResult = aws apprunner create-service `
        --cli-input-json "file://$ConfigFile" `
        --region $Region `
        --output json | ConvertFrom-Json

    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create App Runner service." }
    $ServiceArn = $CreateResult.Service.ServiceArn
    Write-Success "App Runner service creation initiated!"
}

# --- Step 10: Wait for deployment ---
Write-Step "Waiting for deployment to complete..."
$MaxWait = 20  # 20 * 30s = 10 minutes max
$Waited = 0
do {
    Start-Sleep -Seconds 30
    $Waited++
    $Status = aws apprunner describe-service `
        --service-arn $ServiceArn `
        --region $Region `
        --query "Service.Status" `
        --output text
    $ServiceUrl = aws apprunner describe-service `
        --service-arn $ServiceArn `
        --region $Region `
        --query "Service.ServiceUrl" `
        --output text
    Write-Host "  Status: $Status (${Waited}/${MaxWait} checks)" -ForegroundColor Gray
} while ($Status -eq "OPERATION_IN_PROGRESS" -and $Waited -lt $MaxWait)

if ($Status -eq "RUNNING") {
    $AppUrl = "https://$ServiceUrl"
    Write-Host "`n" -NoNewline
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "`n  App URL:      $AppUrl" -ForegroundColor Cyan
    Write-Host "  Health Check: $AppUrl/api/capabilities" -ForegroundColor Cyan
    Write-Host "  Frontend:     $AppUrl/app" -ForegroundColor Cyan
    Write-Host "  ECR Image:    $FullImageUri" -ForegroundColor Cyan
    Write-Host "  Region:       $Region" -ForegroundColor Cyan
    Write-Host "`n  CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home?region=$Region#logsV2:log-groups" -ForegroundColor Gray
    Write-Host ""

    # --- Step 11: Verify deployment ---
    Write-Step "Running health check..."
    Start-Sleep -Seconds 5
    try {
        $Health = Invoke-RestMethod -Uri "$AppUrl/api/capabilities" -Method Get -TimeoutSec 30
        Write-Success "Health check passed! Response:"
        $Health | ConvertTo-Json | Write-Host -ForegroundColor Gray
    } catch {
        Write-Warn "Health check request failed (app may still be starting): $_"
        Write-Host "Manually verify: $AppUrl/api/capabilities" -ForegroundColor Yellow
    }
} else {
    Write-Warn "Deployment status: $Status"
    Write-Host "Check the AWS App Runner console for details:" -ForegroundColor Yellow
    Write-Host "https://ap-south-1.console.aws.amazon.com/apprunner/home?region=$Region" -ForegroundColor Cyan
}

Write-Host "`nDeployment script completed.`n" -ForegroundColor Magenta

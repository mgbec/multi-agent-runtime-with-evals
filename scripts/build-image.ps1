# ============================================================================
# Build and Verify Docker Image for AgentCore Runtime
# ============================================================================
# This script is called by Terraform during deployment to:
# 1. Trigger CodeBuild to build the Docker image
# 2. Wait for the build to complete
# 3. Verify the image was successfully pushed to ECR
#
# Parameters:
#   $1 - CodeBuild project name
#   $2 - AWS region
#   $3 - ECR repository name
#   $4 - Image tag
#   $5 - ECR repository URL

param(
    [Parameter(Mandatory=$true)][string]$ProjectName,
    [Parameter(Mandatory=$true)][string]$Region,
    [Parameter(Mandatory=$true)][string]$RepoName,
    [Parameter(Mandatory=$true)][string]$ImageTag,
    [Parameter(Mandatory=$true)][string]$RepoUrl
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Print functions
# ============================================================================

function Print-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Blue }
function Print-Success($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Print-Warning($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Print-Error($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Print-Header($msg) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host $msg -ForegroundColor Blue
    Write-Host "============================================" -ForegroundColor Blue
}

# ============================================================================
# Start Build Process
# ============================================================================

Print-Header "Building Docker Image for AgentCore Runtime"

Print-Info "CodeBuild Project: $ProjectName"
Print-Info "Region: $Region"
Print-Info "Target Image: ${RepoUrl}:${ImageTag}"
Write-Host ""

# Start CodeBuild
Print-Info "Starting CodeBuild project..."

try {
    $BuildId = aws codebuild start-build `
        --project-name $ProjectName `
        --region $Region `
        --query 'build.id' `
        --output text
    if ($LASTEXITCODE -ne 0) { throw "Failed to start CodeBuild" }
} catch {
    Print-Error "Failed to start CodeBuild: $_"
    exit 1
}

Print-Success "Build started: $BuildId"
Print-Info "Waiting for build to complete (typically 5-10 minutes)..."
Write-Host ""

# ============================================================================
# Monitor Build Progress
# ============================================================================

$Attempt = 0
$MaxAttempts = 60  # 10 minutes (60 * 10s)

while ($Attempt -lt $MaxAttempts) {
    $Attempt++

    $Status = aws codebuild batch-get-builds `
        --ids $BuildId `
        --region $Region `
        --query 'builds[0].buildStatus' `
        --output text 2>$null

    if ($Status -ne "IN_PROGRESS") {
        Print-Info "Build process completed with status: $Status"
        break
    }

    # Progress indicator
    if ($Attempt % 6 -eq 0) {
        $Minutes = [math]::Floor($Attempt / 6)
        Print-Info "Build in progress... ($Minutes minutes elapsed)"
    }

    Start-Sleep -Seconds 10
}

if ($Attempt -eq $MaxAttempts) {
    Print-Error "Build timeout after 10 minutes"
    Print-Warning "Check build status at: https://console.aws.amazon.com/codesuite/codebuild/projects/$ProjectName/history?region=$Region"
    exit 1
}

if ($Status -ne "SUCCEEDED") {
    Print-Error "Build failed with status: $Status"
    Print-Warning "Check build logs at: https://console.aws.amazon.com/codesuite/codebuild/projects/$ProjectName/history?region=$Region"
    exit 1
}

Write-Host ""

# ============================================================================
# Verify Image in ECR
# ============================================================================

Print-Header "Verifying Docker Image in ECR"

Print-Info "Checking for image: ${RepoName}:${ImageTag}"
Print-Info "Waiting for ECR propagation..."
Write-Host ""

Start-Sleep -Seconds 5

$VerifyAttempt = 0
$MaxVerifyAttempts = 12  # 1 minute (12 * 5s)

while ($VerifyAttempt -lt $MaxVerifyAttempts) {
    $VerifyAttempt++

    $result = aws ecr describe-images `
        --repository-name $RepoName `
        --image-ids imageTag=$ImageTag `
        --region $Region 2>$null

    if ($LASTEXITCODE -eq 0) {
        Print-Success "Docker image successfully verified in ECR!"
        Write-Host ""
        Print-Info "Image URI: ${RepoUrl}:${ImageTag}"

        try {
            $ImageSize = aws ecr describe-images `
                --repository-name $RepoName `
                --image-ids imageTag=$ImageTag `
                --region $Region `
                --query 'imageDetails[0].imageSizeInBytes' `
                --output text 2>$null

            if ($ImageSize -and $ImageSize -ne "None") {
                $ImageSizeMB = [math]::Floor([long]$ImageSize / 1024 / 1024)
                Print-Info "Image Size: ${ImageSizeMB} MB"
            }
        } catch {}

        Write-Host ""
        Print-Success "Build and verification completed successfully!"
        exit 0
    }

    if ($VerifyAttempt % 3 -eq 0) {
        Print-Info "Still waiting for image to appear in ECR... (attempt $VerifyAttempt/$MaxVerifyAttempts)"
    }

    Start-Sleep -Seconds 5
}

# ============================================================================
# Error: Image Not Found
# ============================================================================

Print-Error "Docker image not found in ECR after build completion"
Write-Host ""
Print-Warning "This indicates the build or push step failed."
Print-Info "Troubleshooting steps:"
Print-Info "  1. Check CodeBuild logs:"
Print-Info "     https://console.aws.amazon.com/codesuite/codebuild/projects/$ProjectName/history?region=$Region"
Print-Info ""
Print-Info "  2. Verify ECR repository:"
Print-Info "     aws ecr describe-images --repository-name $RepoName --region $Region"
Print-Info ""
Print-Info "  3. Check IAM permissions for CodeBuild role"

exit 1

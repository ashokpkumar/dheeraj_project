# build-and-deploy-ui.ps1
# PowerShell version of build-and-deploy-ui.bat
# Build and deploy React UI container

param(
    [string]$Command = "build"
)

$UIPath = "..\..\UI\my-react-flow-app"
$ImageName = "automation:ui"
$ContainerName = "automation_ui"
$Port = 3000

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "   React UI Build & Deploy" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

# Check if Docker is running
try {
    docker ps > $null 2>&1
} catch {
    Write-Host "ERROR: Docker is not running" -ForegroundColor Red
    exit 1
}

# Check if UI directory exists
if (-not (Test-Path $UIPath)) {
    Write-Host "ERROR: UI directory not found: $UIPath" -ForegroundColor Red
    Write-Host "Please ensure you are in the backend/automation directory`n" -ForegroundColor Yellow
    exit 1
}

Write-Host "UI Path: $UIPath" -ForegroundColor Cyan
Write-Host "Image: $ImageName"
Write-Host "Container: $ContainerName`n"

switch ($Command) {
    "build" {
        Write-Host "Building React UI image..." -ForegroundColor Yellow
        Write-Host "Command: docker build -t $ImageName $UIPath`n"
        docker build -t $ImageName $UIPath
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`nBuild completed successfully" -ForegroundColor Green
            Write-Host "`nNext steps:"
            Write-Host "  Run container: .\build-and-deploy-ui.ps1 run"
            Write-Host "  View logs:     .\build-and-deploy-ui.ps1 logs`n"
        } else {
            Write-Host "ERROR: Build failed" -ForegroundColor Red
            exit 1
        }
    }
    
    "run" {
        Write-Host "Building React UI image..." -ForegroundColor Yellow
        docker build -t $ImageName $UIPath
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Build failed" -ForegroundColor Red
            exit 1
        }
        
        Write-Host "`nImage built successfully, starting container...`n" -ForegroundColor Green
        
        # Check if container exists
        $existing = docker ps -a --format "{{.Names}}" 2>$null | Select-String "^$ContainerName$"
        if ($existing) {
            Write-Host "Stopping and removing existing container: $ContainerName"
            docker stop $ContainerName > $null 2>&1
            docker rm $ContainerName > $null 2>&1
        }
        
        Write-Host "`nStarting React UI container..." -ForegroundColor Yellow
        docker run -d --name $ContainerName -p "${Port}:3000" --network automation_network $ImageName
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n========================================" -ForegroundColor Green
            Write-Host "   React UI Started" -ForegroundColor Green
            Write-Host "========================================`n" -ForegroundColor Green
            Write-Host "Container: $ContainerName"
            Write-Host "Image: $ImageName"
            Write-Host "Port: $Port"
            Write-Host "URL: http://localhost:$Port`n" -ForegroundColor Cyan
            Write-Host "View logs: docker logs -f $ContainerName"
            Write-Host "Stop:      docker stop $ContainerName`n"
        } else {
            Write-Host "ERROR: Failed to start container" -ForegroundColor Red
            exit 1
        }
    }
    
    "stop" {
        Write-Host "Stopping container: $ContainerName..." -ForegroundColor Yellow
        docker stop $ContainerName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Container stopped" -ForegroundColor Green
        } else {
            Write-Host "ERROR: Failed to stop container" -ForegroundColor Red
        }
    }
    
    "start" {
        Write-Host "Starting container: $ContainerName..." -ForegroundColor Yellow
        docker start $ContainerName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Container started" -ForegroundColor Green
            Write-Host "URL: http://localhost:$Port`n" -ForegroundColor Cyan
        } else {
            Write-Host "ERROR: Failed to start container" -ForegroundColor Red
        }
    }
    
    "restart" {
        Write-Host "Restarting container: $ContainerName..." -ForegroundColor Yellow
        docker restart $ContainerName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Container restarted" -ForegroundColor Green
            Write-Host "URL: http://localhost:$Port`n" -ForegroundColor Cyan
        } else {
            Write-Host "ERROR: Failed to restart container" -ForegroundColor Red
        }
    }
    
    "logs" {
        Write-Host "`nViewing logs for: $ContainerName" -ForegroundColor Cyan
        Write-Host "(Press Ctrl+C to stop)`n"
        docker logs -f $ContainerName
    }
    
    "shell" {
        Write-Host "Opening shell in: $ContainerName..." -ForegroundColor Yellow
        docker exec -it $ContainerName /bin/bash
    }
    
    "remove" {
        Write-Host "WARNING: This will remove the container" -ForegroundColor Yellow
        $existing = docker ps -a --format "{{.Names}}" 2>$null | Select-String "^$ContainerName$"
        if ($existing) {
            Write-Host "Removing container: $ContainerName..." -ForegroundColor Cyan
            docker rm $ContainerName
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Container removed" -ForegroundColor Green
            } else {
                Write-Host "ERROR: Failed to remove container" -ForegroundColor Red
            }
        } else {
            Write-Host "Container not found" -ForegroundColor Yellow
        }
    }
    
    "help" {
        Write-Host "Usage: .\build-and-deploy-ui.ps1 [command]`n" -ForegroundColor Cyan
        Write-Host "Commands:" -ForegroundColor Yellow
        Write-Host "  build              - Build React UI image only (default)"
        Write-Host "  run                - Build and run UI container"
        Write-Host "  stop               - Stop running UI container"
        Write-Host "  start              - Start stopped UI container"
        Write-Host "  restart            - Restart UI container"
        Write-Host "  logs               - View container logs"
        Write-Host "  shell              - Open shell in running container"
        Write-Host "  remove             - Remove UI container"
        Write-Host "  help               - Show this help message`n"
        
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\build-and-deploy-ui.ps1 build"
        Write-Host "  .\build-and-deploy-ui.ps1 run"
        Write-Host "  .\build-and-deploy-ui.ps1 logs`n"
    }
    
    default {
        Write-Host "ERROR: Unknown command: $Command" -ForegroundColor Red
        Write-Host "Run '.\build-and-deploy-ui.ps1 help' for usage`n"
        exit 1
    }
}

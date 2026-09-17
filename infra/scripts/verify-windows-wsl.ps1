Write-Host "========================================"
Write-Host " OrderNexa AI - Windows / WSL Check"
Write-Host "========================================"
Write-Host ""
Write-Host "[WSL version]"
wsl --version
Write-Host ""
Write-Host "[WSL status]"
wsl --status
Write-Host ""
Write-Host "[Installed distributions]"
wsl -l -v
Write-Host ""
Write-Host "Recommended:"
Write-Host "- WSL 2"
Write-Host "- Ubuntu 24.04 LTS is fully acceptable; do not upgrade solely for this project."
Write-Host "- Docker Desktop using WSL 2 backend"
Write-Host "- Docker Desktop WSL integration enabled for the Ubuntu distro"

# secret-scan.ps1 - reemplazo MANUAL del workflow "Secret Scan" (GitHub Actions deshabilitado).
# Corre gitleaks sobre todo el repo (fetch-depth completo no hace falta en local: ya tenes el git).
$ErrorActionPreference = "Stop"

if (Get-Command gitleaks -ErrorAction SilentlyContinue) {
    Write-Host "gitleaks (local)"
    gitleaks detect --source . --redact --verbose
    exit $LASTEXITCODE
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "gitleaks (docker)"
    docker run --rm -v "${PWD}:/repo" zricethezav/gitleaks:latest detect --source /repo --redact --verbose
    exit $LASTEXITCODE
}

Write-Warning "gitleaks no instalado. Instalalo (https://github.com/gitleaks/gitleaks#installing) o usá Docker."
exit 2
# Installs only the accounting app from this extracted development-branch ZIP.
# Preserves local accounting migrations, test settings and PostgreSQL data.
# Run from the extracted ZIP: powershell -ExecutionPolicy Bypass -File .\scripts\install_accounting_test.ps1
$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$source = Join-Path $sourceRoot "accounting"
$targetRoot = "C:\pforbes_books_accounting_test"
$target = Join-Path $targetRoot "accounting"
$python = Join-Path $targetRoot ".venv\Scripts\python.exe"
$settings = Join-Path $targetRoot "config\settings_accounting_test.py"

if (!(Test-Path (Join-Path $source "test_end_to_end.py"))) {
    throw "This ZIP does not contain the integrated accounting core. Download the latest feature/accounting-foundation ZIP."
}
if (!(Test-Path $target) -or !(Test-Path $python) -or !(Test-Path $settings)) {
    throw "The local accounting test installation is not at the expected path. No files were changed."
}
if ($sourceRoot -eq $targetRoot) {
    throw "Do not run the installer from inside the live local test project."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $env:LOCALAPPDATA "PforbesBooksAccountingBackups\$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Write-Host "Backing up accounting folder to: $backupDir"
Copy-Item -LiteralPath $target -Destination (Join-Path $backupDir "accounting") -Recurse -Force

# Moving accidental duplicate package directories out of Python discovery fixes
# the 7 import errors caused by nested copies or a root package marker.
$nested = Join-Path $target "accounting"
if (Test-Path $nested) {
    Write-Host "Quarantining unexpected nested accounting folder to backup."
    Move-Item -LiteralPath $nested -Destination (Join-Path $backupDir "nested_accounting")
}
$rootInit = Join-Path $targetRoot "__init__.py"
if (Test-Path $rootInit) {
    Write-Host "Quarantining unexpected project-root __init__.py to backup."
    Move-Item -LiteralPath $rootInit -Destination (Join-Path $backupDir "project_root_init.py")
}

Write-Host "Installing complete accounting app while preserving local migrations."
Get-ChildItem -LiteralPath $source -Force | Where-Object { $_.Name -notin @("migrations", "__pycache__") } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
}

Push-Location $targetRoot
try {
    Write-Host "Running accounting tests using the existing local settings..."
    & $python manage.py test accounting --settings=config.settings_accounting_test
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) {
    Write-Warning "Accounting tests did not pass. Your previous accounting folder is backed up at $backupDir. Do not deploy."
    exit $code
}
Write-Host "Accounting core tests passed. Backup retained at $backupDir"

# Installs the accounting and contacts/receipts apps from this extracted test ZIP.
# Preserves local accounting migrations, test settings and PostgreSQL data.
# Run from the extracted ZIP: powershell -ExecutionPolicy Bypass -File .\scripts\install_accounting_test.ps1
$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$source = Join-Path $sourceRoot "accounting"
$contactSource = Join-Path $sourceRoot "accounting_contacts"
$targetRoot = "C:\pforbes_books_accounting_test"
$target = Join-Path $targetRoot "accounting"
$contactTarget = Join-Path $targetRoot "accounting_contacts"
$python = Join-Path $targetRoot ".venv\Scripts\python.exe"
$liveSettings = Join-Path $targetRoot "config\settings.py"
$testSettings = Join-Path $targetRoot "config\settings_accounting_test.py"

if (!(Test-Path (Join-Path $source "test_end_to_end.py"))) {
    throw "This ZIP does not contain the integrated accounting core. Download the latest feature/accounting-foundation ZIP."
}
if (!(Test-Path $target) -or !(Test-Path $python) -or !(Test-Path $liveSettings) -or !(Test-Path $testSettings)) {
    throw "The local accounting test installation is not at the expected path. No files were changed."
}
if (!(Test-Path (Join-Path $contactSource "migrations\0001_initial.py"))) {
    throw "Contacts package or its migration is missing from this ZIP; no files were changed."
}
if ($sourceRoot -eq $targetRoot) {
    throw "Do not run the installer from inside the live local test project."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $env:LOCALAPPDATA "PforbesBooksAccountingBackups\$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Write-Host "Backing up accounting folder to: $backupDir"
Copy-Item -LiteralPath $target -Destination (Join-Path $backupDir "accounting") -Recurse -Force
Copy-Item -LiteralPath $liveSettings -Destination (Join-Path $backupDir "settings.py") -Force
Copy-Item -LiteralPath $testSettings -Destination (Join-Path $backupDir "settings_accounting_test.py") -Force
if (Test-Path $contactTarget) {
    Copy-Item -LiteralPath $contactTarget -Destination (Join-Path $backupDir "accounting_contacts") -Recurse -Force
}
Write-Host "Backing up current PostgreSQL accounting records as JSON (separate from the database)..."
Push-Location $targetRoot
try {
    & $python manage.py dumpdata accounting --settings=config.settings --indent 2 --output (Join-Path $backupDir "accounting_data.json")
    if ($LASTEXITCODE -ne 0) { throw "Cannot back up PostgreSQL accounting data. No code was updated." }
    $backupFile = Join-Path $backupDir "accounting_data.json"
    if (!(Test-Path $backupFile) -or (Get-Item -LiteralPath $backupFile).Length -lt 10) { throw "PostgreSQL accounting backup is missing or empty; no code was updated." }
    if (Test-Path $contactTarget) {
        $settingsTextBefore = Get-Content -LiteralPath $liveSettings -Raw
        if ($settingsTextBefore -match "accounting_contacts[.]apps[.]AccountingContactsConfig") {
            & $python manage.py dumpdata accounting_contacts --settings=config.settings --indent 2 --output (Join-Path $backupDir "contacts_and_receipts_data.json")
            if ($LASTEXITCODE -ne 0) { throw "Cannot back up existing contacts and receipts. No code was updated." }
        }
    }
} finally {
    Pop-Location
}

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

Write-Host "Installing vendor, customer, and receipt modules."
if (!(Test-Path $contactTarget)) { New-Item -ItemType Directory -Path $contactTarget | Out-Null }
Get-ChildItem -LiteralPath $contactSource -Force | Where-Object { $_.Name -ne "__pycache__" } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $contactTarget -Recurse -Force
}
# A project-level templates/ directory takes precedence over templates shipped
# inside Django apps. Older local copies caused the guided-income form to fail
# even though the new template was installed. Quarantine ONLY exact conflicting
# accounting and contact template paths, preserving every original in the backup.
$shadowRoot = Join-Path $targetRoot "templates"
$shadowBackupRoot = Join-Path $backupDir "overridden_root_templates"
foreach ($templateSource in @(
    (Join-Path $source "templates"),
    (Join-Path $contactSource "templates")
)) {
    if (!(Test-Path $templateSource)) { continue }
    Get-ChildItem -LiteralPath $templateSource -Recurse -File -Filter "*.html" | ForEach-Object {
        $relative = $_.FullName.Substring($templateSource.Length).TrimStart('\')
        $rootCopy = Join-Path $shadowRoot $relative
        if (Test-Path -LiteralPath $rootCopy -PathType Leaf) {
            $backupCopy = Join-Path $shadowBackupRoot $relative
            $backupParent = Split-Path -Parent $backupCopy
            if (!(Test-Path $backupParent)) {
                New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
            }
            Write-Host "Backing up overriding template: $relative"
            Move-Item -LiteralPath $rootCopy -Destination $backupCopy -Force
        }
    }
}
# The local test settings import all values from config.settings.
# Register the new app ONLY in settings.py or Django sees duplicate labels.
$settingsText = Get-Content -LiteralPath $liveSettings -Raw
if ($settingsText -notmatch "accounting_contacts[.]apps[.]AccountingContactsConfig") {
    Add-Content -LiteralPath $liveSettings -Encoding UTF8 -Value "`r`n# Contacts and receipts for the local accounting test app`r`nINSTALLED_APPS = [*INSTALLED_APPS, 'accounting_contacts.apps.AccountingContactsConfig']`r`n"
}
# Clean up the old installer mistake, if its extra registration remains
# in settings_accounting_test.py and this file inherits from settings.py.
$testText = Get-Content -LiteralPath $testSettings -Raw
if ($testText -match '(?m)^from \.settings import \*' -and
    $testText -match "accounting_contacts[.]apps[.]AccountingContactsConfig") {
    $duplicate = "INSTALLED_APPS = [*INSTALLED_APPS, 'accounting_contacts.apps.AccountingContactsConfig']"
    if ($testText.Contains($duplicate)) {
        $testText = $testText.Replace($duplicate, "")
        [System.IO.File]::WriteAllText($testSettings, $testText, (New-Object System.Text.UTF8Encoding($false)))
    }
}
Push-Location $targetRoot
try {
    Write-Host "Checking contact migration against the models..."
    & $python manage.py makemigrations accounting_contacts --check --dry-run --settings=config.settings
    if ($LASTEXITCODE -ne 0) { throw "Migration check failed. Do not apply changes or deploy." }
    # Account normal balance is an additive column. The local accounting migrations
    # are deliberately preserved across ZIP installs, so generate its migration
    # against the existing local chain rather than overwriting that history.
    Write-Host "Creating the additive accounting migration for Normal Balance if needed..."
    & $python manage.py makemigrations accounting --noinput --settings=config.settings
    if ($LASTEXITCODE -ne 0) { throw "Accounting migration generation failed. Do not deploy." }
    Write-Host "Applying accounting schema changes to local PostgreSQL..."
    & $python manage.py migrate accounting --noinput --settings=config.settings
    if ($LASTEXITCODE -ne 0) { throw "Accounting migration failed. Restore using installer backup; do not deploy." }
    Write-Host "Creating only the new contacts and receipts tables in local PostgreSQL..."
    & $python manage.py migrate accounting_contacts --noinput --settings=config.settings
    if ($LASTEXITCODE -ne 0) { throw "Contacts migration failed. Do not deploy." }
    Write-Host "Running both accounting and contacts tests..."

    & $python manage.py test accounting accounting_contacts --settings=config.settings_accounting_test
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) {
    Write-Warning "Accounting tests did not pass. Your previous accounting folder is backed up at $backupDir. Do not deploy."
    exit $code
}
# Apply the explicitly approved Sales Income layout only AFTER all automated tests pass.
# The organizer is transactional, checks for unexpected name/number conflicts,
# preserves existing account PKs and journal links, and is safe to rerun.
Write-Host "Organizing Sales Income accounts 4010-4015 (no other account categories)..."
Push-Location $targetRoot
try {
    & $python manage.py shell --settings=config.settings -c "from accounting.sales_setup import organize_sales_income; print(organize_sales_income())"
    if ($LASTEXITCODE -ne 0) {
        throw "Sales account validation or update failed. No partial sales reorganization was committed. Backup: $backupDir"
    }
} finally {
    Pop-Location
}
Write-Host "Combined accounting and contacts tests passed. PostgreSQL backup retained at $backupDir"

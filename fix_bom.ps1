# Fix BOM (Byte Order Mark) in all Python and text files
# Run this in PowerShell from your project root

Write-Host "Scanning for files with BOM..." -ForegroundColor Yellow

$bomFiles = @()

# Scan all Python and text files
Get-ChildItem -Path . -Recurse -Include *.py,*.txt,*.md | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
    
    # Check for UTF-8 BOM (EF BB BF)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $bomFiles += $_.FullName
        Write-Host "Found BOM in: $($_.FullName)" -ForegroundColor Red
    }
}

if ($bomFiles.Count -eq 0) {
    Write-Host "`nNo BOM found! All files are clean." -ForegroundColor Green
    exit
}

Write-Host "`nFound $($bomFiles.Count) file(s) with BOM" -ForegroundColor Yellow
Write-Host "Do you want to fix them? (Y/N): " -NoNewline
$response = Read-Host

if ($response -eq 'Y' -or $response -eq 'y') {
    foreach ($file in $bomFiles) {
        try {
            # Read content with BOM
            $content = Get-Content -Path $file -Raw -Encoding UTF8
            
            # Write back without BOM
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($file, $content, $utf8NoBom)
            
            Write-Host "Fixed: $file" -ForegroundColor Green
        }
        catch {
            Write-Host "Error fixing $file : $_" -ForegroundColor Red
        }
    }
    Write-Host "`nAll files fixed!" -ForegroundColor Green
}
else {
    Write-Host "Cancelled." -ForegroundColor Yellow
}

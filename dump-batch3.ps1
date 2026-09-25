<#
    dump-batch3.ps1 — Endpoints + schemas ko .txt me nikaalta hai

    SAFETY: Ye script sirf PADHTA hai. Repo me koi file delete, modify ya move
    nahi hoti. Output repo ke BAHAR (..\baatx-dumps) jaata hai.

    CHALAYEIN (project root se):
      cd "C:\Users\admin\Downloads\Baat-X-main (1)\Baat-X-main"
      powershell -ExecutionPolicy Bypass -File .\dump-batch3.ps1
#>

$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
$out  = Join-Path (Split-Path $repo -Parent) 'baatx-dumps'

if (-not (Test-Path $out)) { New-Item -ItemType Directory -Path $out | Out-Null }

# Endpoints aur schemas alag files me, taaki dono manageable size ke rahein.
$endpointsFile = Join-Path $out 'batch3a-endpoints.txt'
$schemasFile   = Join-Path $out 'batch3b-schemas.txt'

foreach ($f in @($endpointsFile, $schemasFile)) {
    if (Test-Path $f) { Clear-Content $f } else { New-Item -ItemType File -Path $f | Out-Null }
}

function Add-Folder {
    param([string]$Batch, [string]$RelativeFolder)

    $full = Join-Path $repo $RelativeFolder
    if (-not (Test-Path $full)) {
        Write-Host "  - nahi mila: $RelativeFolder" -ForegroundColor DarkGray
        return
    }

    Get-ChildItem $full -Recurse -File -Filter '*.py' |
        Where-Object { $_.FullName -notmatch '__pycache__' } |
        Sort-Object Name |
        ForEach-Object {
            $rel = $_.FullName.Substring($repo.Length).TrimStart('\')
            Add-Content $Batch "`n`n===== FILE: $rel ====="
            Get-Content $_.FullName -Raw | Add-Content $Batch
            Write-Host "  + $rel" -ForegroundColor Green
        }
}

Write-Host "`n[3a] Endpoints" -ForegroundColor Cyan
Add-Folder $endpointsFile 'backend\app\api\v1\endpoints'
Add-Folder $endpointsFile 'backend\app\api\v1\routers'      # agar alag naam ho

Write-Host "`n[3b] Schemas" -ForegroundColor Cyan
Add-Folder $schemasFile 'backend\app\schemas'

# Router registration bhi chahiye - organizations router yahan add karna hai.
Write-Host "`n[3a] Router + main" -ForegroundColor Cyan
@(
    'backend\app\api\v1\router.py',
    'backend\app\api\v1\api.py',
    'backend\app\api\v1\__init__.py',
    'backend\app\main.py'
) | ForEach-Object {
    $full = Join-Path $repo $_
    if (Test-Path $full -PathType Leaf) {
        Add-Content $endpointsFile "`n`n===== FILE: $_ ====="
        Get-Content $full -Raw | Add-Content $endpointsFile
        Write-Host "  + $_" -ForegroundColor Green
    }
}

Write-Host "`n================ SUMMARY ================" -ForegroundColor Yellow
Get-ChildItem $out -Filter 'batch3*.txt' |
    Select-Object Name, @{ n = 'KB'; e = { [math]::Round($_.Length / 1KB, 1) } } |
    Format-Table -AutoSize

Write-Host "Files yahan: $out" -ForegroundColor Yellow

Write-Host "`n=========== SECRETS CHECK ===========" -ForegroundColor Yellow
$hits = Select-String -Path (Join-Path $out 'batch3*.txt') `
    -Pattern 'sk-[A-Za-z0-9]', 'JWT_SECRET\s*=\s*["'']?\S', 'API_KEY\s*=\s*["'']?\S' `
    -ErrorAction SilentlyContinue

if ($hits) {
    Write-Host "Upload se pehle ye lines check kar lein:" -ForegroundColor Red
    $hits | Select-Object -First 20 Filename, LineNumber, Line | Format-Table -AutoSize
} else {
    Write-Host "Koi obvious secret nahi mila." -ForegroundColor Green
}

Write-Host "`nRepo me koi file delete ya modify nahi hui." -ForegroundColor Green

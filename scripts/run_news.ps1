# Wrapper quét tin tức kinh tế + AI phân tích ảnh hưởng (Windows Task Scheduler, 9h & 14h).
# Ghi log UTF-8 ra logs\news_YYYY-MM-DD.log

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$logDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "news_$stamp.log"

$py = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

"==== Quét tin $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File -FilePath $log -Append -Encoding utf8
& $py -m app.news_scan 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
"==== Kết thúc $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (exit=$LASTEXITCODE) ====`n" | Out-File -FilePath $log -Append -Encoding utf8

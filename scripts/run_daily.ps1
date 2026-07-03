# Wrapper chạy pipeline hằng ngày (dùng cho Windows Task Scheduler).
# Tự cd vào project, chạy bằng python trong .venv, ghi log ra logs\pipeline_YYYY-MM-DD.log

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $PSScriptRoot   # thư mục gốc project
Set-Location $ProjectDir
$env:PYTHONIOENCODING = "utf-8"
# Để PowerShell đọc stdout của python dưới dạng UTF-8 (tránh log bị mojibake tiếng Việt)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$logDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "pipeline_$stamp.log"

$py = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # dự phòng nếu không có venv

"==== Bắt đầu $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File -FilePath $log -Append -Encoding utf8
& $py -m app.pipeline 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
"==== Kết thúc $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (exit=$LASTEXITCODE) ====`n" | Out-File -FilePath $log -Append -Encoding utf8

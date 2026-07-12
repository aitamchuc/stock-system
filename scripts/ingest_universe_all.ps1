# Nạp toàn bộ ~1500 mã: lặp gọi ingest_universe.py cho tới khi xong (~85 phút).
# Chạy tách rời:  Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\ingest_universe_all.ps1' -WindowStyle Hidden

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$logDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "ingest_universe.log"
$py = Join-Path $ProjectDir ".venv\Scripts\python.exe"

"==== BẮT ĐẦU $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File $log -Append -Encoding utf8

for ($i = 1; $i -le 16; $i++) {
    "---- lượt $i ----" | Out-File $log -Append -Encoding utf8
    $out = & $py scripts\ingest_universe.py --minutes 9 2>&1 | Out-String
    $out | Out-File $log -Append -Encoding utf8
    if ($out -match "Đã nạp xong toàn bộ") { break }
    if ($out -match "còn lại: 0") { break }
}

"==== KẾT THÚC $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====" | Out-File $log -Append -Encoding utf8

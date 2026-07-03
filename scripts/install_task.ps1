# Đăng ký Windows Task Scheduler chạy pipeline lúc 17:00 các ngày T2–T6.
# Chạy: powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1
# Gỡ:   Unregister-ScheduledTask -TaskName "VN_Stock_Daily" -Confirm:$false

param(
    [string]$TaskName = "VN_Stock_Daily",
    [string]$Time = "17:00",               # nhiều mốc phân tách bằng dấu phẩy: -Time "09:00,14:00"
    [string]$Wrapper = "run_daily.ps1",
    [string]$Description = "Quét dữ liệu, chấm điểm cổ phiếu VN, tích lũy dòng tiền khối ngoại và gửi cảnh báo Telegram (17:00 T2-T6)."
)

$ProjectDir = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $ProjectDir "scripts\$Wrapper"

if (-not (Test-Path $wrapper)) {
    Write-Error "Không tìm thấy $wrapper"; exit 1
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`""

# Một trigger cho mỗi mốc giờ (hỗ trợ chạy nhiều lần/ngày)
$times = $Time.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$trigger = @()
foreach ($t in $times) {
    $parts = $t.Split(':')
    $at = Get-Date -Hour ([int]$parts[0]) -Minute ([int]$parts[1]) -Second 0
    $trigger += New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $at
}

# StartWhenAvailable: nếu máy tắt lúc 17:00 thì chạy bù khi bật máy lần sau.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

# LogonType Interactive: chỉ chạy khi user đã đăng nhập (không cần lưu mật khẩu).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description $Description `
    -Force | Out-Null

Write-Output "✅ Đã đăng ký task '$TaskName' chạy lúc $($times -join ', ') các ngày T2-T6."
Write-Output "   Xem:      Get-ScheduledTask -TaskName '$TaskName'"
Write-Output "   Chạy thử: Start-ScheduledTask -TaskName '$TaskName'"
Write-Output "   Gỡ bỏ:    Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"

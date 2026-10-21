param([string]$Title = "naiva", [string]$Message = "check it")
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
try {
    $notify = New-Object System.Windows.Forms.NotifyIcon
    $notify.Icon = [System.Drawing.SystemIcons]::Warning
    $notify.BalloonTipTitle = $Title
    $notify.BalloonTipText = $Message
    $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
    $notify.Visible = $true
    $notify.ShowBalloonTip(8000)
    Start-Sleep -Seconds 8
    $notify.Dispose()
    "ok"
} catch {
    "failed: " + $_.Exception.Message
}
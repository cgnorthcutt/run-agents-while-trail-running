param(
    [ValidateRange(1, 86400)][int]$Seconds = 43200,
    [string]$StopFile
)
# Run directly in a foreground Windows terminal, not detached WSL interop.
# This process/thread-scoped request does not prevent reboots or edit power plans.
$ErrorActionPreference = 'Stop'
if ($StopFile -and $StopFile -notmatch '\A(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+\\)') {
    throw 'StopFile must be an explicitly chosen absolute Windows path.'
}
if (-not ('PhoneMiniAwake' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PhoneMiniAwake {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
}
$continuous = [uint32]2147483648 # ES_CONTINUOUS
$systemRequired = [uint32]2147483649 # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
$timer = [System.Diagnostics.Stopwatch]::StartNew()
try {
    if ([PhoneMiniAwake]::SetThreadExecutionState($systemRequired) -eq 0) {
        throw 'Windows rejected the temporary system-awake request.'
    }
    Write-Host 'Temporary system-awake request active; display may sleep.'
    Write-Host 'Verify with powercfg /requests in another Windows terminal. Ctrl+C releases.'
    while ($timer.Elapsed.TotalSeconds -lt $Seconds) {
        if ($StopFile -and (Test-Path -LiteralPath $StopFile)) { break }
        $remaining = $Seconds - $timer.Elapsed.TotalSeconds
        if ($remaining -gt 0) {
            $milliseconds = [int][Math]::Ceiling(1000 * [Math]::Min(15.0, $remaining))
            Start-Sleep -Milliseconds $milliseconds
        }
    }
} finally {
    if ([PhoneMiniAwake]::SetThreadExecutionState($continuous) -eq 0) {
        throw 'Could not verify awake-request release.'
    }
    $timer.Stop()
    Write-Host 'Awake request released; normal idle policy applies. No shutdown requested.'
}

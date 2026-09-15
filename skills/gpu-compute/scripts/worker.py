#!/usr/bin/env python3
"""Stream reviewed jobs or a trusted command through a fixed SSH transport."""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT = Path.home() / '.config/phone-mini-gpu/machine.json'
LIMIT = 16 * 1024 * 1024
ALIAS = r'[A-Za-z0-9][A-Za-z0-9_.-]*'
WSL_NAME = r'[A-Za-z0-9_][A-Za-z0-9_.-]*'


def checked(value, pattern, field):
    if not isinstance(value, str) or not re.fullmatch(pattern, value, re.ASCII):
        raise ValueError(f'Invalid {field}; use a safe ASCII alias/name.')
    return value


def transport_command(cfg, hold_awake=False):
    if not isinstance(cfg, dict):
        raise ValueError('Configuration must be a JSON object.')
    host = checked(cfg.get('ssh_host'), ALIAS, 'ssh_host')
    port = cfg.get('ssh_port', 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('ssh_port must be an integer from 1 through 65535.')
    transport = cfg.get('transport')
    if transport == 'linux':
        return host, transport, 'bash --noprofile --norc -s'
    if transport != 'windows-wsl':
        raise ValueError('transport must be linux or windows-wsl.')
    distro = checked(cfg.get('wsl_distribution'), WSL_NAME, 'wsl_distribution')
    user = checked(cfg.get('wsl_user'), WSL_NAME, 'wsl_user')
    seconds = cfg.get('awake_seconds', 46800)
    if type(seconds) is not int or not 1 <= seconds <= 86400:
        raise ValueError('awake_seconds must be an integer from 1 through 86400.')
    # ASCII/base64 stdin avoids native-shell quoting and encoding transformations.
    ps = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$distro = '%s'
$userName = '%s'
$pattern = '\A[A-Za-z0-9_][A-Za-z0-9_.-]*\z'
if ($distro -cnotmatch $pattern -or $userName -cnotmatch $pattern) {
    throw 'Unsafe WSL distribution or user name'
}
$si = New-Object System.Diagnostics.ProcessStartInfo
$si.UseShellExecute = $false
$si.FileName = 'wsl.exe'
$si.Arguments = '--distribution ' + $distro + ' --user ' + $userName + ' --exec bash --noprofile --norc -s'
$si.RedirectStandardInput = $true
$text = [Console]::In.ReadToEnd()
$p = New-Object System.Diagnostics.Process
$p.StartInfo = $si
$held = $false
$started = $false
$inputClosed = $false
$deliveryFailed = $false
$timer = [Diagnostics.Stopwatch]::StartNew()
try {
    if (%s) {
        Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class JobPower { [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags); }'
        if ([JobPower]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
            throw 'Could not request temporary system-awake state'
        }
        $held = $true
    }
    if (-not $p.Start()) { throw 'Could not start WSL' }
    $started = $true
    # PowerShell 5.1 lacks ProcessStartInfo.StandardInputEncoding.
    $bytes = [Text.Encoding]::UTF8.GetBytes($text)
    $write = $null
    try {
        $write = $p.StandardInput.BaseStream.BeginWrite($bytes, 0, $bytes.Length, $null, $null)
    } catch {
        $deliveryFailed = $true
        $p.StandardInput.BaseStream.Close()
        $inputClosed = $true
    }
    while ($true) {
        if (-not $inputClosed -and $write.IsCompleted) {
            try { $p.StandardInput.BaseStream.EndWrite($write) }
            catch { $deliveryFailed = $true }
            finally { $p.StandardInput.BaseStream.Close(); $inputClosed = $true }
        }
        if ($held -and $timer.Elapsed.TotalSeconds -ge %d) {
            if ([JobPower]::SetThreadExecutionState([uint32]2147483648) -eq 0) {
                throw 'Could not verify awake-request release'
            }
            $held = $false
            [Console]::Error.WriteLine('Awake time limit reached; normal idle policy applies.')
        }
        if ($p.WaitForExit(100)) { break }
    }
    if (-not $inputClosed) {
        if ($write.IsCompleted) {
            try { $p.StandardInput.BaseStream.EndWrite($write) }
            catch { $deliveryFailed = $true }
        } else { $deliveryFailed = $true }
        $p.StandardInput.BaseStream.Close()
        $inputClosed = $true
    }
    $result = $p.ExitCode
    if ($deliveryFailed) {
        [Console]::Error.WriteLine('WSL input delivery failed; inspect the job before retrying.')
        if ($result -eq 0) { $result = 74 }
    }
} finally {
    try {
        if ($started -and -not $inputClosed) { $p.StandardInput.BaseStream.Close() }
    } finally {
        if ($held -and [JobPower]::SetThreadExecutionState([uint32]2147483648) -eq 0) {
            throw 'Could not verify awake-request release'
        }
        $timer.Stop()
    }
}
exit $result
""" % (distro, user, '$true' if hold_awake else '$false', seconds)
    # Keep the native command below cmd.exe's length limit without changing code.
    ps = '\n'.join(line.strip() for line in ps.splitlines()
                   if line.strip() and not line.lstrip().startswith('#'))
    encoded = base64.b64encode(ps.encode('utf-16le')).decode('ascii')
    command = 'powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand ' + encoded
    if len(command) > 8000:
        raise ValueError('WSL names make the Windows command too long; use shorter names.')
    return host, transport, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT))
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('run', help='read at most 16 MiB of job script from stdin')
    sub.add_parser('exec', help='execute one trusted command string').add_argument('command')
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).expanduser().read_text(encoding='utf-8'))
    host, transport, command = transport_command(cfg, hold_awake=args.action == 'run')
    if args.action == 'run':
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('Job exceeds the 16 MiB stdin limit.')
        variable = 'job_payload'
    else:
        raw = args.command.encode('utf-8')
        variable = 'exec_payload'
    encoded = base64.b64encode(raw).decode('ascii')
    header = (f"expected_transport='{transport}'\noperation='{args.action}'\n"
              f"{variable}='{encoded}'\n")
    runner = Path(__file__).resolve().with_name('remote-job.sh').read_bytes()
    payload = header.encode('ascii') + runner
    argv = [
        'ssh', '-T', '-a', '-x', '-oForwardAgent=no', '-oClearAllForwardings=yes',
        '-oBatchMode=yes', '-oStrictHostKeyChecking=yes', '-oConnectTimeout=8',
        '-oServerAliveInterval=30', '-oServerAliveCountMax=3', host, command,
    ]
    # Only stdin is piped; stdout/stderr remain inherited and live.
    return subprocess.run(argv, input=payload).returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, json.JSONDecodeError):
        sys.exit('Worker failed: check private config/JSON, adjacent runner, and SSH installation.')
    except ValueError as error:
        sys.exit(f'Worker failed: {error}')
    except KeyboardInterrupt:
        sys.exit(130)

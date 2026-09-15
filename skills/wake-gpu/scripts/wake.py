#!/usr/bin/env python3
"""Authorized LAN wake and a bounded TCP probe; standard library only."""
import argparse
import ipaddress
import json
import re
import socket
import sys
import time
from pathlib import Path

DEFAULT = Path.home() / '.config/phone-mini-gpu/machine.json'
RFC1918 = tuple(ipaddress.IPv4Network(n) for n in
                ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def lan_ip(value, field):
    if not isinstance(value, str):
        raise ValueError(f'{field} must be an RFC1918 IPv4 string.')
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError(f'{field} must be a dotted IPv4 address.') from None
    if not any(address in network for network in RFC1918):
        raise ValueError(f'{field} must be within RFC1918 space.')
    return str(address)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(DEFAULT))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).expanduser().read_text(encoding='utf-8'))
    if not isinstance(cfg, dict):
        raise ValueError('Configuration must be a JSON object.')
    value = cfg.get('wol_mac')
    if not isinstance(value, str) or not re.fullmatch(
            r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', value):
        raise ValueError('wol_mac must contain six colon-separated hex octets.')
    mac = bytes.fromhex(value.replace(':', ''))
    if mac in (b'\x00' * 6, b'\xff' * 6) or mac[0] & 1:
        raise ValueError('wol_mac must be a nonzero unicast NIC MAC.')
    source = lan_ip(cfg.get('wol_source_ip'), 'wol_source_ip')
    broadcast = lan_ip(cfg.get('wol_broadcast_ip'), 'wol_broadcast_ip')
    target = lan_ip(cfg.get('ssh_lan_ip'), 'ssh_lan_ip')
    port = cfg.get('ssh_port', 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('ssh_port must be an integer from 1 through 65535.')
    # No subnet inference: private addresses alone do not imply a /24.
    packet = b'\xff' * 6 + mac * 16
    if args.dry_run:
        print(f'Dry-run packet length: {len(packet)} bytes.')
        return 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.settimeout(3)
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sender.bind((source, 0))
        sender.sendto(packet, (broadcast, 9))
    print('Phase 1: UDP magic packet sent; delivery is unconfirmed.', flush=True)
    print('Phase 2: checking TCP reachability for up to 60 seconds.', flush=True)
    deadline = time.monotonic() + 60
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print('Phase 2 timed out: TCP unavailable. Ask the owner; no repairs made.',
                  file=sys.stderr)
            return 1
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(min(3, remaining))
                probe.connect((target, port))
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(2, remaining))
            continue
        print('Phase 3: TCP reachable; SSH identity/authentication NOT yet verified.')
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, json.JSONDecodeError):
        sys.exit('Wake failed: check private config permissions/JSON and local LAN settings.')
    except ValueError as error:
        sys.exit(f'Wake failed: {error}')
    except KeyboardInterrupt:
        sys.exit(130)

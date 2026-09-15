---
name: wake-gpu
description: Validate private LAN wake settings, send an authorized magic packet, and check bounded TCP reachability.
---

# Wake the worker

Follow the clone's [setup runbook](../../AGENTS.md) once. Commands below start at the clone root; from other projects use the absolute helper path in this installed skill. Use the coordinator's private `~/.config/phone-mini-gpu/machine.json`; `--config PATH` selects another private file. Never put machine details into this skill.

```sh
python3 skills/wake-gpu/scripts/wake.py --dry-run
```

Dry-run validates without sending or probing and reports only packet length. A wake request or an agreed policy that authorized compute may wake the worker permits running without `--dry-run`; do not ask again when already authorized. If already awake, skip waking. The script binds the configured LAN source, sends one packet, and polls the SSH TCP port for at most 60 seconds. Packet submission is not delivery; TCP reachability is not SSH identity/authentication. Continue with the compute preflight to verify SSH.

WOL requires manually verified wired-LAN/BIOS/NIC settings. On failure, report the phase and ask; never change firewall, routing, SSH shells, power policy, or network configuration automatically. Never sleep or shut down the worker.

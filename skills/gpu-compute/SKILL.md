---
name: gpu-compute
description: Run builds, tests, rendering, data processing, and GPU jobs on a remote worker while an always-on coordinator manages SSH, progress, and results.
---

# Run compute on the worker

Follow the clone's [setup runbook](../../AGENTS.md) once. Commands below start at the clone root; from other projects use the absolute helper path in this installed skill. Keep planning, editing, transfers, and cloud-model API calls on the coordinator. Route heavy work to the worker; use the [measured benchmark profile](references/benchmarks.md) when choosing hardware and estimating time. Benchmark unfamiliar workloads before committing a long run.

Use ordinary accounts and existing verified SSH keys. Keep model/API credentials on the coordinator. Start with one heavy job and at most four CPU workers. Check available memory, disk, GPU capacity, and existing jobs first; the four-thread defaults and `nice` priority are not resource quotas.

```sh
python3 skills/gpu-compute/scripts/worker.py run < /path/to/reviewed-job.sh
```

The helper creates `~/codex/jobs/JOB/{work,tmp,config,data,state}`, caches under `~/codex/cache`, and `job.log` plus `CHANGES.md`. Existing scratch directories must belong to the worker user and have mode 700; the helper refuses incompatible directories without changing them. Every job appends purpose, meaningful changes, and outcome to `$CODEX_CHANGELOG`. Job scripts must wait for all background computation and checkpoint subprocesses before exiting, so completion records and awake time cover the whole workload.

This directory layout is not a sandbox: WSL can access Windows files. Preserve personal files, unrelated processes, and system/security settings. Honor existing task authorization; prepare concrete changes before asking about anything outside it. If the worker is asleep, use [wake-gpu](../wake-gpu/SKILL.md) within the agreed wake policy. Do not silently substitute the coordinator after failure.

## Phone disconnect test and persistent jobs

Run this in **Bash on the coordinator**, from the clone root. It creates a fresh private local directory and starts a two-minute heartbeat in detached tmux with an explicit working directory:

```bash
umask 077
mkdir -p "$HOME/.local/state/phone-mini-gpu"
local_run=$(mktemp -d "$HOME/.local/state/phone-mini-gpu/run.XXXXXXXX")
cat > "$local_run/job.sh" <<'SH'
set -euo pipefail
printf '%s\n' '- Purpose: phone disconnect heartbeat test.' >> "$CODEX_CHANGELOG"
for i in $(seq 1 12); do date -u +%FT%TZ; sleep 10; done
printf '%s\n' 'ok' > result.txt
printf '%s\n' '- Outcome: completed heartbeat and saved result.txt.' >> "$CODEX_CHANGELOG"
SH
cat > "$local_run/launch.sh" <<'SH'
set -uo pipefail
local_run=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 skills/gpu-compute/scripts/worker.py run < "$local_run/job.sh" 2>&1 | tee "$local_run/transport.log"
codes=("${PIPESTATUS[@]}")
printf 'worker exit=%s; tee exit=%s\n' "${codes[0]}" "${codes[1]}" > "$local_run/exit.txt"
SH
session="gpu-${local_run##*.}"
tmux new-session -d -s "$session" -c "$PWD" bash --noprofile --norc "$local_run/launch.sh"
printf 'Session: %s\nLocal records: %s\n' "$session" "$local_run"
```

Disconnect the phone for at least 30 seconds while the job is running. Reconnect and read `transport.log` from the printed local directory: timestamps must continue across the gap. At completion check `exit.txt` for both exit codes 0, and retrieve `result.txt` plus worker lifecycle records as below. A finished tmux session can disappear; its files remain.

Use the same pattern for real jobs, replacing the heartbeat with the reviewed workload. SSH remains foreground inside **coordinator tmux**, so phone or laptop disconnection does not itself cancel the work. The coordinator and worker must stay powered and connected. Neither tmux nor a job directory provides reboot recovery.

`transport: windows-wsl` requests temporary Windows system-awake state for `run` and releases it at completion/failure or the `awake_seconds` limit. Choose a limit that covers computation and saving; expiration does not stop the workload. The display may sleep; power plans are unchanged. Existing `transport: linux` endpoints that enter WSL need the separate bounded Windows request described in [AGENTS.md](../../AGENTS.md). Verify the request with `powercfg /requests` during setup. Never automatically sleep or shut down a personal worker.

## Inspect and retrieve

Use the printed session and local directory:

```sh
tmux ls
tmux attach -t REPLACE_WITH_SESSION
# Detach with Ctrl-b, then d. Or read without attaching:
tail -n 30 /REPLACE_WITH_LOCAL_RUN/transport.log
```

Use the actual printed `JOB_DIR` below in place of `/home/USER/codex/jobs/JOB`. Retrieve into a fresh private local directory. Stage downloads as `.part` so a failed SSH call does not replace a result:

```bash
local_results=$(mktemp -d "$HOME/.local/state/phone-mini-gpu/results.XXXXXXXX")
python3 skills/gpu-compute/scripts/worker.py exec 'cat -- /home/USER/codex/jobs/JOB/work/result.txt' > "$local_results/result.txt.part" && mv "$local_results/result.txt.part" "$local_results/result.txt"
python3 skills/gpu-compute/scripts/worker.py exec 'cat -- /home/USER/codex/jobs/JOB/job.log' > "$local_results/job.log.part" && mv "$local_results/job.log.part" "$local_results/job.log"
python3 skills/gpu-compute/scripts/worker.py exec 'cat -- /home/USER/codex/jobs/JOB/CHANGES.md' > "$local_results/CHANGES.md.part" && mv "$local_results/CHANGES.md.part" "$local_results/CHANGES.md"
```

Windows SSH's SFTP addresses the Windows filesystem; use these streamed reads for WSL artifacts. `exec` runs one trusted shell command, not an allowlisted read API. It checks Linux/non-root; the Windows transport additionally verifies WSL. It preserves remote exit codes; SSH failures commonly return 255, audit-write failures return 74.

`job.log` contains START/FINISH records. The coordinator `tee` captures stdout/stderr; no worker `output.log` is created. A trainer should explicitly write its own progress log, fixed held-out loss/perplexity over iterations, elapsed time, and checkpoints. Perplexity is `exp(loss)` for cross-entropy in nats. Keep evaluation settings consistent and distinguish training from validation.

After a lost SSH connection, inspect logs, relevant processes, and checkpoints before relaunching: work may still be running. Training code owns checkpoint/recovery behavior. Retrieve useful results and both lifecycle/change records. Remove only this task's reproducible intermediates when authorized. Keep raw logs private; publish reviewed, sanitized measurements. `--config PATH` goes before `run` or `exec` and defaults to `~/.config/phone-mini-gpu/machine.json`.

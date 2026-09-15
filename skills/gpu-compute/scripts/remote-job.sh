#!/usr/bin/env bash
# Trusted scratch/audit runner, not a security sandbox. HOME is never reassigned.
set -euo pipefail
umask 077
die() { printf 'worker: %s\n' "$*" >&2; exit 1; }
[[ $(uname -s) == Linux ]] || die 'Linux is required.'
uid=$(id -u)
[[ $uid != 0 ]] || die 'Refusing root; select an ordinary Linux/WSL user.'
if [[ $expected_transport == windows-wsl ]]; then
    read -r kernel < /proc/sys/kernel/osrelease
    [[ ${kernel,,} == *microsoft* ]] || die 'Windows transport did not reach WSL.'
fi

# Preserve quotes and trailing newlines in the single trusted exec string.
if [[ ${operation:-run} == exec ]]; then
    command=$(printf '%s' "$exec_payload" | base64 --decode && printf '.')
    unset exec_payload
    exec bash --noprofile --norc -c "${command%.}" </dev/null
fi

check_path() {
    local resolved fs
    [[ ! -L "$1" ]] || die 'Refusing a symlink scratch path.'
    resolved=$(realpath -e -- "$1") || die 'Cannot resolve scratch path.'
    case "$resolved" in /mnt|/mnt/*) die 'Scratch must not be under /mnt.' ;; esac
    fs=$(stat -f -c %T -- "$resolved") || die 'Cannot inspect scratch filesystem.'
    case "${fs,,}" in
        drvfs|9p|wslfs|*ntfs*|*exfat*|fuseblk|cifs|smb*|msdos|vfat)
            die 'Refusing a Windows-backed scratch filesystem.' ;;
    esac
}
[[ $HOME == /* && -d $HOME ]] || die 'HOME must be an existing absolute directory.'
check_path "$HOME"
root="$HOME/codex"
jobs="$root/jobs"
cache="$root/cache"
for path in "$root" "$jobs" "$cache" "$cache/huggingface" "$cache/torch" "$cache/pip"; do
    [[ ! -L "$path" ]] || die 'Refusing symlink job root/jobs/cache.'
    if [[ ! -e $path ]]; then mkdir -- "$path"; fi
    [[ -d "$path" ]] || die 'Expected a scratch directory; existing files are preserved.'
    check_path "$path"
    [[ $(stat -c %u -- "$path") == "$uid" ]] || die 'Scratch must belong to this user.'
    [[ $(stat -c %a -- "$path") == 700 ]] || die 'Existing scratch permissions must be 700; ask its owner before changing them.'
done
job_dir=$(mktemp -d "$jobs/job-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
mkdir -- "$job_dir"/{work,tmp,config,data,state}
export CODEX_JOB_DIR="$job_dir" CODEX_CHANGELOG="$job_dir/CHANGES.md"
export TMPDIR="$job_dir/tmp" XDG_CONFIG_HOME="$job_dir/config"
export XDG_DATA_HOME="$job_dir/data" XDG_STATE_HOME="$job_dir/state"
export XDG_CACHE_HOME="$cache" HF_HOME="$cache/huggingface"
export TORCH_HOME="$cache/torch" PIP_CACHE_DIR="$cache/pip"
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4

audit() {
    local when
    when=$(date -u +%FT%TZ) || return 1
    printf '%s %s\n' "$when" "$*" >> "$job_dir/job.log" &&
        printf -- '- %s %s\n' "$when" "$*" >> "$CODEX_CHANGELOG"
}
finish() {
    local code=$?
    trap - EXIT
    if ! audit "FINISH exit=$code"; then
        printf '%s\n' 'Audit failure; returning 74.' >&2 || :
        code=74
    fi
    exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
audit START || exit 74
printf 'JOB_DIR=%s\nCHANGES=%s\nAUDIT_LOG=%s\n' "$job_dir" "$CODEX_CHANGELOG" "$job_dir/job.log"
printf '%s' "$job_payload" | base64 --decode > "$job_dir/job.sh"
unset job_payload
cd -- "$job_dir/work"
# No output.log: capture stdout/stderr with coordinator tee or explicit job logs.
nice -n 10 bash --noprofile --norc "$job_dir/job.sh" </dev/null

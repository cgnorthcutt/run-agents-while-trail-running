# phone-mini-codex-gpu

**Start work from your phone. Let your sleeping gaming PC wake up and do the heavy lifting.**

I started training a 1.49B-parameter model from scratch with nanoGPT on a trail run, using my phone over 5G. The next morning I checked loss and perplexity from my phone without touching a laptop.

The setup: a ~$200 used 2020 M1 Mac mini runs the agent and stays on. My gaming PC has an RTX 5090 and 128 GB RAM. It wakes when needed for compute. The phone is the remote control.

```text
Phone → always-on mini → Wake-on-LAN + private LAN SSH → gaming PC → WSL2 → GPU
```

This repo shares the setup instructions, reusable agent skills, and real benchmarks. Use it for training, builds, rendering, or other heavy jobs while trail running, hiking, or sleeping.

## Set it up with your agent

You need an always-on coordinator, a GPU worker, and a phone. The documented phone connection uses ChatGPT Remote on a Mac or Windows host. The helpers run on a Mac/Linux coordinator with Python 3, SSH, and tmux. Windows workers need WSL2; waking requires wired Ethernet and compatible BIOS/NIC settings.

Clone on the coordinator:

```sh
git clone https://github.com/cgnorthcutt/phone-mini-codex-gpu.git
cd phone-mini-codex-gpu
```

Give your agent this prompt:

> Read AGENTS.md and both skills in this repo. Help me replicate this setup for my devices. Keep machine details in the private config, preserve existing settings, and honor my existing authorizations. Verify wake, SSH, GPU access, and progress across a phone disconnect before running a real job.

The [setup runbook](AGENTS.md) covers accounts, private configuration, SSH keys, skills, and a working test. Pair your phone through the [official remote connection setup](https://learn.chatgpt.com/docs/remote-connections). Keep the coordinator awake and connected while work runs.

## What the skills do

- [wake-gpu](skills/wake-gpu/SKILL.md): wake your worker over the home LAN and check reachability.
- [gpu-compute](skills/gpu-compute/SKILL.md): choose compute using benchmarks, run jobs with logs, keep Windows awake for the job, and retrieve results.

The main Windows route uses Windows OpenSSH to start WSL without changing the SSH default shell. Existing Linux/WSL SSH endpoints are also supported; see the runbook for their power-management differences. Machine addresses and credentials stay in your private configuration.

## Check progress anytime

Ask your agent: **“Show me the current job's progress and latest logs.”** Or use the coordinator terminal:

```sh
tmux ls
tmux attach -t REPLACE_WITH_PRINTED_SESSION
```

Detach with **Ctrl-b, then d**. The compute skill prints a private directory containing `transport.log` and the final exit codes. Jobs continue when the phone disconnects; both computers still need power and network access. Training code supplies its own metrics and checkpoints.

## The nanoGPT example

The short RTX 5090 test measured **about 5,706 training tokens/sec** and **26 GiB peak reserved GPU memory**. Only two full updates were timed after warm-up; this excludes evaluation and saving.

Below is a **7.25-hour snapshot** from the 12-hour experiment on source-declared US public-domain verse. Validation plateaued while training loss fell, suggesting overfitting. The [benchmark notes](skills/gpu-compute/references/benchmarks.md) include hardware, model settings, raw timings, corpus details, and limitations. Bring your own training code and data; the custom training loop is not included here.

![nanoGPT training and validation loss and perplexity at 7.25 hours](skills/gpu-compute/references/learning-curve.png)

## Keep the setup private

Use ordinary accounts, dedicated SSH keys, verified host keys, and LAN-scoped access. The documented phone connection uses the app's authenticated remote flow; the GPU link stays on the home LAN. Do not expose SSH, an app server, or a dashboard to the public internet. Job directories organize work but do not sandbox it—WSL can access Windows files. Keep keys, machine settings, and raw logs out of git.

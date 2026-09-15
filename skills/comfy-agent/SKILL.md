---
name: comfy-agent
description: Use when the user wants to generate or edit images or video with ComfyUI (running locally or on a RunPod pod), run an existing ComfyUI workflow or template from an agent, or when a ComfyUI job must be submitted, monitored, or its outputs downloaded without touching the ComfyUI web UI
---

# comfy-agent

Drive a ComfyUI server through its HTTP API with one CLI, `scripts/comfy_agent.py`.
Same commands for a local ComfyUI and a RunPod pod; only `COMFY_URL` changes.

## Setup (once per ComfyUI instance)

```bash
export COMFY_URL=http://127.0.0.1:8188            # or https://<pod-id>-8188.proxy.runpod.net
python3 <skill-dir>/scripts/comfy_agent.py doctor  # banner, version, GPU, environment limits
```

Optional: `COMFY_AUTH` (`user:pass` or `Bearer <token>`), `COMFY_OUT` (default `./comfy-out`).
Add `--json` to any command for machine-readable output. Exit codes: 0 ok / still running, 1 usage, 2 cannot connect, 3 workflow rejected, 4 unsupported here, 5 job failed.

## Standard loop

1. `doctor` — confirm connection; read the `limits` it prints.
2. Pick a workflow file in **API format** (ComfyUI: Workflow > Export (API)). UI-format files are refused with exit 4.
3. `run <wf.json> --set '#<id>.<input>=<value>' [--seed random]` — returns `prompt_id` immediately.
4. `status <prompt_id>` or `wait <prompt_id> --timeout 120` — `wait` returns exit 0 with `timed_out: true` if not finished; call it again.
5. `fetch <prompt_id>` — downloads every output into `COMFY_OUT/<time>-<id>/` with `manifest.json` (prompt, overrides, seeds).

For short image jobs `run --wait` does steps 3–5 in one call.

## Rules keyed to what you observe

- If `doctor` reports `runpod`: never use `--wait` with a timeout above 300; poll with `status` instead, and tell the user to `fetch` before terminating the pod. The pod's disk is gone after terminate.
- If the workflow contains video nodes (`VHS_*`, `WanVideo*`, `LTX*`, or a `length`/`frames` input > 1): treat it as a long job. Submit, then poll every 30–60 s.
- If `run` exits 3 with `issues`: read `node`, `input`, `details`. Fix with `--set` when it is a value; report to the user when it names a model or node that is missing. Do not guess a different model file.
- If `status` shows `error` with `CUDA out of memory`: run `free --unload-models`, lower size/frames via `--set`, retry once, then report.
- If exit code is 2 right after a pod started: ComfyUI is still booting. Retry `doctor` after 30 s.

## Command reference

| Command | Purpose |
|---|---|
| `doctor` | connectivity, versions, GPU, RunPod detection, dashboard |
| `run wf.json [--set ...] [--seed random] [--wait --timeout S --out DIR]` | submit (and optionally wait + fetch) |
| `status ID` / `wait ID [--timeout S]` | job state; `wait` never fails on timeout |
| `fetch ID [--out DIR]` | download outputs + manifest |
| `queue` / `cancel ID` / `cancel --all` | inspect or clear the queue |
| `models [folder] [--grep X]` / `nodes [--grep X]` | what is installed on the server |
| `free [--unload-models]` | release VRAM |
| `ledger [--last N]` | jobs submitted from this machine |

`--help` on any command lists every flag.

## References

- `references/environments.md` — local vs RunPod differences, URLs, timeouts, dashboard.

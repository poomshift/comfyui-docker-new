# Environments: local ComfyUI vs RunPod pod

| | Local | RunPod (PromptAlchemist template) |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | `https://<pod-id>-8188.proxy.runpod.net` |
| Dashboard (model downloads, logs) | none | `https://<pod-id>-8189.proxy.runpod.net` (auto-derived) |
| JupyterLab | none | `https://<pod-id>-8888.proxy.runpod.net` |
| Auth | none unless you added one | none by default; set `COMFY_AUTH` if the pod runs a reverse proxy with auth |
| Request limit | none | proxy closes any single HTTP request idle for about 100 s |
| Persistence | disk stays | **everything is deleted on terminate** |
| Boot time | seconds | minutes: model downloads run before ComfyUI starts; `doctor` returns exit 2 until then |

## Finding the pod URL

RunPod's Connect tab shows `https://<pod-id>-8188.proxy.runpod.net`. The pod id is the 14-character string before `-8188`.
The CLI recognises this pattern and switches on RunPod behaviour (dashboard derivation, limits note in `doctor`).

## Why submit-then-poll

ComfyUI itself has no request limit, but the RunPod proxy cuts idle requests at ~100 s. `run` returns the
`prompt_id` in under a second; `status`/`wait` make one short request per poll; `fetch` streams the file,
which keeps the connection busy so it is not cut. Nothing in the CLI holds a request open across a generation.

Separately, the agent's own shell tool usually has a timeout of 2–10 minutes. Long video jobs must be
polled across several tool calls: `run` -> (later) `status` -> `fetch`.

## Before terminating a pod

1. `queue` — make sure nothing you still want is running.
2. `fetch <id>` for every job in `ledger --last 20` whose files you have not saved.
3. Only then terminate. There is no recovery afterwards.

## Reading errors by exit code

| Exit | Meaning | Typical cause on RunPod |
|---|---|---|
| 2 | cannot connect | pod still booting; wrong pod id; pod terminated |
| 3 | workflow rejected | model file name differs from what is installed; custom node missing |
| 4 | unsupported | UI-format workflow (export API format instead) |
| 5 | job failed | CUDA out of memory; bad input file |

#!/usr/bin/env bash
# Manual integration check against a real ComfyUI. Usage:
#   COMFY_URL=http://127.0.0.1:8188 WF=path/to/api_workflow.json bash skills/comfy-agent/tests/smoke.sh
set -euo pipefail
CLI="python3 $(dirname "$0")/../scripts/comfy_agent.py"
: "${COMFY_URL:?set COMFY_URL}"
: "${WF:?set WF to an API-format workflow that runs quickly}"

$CLI doctor
$CLI models | head -20
PID=$($CLI --json run "$WF" --seed random | python3 -c 'import json,sys; print(json.load(sys.stdin)["prompt_id"])')
echo "prompt_id=$PID"
$CLI wait "$PID" --timeout 240 --interval 5
$CLI fetch "$PID" --out "${COMFY_OUT:-./comfy-out}"
$CLI ledger --last 3
echo "smoke OK"

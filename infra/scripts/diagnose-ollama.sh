#!/usr/bin/env bash
# Run from the OrderNexa project root. No secrets or uploaded PO content printed.
set -uo pipefail
cd "$(dirname "$0")/../.."
printf '\n=== Ollama local CPU diagnostics (synthetic prompt only) ===\n'
docker compose config --quiet || exit 1
printf '\n--- Containers ---\n'
docker compose ps ollama api || true
printf '\n--- Effective CPU settings ---\n'
docker compose exec -T ollama sh -c 'printenv | grep -E "^OLLAMA_(HOST|VULKAN|LLM_LIBRARY|NO_CLOUD|CONTEXT_LENGTH|LOAD_TIMEOUT)="' || true
printf '\n--- Host resources before test ---\n'
free -h || true
docker stats --no-stream ordernexa-ollama || true
printf '\n--- Installed models ---\n'
timeout -k 3s 25s docker compose exec -T ollama ollama list || true
printf '\n--- Test SMALL model with 55-second ceiling ---\n'
set +e
timeout -s INT -k 5s 55s docker compose exec -T ollama \
    ollama run qwen2.5:0.5b 'Say READY.'
status=$?
set -e
printf '\nModel test exit code: %s (0=completed, 124=timeout)\n' "$status"
printf '\n--- Host resources after test ---\n'
free -h || true
docker stats --no-stream ordernexa-ollama || true
printf '\n--- Kernel memory pressure (if exposed by WSL) ---\n'
cat /proc/pressure/memory 2>/dev/null || true
printf '\n--- Recent Ollama runtime logs (synthetic request only) ---\n'
docker compose logs --since=4m --tail=180 ollama | \
    grep -Eai 'error|warn|runner|load|oom|out.of.memory|fail|status|compute|repack|memory|libDirs' | tail -85 || true
printf '\n--- Docker OOM flag (false does NOT rule out memory stalls) ---\n'
docker inspect --format='OOM killed: {{.State.OOMKilled}}' ordernexa-ollama || true
if [[ $status -eq 0 ]]; then
    printf '\nSmall model generated. Next check Granite once, then run the explicit API probe.\n'
elif [[ $status -eq 124 ]]; then
    printf '\nSmall model itself timed out. Do NOT repeat full document upload.\n'
    printf 'Inspect runner logs and test Ollama natively outside the Docker container.\n'
else
    printf '\nSmall model exited abnormally. Use the recent log lines above.\n'
fi
exit 0

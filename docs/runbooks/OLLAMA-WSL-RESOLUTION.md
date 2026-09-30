# Local Ollama runner: evidence, isolation and recovery

**Read before another purchase-order upload.** Existing customer/ERP code does
not explain the user's repeated tiny-model failure.

## What the actual logs established

- `GET /api/tags` and `ollama list` worked: Docker DNS, the HTTP listener and
  model registry were reachable.
- `granite3.2-vision:2b` began tensor loading (approximately 358 MiB CPU buffer
  and 1,114 MiB CPU repack buffer) but its runner kept alternating between
  `llm server not responding` and `llm server loading model`.
- `qwen2.5:0.5b` (397 MB installed model) also failed under a 90-second timeout,
  even after forcing `cpu_avx2`. The prior CPU observation was approximately
  245% for Ollama while it consumed about 460 MiB. Linux `free -h` showed about
  1.6 GiB *available after the test*. These readings do **not** prove an OOM
  event or prove that the model runner is healthy.
- CPU flags include `avx` and `avx2`; the override in Compose is available.
- Increasing RAM alone is **not a verified fix** for the tiny-model failure.

## Test 1: collect evidence once — don't run a 240-second upload

In Ubuntu from the project root:

```bash
chmod +x infra/scripts/diagnose-ollama.sh
./infra/scripts/diagnose-ollama.sh
```

It tests your EXISTING small model, reports the exit code, Linux memory pressure,
container OOM flag and recent runner logs. It does not print real order data.

If it still times out, STOP. Editing FastAPI extraction prompts will not fix a
Dockerized Ollama runner that cannot generate a short independent prompt.

## Test 2: isolate Docker-specific vs host-specific runner failures

The next useful A/B test is **the same Ollama product on Windows directly**,
not Gemini and not a replacement API architecture.

1. Stop just the Docker Ollama service: `docker compose stop ollama`. This does
   not remove the existing model volume or other infrastructure.
2. Use the official Windows Ollama application/installer. In PowerShell,
   start with `ollama --version`, `ollama pull qwen2.5:0.5b`, then
   `ollama run qwen2.5:0.5b "Say READY"`. It may require downloading the small
   model again because the Windows install has its own model directory.
3. If Windows-native Ollama also hangs on the tiny model, inspect Windows CPU,
   memory, virtualization and antivirus/storage pressure before assigning more
   WSL RAM. A second host implementation has isolated Docker as a variable.
4. **Only if Windows-native inference actually succeeds**, route FastAPI to it
   by configuring `OLLAMA_BASE_URL=http://host.docker.internal:11434` in your
   existing PRIVATE `.env`, after confirming the Windows listener is reachable
   from the API container. Keep the same `OllamaProvider`, schemas and business
   engine. No switch to a cloud AI vendor is needed.
5. Windows Ollama often listens on localhost only. Do NOT indiscriminately
   expose unauthenticated port 11434 to public networks. If local container
   routing requires a wider binding, use host firewall restrictions allowing
   only the trusted Docker subnet and verify from inside Docker before use.
6. With Windows inference working, test the `/api/v1/ops/ai-inference-probe`
   endpoint, then a single synthetic structured extraction, THEN a real upload.

If you prefer Docker-only, testing an alternate *verified compatible* Ollama
release with the same named model volume is another hypothesis test, not a
promise of repair. Back up your named model volume before any migration and do
not delete it during troubleshooting.

## Important design constraint

On an 8 GB physical machine, running two PostgreSQL databases, Odoo, n8n,
FastAPI, MinIO and a multimodal model simultaneously has limited headroom.
Temporarily stopping nonessential services and/or upgrading hardware will
improve capacity, but neither should be sold as a proven remedy for the small
model's independent runner timeout.

## While inference is unavailable, do not falsify AI outcomes

The release's HTTP upload will produce a **bounded 503 JSON response** if
Ollama times out, retaining the original in MinIO. Under the Operations Console,
enter the returned `artifact_id`, choose **Preview for human review**, check
and correct every field against the original, then confirm it as a HUMAN action.
This invokes the existing deterministic C2C validation without fabricating
an LLM result. Use a configured local operator key.

The explicit inference-probe endpoint tests real Qwen generation only on
request; `/api/tags` checks connectivity and is not displayed as model-ready.

# Windows Ollama model mismatch: diagnosis and controlled fix

**What happened:** FastAPI was correctly pointed to Windows Ollama at
`http://host.docker.internal:11434`, but `OLLAMA_MODEL` selected
`granite3.2-vision:2b`, which had only been shown installed **inside Docker**.
Windows Ollama had previously been set up with `qwen2.5:0.5b`. A working
`READY` response from Qwen does **not** demonstrate that Granite is installed
on the same Ollama instance. `/api/chat` HTTP 404 commonly means the requested
model is missing. Confirm using the actual Windows Ollama registry.

## 1. Never replace the wrong `.env` or remove Docker volumes

In Ubuntu, from project root, preserve your existing private environment file:

```bash
cp -p .env ".env.before-ollama-routing-$(date +%Y%m%d-%H%M)"
```

In Windows PowerShell, check installed **Windows** models:

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags |
  Select-Object -ExpandProperty models |
  Select-Object name
```

## 2. Text-only local integration, using EXISTING downloaded small model

For a **temporary connectivity/schema test** on `.txt`, `.csv`, native-text
PDF and `.xlsx` documents, add or update these settings in your local `.env`:

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=granite3.2-vision:2b
OLLAMA_TEXT_MODEL=qwen2.5:0.5b
OLLAMA_VISION_MODEL=granite3.2-vision:2b
OLLAMA_READ_TIMEOUT_SECONDS=240
OLLAMA_PROBE_TIMEOUT_SECONDS=180
```

Qwen 0.5B is installed on Windows and already generated `READY` in earlier
manual tests. **It is NOT validated for business PO extraction**: its output
can fail the strict Pydantic schema or omit fields. Do not enable unattended
ERP writes based on this temporary text model. Manually review extracted
fields. The independent vision setting prevents the program from sending a
PNG or scanned PDF to a text-only model by accident.

If you want Granite as the text **and** image model, install Granite in
Windows and set both model variables to `granite3.2-vision:2b` instead.
With 8 GB RAM, its cold start and vision capability are unverified; avoid
large unattended jobs until measured on your hardware.

## 3. For real Granite vision, install on Windows (not in Docker)

In **Windows PowerShell**, with native Ollama running:

```powershell
ollama pull granite3.2-vision:2b
ollama list
```

Do not pull anything in Docker for the Windows-hosted backend. Test Granite
separately on Windows before sending a large PDF/image. Pulling may need
extra disk space; loading the vision model may take several minutes on 8 GB RAM.
Keep non-essential services stopped during testing.

## 4. Validate the installed models FROM YOUR API CONTAINER

Because `./apps/api:/app` is already bind-mounted into the container,
rebuilding is unnecessary for these Python-only updates. You **must** recreate
the API container after editing `.env`, so it loads the new environment:

```bash
docker compose up -d --no-deps --force-recreate api
docker compose exec -T api python -m app.services.ollama_preflight --mode text
docker compose exec -T api python -m app.services.ollama_preflight --mode vision
```

This check reads `/api/tags` at `OLLAMA_BASE_URL`. It does not generate text.
After success, run a minimal `/api/chat` JSON-schema test and only then try
`extract_order_draft` on a text PO. Verify every business-critical field.

## 5. Permanent safety behavior

- Text and image extraction can select independent models. If no override is
  supplied, the preexisting `OLLAMA_MODEL` setting still works for both.
- If inference returns 404 and the configured server's model registry is
  accessible but the requested model is absent, OrderNexa raises the
  actionable non-retryable `MODEL_NOT_INSTALLED` error instead of a vague
  `OLLAMA_HTTP_ERROR` and should retain uploaded documents for review.
- If the requested model actually exists but the route returns 404, the
  system keeps `OLLAMA_HTTP_ERROR` because a missing model is not proven.
- This fix prevents the Docker-vs-Windows model registry confusion. It does
  not guarantee enough RAM, acceptable Granite loading times or extraction
  accuracy. The fallback for an uncertain document remains human review.

## Windows cold starts and local console timeouts

Observed Qwen 0.5B Windows startup time was approximately 105 seconds,
followed by sub-second generation on the first successful request. Earlier
25- to 55-second probes produced false failures. This hotfix extends the
probe to 180 seconds and uses a 10-minute model keep-alive; the Console
waits 210 seconds for an explicitly requested probe and 270 seconds for
intake/retry when the backend inference timeout is 240 seconds. These are
local-development safeguards only; the long-running uploads should later
be refactored into durable asynchronous jobs for a production deployment.

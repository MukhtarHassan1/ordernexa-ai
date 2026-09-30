OrderNexa Ollama Windows/Docker model-routing repair (targeted overlay)

ROOT CAUSE OF OBSERVED 404 (most likely):
Your FastAPI targets Windows Ollama, and the requested model is Granite.
Windows Ollama previously downloaded Qwen only. The Granite model shown
in `docker compose exec ollama ollama list` lives in Docker's separate
model volume. Check the Windows registry before assuming the 404 cause.

CHANGES
- Adds separate optional OLLAMA_TEXT_MODEL and OLLAMA_VISION_MODEL.
- Preserves original OLLAMA_MODEL behavior when overrides are absent.
- Diagnoses 404 by querying the configured server's /api/tags; missing
  installed model produces MODEL_NOT_INSTALLED with actionable details.
- Includes a no-inference preflight command and tests.
- Sets default probe timeout to 180s and keeps tested Qwen warm 10m.
- Aligns local Console probe and upload/retry UI timeouts with slow
  Windows cold starts; shows configured text and vision selections.

APPLY (Ubuntu; cwd ~/projects/ordernexa-ai):
1. Back up your source files and .env.
2. unzip -t /mnt/c/Users/Hammad/Downloads/OrderNexa_Ollama_Model_Routing_Fix.zip
3. unzip -o /mnt/c/Users/Hammad/Downloads/OrderNexa_Ollama_Model_Routing_Fix.zip -d .
4. Edit your existing PRIVATE .env (do not replace it):
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=granite3.2-vision:2b
   OLLAMA_TEXT_MODEL=qwen2.5:0.5b
   OLLAMA_VISION_MODEL=granite3.2-vision:2b
   OLLAMA_READ_TIMEOUT_SECONDS=240
   OLLAMA_PROBE_TIMEOUT_SECONDS=180
   Qwen 0.5B is for temporary connectivity/schema testing only.
5. docker compose up -d --no-deps --force-recreate api
6. docker compose exec -T api python -m app.services.ollama_preflight --mode text
   docker compose exec -T api python -m app.services.ollama_preflight --mode vision
7. docker compose exec -T api pytest -q tests/test_gateway.py

For vision: in WINDOWS PowerShell run `ollama list`; if Granite is missing
there, run `ollama pull granite3.2-vision:2b`. Only after it is installed
can the vision preflight pass. Model availability is NOT proof that
Granite will perform acceptably on the current 8 GB Windows machine.
See docs/runbooks/OLLAMA-WINDOWS-MODEL-ROUTING.md for exact verification.

NO Docker database volumes or private .env are included in this ZIP.
DO NOT run `docker compose down -v`.

OrderNexa collection fix — 2026-09-28
====================================
Issue: the upgrade patch's two test files mistakenly used Path(__file__).resolve().parents[3].
In Docker, test files are /app/tests/*.py, so this raises IndexError before tests run.
This patch updates ONLY tests/test_core.py and tests/test_quality_dataset.py to resolve
fixtures first from the Compose volumes /sample-data and /evals, then from the host repo.

Apply from your WSL terminal (adjust /mnt/c/Users/... to your downloaded patch path):
  cd ~/projects/ordernexa-ai
  unzip -o /path/to/OrderNexa_Test_Collection_Fix_20260928.zip -d .
  docker inspect ordernexa-api --format '{{range .Mounts}}{{println .Destination}}{{end}}'
  # Expected: /app, /sample-data, /evals
  # If /sample-data or /evals absent, use the patch's docker-compose.yml:
  # export COMPOSE_FILE=docker-compose.yml
  # docker compose up -d --no-deps --force-recreate api
  docker compose exec -T api sh -c 'test -f /sample-data/purchase-orders/po-88192-upload.txt && test -f /evals/datasets/synthetic_po_eval.jsonl && echo "Test fixtures mounted: OK"'
  docker compose exec -T api pytest -q tests

This only fixes collection/fixture path handling. Subsequent test failures, if any, are separate
and should be reported with their full traceback. No application logic/DB/volumes are changed.

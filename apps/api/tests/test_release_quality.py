import json
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    """Locate the repository in both the test container and a normal checkout."""
    candidates = [Path("/repo")]
    candidates.extend(parent for parent in Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "workflows" / "n8n").is_dir() and (candidate / ".env.example").is_file():
            return candidate
    raise RuntimeError("Could not locate OrderNexa repository root for release-quality tests.")


def test_all_n8n_templates_are_inactive_and_secret_free():
    base = repo_root() / "workflows" / "n8n"
    paths = sorted(base.glob("*.json"))
    assert len(paths) >= 5
    forbidden_literals = [
        "sk_live_", "sk_test_", "whsec_", "pat-", "Bearer eyJ",
        "X-OrderNexa-Operator-Key: ", "X-OrderNexa-Ingest-Secret: ",
    ]
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        assert obj["active"] is False
        assert obj.get("nodes") and obj.get("connections")
        names = [n["name"] for n in obj["nodes"]]
        assert len(names) == len(set(names))
        assert not any(value in raw for value in forbidden_literals)


def test_safe_env_example_exists_and_has_no_real_secret_values():
    path = repo_root() / ".env.example"
    raw = path.read_text(encoding="utf-8")
    assert "APP_SECRET=" in raw
    assert "N8N_INGEST_SECRET=" in raw
    assert "GRAPH_CLIENT_SECRET=" in raw
    assert "STRIPE_ENABLED=false" in raw
    assert "sk_live_" not in raw
    assert "whsec_" not in raw


def test_dataset_validator_json_out_contract(tmp_path):
    root = repo_root()
    validator = root / "evals" / "runners" / "validate_dataset.py"
    dataset = root / "evals" / "datasets" / "synthetic_po_eval.jsonl"
    out = tmp_path / "report.json"
    subprocess.run(
        [sys.executable, str(validator), str(dataset), "--json-out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["cases"] == 32
    assert report["case_count"] == 32
    assert report["release_claim_eligible"] is True


def test_local_env_generator_keeps_legacy_operator_key_blank_and_all_roles_present():
    root = repo_root()
    source = (root / "infra" / "scripts" / "create-local-env.py").read_text(encoding="utf-8")
    assert "ORDERNEXA_OPERATOR_KEY=" in source
    assert "ORDERNEXA_OPERATOR_KEY={role_keys['OPERATIONS_MANAGER']}" not in source
    for role in ["ADMIN", "AUDITOR", "FINANCE_MANAGER", "OPERATIONS_MANAGER", "SALES_MANAGER"]:
        assert f'"{role}": secret(32)' in source

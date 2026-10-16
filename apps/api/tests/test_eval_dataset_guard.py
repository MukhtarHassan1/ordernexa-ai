from pathlib import Path
import importlib.util


def _find_evals_root() -> Path:
    """
    Locate the OrderNexa evals directory both:
    - inside Docker, where it is mounted at /evals
    - from a normal repository checkout
    """
    test_file = Path(__file__).resolve()

    candidates = [Path("/evals")]
    candidates.extend(parent / "evals" for parent in test_file.parents)

    for candidate in candidates:
        validator = candidate / "runners" / "validate_dataset.py"

        if validator.is_file():
            return candidate

    checked = ", ".join(str(path) for path in candidates)

    raise RuntimeError(
        f"Could not locate OrderNexa evals directory. Checked: {checked}"
    )


EVALS_ROOT = _find_evals_root()

SPEC = importlib.util.spec_from_file_location(
    "validate_dataset",
    EVALS_ROOT / "runners" / "validate_dataset.py",
)

assert SPEC is not None
assert SPEC.loader is not None

MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_generated_500_is_explicitly_not_release_claim_eligible():
    report = MOD.validate(
        EVALS_ROOT
        / "datasets"
        / "generated_draft_500_REQUIRES_REVIEW.jsonl"
    )

    assert report["cases"] == 500
    assert report["unreviewed_generated_labels"] == 500
    assert report["release_claim_eligible"] is False


def test_small_manually_labeled_fixture_is_structurally_eligible():
    report = MOD.validate(
        EVALS_ROOT
        / "datasets"
        / "synthetic_po_eval.jsonl"
    )

    assert report["cases"] == 32
    assert not report["errors"]
    assert report["release_claim_eligible"] is True

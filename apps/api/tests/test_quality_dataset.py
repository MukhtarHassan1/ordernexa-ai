import json
from pathlib import Path


def test_synthetic_labeled_data_is_real_and_not_fake_scores():
    # Docker mounts evals at /evals; host pytest uses repository-relative data.
    path = Path('/evals/datasets/synthetic_po_eval.jsonl')
    if not path.is_file():
        repo_root = Path(__file__).resolve().parents[1].parent.parent
        path = repo_root / 'evals/datasets/synthetic_po_eval.jsonl'
    assert path.is_file(), f'Missing evaluation fixture: {path}. Check ./evals:/evals mount.'
    rows=[json.loads(x) for x in path.read_text().splitlines() if x]
    assert len(rows)==32
    assert len({x['id'] for x in rows})==len(rows)
    assert all('source_text' in x and 'expected' in x for x in rows)
    assert sum(x.get('must_flag_injection',False) for x in rows)==4
    assert sum(x.get('must_request_review',False) for x in rows)==4

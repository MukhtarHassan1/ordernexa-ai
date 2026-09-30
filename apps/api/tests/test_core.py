from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.models.enums import TransactionStatus
from app.schemas.c2c import ManualOrderInput
from app.services.c2c_validation_service import normalize_company_name
from app.services.manual_document_preview import PreviewNotPossible, preview_purchase_order
from app.services.state_machine import InvalidStateTransition, validate_transition

# Docker mounts the repository's sample-data directory at /sample-data.
# The fallback also supports running pytest directly on the host.
SAMPLE = Path('/sample-data/purchase-orders/po-88192-upload.txt')
if not SAMPLE.is_file():
    repo_root = Path(__file__).resolve().parents[1].parent.parent
    SAMPLE = repo_root / 'sample-data/purchase-orders/po-88192-upload.txt'

if not SAMPLE.is_file():
    raise FileNotFoundError(
        f'PO test fixture is missing: {SAMPLE}. '
        'Check the api service mount ./sample-data:/sample-data:ro.'
    )


def test_canonical_text_preview_requires_human():
    result = preview_purchase_order(filename='po-88192-upload.txt', data=SAMPLE.read_bytes())
    draft = ManualOrderInput.model_validate(result['candidate'])
    assert result['method'] == 'DETERMINISTIC_PREVIEW_NOT_AI'
    assert result['requires_human_confirmation'] is True
    assert draft.po_number == 'PO-88192'
    assert draft.customer_hint == 'Northstar Engineering Ltd'
    assert draft.delivery_warehouse_code == 'MAN'
    assert draft.requested_delivery_date == date(2026,9,30)
    assert [(line.product_term, line.quantity) for line in draft.lines] == [
        ('XTR-42', Decimal('40')), ('BRK-90', Decimal('15'))
    ]
    assert draft.lines[0].requested_unit_price == Decimal('260.00')
    # Explicit human preview MUST NOT hallucinate an authoritative SKU or price.
    assert not hasattr(draft.lines[0], 'resolved_sku')


def test_parser_rejects_incomplete_documents():
    with pytest.raises(PreviewNotPossible):
        preview_purchase_order(filename='bad.txt', data=b'Customer: Northstar\nNo PO number')
    with pytest.raises(PreviewNotPossible):
        preview_purchase_order(filename='bad.txt', data=b'PO Number: X\nCustomer: Northstar\nDeliver To: Cardiff')


def test_state_machine_blocks_illegal_erp_without_validations():
    validate_transition(TransactionStatus.RECEIVED, TransactionStatus.TRIAGED)
    validate_transition(TransactionStatus.FAILED_RETRYABLE, TransactionStatus.RECOVERY_PENDING)
    validate_transition(TransactionStatus.RECOVERY_PENDING, TransactionStatus.ERP_PENDING)
    with pytest.raises(InvalidStateTransition):
        validate_transition(TransactionStatus.RECEIVED, TransactionStatus.ERP_CREATED)
    with pytest.raises(InvalidStateTransition):
        validate_transition(TransactionStatus.COMPLETED, TransactionStatus.ERP_PENDING)


def test_manual_order_rejects_duplicate_line_numbers():
    payload = {'po_number':'PO-DEMO','customer_hint':'Northstar','lines':[
        {'line_number':1,'product_term':'XTR-42','quantity':'1'},
        {'line_number':1,'product_term':'BRK-90','quantity':'3'},
    ]}
    with pytest.raises(ValidationError):
        ManualOrderInput.model_validate(payload)


def test_customer_matching_removes_legal_suffixes_only():
    assert normalize_company_name('Northstar Engineering Ltd') == 'northstar engineering'
    assert normalize_company_name('Northstar Engineering Services Ltd') != 'northstar engineering'

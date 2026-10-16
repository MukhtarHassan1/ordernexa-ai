import io
import zipfile
import pytest

from app.services.intake_service import DocumentNeedsReview, _validate_content_signature


def test_extension_mismatch_is_rejected_before_parser():
    with pytest.raises(DocumentNeedsReview):
        _validate_content_signature('order.pdf', b'not a pdf')
    with pytest.raises(DocumentNeedsReview):
        _validate_content_signature('order.png', b'not a png')


def test_utf8_text_is_allowed_and_binary_text_is_rejected():
    _validate_content_signature('order.txt', b'PO Number: PO-1\n')
    with pytest.raises(DocumentNeedsReview):
        _validate_content_signature('order.txt', b'abc\x00def')


def test_minimal_xlsx_signature_requires_office_structure():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('xl/workbook.xml','<workbook/>')
    _validate_content_signature('order.xlsx',buf.getvalue())
    bad=io.BytesIO()
    with zipfile.ZipFile(bad,'w') as z:z.writestr('random.txt','x')
    with pytest.raises(DocumentNeedsReview):
        _validate_content_signature('order.xlsx',bad.getvalue())

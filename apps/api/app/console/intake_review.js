/* Pure intake response helpers: used by browser + Node regression tests. */
(function (root) {
  'use strict';
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function normalize(value) {
    const envelope = asObject(value);
    const data = asObject(envelope.detail || envelope);
    const details = asObject(data.details);
    const id = data.artifact_id || details.artifact_id || '';
    const transactionId = data.existing_transaction || data.transaction_public_id || '';
    return {
      code: typeof data.code === 'string' ? data.code : '',
      message: typeof data.message === 'string' ? data.message : '',
      artifactId: typeof id === 'string' ? id : '',
      transactionId: typeof transactionId === 'string' ? transactionId : '',
      reviewFlags: Array.isArray(details.review_flags) ? details.review_flags.filter(x => typeof x === 'string') : [],
      correctedFields: Array.isArray(details.corrected_fields) ? details.corrected_fields.filter(x => typeof x === 'string') : [],
      reviewAvailable: details.manual_review_available !== false,
    };
  }
  const descriptions = Object.freeze({
    REVIEW_REQUIRED_NONCANONICAL_AI_CONFIDENCE: 'AI reported a nonstandard confidence value. Confidence alone is not evidence.',
    REVIEW_REQUIRED_SOURCE_CONFLICT_PO_NUMBER: 'The PO number was corrected from the source. Check it against the original.',
    REVIEW_REQUIRED_SOURCE_CONFLICT_CUSTOMER_HINT: 'The customer name differed from the original. Check the exact buyer name.',
    REVIEW_REQUIRED_SOURCE_CONFLICT_REQUESTED_DELIVERY_DATE: 'The AI delivery date differed from the original. Verify the date.',
    REVIEW_REQUIRED_UNTRUSTED_CUSTOMER_DOMAIN: 'An AI-supplied customer domain was discarded. Only verified account metadata can establish identity.',
    REVIEW_REQUIRED_SOURCE_CONFLICT_LINES: 'One or more line items disagreed with the source. Verify quantities, SKUs, and prices.',
    REVIEW_REQUIRED_UNVERIFIED_LINES: 'Line items could not be independently verified from the source.',
    REVIEW_REQUIRED_SUSPICIOUS_DOCUMENT_INSTRUCTIONS: 'The source may contain instructions intended to manipulate the AI. Review the document.'
  });
  function explain(flag) {
    return descriptions[flag] || String(flag).replace(/^REVIEW_REQUIRED_/, '').replaceAll('_', ' ').toLowerCase() + '. Verify against the original.';
  }
  function emptyManualCandidate() {
    return {
      po_number: '', customer_hint: '', customer_domain: null,
      currency: 'GBP', delivery_warehouse_code: '', requested_delivery_date: null,
      lines: [{ line_number: 1, product_term: '', quantity: '1', uom: 'EA', requested_unit_price: null }],
    };
  }
  const exported = { normalize, explain, emptyManualCandidate };
  root.OrderNexaReviewFlow = exported;
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
})(typeof globalThis !== 'undefined' ? globalThis : this);

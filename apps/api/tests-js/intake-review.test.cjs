const assert = require('node:assert/strict');
const test = require('node:test');
const f = require('../app/console/intake_review.js');
test('nested FastAPI review response returns preserved artifact ID and human actions', () => {
 const x = f.normalize({detail:{code:'DOCUMENT_NEEDS_REVIEW',message:'Review required',details:{artifact_id:'5c5bf862-30c1-40c1-a1f2-4b59f37ef015',manual_review_available:true,review_flags:['REVIEW_REQUIRED_SOURCE_CONFLICT_PO_NUMBER']}}});
 assert.equal(x.artifactId,'5c5bf862-30c1-40c1-a1f2-4b59f37ef015');
 assert.equal(x.code,'DOCUMENT_NEEDS_REVIEW');
 assert.equal(x.reviewAvailable,true);
 assert.match(f.explain(x.reviewFlags[0]),/PO number/);
});
test('legacy top-level artifact IDs are recognized', () => {
 assert.equal(f.normalize({code:'MODEL_TIMEOUT',artifact_id:'test'}).artifactId,'test');
});
test('duplicate transactions are exposed without re-upload', () => {
 assert.equal(f.normalize({detail:{code:'DUPLICATE_DOCUMENT',existing_transaction:'TXN-1'}}).transactionId,'TXN-1');
});
test('malformed payload never invents an artifact ID', () => {
 assert.equal(f.normalize({detail:{details:{artifact_id:123}}}).artifactId,'');
});
test('manual fallback contains no invented customer, SKU or warehouse data', () => {
 const candidate = f.emptyManualCandidate();
 assert.equal(candidate.customer_hint,'');
 assert.equal(candidate.customer_domain,null);
 assert.equal(candidate.delivery_warehouse_code,'');
 assert.equal(candidate.lines[0].product_term,'');
});

const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const helpers = require('../app/console/intake_review.js');
const appSource = fs.readFileSync(require.resolve('../app/console/app.js'), 'utf8');

function makeApp({ uploadDetail, previewOk = true }) {
  const elements = new Map(); const requests = []; const state = new Map();
  state.set('ordernexa.operator.key','dummy-test-key');
  function elem(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: true, value:'', files:[], disabled:false, checked:false, classList:{toggle(){}},
      append(...nodes){(this.children ||= []).push(...nodes)}, replaceChildren(){this.children=[]},
      scrollIntoView(){}, focus(){}, onclick:null, textContent:'', innerHTML:'',
    });
    return elements.get(id);
  }
  elem('#document').files=[{ name:'po-test.txt', size:10 }];
  function response(status, detail) { return { ok:status<400, status, text: async()=>JSON.stringify(detail) }; }
  const ctx={
    window:{OrderNexaReviewFlow:helpers,confirm:()=>true,prompt:()=>''},
    sessionStorage:{getItem:k=>state.get(k),setItem:(k,v)=>state.set(k,v)},
    document:{ querySelector:elem, querySelectorAll:()=>[], addEventListener(){},
      createElement:()=>({textContent:'',remove(){},click(){}}),body:{append(){}} },
    fetch: async(url)=>{
      requests.push(url);
      if(url.endsWith('/intake/upload')) return response(422,{detail:uploadDetail});
      if(url.endsWith('/preview')) return previewOk
        ? response(200,{artifact_id:'5c5bf862-30c1-40c1-a1f2-4b59f37ef015',
           source_evidence:['SOURCE_TEXT line 1: PO Number: PO-88192'],
           candidate:{po_number:'PO-88192',customer_hint:'Northstar Engineering Ltd',
             currency:'GBP',delivery_warehouse_code:'MAN',
             lines:[{line_number:1,product_term:'XTR-42',quantity:'40',uom:'EA',requested_unit_price:'260'}]}})
        : response(422,{detail:{code:'INVALID_REVIEW',message:'Unparseable source'}});
      if(url.endsWith('/health/live')) return response(200,{status:'ok'});
      if(url.endsWith('/ops/overview')) return response(200,{total_transactions:0});
      if(url.endsWith('/transactions')) return response(200,[]);
      if(url.endsWith('/ops/pending-approvals')) return response(200,[]);
      if(url.endsWith('/ops/open-incidents')) return response(200,[]);
      return response(404,{detail:'Not found'});
    },
    FormData:class {append(){}}, AbortSignal, Date,
    setTimeout:()=>0,console,
  };
  vm.runInNewContext(appSource,ctx);
  return {elem,requests,state};
}
const errorPayload={
  code:'DOCUMENT_NEEDS_REVIEW',message:'Source conflict',
  details:{artifact_id:'5c5bf862-30c1-40c1-a1f2-4b59f37ef015',
    manual_review_available:true,review_flags:['REVIEW_REQUIRED_SOURCE_CONFLICT_PO_NUMBER']}
};
test('upload saves nested artifact, automatically loads human preview without reupload',async()=>{
  const a=makeApp({uploadDetail:errorPayload});
  await a.elem('#upload-form').onsubmit({preventDefault(){}});
  assert.equal(a.elem('#artifact-id').value,errorPayload.details.artifact_id);
  assert.equal(a.state.get('ordernexa.lastArtifactId'),errorPayload.details.artifact_id);
  assert.equal(a.elem('#review-panel').hidden,false);
  assert.equal(a.elem('#source-proof').hidden,false);
  assert.match(a.elem('#review-candidate').value,/PO-88192/);
  assert.equal(a.requests.filter(x=>x.endsWith('/intake/upload')).length,1);
  assert.equal(a.requests.filter(x=>x.endsWith('/preview')).length,1);
});
test('unparseable source offers explicit manual entry instead of inventing a preview',async()=>{
  const a=makeApp({uploadDetail:errorPayload,previewOk:false});
  await a.elem('#upload-form').onsubmit({preventDefault(){}});
  assert.equal(a.elem('#review-panel').hidden,true);
  a.elem('#artifact-manual').onclick();
  assert.equal(a.elem('#review-panel').hidden,false);
  assert.match(a.elem('#review-candidate').value,/"po_number": ""/);
  assert.equal(a.elem('#review-verified').checked,false);
});
test('duplicate document shows existing transaction rather than retrying Ollama',async()=>{
  const a=makeApp({uploadDetail:{code:'DUPLICATE_DOCUMENT',existing_transaction:'TXN-2026-1'}});
  await a.elem('#upload-form').onsubmit({preventDefault(){}});
  assert.equal(a.elem('#upload-view-transaction').hidden,false);
  assert.match(a.elem('#upload-next-message').textContent,/TXN-2026-1/);
  assert.equal(a.requests.filter(x=>x.endsWith('/preview')).length,0);
});

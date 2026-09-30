/* OrderNexa local demo UI. All figures originate from live backend responses. */
const API='/api/v1';
const $=s=>document.querySelector(s);
let page='overview', transactions=[], artifactId='', currentPreview=null, lastTransactionId='';
const reviewFlow=window.OrderNexaReviewFlow;
const fmtMoney=(n,c='GBP')=>{try{return new Intl.NumberFormat('en-GB',{style:'currency',currency:c,maximumFractionDigits:0}).format(Number(n||0))}catch{return `${c} ${n}`}};
const fmtTime=x=>x?new Date(x).toLocaleString('en-GB',{dateStyle:'medium',timeStyle:'short'}):'—';
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge=x=>{let a=String(x||'UNKNOWN');let cls=/COMPLETED|HEALTHY|VERIFIED|READY|PROCESSED/.test(a)?'good':/FAILED|DEGRADED|UNHEALTHY/.test(a)?'bad':'warn';return `<span class="tag ${cls}">${esc(a.replaceAll('_',' '))}</span>`};
function notify(msg,error=false){let el=$('#flash');el.hidden=false;el.className=`flash${error?' error':''}`;el.textContent=msg;setTimeout(()=>el.hidden=true,8500)}
const getKey=()=>sessionStorage.getItem('ordernexa.operator.key')||'';
async function api(path,{method='GET',body=null,timeout=25000,form=false}={}){
  const h={}; if(getKey())h['X-OrderNexa-Operator-Key']=getKey();
  if(body&&!form)h['Content-Type']='application/json';
  const res=await fetch(`${API}${path}`,{method,headers:h,body:form?body:body?JSON.stringify(body):null,signal:AbortSignal.timeout(timeout)});
  const txt=await res.text();let obj;try{obj=txt?JSON.parse(txt):{}}catch{obj={detail:txt.slice(0,400)}}
  if(!res.ok){let d=obj.detail??obj;let err=new Error(typeof d==='string'?d:(d.message||d.code||`HTTP ${res.status}`));err.data=d;err.http=res.status;throw err}
  return obj;
}
function show(pageName){if(pageName==='intake'&&!$('#artifact-id').value){$('#artifact-id').value=sessionStorage.getItem('ordernexa.lastArtifactId')||'';}page=pageName;document.querySelectorAll('.page').forEach(x=>x.hidden=x.id!==`page-${pageName}`);document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('selected',x.dataset.page===pageName));$('#page-name').textContent=pageName.toUpperCase().replaceAll('-',' ');load(pageName)}
async function load(p){try{if(p==='overview')return overview();if(p==='transactions')return transactionList();if(p==='approvals')return approvals();if(p==='recovery')return incidents();if(p==='health')return integrations();if(['automation','voice','audit'].includes(p))return window.OrderNexaAutomation?.load(p)}catch(e){notify(e.message,true)}}
async function overview(){const [m,t,p,i]=await Promise.all([api('/ops/overview'),api('/transactions'),api('/ops/pending-approvals'),api('/ops/open-incidents')]);transactions=t;
const cards=[['Total transactions',m.total_transactions,'Recorded in transaction digital twin',''],['Order value',fmtMoney(m.total_order_value),'Total of recorded transaction values',''],['Awaiting approval',m.approval_required,`${m.pending_approvals} individual pending decisions`,'warn'],['Blocked revenue',fmtMoney(m.blocked_revenue),'Approval & exception statuses','danger'],['Verified ERP orders',m.verified_erp_orders,'Read-after-write confirmed',''],['Completed',m.completed_transactions,'Local demo completion scope',''],['Open incidents',m.open_incidents,'Real unresolved records','warn'],['Recorded AI decisions',m.ai_decisions,'Not an accuracy measurement','']];
$('#metrics').innerHTML=cards.map(([name,val,foot,cls])=>`<div class="metric ${cls}"><div class="metric-label">${name}</div><div class="metric-value">${val}</div><div class="metric-foot">${foot}</div></div>`).join('');
$('#recent-transactions').innerHTML=t.length?t.slice(0,7).map(x=>`<div class="list-row"><div><strong>${esc(x.public_id)}</strong><small>${esc(x.customer_reference||x.source)} · ${fmtTime(x.created_at)}</small></div><div>${badge(x.status)} <button class="text-button" data-open="${esc(x.public_id)}">Inspect →</button></div></div>`).join(''):'No transactions stored yet.';
$('#attention').innerHTML=`<div class="list-row"><div><strong>${p.length} pending approvals</strong><small>Human decisions requested by deterministic policy</small></div>${badge(p.length?'REQUIRES_ACTION':'CLEAR')}</div><div class="list-row"><div><strong>${i.length} open incidents</strong><small>Checkpoints for safe recovery</small></div>${badge(i.length?'OPEN':'CLEAR')}</div>`;
}
function row(x){return `<tr><td><button class="text-button" data-open="${esc(x.public_id)}">${esc(x.public_id)}</button></td><td>${esc(x.customer_reference||'—')}</td><td>${fmtMoney(x.value,x.currency)}</td><td>${badge(x.status)}</td><td>${fmtTime(x.created_at)}</td></tr>`}
function renderTransactions(){const q=$('#transaction-search').value.toLowerCase(),f=$('#transaction-filter').value;const list=transactions.filter(x=>(!f||x.status===f)&&`${x.public_id} ${x.customer_reference} ${x.status}`.toLowerCase().includes(q));$('#transactions-table').innerHTML=list.length?`<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>TRANSACTION</th><th>CUSTOMER PO</th><th>VALUE</th><th>STATUS</th><th>CREATED</th></tr></thead><tbody>${list.map(row).join('')}</tbody></table></div>`:'No matching transactions';}
async function transactionList(){transactions=await api('/transactions');renderTransactions()}
async function openTransaction(id){show('transactions');const [t,h]=await Promise.all([api(`/c2c/transactions/${encodeURIComponent(id)}`),api(`/transactions/${encodeURIComponent(id)}/timeline`)]);const p=$('#transaction-detail');p.hidden=false;p.innerHTML=`<div class="panel-title">${esc(id)} / Decision inspector ${badge(t.transaction.status)}</div><div class="columns"><div><h3>Policy & authority</h3>${t.policy_decisions.length?t.policy_decisions.map(x=>`<div class="list-row"><div><strong>${esc(x.outcome)}</strong><small>${esc((x.reasons||[]).join(' • '))}</small></div></div>`).join(''):'No policy decision recorded'}<h3>Evidence</h3>${t.evidence.length?t.evidence.map(x=>`<div class="list-row"><div><strong>${esc(x.label)}</strong><small>${esc(x.evidence_type)} · ${esc(x.source_ref)}</small><small>${esc(x.excerpt||'')}</small></div></div>`).join(''):'No evidence stored'}</div><div><h3>Audit timeline</h3>${h.length?h.map(e=>`<div class="list-row"><div><strong>${esc(e.event_type)}</strong><small>${fmtTime(e.created_at)} · ${esc(e.actor_type)}</small></div></div>`).join(''):'No events'}<h3>Checkpoints</h3>${t.checkpoints.map(c=>`<div class="list-row"><strong>${esc(c.step)}</strong>${badge(c.status)}</div>`).join('')}</div></div>`;const buttons = (t.transaction.status === 'READY' ? `<button class="button primary" data-local-erp="${esc(id)}">Create verified Odoo order</button>` : '') +
(t.transaction.status === 'ERP_CREATED' ? `<button class="button secondary" data-local-archive="${esc(id)}">Archive and verify</button>` : '') +
(t.transaction.status === 'COMPLETED' ? `<button class="button primary" data-local-sync="${esc(id)}">Plan external sync</button>` : '');
if(buttons)p.insertAdjacentHTML('beforeend', `<div class="action-footer"><h3>Permitted next operation</h3><p>Only the authorized operator may advance this transaction. Confirm source and policy evidence first.</p>${buttons}</div>`);
p.scrollIntoView({behavior:'smooth',block:'start'})}
async function approvals(){let list=await api('/ops/pending-approvals');$('#approval-list').innerHTML=list.length?list.map(x=>`<div class="card"><div class="card-head"><strong>${esc(x.transaction_public_id)}</strong>${badge('PENDING')}</div><div class="value">${fmtMoney(x.value,x.currency)}</div><p>${esc(x.reason)}</p><small>Required: ${esc(x.approver_role)} · PO ${esc(x.customer_reference)}</small><div class="button-row"><button class="button primary" data-approve="${esc(x.approval_id)}">Approve</button><button class="button secondary" data-reject="${esc(x.approval_id)}">Reject</button><button class="button secondary" data-open="${esc(x.transaction_public_id)}">Evidence</button><button class="button secondary" data-teams-approval="${esc(x.transaction_public_id)}">Notify Teams</button></div></div>`).join(''):'<div class="panel">No pending approvals are stored.</div>'}
async function decide(id,decision){if(!getKey())return notify('Configure an operator key first.',true);const note=window.prompt(`${decision} this approval? Record your business reason:`,decision==='APPROVE'?'Reviewed policy and evidence.':'Insufficient authority or evidence.');if(note===null)return;if(!note.trim())return notify('A business reason is required.',true);if(!window.confirm(`${decision} this approval? This will be audited.`))return;try{const d=await api(`/execution/approvals/${id}/decision`,{method:'POST',body:{decision,approver_role:'SERVER_OVERRIDE',actor_id:'SERVER_OVERRIDE',note}});notify(`Approval recorded. Transaction status: ${d.transaction_status}`);await approvals()}catch(e){notify(e.message,true)}}
async function incidents(){const list=await api('/ops/open-incidents');$('#incident-list').innerHTML=list.length?list.map(i=>`<div class="card"><div class="card-head"><strong>${esc(i.transaction_public_id)}</strong>${badge(i.severity)}</div><h3>${esc(i.category)}</h3><p>${esc(i.message)}</p><div class="button-row"><button class="button primary" data-recover="${esc(i.transaction_public_id)}">Recover verified checkpoint</button><button class="button secondary" data-open="${esc(i.transaction_public_id)}">Inspect</button></div></div>`).join(''):'<div class="panel">No open incidents are stored.</div>'}
async function recover(id){if(!window.confirm(`Recover ${id} from its verified downstream checkpoint? This should NOT recreate an ERP order.`))return;try{let result=await api(`/execution/transactions/${encodeURIComponent(id)}/recover`,{method:'POST',body:{}});notify(`${id}: ${result.status}`);incidents()}catch(e){notify(e.message,true)}}
async function integrations(){const [i,q]=await Promise.all([api('/ops/integration-health'),api('/ops/ai-quality')]);$('#dependencies').innerHTML=i.dependencies.map(d=>`<div class="list-row"><div><strong>${esc(d.name)}</strong><small>${esc(d.detail||'')}</small></div>${badge(d.status)}</div>`).join('');$('#quality-snapshot').textContent=`Recorded decisions: ${q.recorded_ai_decisions}  •  Non-accepted decisions: ${q.non_accepted_decisions}\nCurated field accuracy: ${q.field_accuracy??'Not evaluated'}`;await window.OrderNexaAutomation?.evaluationReports?.()}
async function probe(){let btn=$('#probe-ai');btn.disabled=true;$('#probe-result').hidden=false;$('#probe-result').textContent='Performing a real (short) inference test…';try{const r=await api('/ops/ai-inference-probe',{method:'POST',body:{},timeout:210000});$('#probe-result').textContent=JSON.stringify(r,null,2);notify(`Real model generated successfully in ${r.elapsed_seconds}s.`)}catch(e){$('#probe-result').textContent=JSON.stringify(e.data||{message:e.message},null,2);notify('Model inference did not become ready. Review Ollama diagnostics.',true)}finally{btn.disabled=false}}
function rememberArtifact(id){
  if(typeof id!=='string'||!id)return;
  artifactId=id; $('#artifact-id').value=id;
  // UUID only. Never persist original documents, candidate data, or operator keys.
  sessionStorage.setItem('ordernexa.lastArtifactId',id);
}
function nextStep(title,message,flags=[],transactionId=''){
  const box=$('#upload-next-step');box.hidden=false;
  $('#upload-next-title').textContent=title;
  $('#upload-next-message').textContent=message;
  $('#upload-review-reasons').replaceChildren();
  flags.forEach(flag=>{const li=document.createElement('li');li.textContent=reviewFlow.explain(flag);$('#upload-review-reasons').append(li)});
  $('#upload-go-review').hidden=!artifact();
  $('#upload-view-transaction').hidden=!transactionId;
  if(transactionId)lastTransactionId=transactionId;
}
async function loadArtifactPreview(id,{automatic=false}={}){
  rememberArtifact(id);
  const p=$('#artifact-response');p.hidden=false;
  try {
    p.textContent='Loading saved source evidence…';
    const d=await api(`/intake/artifacts/${encodeURIComponent(id)}/preview`);
    currentPreview=d;
    $('#review-panel').hidden=false;
    $('#review-candidate').value=JSON.stringify(d.candidate,null,2);
    $('#review-verified').checked=false;
    $('#source-proof').hidden=!Array.isArray(d.source_evidence)||!d.source_evidence.length;
    $('#review-evidence').textContent=(d.source_evidence||[]).join('\n');
    $('#review-guidance').textContent='Check EVERY field against the saved original. Source evidence is for assistance only. An authorized human must confirm.';
    p.textContent='Deterministic preview loaded from the saved original (not AI). Review every value before submitting.';
    $('#review-panel').scrollIntoView({behavior:'smooth',block:'start'});
    return d;
  }catch(err){
    currentPreview=null;
    $('#review-panel').hidden=true;
    p.textContent=JSON.stringify(err.data||{message:err.message},null,2);
    if(automatic)notify('Saved artifact is safe, but this format cannot be prefilled. Download the original and use manual entry.',false);
    else notify(err.message,true);
    return null;
  }
}
async function reviewError(err){
  const info=reviewFlow.normalize(err.data||{});
  if(info.artifactId)rememberArtifact(info.artifactId);
  if(info.code==='DOCUMENT_NEEDS_REVIEW'&&info.artifactId&&info.reviewAvailable){
    nextStep('DOCUMENT SAVED — REVIEW REQUIRED',
      `Ollama finished, but source checks rejected unverified or conflicting claims. Artifact: ${info.artifactId}. NO order or ERP write has been authorized. Review this saved artifact instead of uploading again.`,
      info.reviewFlags);
    notify('Source conflicts identified. Original saved; opening review instead of repeating AI.',false);
    await loadArtifactPreview(info.artifactId,{automatic:true});
    return true;
  }
  if(info.code==='DUPLICATE_DOCUMENT'&&info.transactionId){
    nextStep('ALREADY PROCESSED — DO NOT REUPLOAD',
      `A transaction already exists: ${info.transactionId}. Open it to inspect its current state.`,[],info.transactionId);
    notify('Existing transaction found; no second document was created.',false);
    return true;
  }
  if(info.code==='ARTIFACT_BUSY'&&info.artifactId){
    nextStep('DOCUMENT STILL PROCESSING',
      `Artifact ${info.artifactId} is processing. Check its status instead of retrying.`,[]);
    return true;
  }
  if(info.artifactId){
    nextStep('ORIGINAL DOCUMENT SAVED',
      `Artifact ${info.artifactId}. The AI could not complete safely; check status, download the original, or review manually.`,[]);
    return true;
  }
  return false;
}
async function upload(e){
  e.preventDefault();
  if(!getKey())return notify('Set the operator key first.',true);
  const file=$('#document').files[0];if(!file)return;
  const button=$('#upload-form button[type=submit]');button.disabled=true;
  $('#upload-next-step').hidden=true;
  const f=new FormData();f.append('file',file);
  const pre=$('#upload-response');pre.hidden=false;
  pre.textContent='Uploading once; Ollama inference and source verification in progress…';
  try{
    const result=await api('/intake/upload',{method:'POST',body:f,form:true,timeout:330000});
    pre.textContent=JSON.stringify(result,null,2);
    rememberArtifact(result.artifact_id);
    const id=result.transaction?.public_id;
    if(id)nextStep('TRANSACTION CREATED',
      `Transaction ${id} is in status ${result.transaction.status}. Inspect policy and evidence before ERP execution.`,[],id);
    notify(id?`${id}: ${result.transaction.status}`:'Document processed.');
  }catch(err){
    pre.textContent=JSON.stringify(err.data||{message:err.message},null,2);
    if(!await reviewError(err))notify(err.message,true);
  }finally{button.disabled=false}
}
const artifact=()=>$('#artifact-id').value.trim();
async function doArtifact(action){
  if(!artifact())return notify('Enter an artifact UUID first.',true);
  const id=artifact();rememberArtifact(id);
  const pre=$('#artifact-response');pre.hidden=false;pre.textContent='Loading…';
  if(action==='preview')return loadArtifactPreview(id);
  try{
    let d;
    if(action==='status'){
      d=await api(`/intake/artifacts/${encodeURIComponent(id)}`);
      if(d.transaction_public_id){nextStep('ALREADY ATTACHED TO TRANSACTION',
        `Artifact ${id} belongs to ${d.transaction_public_id}. No duplicate upload is needed.`,[],d.transaction_public_id);}
    }
    if(action==='retry')d=await api(`/intake/artifacts/${encodeURIComponent(id)}/retry`,{method:'POST',body:{},timeout:330000});
    pre.textContent=JSON.stringify(d,null,2);
    if(d.artifact_id)rememberArtifact(d.artifact_id);
    if(d.transaction?.public_id){nextStep('TRANSACTION CREATED',
      `Transaction ${d.transaction.public_id} is in status ${d.transaction.status}. Inspect it before any execution.`,[],d.transaction.public_id);}
    notify(`Artifact ${action} completed.`);
  }catch(e){
    pre.textContent=JSON.stringify(e.data||{message:e.message},null,2);
    if(!await reviewError(e))notify(e.message,true);
  }
}
function startManualEntry(){
  if(!artifact())return notify('Enter a saved artifact ID first.',true);
  if(!getKey())return notify('Configure your authorized operator key first.',true);
  if(!window.confirm('Manual entry requires that you download and read the original document. Continue?'))return;
  currentPreview={artifact_id:artifact(),method:'EXPLICIT_MANUAL_ENTRY'};
  $('#review-panel').hidden=false;
  $('#review-candidate').value=JSON.stringify(reviewFlow.emptyManualCandidate(),null,2);
  $('#review-verified').checked=false;
  $('#source-proof').hidden=true;
  $('#review-guidance').textContent='EXPLICIT MANUAL ENTRY: No source parsing is assumed. Download and read the original. Enter ALL required data, and verify every field; do not invent unavailable values.';
  $('#review-panel').scrollIntoView({behavior:'smooth',block:'start'});
}
async function downloadOriginal(){
  if(!artifact())return notify('Enter a saved artifact ID first.',true);
  if(!getKey())return notify('Configure your authorized operator key first.',true);
  try{
    const res=await fetch(`${API}/intake/artifacts/${encodeURIComponent(artifact())}/original`,{
      headers:{'X-OrderNexa-Operator-Key':getKey()},signal:AbortSignal.timeout(30000)});
    if(!res.ok){let d=await res.json().catch(()=>({}));throw Error(d.detail?.message||d.detail||`HTTP ${res.status}`)}
    const cd=res.headers.get('Content-Disposition')||'';
    const match=cd.match(/filename="([A-Za-z0-9._-]+)"/);
    const filename=match?.[1]||`saved-source-${artifact()}`;
    const url=URL.createObjectURL(await res.blob());
    const a=document.createElement('a');a.href=url;a.download=filename;
    document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),2000);
    notify('Original downloaded. Compare it with every proposed field.');
  }catch(e){notify(`Cannot download original: ${e.message}`,true)}
}
async function confirmReview(){
  if(!$('#review-verified').checked)return notify('You must verify the original source document.',true);
  if(!currentPreview?.artifact_id||currentPreview.artifact_id!==artifact())return notify('Preview this artifact or select explicit manual entry before confirming.',true);
  const btn=$('#review-submit');
  try{
    const candidate=JSON.parse($('#review-candidate').value);
    if(!window.confirm('Submit human-verified fields to deterministic business validation? This creates a transaction.'))return;
    btn.disabled=true;
    const d=await api(`/intake/artifacts/${encodeURIComponent(artifact())}/human-confirm`,{method:'POST',body:candidate,timeout:60000});
    $('#review-response').hidden=false;
    $('#review-response').textContent=JSON.stringify(d,null,2);
    if(d.public_id){lastTransactionId=d.public_id;$('#review-open-transaction').hidden=false;
      nextStep('HUMAN-VERIFIED TRANSACTION CREATED',
        `${d.public_id}: ${d.status}. Review customer/SKU resolution, pricing, inventory, credit and approvals.`,[],d.public_id);}
    notify(`${d.public_id}: validation recorded. Continue from the transaction, not another upload.`);
  }catch(e){
    $('#review-response').hidden=false;
    $('#review-response').textContent=JSON.stringify(e.data||{message:e.message},null,2);
    const info=reviewFlow.normalize(e.data||{});
    if(info.transactionId){lastTransactionId=info.transactionId;$('#review-open-transaction').hidden=false;
      notify(`Transaction ${info.transactionId} requires further identity or product resolution. Inspect it.`,false);}
    else notify(e.message,true);
  }finally{btn.disabled=false}
}
async function checkLive(){try{let r=await api('/health/live');$('#live-status').textContent=r.status==='ok'?'API ONLINE':'API WARNING';$('#live-status').className='pill '+(r.status==='ok'?'good':'bad')}catch{$('#live-status').textContent='API UNAVAILABLE';$('#live-status').className='pill bad'}}
document.addEventListener('click',e=>{let t=e.target.closest('[data-page],[data-open],[data-approve],[data-reject],[data-recover]');if(!t)return;if(t.dataset.page)show(t.dataset.page);if(t.dataset.open)openTransaction(t.dataset.open).catch(err=>notify(err.message,true));if(t.dataset.approve)decide(t.dataset.approve,'APPROVE');if(t.dataset.reject)decide(t.dataset.reject,'REJECT');if(t.dataset.recover)recover(t.dataset.recover)});
$('#refresh').onclick=()=>{load(page);checkLive()};$('#transaction-search').oninput=renderTransactions;$('#transaction-filter').onchange=renderTransactions;
$('#upload-form').onsubmit=upload;$('#artifact-status').onclick=()=>doArtifact('status');$('#artifact-preview').onclick=()=>doArtifact('preview');$('#artifact-retry').onclick=()=>doArtifact('retry');$('#artifact-download').onclick=downloadOriginal;$('#artifact-manual').onclick=startManualEntry;$('#upload-go-review').onclick=()=>loadArtifactPreview(artifact());$('#upload-view-transaction').onclick=()=>lastTransactionId&&openTransaction(lastTransactionId).catch(e=>notify(e.message,true));$('#review-open-transaction').onclick=()=>lastTransactionId&&openTransaction(lastTransactionId).catch(e=>notify(e.message,true));$('#review-submit').onclick=confirmReview;$('#probe-ai').onclick=probe;
$('#configure-key').onclick=()=>{$('#modal').hidden=false;$('#operator-key').value='';$('#operator-key').focus()};$('#modal-cancel').onclick=()=>$('#modal').hidden=true;$('#modal-save').onclick=()=>{const k=$('#operator-key').value.trim();if(!k){notify('Enter a key.',true);return}sessionStorage.setItem('ordernexa.operator.key',k);$('#modal').hidden=true;notify('Operator key set for this tab only.')};
$('#footer-clock').textContent=new Date().toLocaleDateString('en-GB');$('#artifact-id').value=sessionStorage.getItem('ordernexa.lastArtifactId')||'';checkLive();load('overview');

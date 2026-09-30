/* OrderNexa automation console extension. Never invents transaction completion. */
(() => {
  const el = id => document.getElementById(id);
  const html = value => esc(value);
  const ready = bool => bool ? '<span class="tag good">Configured</span>' : '<span class="tag warn">Not configured</span>';
  async function evaluationReports() {
    const holder = el('evaluation-runs');
    if (!holder) return;
    if (!getKey()) {holder.textContent = 'Configure operator access to read saved benchmark reports.'; return;}
    const data = await api('/ops/evaluation-reports');
    holder.innerHTML = !data.items.length ? '<p>No real model evaluation results have been recorded. Run the labeled evaluator; do not interpret offline parser tests as model accuracy.</p>' : data.items.slice(0, 8).map(x =>
      `<div class="list-row"><div><strong>${html(x.file)} · ${html(x.cases)} cases</strong><small>${html(x.provider)} · ${fmtTime(x.run_at)} · ${html(x.dataset)}</small><small>Raw model: ${x.raw_model_field_accuracy == null ? 'not measured' : (x.raw_model_field_accuracy * 100).toFixed(1) + '%'} | Source-grounded: ${x.source_grounded_accuracy == null ? 'not measured' : (x.source_grounded_accuracy * 100).toFixed(1) + '%'} | Safety: ${x.safety_pass_rate == null ? 'not measured' : (x.safety_pass_rate * 100).toFixed(1) + '%'}</small></div>${badge(x.critical_gate_pass ? 'GATE_PASS' : 'GATE_NOT_PASSED')}</div>`).join('');
  }
  async function configuration() {
    const cfg = await api('/automation/configuration');
    el('automation-config').innerHTML = [
      ['Background worker enabled', cfg.worker_enabled],
      ['Explicit external writes', cfg.external_writes_enabled],
      ['Microsoft Graph / Outlook', cfg.graph_configured],
      ['SharePoint drive', cfg.sharepoint_configured],
      ['HubSpot', cfg.hubspot_configured],
      ['Teams Workflows', cfg.teams_configured],
      ['n8n intake', cfg.n8n_configured],
      ['Voice service', cfg.voice_configured],
      ['Human-reviewed email drafts', cfg.customer_email_enabled],
    ].map(([title, active]) => `<div class="list-row"><strong>${html(title)}</strong>${ready(active)}</div>`).join('');
  }
  async function jobs() {
    const data = await api('/automation/jobs?limit=80');
    el('automation-jobs').innerHTML = !data.items.length ? '<p>No automation jobs recorded yet.</p>' :
      `<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>TYPE</th><th>STATUS</th><th>REFERENCE</th><th>ATTEMPTS</th><th>LAST RESULT</th><th>ACTION</th></tr></thead><tbody>${data.items.map(x => {
        const canPreview = x.kind === 'OUTLOOK_DRAFT' && x.status === 'VERIFIED';
      const canReview = x.status === 'REVIEW_REQUIRED' && Boolean(x.result.artifact_id);
      const canRetry = ['BLOCKED_CONFIG', 'FAILED_MANUAL'].includes(x.status) && !['OUTLOOK_DRAFT', 'TEAMS_NOTIFY'].includes(x.kind);
        return `<tr><td><strong>${html(x.kind)}</strong></td><td>${badge(x.status)}</td><td>${html(x.result.transaction_public_id || x.transaction_id || '—')}</td><td>${html(x.attempt_count)}</td><td><small>${html(x.last_error || x.result.message || '—')}</small></td><td>${canRetry ? `<button class="button secondary" data-job-retry="${html(x.id)}">Retry once resolved</button>` : canPreview ? `<button class="button primary" data-outlook-preview="${html(x.id)}">Review draft → Send</button>` : canReview ? `<button class="button primary" data-artifact-review="${html(x.result.artifact_id)}">Review saved artifact</button>` : html(x.status === 'BLOCKED_UNCERTAIN' ? 'Remote reconciliation required' : '—')}</td></tr>`;
      }).join('')}</tbody></table></div>`;
  }
  async function voice() {
    const data = await api('/automation/voice/requests');
    el('voice-requests').innerHTML = !data.items.length ? '<div class="panel">No voice change requests recorded.</div>' :
      data.items.map(x => `<div class="card"><div class="card-head"><strong>${html(x.request_type)}</strong>${badge(x.status)}</div><small>Request ${html(x.id)} · ${fmtTime(x.created_at)}</small><p>${html(x.request_note)}</p><small>Internal transaction: ${html(x.transaction_id)}</small><div class="button-row">${x.status === 'PENDING_VERIFICATION' ? `<button class="button secondary" data-voice-decision="ACKNOWLEDGED" data-voice-id="${html(x.id)}">Acknowledge after caller verification</button><button class="button secondary" data-voice-decision="DECLINED" data-voice-id="${html(x.id)}">Decline</button>` : ''}</div></div>`).join('');
  }
  async function audit() {
    const id = el('audit-public-id').value.trim();
    if (!/^TXN-[0-9]{4}-[0-9]{6}$/.test(id)) return notify('Provide a valid public transaction ID.', true);
    el('audit-events').textContent = 'Loading event hashes…';
    const data = await api(`/automation/audit/${encodeURIComponent(id)}`);
    el('audit-events').innerHTML = !data.events.length ? 'No events stored.' : data.events.map(e => `<div class="list-row"><div><strong>${html(e.event_type)}</strong><small>${html(e.step)} · ${html(e.actor_type)} · ${fmtTime(e.timestamp)}</small><small class="hash-small">Payload SHA-256: ${html(e.payload_hash)} · Trace: ${html(e.trace_id)}</small></div></div>`).join('');
  }
  async function queue(e) {
    e.preventDefault();
    if (!getKey()) return notify('Configure your operations-manager key first.', true);
    const id = el('sync-public-id').value.trim();
    if (!/^TXN-[0-9]{4}-[0-9]{6}$/.test(id)) return notify('Provide a valid public transaction ID.', true);
    const body = {
      verified_contact_email: el('sync-email').value.trim() || null,
      sharepoint: el('sync-sharepoint').checked,
      hubspot: el('sync-hubspot').checked,
      outlook_draft: el('sync-outlook').checked,
      teams_notify: el('sync-teams').checked,
      confirm_external_data_transfer: el('sync-authorized').checked,
    };
    if (!body.confirm_external_data_transfer) return notify('You must authorize each external transfer.', true);
    if (!window.confirm(`Queue external synchronization for ${id}? Each step requires verified source data and configuration.`)) return;
    const result = await api(`/automation/transactions/${encodeURIComponent(id)}/schedule`, {method:'POST', body});
    const pre = el('sync-result');pre.hidden = false;pre.textContent = JSON.stringify(result, null, 2);
    notify('Durable jobs created. Queued does not mean delivered.');
    await jobs();
  }
  async function retry(id) {
    if (!window.confirm('Have you corrected the dependency and checked that no external side effect was duplicated?')) return;
    await api(`/automation/jobs/${encodeURIComponent(id)}/retry`, {method:'POST', body:{}});
    notify('Job made eligible for processing; no direct external write was made from the browser.');
    await jobs();
  }
  async function outlookPreview(id) {
    const draft = await api(`/automation/jobs/${encodeURIComponent(id)}/outlook-preview`);
    if (!window.confirm(`REVIEW UNSENT DRAFT\nRecipient: ${draft.recipient}\nSubject: ${draft.subject}\n\n${draft.body}\n\nOnly proceed if the recipient, subject, and body are approved. This can send real customer email ONCE.`)) return;
    if (!window.confirm('FINAL CONFIRMATION: Release this exact draft for sending? Do not repeat if the response is uncertain.')) return;
    const res = await api(`/automation/jobs/${encodeURIComponent(id)}/send-outlook`, {method:'POST', body:{preview_sha256:draft.preview_sha256, confirm_send_once:true}, timeout:60000});
    notify(res.notice || res.status);
    await jobs();
  }
  async function voiceReview(id, decision) {
    const note = window.prompt(`${decision} request. State how you verified the caller, or why the request was declined:`);
    if (!note || note.trim().length < 3) return notify('A substantive review note is required.', true);
    await api(`/automation/voice/requests/${encodeURIComponent(id)}/decision`, {method:'POST', body:{decision, note}});
    notify('Review decision recorded; underlying order was not modified.');
    await voice();
  }
  async function localExecution(id, step) {
    if (!getKey()) return notify('Configure the role-appropriate operator key.', true);
    let path, body = {};
    if (step === 'erp') {
      path = `/execution/transactions/${encodeURIComponent(id)}/erp`;
      if (!window.confirm('Customer, SKU, pricing, inventory, credit, AND role approvals verified? Create at most one Odoo order?')) return;
    } else if (step === 'archive') {
      path = `/execution/transactions/${encodeURIComponent(id)}/downstream`;
      body = {simulate_failure:false};
      if (!window.confirm('Archive and verify the existing Odoo order without repeating ERP creation?')) return;
    } else {
      el('sync-public-id').value = id;
      return show('automation');
    }
    const result = await api(path, {method:'POST', body, timeout:70000});
    notify(`${id}: ${result.status || result.external_order_name || 'Operation returned.'}`);
    await openTransaction(id);
  }
  window.OrderNexaAutomation = {evaluationReports, load: async section => {
    try {
      if (!getKey()) return notify('Configure authorized operator access to inspect automation and audit records.', true);
      if (section === 'automation') await Promise.all([configuration(), jobs()]);
      if (section === 'health') await evaluationReports();
      if (section === 'voice') await voice();
      if (section === 'audit') {
        if (!el('audit-public-id').value && lastTransactionId) el('audit-public-id').value = lastTransactionId;
      }
    } catch (err) {notify(err.message, true)}
  }};
  el('external-sync-form').addEventListener('submit', ev => queue(ev).catch(err => notify(err.message, true)));
  el('jobs-refresh').addEventListener('click', () => jobs().catch(err => notify(err.message, true)));
  el('audit-load').addEventListener('click', () => audit().catch(err => notify(err.message, true)));
  document.addEventListener('click', ev => {
    const target = ev.target.closest('[data-job-retry],[data-voice-id],[data-local-erp],[data-local-archive],[data-local-sync],[data-teams-approval],[data-outlook-preview],[data-artifact-review]');
    if (!target) return;
    if (target.dataset.teamsApproval) {if(window.confirm('Queue one Teams notification? Approval remains protected in the web console.')) api(`/automation/transactions/${encodeURIComponent(target.dataset.teamsApproval)}/notify-approvals`,{method:'POST',body:{}}).then(()=>notify('Approval notification queued (delivery unverified).')).catch(err=>notify(err.message,true));}
    if (target.dataset.artifactReview) {document.getElementById('artifact-id').value = target.dataset.artifactReview; sessionStorage.setItem('ordernexa.lastArtifactId', target.dataset.artifactReview); show('intake'); document.getElementById('artifact-preview').click();}
    if (target.dataset.outlookPreview) outlookPreview(target.dataset.outlookPreview).catch(err=>notify(err.message,true));
    if (target.dataset.jobRetry) retry(target.dataset.jobRetry).catch(err=>notify(err.message,true));
    if (target.dataset.voiceId) voiceReview(target.dataset.voiceId, target.dataset.voiceDecision).catch(err=>notify(err.message,true));
    for (const [key, action] of [['localErp','erp'], ['localArchive','archive'], ['localSync','sync']]) {
      if (target.dataset[key]) localExecution(target.dataset[key], action).catch(err=>notify(err.message,true));
    }
  });
})();

/* Client lead search: durable jobs, incremental results, cancellation, recovery. */
(() => {
  const terminal = new Set(['completed', 'partial', 'cancelled', 'failed', 'interrupted']);
  const storageKey = 'aryan-active-search-v2';
  let activeId = null;
  let polling = false;
  let platform = false;
  let lastEventCount = 0;
  const oldRender = renderTable;
  const oldRun = runLeadGen;
  const oldExportVerify = verifyLeadsBeforeXlsxExport;
  const panel = document.createElement('section');
  panel.className = 'search-status-panel';
  panel.setAttribute('aria-live', 'polite');
  panel.innerHTML = `<div class="search-status-heading"><div><span class="search-eyebrow">YOUR NEXT OPPORTUNITY</span><h2 id="search-status-title">Find companies you can contact.</h2></div><button id="cancel-search" hidden>Stop search</button></div><p id="search-status-copy">Choose a business category and location. We search, check company websites, and find the best available contact routes.</p><div class="search-meter"><span id="search-meter-fill"></span></div><div class="search-status-footer"><span id="search-coverage">Ready when you are</span><span>Location checked · Company deduplicated · Sources included</span></div><label class="search-export-option"><input id="smtp-before-export" type="checkbox"> Run additional mailbox checks before export (slower)</label>`;
  const tableSection = document.getElementById('leads-tbody').closest('section');
  tableSection.id = 'client-results';
  tableSection.before(panel);
  const cancelBtn = document.getElementById('cancel-search');
  const statusTitle = document.getElementById('search-status-title');
  const statusCopy = document.getElementById('search-status-copy');
  const coverage = document.getElementById('search-coverage');

  // Advanced controls stay available without dominating the client workflow.
  for (const id of ['obs-discovered', 'cookie-input', 'log-container']) {
    const section = document.getElementById(id)?.closest('section');
    if (!section) continue;
    const details = document.createElement('details');
    details.className = 'search-advanced';
    const summary = document.createElement('summary');
    summary.textContent = id === 'obs-discovered' ? 'Search details & sources' : id === 'cookie-input' ? 'Optional LinkedIn connection' : 'Search activity';
    section.before(details);
    details.append(summary, section);
  }
  const verifiedCard = verifiedCount.parentElement.querySelector('div');
  if (verifiedCard) verifiedCard.textContent = 'Email confirmed';
  leadsCount.parentElement.parentElement.classList.add('client-metrics');
  leadCountInput.max = '50';
  roleInput.value = '';
  roleInput.placeholder = 'Optional; company contacts by default';
  const oldSetMode = setMode;
  setMode = function (mode) {
    platform = ['generic', 'velit'].includes(mode) && platform;
    oldSetMode(mode);
    panel.style.display = mode === 'vento' ? 'none' : '';
    leadCountInput.max = mode === 'generic' ? '50' : mode === 'velit' ? '100' : '200';
    roleInput.parentElement.hidden = mode === 'generic';
    if (mode === 'generic') roleInput.value = '';
  };
  roleInput.parentElement.hidden = state.mode === 'generic';
  industryInput.placeholder = 'e.g. SaaS Development, Accountants, Digital Marketing';
  document.body.classList.add('client-lead-platform');

  function safeUrl(value) {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; }
  }
  function link(value, label) {
    const url = safeUrl(value);
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : '';
  }
  function checkedEmail(lead) { return lead.email_smtp_verified === true || lead.email_verification?.smtp_verified === true; }

  renderTable = function () {
    if (!platform || !['generic', 'velit'].includes(state.mode)) return oldRender();
    const empty = document.getElementById('empty-state');
    empty.classList.toggle('hidden', state.leads.length > 0);
    [...leadsTbody.querySelectorAll('tr:not(#empty-state)')].forEach(row => row.remove());
    const headers = ['Company', 'Contact', 'Quality', 'Location', 'Evidence', 'Actions'];
    document.querySelectorAll('#leads-table-head-row th').forEach((cell, i) => { if (i) cell.textContent = headers[i - 1]; });
    state.leads.forEach((lead, index) => {
      const row = document.createElement('tr');
      row.className = 'lead-row client-lead-row';
      const confirmed = checkedEmail(lead);
      const emailLabel = confirmed ? 'Email confirmed' : lead.contact_email ? (lead.email_mx_found ? 'Mail server found · delivery unconfirmed' : 'Email delivery unconfirmed') : 'No email found';
      row.innerHTML = `<td><input type="checkbox" class="lead-checkbox" data-id="${escapeHtml(lead.company_name)}" ${state.selectedIds.has(lead.company_name) ? 'checked' : ''} aria-label="Select ${escapeHtml(lead.company_name)}"></td>
        <td><strong>${escapeHtml(lead.company_name)}</strong><div class="client-subtext">${link(lead.company_website, new URL(safeUrl(lead.company_website) || 'https://invalid.example').hostname)}</div><span class="client-category">${escapeHtml(lead.industry || '')}</span></td>
        <td><div class="client-email">${escapeHtml(lead.contact_email || 'Email not found')}</div><div>${escapeHtml(lead.contact_phone || '')}</div><div class="client-subtext">${lead.contact_person_name ? escapeHtml(lead.contact_person_name + (lead.contact_person_title ? ' · ' + lead.contact_person_title : '')) : 'Company contact'}</div>${lead.contact_page ? link(lead.contact_page, 'Contact page ↗') : ''} ${(lead.whatsapp_urls || []).slice(0, 1).map(url => link(url, 'WhatsApp ↗')).join('')}</td>
        <td><span class="client-quality">${Number(lead.quality_score || 0)}/100</span><div class="client-subtext">${lead.usable && !lead.rejected ? 'Usable company lead' : 'Review required'}</div><span class="client-email-status ${confirmed ? 'confirmed' : ''}">${escapeHtml(emailLabel)}</span></td>
        <td><strong>${escapeHtml(lead.location || '')}</strong><div class="client-subtext">${lead.location_match ? 'Website evidence found' : 'Location unconfirmed'}</div></td>
        <td><details class="client-evidence"><summary>Why this lead?</summary><p>${escapeHtml(lead.industry_evidence || lead.value_proposition || '')}</p><p>${escapeHtml(lead.location_evidence || '')}</p>${(lead.source_details || []).slice(0, 5).map(source => link(source.url, 'Source ↗')).join(' ')}</details></td>
        <td>${lead.contact_email ? `<button class="client-verify" data-index="${index}">${lead.verifying ? 'Checking…' : 'Verify email'}</button>` : ''}<div class="client-subtext">${lead.checked_at ? new Date(lead.checked_at).toLocaleDateString() : ''}</div></td>`;
      const verifyButton = row.querySelector('.client-verify');
      if (verifyButton) {
        verifyButton.disabled = state.running || lead.verifying;
        verifyButton.addEventListener('click', () => verifyLead(lead));
      }
      leadsTbody.append(row);
    });
    leadsCount.textContent = state.leads.length;
    usableCount.textContent = state.leads.filter(lead => lead.usable && !lead.rejected).length;
    verifiedCount.textContent = state.leads.filter(checkedEmail).length;
    updateSelectedCount();
  };

  verifyLeadsBeforeXlsxExport = async function (leads, label) {
    if (platform && ['generic', 'velit'].includes(state.mode) && !document.getElementById('smtp-before-export').checked) return leads.map(lead => ({ ...lead, verifying: false }));
    return oldExportVerify(leads, label);
  };

  async function api(url, options) {
    const response = await fetch(url, options);
    let data;
    try { data = await response.json(); } catch { throw new Error('The server response could not be read. Please retry.'); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Search could not be started. Check your inputs and try again.');
    return data;
  }

  function showJob(job) {
    platform = true;
    activeId = job.id;
    const result = job.result || { leads: [], metadata: {} };
    const meta = result.metadata || {};
    const done = terminal.has(job.status);
    state.leads = (result.leads || []).map(lead => ({ ...lead }));
    state.lastRunJson = job;
    state.lastRunFilename = `lead-search-${job.id.slice(0, 8)}.json`;
    viewRunJsonBtn.disabled = false;
    downloadRunJsonBtn.disabled = false;
    const target = job.request.target_count;
    statusTitle.textContent = done ? (meta.stop_reason === 'target_reached' ? `${state.leads.length} company leads ready.` : `${state.leads.length} of ${target} leads found.`) : `${state.leads.length} of ${target} leads found`;
    const latest = (result.steps || []).at(-1)?.message;
    const finalCopy = job.status === 'cancelled' ? 'Search stopped. Your results are preserved and ready to export.' : job.status === 'interrupted' ? 'The server restarted. Saved results are available; start a new search to continue.' : job.status === 'failed' ? 'The search could not finish. Saved results are preserved. Please retry.' : meta.shortfall ? `Found ${state.leads.length} matching companies within this search's limits. Try a broader location or category for more. We do not add out-of-location companies to fill the count.` : 'Company websites and contact routes checked. Email delivery remains unconfirmed unless explicitly marked confirmed.';
    const warnings = [...(meta.warnings || []), ...(done && (meta.quality_policy_version || 0) < 3 ? ['These saved results predate the latest quality checks. Start a new search to apply them.'] : [])].join(' ');
    statusCopy.textContent = done ? `${finalCopy}${warnings ? ' ' + warnings : ''}` : latest || 'Your search is queued and will start shortly.';
    const credits = meta.provider_usage?.tavily;
    coverage.textContent = `${meta.checked_targets || 0} companies checked · ${(meta.queries_used || []).length} searches · ${Math.round(meta.elapsed_seconds || 0)}s${credits ? ` · ${credits.reported_credits ?? 0} Tavily credits${credits.complete ? '' : ' (partial usage)'}` : ''}`;
    document.getElementById('search-meter-fill').style.width = `${Math.min(100, state.leads.length / target * 100)}%`;
    cancelBtn.hidden = done;
    setBusy(!done);
    [industryInput, locationInput, leadCountInput, roleInput, btnModeGeneric, btnModeVelit, btnModeVento].forEach(input => input.disabled = !done);
    timerDisplay.textContent = `${Math.round(meta.elapsed_seconds || 0)}s`;
    obsDiscovered.textContent = meta.discovered_targets || 0;
    obsCorporate.textContent = meta.checked_targets || 0;
    obsReturned.textContent = state.leads.length;
    obsVerified.textContent = state.leads.filter(lead => lead.location_match).length;
    obsExtracted.textContent = state.leads.filter(lead => lead.contact_email || lead.contact_phone).length;
    obsQueryList.innerHTML = (meta.queries_used || []).map(query => `<p>${escapeHtml(query)}</p>`).join('');
    obsDropReasons.innerHTML = Object.entries(meta.rejection_reasons || {}).map(([key, count]) => `<p>${escapeHtml(key.replaceAll('_', ' '))}: ${count}</p>`).join('') || 'No rejected candidates yet.';
    for (const event of (result.steps || []).slice(lastEventCount)) addLog(escapeHtml(event.message), 'info');
    lastEventCount = (result.steps || []).length;
    renderTable();
    if (!state.leads.length) document.getElementById('empty-state-message').textContent = done ? finalCopy : 'Researching companies and checking their contact details…';
    if (done) finishProgress();
  }

  async function poll(id) {
    if (polling) return;
    polling = true;
    let failures = 0;
    try {
      while (activeId === id) {
        try {
          const job = await api(`/api/lead-searches/${encodeURIComponent(id)}`);
          failures = 0;
          showJob(job);
          if (terminal.has(job.status)) break;
        } catch (error) {
          statusCopy.textContent = 'Connection interrupted. Reconnecting to your saved search…';
          if (++failures >= 8) {
            statusCopy.textContent = 'Unable to reconnect. Refresh this page to recover your search.';
            break;
          }
        }
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
    } finally { polling = false; }
  }

  async function run() {
    if (state.running) return;
    const industry = industryInput.value.trim();
    const location = locationInput.value.trim();
    const target = Number(leadCountInput.value || 15);
    const maximum = state.mode === 'velit' ? 100 : 50;
    if (industry.length < 2 || location.length < 2 || !Number.isInteger(target) || target < 1 || target > maximum) {
      statusCopy.textContent = `Enter a business category, location, and a target between 1 and ${maximum}.`;
      return;
    }
    platform = true;
    state.leads = [];
    state.selectedIds.clear();
    lastEventCount = 0;
    setBusy(true);
    renderTable();
    statusTitle.textContent = 'Starting your search…';
    statusCopy.textContent = 'We will keep looking for usable company contacts until the target or search limit is reached.';
    const requestKey = crypto.randomUUID();
    try {
      const job = await api('/api/lead-searches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ industry, location, target_count: target, target_role: roleInput.value.trim(), mode: state.mode, request_key: requestKey }) });
      activeId = job.id;
      localStorage.setItem(storageKey, job.id);
      showJob(job);
      await poll(job.id);
    } catch (error) {
      statusCopy.textContent = error.message;
      setBusy(false);
    }
  }
  // Existing Enter handlers resolve this function at event time. Both entry
  // points must dispatch by mode without replacing specialized workflows.
  runLeadGen = function () {
    if (state.running) return;
    if (['generic', 'velit'].includes(state.mode)) return run();
    platform = false;
    return oldRun();
  };
  startBtn.addEventListener('click', event => {
    if (!['generic', 'velit'].includes(state.mode)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    runLeadGen();
  }, true);
  cancelBtn.addEventListener('click', async () => {
    if (!activeId) return;
    cancelBtn.disabled = true;
    try { showJob(await api(`/api/lead-searches/${encodeURIComponent(activeId)}/cancel`, { method: 'POST' })); }
    catch (error) { statusCopy.textContent = error.message; }
    finally { cancelBtn.disabled = false; }
  });
  const saved = localStorage.getItem(storageKey);
  if (saved) {
    api(`/api/lead-searches/${encodeURIComponent(saved)}`).then(job => {
      setMode(job.request.mode || 'generic');
      industryInput.value = job.request.industry;
      locationInput.value = job.request.location;
      leadCountInput.value = job.request.target_count;
      showJob(job);
      if (!terminal.has(job.status)) poll(job.id);
    }).catch(() => localStorage.removeItem(storageKey));
  }
})();

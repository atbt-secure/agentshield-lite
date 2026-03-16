/* ============================================================
   AgentShield Dashboard — app.js
   ============================================================ */

const API_BASE = 'http://localhost:8000';
const REFRESH_INTERVAL_MS = 10000;

// ── State ────────────────────────────────────────────────────
let currentPage = 'overview';
let logsOffset = 0;
const logsLimit = 50;
let showAcknowledgedAlerts = false;
let refreshTimer = null;
let editingPolicyId = null;

// ── Navigation ───────────────────────────────────────────────

const PAGE_TITLES = {
  overview: 'Overview',
  logs:     'Activity Logs',
  alerts:   'Security Alerts',
  policies: 'Security Policies',
  agents:   'Agents',
};

function navigate(page, navEl) {
  // Hide all pages
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  // Show selected
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');
  if (navEl) navEl.classList.add('active');

  currentPage = page;
  document.getElementById('page-title').textContent = PAGE_TITLES[page] || page;

  // Load page data
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'overview': loadOverview(); break;
    case 'logs':     fetchLogs(); break;
    case 'alerts':   fetchAlerts(); break;
    case 'policies': fetchPolicies(); break;
    case 'agents':   fetchAgents(); break;
  }
}

// ── API helpers ──────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API error ${resp.status}: ${text}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

// ── Overview ─────────────────────────────────────────────────

async function loadOverview() {
  await Promise.all([fetchStats(), fetchTimeline(), fetchTopAgents()]);
}

async function fetchStats() {
  try {
    const data = await apiFetch('/api/dashboard/stats');
    renderStats(data);
  } catch (e) {
    console.error('fetchStats:', e);
  }
}

function renderStats(d) {
  setText('stat-total',      d.total_actions ?? '—');
  setText('stat-blocked',    d.blocked_actions ?? '—');
  setText('stat-block-rate', `${d.block_rate ?? 0}% block rate`);
  setText('stat-high-risk',  d.high_risk_actions ?? '—');
  setText('stat-alerts',     d.unacknowledged_alerts ?? '—');
  setText('stat-agents',     d.unique_agents ?? '—');

  const avgEl = document.getElementById('stat-avg-risk');
  if (avgEl) {
    const score = d.avg_risk_score ?? 0;
    avgEl.textContent = score.toFixed(1);
    avgEl.className = `stat-value ${riskColorClass(score)}`;
  }

  // Update sidebar alerts badge
  const badge = document.getElementById('alerts-badge');
  if (badge) {
    const count = d.unacknowledged_alerts ?? 0;
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline-flex' : 'none';
  }
}

async function fetchTimeline() {
  try {
    const data = await apiFetch('/api/dashboard/timeline?hours=24');
    renderTimeline(data);
  } catch (e) {
    console.error('fetchTimeline:', e);
  }
}

function renderTimeline(items) {
  const tbody = document.getElementById('timeline-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-empty">No activity in the last 24 hours</td></tr>`;
    return;
  }

  // Show most recent first, limit to 50 for overview
  const rows = [...items].reverse().slice(0, 50);
  tbody.innerHTML = rows.map(l => `
    <tr>
      <td class="mono">${l.id}</td>
      <td style="white-space:nowrap; color:var(--text-muted);">${formatTime(l.created_at)}</td>
      <td><code style="font-size:12px;">${escHtml(l.agent_id)}</code></td>
      <td><span class="badge badge-low">${escHtml(l.tool)}</span></td>
      <td class="mono">${escHtml(l.action)}</td>
      <td>${riskScoreCell(l.risk_score)}</td>
      <td>${decisionBadge(l.policy_decision)}</td>
    </tr>
  `).join('');
}

async function fetchTopAgents() {
  try {
    const data = await apiFetch('/api/dashboard/top-agents');
    renderTopAgents(data);
  } catch (e) {
    console.error('fetchTopAgents:', e);
  }
}

function renderTopAgents(items) {
  const tbody = document.getElementById('top-agents-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="table-empty">No agents recorded yet</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map((a, i) => `
    <tr>
      <td class="agent-rank">${i + 1}</td>
      <td><code style="font-size:12px;">${escHtml(a.agent_id)}</code></td>
      <td>${a.action_count}</td>
      <td>${riskScoreCell(a.avg_risk_score)}</td>
    </tr>
  `).join('');
}

// ── Logs ─────────────────────────────────────────────────────

async function fetchLogs() {
  const agentId   = document.getElementById('filter-agent')?.value?.trim() || '';
  const tool      = document.getElementById('filter-tool')?.value?.trim() || '';
  const minRisk   = document.getElementById('filter-min-risk')?.value?.trim() || '';
  const blocked   = document.getElementById('filter-blocked')?.value || '';

  let qs = `limit=${logsLimit}&offset=${logsOffset}`;
  if (agentId)  qs += `&agent_id=${encodeURIComponent(agentId)}`;
  if (tool)     qs += `&tool=${encodeURIComponent(tool)}`;
  if (minRisk)  qs += `&min_risk=${encodeURIComponent(minRisk)}`;
  if (blocked !== '') qs += `&blocked=${blocked}`;

  try {
    const data = await apiFetch(`/api/logs?${qs}`);
    renderLogs(data);
  } catch (e) {
    console.error('fetchLogs:', e);
    const tbody = document.getElementById('logs-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="table-empty">Error loading logs</td></tr>`;
  }
}

function renderLogs(data) {
  const tbody = document.getElementById('logs-tbody');
  if (!tbody) return;

  const items = data.items || [];
  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-empty">No logs found</td></tr>`;
    renderPagination(0, 0);
    return;
  }

  tbody.innerHTML = items.map(l => `
    <tr>
      <td class="mono">${l.id}</td>
      <td style="white-space:nowrap; color:var(--text-muted);">${formatTime(l.created_at)}</td>
      <td><code style="font-size:12px;">${escHtml(l.agent_id)}</code></td>
      <td><span class="badge badge-low" style="font-size:10px;">${escHtml(l.tool)}</span></td>
      <td class="mono">${escHtml(l.action)}</td>
      <td>${riskScoreCell(l.risk_score)}</td>
      <td>${decisionBadge(l.policy_decision)}</td>
      <td style="color:var(--text-muted); font-size:11px; max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
          title="${escHtml(l.policy_matched || '')}">
        ${escHtml(l.policy_matched || '—')}
      </td>
      <td style="color:var(--text-muted);">${l.duration_ms != null ? l.duration_ms.toFixed(1) : '—'}</td>
    </tr>
  `).join('');

  renderPagination(data.total, data.offset);
}

function renderPagination(total, offset) {
  const el = document.getElementById('logs-pagination');
  if (!el) return;
  const page = Math.floor(offset / logsLimit) + 1;
  const pages = Math.ceil(total / logsLimit) || 1;
  el.innerHTML = `
    <span>Showing ${offset + 1}–${Math.min(offset + logsLimit, total)} of ${total}</span>
    <button class="btn btn-secondary btn-sm" onclick="prevPage()" ${offset === 0 ? 'disabled' : ''}>← Prev</button>
    <span>Page ${page} / ${pages}</span>
    <button class="btn btn-secondary btn-sm" onclick="nextPage()" ${offset + logsLimit >= total ? 'disabled' : ''}>Next →</button>
  `;
}

function prevPage() {
  if (logsOffset > 0) {
    logsOffset = Math.max(0, logsOffset - logsLimit);
    fetchLogs();
  }
}

function nextPage() {
  logsOffset += logsLimit;
  fetchLogs();
}

function clearFilters() {
  document.getElementById('filter-agent').value = '';
  document.getElementById('filter-tool').value = '';
  document.getElementById('filter-min-risk').value = '';
  document.getElementById('filter-blocked').value = '';
  logsOffset = 0;
  fetchLogs();
}

// ── Alerts ───────────────────────────────────────────────────

async function fetchAlerts() {
  try {
    const data = await apiFetch(`/api/dashboard/alerts?acknowledged=${showAcknowledgedAlerts}&limit=100`);
    renderAlerts(data);
  } catch (e) {
    console.error('fetchAlerts:', e);
  }
}

function renderAlerts(items) {
  const container = document.getElementById('alerts-list');
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">✅</div>
        <div class="empty-state-title">${showAcknowledgedAlerts ? 'No acknowledged alerts' : 'No unacknowledged alerts'}</div>
        <div class="empty-state-text">All clear — no security alerts to review</div>
      </div>`;
    return;
  }

  container.innerHTML = items.map(a => `
    <div class="alert-item" id="alert-item-${a.id}">
      <span class="alert-icon">${severityIcon(a.severity)}</span>
      <div class="alert-body">
        <div class="alert-message">${escHtml(a.message)}</div>
        <div class="alert-meta">
          <span>${severityBadge(a.severity)}</span>
          <span>Agent: <code>${escHtml(a.agent_id)}</code></span>
          <span>Type: ${escHtml(a.alert_type)}</span>
          ${a.log_id ? `<span>Log #${a.log_id}</span>` : ''}
          <span>${formatTime(a.created_at)}</span>
        </div>
      </div>
      <div class="alert-actions">
        ${!a.acknowledged ? `
          <button class="btn btn-secondary btn-sm" onclick="acknowledgeAlert(${a.id})">Acknowledge</button>
        ` : `
          <span style="font-size:11px; color:var(--text-muted);">Acknowledged</span>
        `}
      </div>
    </div>
  `).join('');
}

async function acknowledgeAlert(alertId) {
  try {
    await apiFetch(`/api/dashboard/alerts/${alertId}/acknowledge`, { method: 'POST' });
    const el = document.getElementById(`alert-item-${alertId}`);
    if (el) {
      el.style.opacity = '0.4';
      el.style.transition = 'opacity 0.3s';
      setTimeout(() => el.remove(), 350);
    }
    showToast('Alert acknowledged', 'success');
    fetchStats(); // update badge count
  } catch (e) {
    showToast(`Failed to acknowledge: ${e.message}`, 'error');
  }
}

function toggleAlertsFilter() {
  showAcknowledgedAlerts = !showAcknowledgedAlerts;
  const btn = document.getElementById('alerts-filter-btn');
  if (btn) btn.textContent = showAcknowledgedAlerts ? 'Show Unacknowledged' : 'Show Acknowledged';
  fetchAlerts();
}

// ── Policies ─────────────────────────────────────────────────

async function fetchPolicies() {
  try {
    const data = await apiFetch('/api/policies');
    renderPolicies(data);
  } catch (e) {
    console.error('fetchPolicies:', e);
  }
}

function renderPolicies(items) {
  const tbody = document.getElementById('policies-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">No policies defined. Add a policy to start enforcing rules.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(p => `
    <tr>
      <td><strong>${p.priority}</strong></td>
      <td>${escHtml(p.name)}</td>
      <td><code style="font-size:11px;">${escHtml(p.tool || '*')}</code></td>
      <td><code style="font-size:11px;">${escHtml(p.action || '*')}</code></td>
      <td>${decisionBadge(p.effect)}</td>
      <td>
        <span class="badge ${p.enabled ? 'badge-allow' : 'badge-block'}">
          ${p.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </td>
      <td style="color:var(--text-muted); font-size:11px; white-space:nowrap;">${formatDate(p.created_at)}</td>
      <td>
        <div style="display:flex; gap:4px;">
          <button class="btn btn-icon btn-sm" title="Edit" onclick="openEditPolicyModal(${JSON.stringify(p).replace(/"/g, '&quot;')})">✏️</button>
          <button class="btn btn-icon btn-sm" title="Delete" onclick="deletePolicy(${p.id}, '${escHtml(p.name)}')">🗑️</button>
        </div>
      </td>
    </tr>
  `).join('');
}

function openPolicyModal() {
  editingPolicyId = null;
  document.getElementById('policy-modal-title').textContent = 'Add Policy';
  document.getElementById('policy-edit-id').value = '';
  document.getElementById('policy-name').value = '';
  document.getElementById('policy-description').value = '';
  document.getElementById('policy-tool').value = '*';
  document.getElementById('policy-action').value = '*';
  document.getElementById('policy-effect').value = 'block';
  document.getElementById('policy-priority').value = '100';
  document.getElementById('policy-enabled').value = 'true';
  document.getElementById('policy-condition').value = '{}';
  document.getElementById('policy-modal-overlay').classList.add('open');
}

function openEditPolicyModal(policy) {
  editingPolicyId = policy.id;
  document.getElementById('policy-modal-title').textContent = 'Edit Policy';
  document.getElementById('policy-edit-id').value = policy.id;
  document.getElementById('policy-name').value = policy.name || '';
  document.getElementById('policy-description').value = policy.description || '';
  document.getElementById('policy-tool').value = policy.tool || '*';
  document.getElementById('policy-action').value = policy.action || '*';
  document.getElementById('policy-effect').value = policy.effect || 'block';
  document.getElementById('policy-priority').value = policy.priority ?? 100;
  document.getElementById('policy-enabled').value = policy.enabled ? 'true' : 'false';
  document.getElementById('policy-condition').value = JSON.stringify(policy.condition || {}, null, 2);
  document.getElementById('policy-modal-overlay').classList.add('open');
}

function closePolicyModal() {
  document.getElementById('policy-modal-overlay').classList.remove('open');
  editingPolicyId = null;
}

async function savePolicy() {
  const name        = document.getElementById('policy-name').value.trim();
  const description = document.getElementById('policy-description').value.trim();
  const tool        = document.getElementById('policy-tool').value.trim() || '*';
  const action      = document.getElementById('policy-action').value.trim() || '*';
  const effect      = document.getElementById('policy-effect').value;
  const priority    = parseInt(document.getElementById('policy-priority').value) || 100;
  const enabled     = document.getElementById('policy-enabled').value === 'true';
  const condStr     = document.getElementById('policy-condition').value.trim();

  if (!name) { showToast('Name is required', 'warning'); return; }
  if (!effect) { showToast('Effect is required', 'warning'); return; }

  let condition = {};
  try { condition = JSON.parse(condStr || '{}'); } catch {
    showToast('Invalid JSON in Conditions field', 'error');
    return;
  }

  const payload = { name, description, tool, action, effect, priority, enabled, condition };

  try {
    if (editingPolicyId) {
      await apiFetch(`/api/policies/${editingPolicyId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('Policy updated', 'success');
    } else {
      await apiFetch('/api/policies', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('Policy created', 'success');
    }
    closePolicyModal();
    fetchPolicies();
  } catch (e) {
    showToast(`Failed to save policy: ${e.message}`, 'error');
  }
}

async function deletePolicy(policyId, name) {
  if (!confirm(`Delete policy "${name}"?`)) return;
  try {
    await apiFetch(`/api/policies/${policyId}`, { method: 'DELETE' });
    showToast('Policy deleted', 'success');
    fetchPolicies();
  } catch (e) {
    showToast(`Failed to delete: ${e.message}`, 'error');
  }
}

// ── Agents ───────────────────────────────────────────────────

async function fetchAgents() {
  try {
    const data = await apiFetch('/api/agents');
    renderAgents(data);
  } catch (e) {
    console.error('fetchAgents:', e);
    const tbody = document.getElementById('agents-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Error loading agents</td></tr>`;
  }
}

function renderAgents(items) {
  const tbody = document.getElementById('agents-tbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr><td colspan="8" class="table-empty">
        No agents registered yet. Click <strong>+ Register Agent</strong> to add one.
      </td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(a => {
    const tagsHtml = (a.tags || []).map(t =>
      `<span class="agent-tag">${escHtml(t)}</span>`
    ).join('');

    const lastSeen = a.last_seen_at
      ? `<span title="${escHtml(a.last_seen_at)}">${formatRelative(a.last_seen_at)}</span>`
      : `<span style="color:var(--text-muted)">Never</span>`;

    const statusBadge = a.enabled
      ? `<span class="badge badge-allow">Enabled</span>`
      : `<span class="badge badge-block">Disabled</span>`;

    return `
      <tr id="agent-row-${escHtml(a.agent_id)}">
        <td style="cursor:pointer;" onclick="openAgentDetail('${escHtml(a.agent_id)}', '${escHtml(a.name)}')" title="View details">
          <div style="font-weight:600; font-size:13px; color:var(--accent-blue-hover);">${escHtml(a.name)}</div>
          <code style="font-size:11px; color:var(--text-muted);">${escHtml(a.agent_id)}</code>
          ${a.description ? `<div style="font-size:11px; color:var(--text-muted); margin-top:2px;">${escHtml(a.description)}</div>` : ''}
        </td>
        <td>${statusBadge}</td>
        <td><div class="agent-tags">${tagsHtml || '<span style="color:var(--text-muted)">—</span>'}</div></td>
        <td style="font-variant-numeric:tabular-nums;">${a.action_count}</td>
        <td style="font-variant-numeric:tabular-nums; color:${a.blocked_count > 0 ? 'var(--risk-high)' : 'inherit'};">${a.blocked_count}</td>
        <td>${riskScoreCell(a.avg_risk_score)}</td>
        <td style="font-size:12px; color:var(--text-muted);">${lastSeen}</td>
        <td>
          <div style="display:flex; gap:4px; flex-wrap:nowrap;">
            <button class="btn btn-icon btn-sm" title="${a.enabled ? 'Disable' : 'Enable'} agent"
              onclick="toggleAgent('${escHtml(a.agent_id)}', ${!a.enabled})">
              ${a.enabled ? '⏸' : '▶'}
            </button>
            <button class="btn btn-icon btn-sm" title="Rotate API key"
              onclick="rotateAgentKey('${escHtml(a.agent_id)}')">🔄</button>
            <button class="btn btn-icon btn-sm" title="Delete agent"
              onclick="deleteAgent('${escHtml(a.agent_id)}', '${escHtml(a.name)}')">🗑️</button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

function openAgentModal() {
  document.getElementById('agent-name').value = '';
  document.getElementById('agent-description').value = '';
  document.getElementById('agent-tags').value = '';
  document.getElementById('agent-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('agent-name').focus(), 60);
}

function closeAgentModal() {
  document.getElementById('agent-modal-overlay').classList.remove('open');
}

async function registerAgent() {
  const name = document.getElementById('agent-name').value.trim();
  const description = document.getElementById('agent-description').value.trim();
  const tagsRaw = document.getElementById('agent-tags').value.trim();
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];

  if (!name) { showToast('Name is required', 'warning'); return; }

  try {
    const agent = await apiFetch('/api/agents', {
      method: 'POST',
      body: JSON.stringify({ name, description, tags }),
    });
    closeAgentModal();
    showApiKeyModal(agent.agent_id, agent.api_key, 'Agent Registered — Save Your API Key');
    fetchAgents();
  } catch (e) {
    showToast(`Failed to register agent: ${e.message}`, 'error');
  }
}

function showApiKeyModal(agentId, apiKey, title = 'API Key') {
  document.getElementById('apikey-modal-title').textContent = title;
  document.getElementById('apikey-agent-id').textContent = agentId;
  document.getElementById('apikey-display').textContent = apiKey;
  document.getElementById('copy-key-btn').textContent = 'Copy';
  document.getElementById('apikey-modal-overlay').classList.add('open');
}

function closeApiKeyModal() {
  document.getElementById('apikey-modal-overlay').classList.remove('open');
}

function copyApiKey() {
  const key = document.getElementById('apikey-display').textContent;
  navigator.clipboard.writeText(key).then(() => {
    const btn = document.getElementById('copy-key-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
    showToast('API key copied to clipboard', 'success');
  }).catch(() => showToast('Copy failed — select key manually', 'error'));
}

async function toggleAgent(agentId, enable) {
  try {
    await apiFetch(`/api/agents/${agentId}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled: enable }),
    });
    showToast(`Agent ${enable ? 'enabled' : 'disabled'}`, 'success');
    fetchAgents();
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'error');
  }
}

async function rotateAgentKey(agentId) {
  if (!confirm(`Rotate API key for agent "${agentId}"?\n\nThe old key will stop working immediately.`)) return;
  try {
    const data = await apiFetch(`/api/agents/${agentId}/rotate-key`, { method: 'POST' });
    showApiKeyModal(data.agent_id, data.api_key, 'New API Key — Save It Now');
  } catch (e) {
    showToast(`Failed to rotate key: ${e.message}`, 'error');
  }
}

async function deleteAgent(agentId, name) {
  if (!confirm(`Delete agent "${name}" (${agentId})?\n\nThis cannot be undone.`)) return;
  try {
    await apiFetch(`/api/agents/${agentId}`, { method: 'DELETE' });
    showToast('Agent deleted', 'success');
    fetchAgents();
  } catch (e) {
    showToast(`Failed to delete: ${e.message}`, 'error');
  }
}

function formatRelative(isoStr) {
  if (!isoStr) return '—';
  try {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch { return isoStr; }
}

// ── Agent Detail panel ────────────────────────────────────────

async function openAgentDetail(agentId, agentName) {
  document.getElementById('detail-agent-name').textContent = agentName;
  document.getElementById('detail-agent-id').textContent = agentId;
  document.getElementById('agent-detail-body').innerHTML = '<div class="table-empty">Loading…</div>';
  document.getElementById('agent-detail-overlay').classList.add('open');

  try {
    const data = await apiFetch(`/api/agents/${encodeURIComponent(agentId)}`);
    renderAgentDetail(data);
  } catch (e) {
    document.getElementById('agent-detail-body').innerHTML =
      `<div class="table-empty">Error loading agent details: ${escHtml(e.message)}</div>`;
  }
}

function closeAgentDetail() {
  document.getElementById('agent-detail-overlay').classList.remove('open');
}

function renderAgentDetail(d) {
  const s = d.stats || {};
  const w = d.last_7_days || {};
  const tools = d.top_tools || [];

  const blockRate = s.action_count > 0
    ? ((s.blocked_count / s.action_count) * 100).toFixed(1)
    : '0.0';

  const tagsHtml = (d.tags || []).map(t =>
    `<span class="agent-tag">${escHtml(t)}</span>`
  ).join('') || '<span style="color:var(--text-muted)">No tags</span>';

  const toolRows = tools.length
    ? tools.map(t => `
        <div class="detail-tool-row">
          <span class="detail-tool-name">${escHtml(t.tool)}</span>
          <div class="detail-tool-bar-wrap">
            <div class="detail-tool-bar" style="width:${Math.round((t.count / (tools[0].count || 1)) * 100)}%;"></div>
          </div>
          <span class="detail-tool-count">${t.count}</span>
        </div>`).join('')
    : '<div style="color:var(--text-muted); font-size:13px;">No tool usage recorded yet</div>';

  document.getElementById('agent-detail-body').innerHTML = `
    <div class="detail-grid">

      <!-- All-time stats -->
      <div class="detail-card">
        <div class="detail-card-title">All-Time Stats</div>
        <div class="detail-stat-row"><span>Total Actions</span><strong>${s.action_count ?? 0}</strong></div>
        <div class="detail-stat-row"><span>Blocked</span>
          <strong style="color:${(s.blocked_count ?? 0) > 0 ? 'var(--risk-high)' : 'inherit'};">
            ${s.blocked_count ?? 0} (${blockRate}%)
          </strong>
        </div>
        <div class="detail-stat-row"><span>Avg Risk Score</span>
          <strong class="${riskColorClass(s.avg_risk_score ?? 0)}">${(s.avg_risk_score ?? 0).toFixed(1)}</strong>
        </div>
      </div>

      <!-- Last 7 days -->
      <div class="detail-card">
        <div class="detail-card-title">Last 7 Days</div>
        <div class="detail-stat-row"><span>Actions</span><strong>${w.action_count ?? 0}</strong></div>
        <div class="detail-stat-row"><span>Blocked</span>
          <strong style="color:${(w.blocked_count ?? 0) > 0 ? 'var(--risk-high)' : 'inherit'};">
            ${w.blocked_count ?? 0}
          </strong>
        </div>
        <div class="detail-stat-row"><span>Status</span>
          <strong>${d.enabled
            ? '<span class="badge badge-allow">Enabled</span>'
            : '<span class="badge badge-block">Disabled</span>'}</strong>
        </div>
        <div class="detail-stat-row"><span>Last Seen</span>
          <strong>${formatRelative(d.last_seen_at)}</strong>
        </div>
      </div>

      <!-- Tags & meta -->
      <div class="detail-card">
        <div class="detail-card-title">Metadata</div>
        <div class="detail-stat-row"><span>Created</span>
          <strong>${formatDate(d.created_at)}</strong>
        </div>
        <div class="detail-stat-row" style="align-items:flex-start;">
          <span>Tags</span>
          <div class="agent-tags" style="justify-content:flex-end;">${tagsHtml}</div>
        </div>
        ${d.description ? `
        <div class="detail-stat-row" style="align-items:flex-start;">
          <span>Description</span>
          <span style="color:var(--text-muted); font-size:12px; text-align:right;">${escHtml(d.description)}</span>
        </div>` : ''}
      </div>
    </div>

    <!-- Top tools chart -->
    <div style="margin-top:20px;">
      <div class="detail-card-title" style="margin-bottom:12px;">Top Tools Used</div>
      <div class="detail-tools-chart">${toolRows}</div>
    </div>
  `;
}

function toggleQuickStart() {
  const el = document.getElementById('quickstart-content');
  if (el) el.classList.toggle('quickstart-hidden');
}

// ── Auto-refresh ─────────────────────────────────────────────

function manualRefresh() {
  const indicator = document.getElementById('refresh-indicator');
  if (indicator) indicator.classList.add('spinning');
  loadPage(currentPage);
  setTimeout(() => {
    if (indicator) indicator.classList.remove('spinning');
  }, 800);
}

// ── SSE live feed ─────────────────────────────────────────────

let sseConnection = null;
let liveRowCount = 0;
const MAX_LIVE_ROWS = 50;

function initSSE() {
  if (sseConnection) sseConnection.close();

  const indicator = document.getElementById('live-indicator');

  try {
    sseConnection = new EventSource(`${API_BASE}/api/stream/events`);

    sseConnection.onopen = () => {
      if (indicator) { indicator.className = 'live-dot live-connected'; indicator.title = 'Live'; }
    };

    sseConnection.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        handleLiveEvent(event);
      } catch {}
    };

    sseConnection.onerror = () => {
      if (indicator) { indicator.className = 'live-dot live-disconnected'; indicator.title = 'Disconnected — reconnecting…'; }
      // Browser auto-reconnects EventSource — just update indicator
    };
  } catch (err) {
    console.warn('SSE not available, using polling', err);
  }
}

function handleLiveEvent(event) {
  // 1. Prepend row to overview timeline (if on overview page)
  if (currentPage === 'overview') {
    prependTimelineRow(event);
  }

  // 2. Flash the live indicator
  const indicator = document.getElementById('live-indicator');
  if (indicator) {
    indicator.classList.add('live-flash');
    setTimeout(() => indicator.classList.remove('live-flash'), 400);
  }

  // 3. Refresh stats counter every 5 live events (lightweight)
  liveRowCount++;
  if (liveRowCount % 5 === 0) fetchStats();
}

function prependTimelineRow(l) {
  const tbody = document.getElementById('timeline-tbody');
  if (!tbody) return;

  // Remove empty-state row if present
  const emptyRow = tbody.querySelector('.table-empty');
  if (emptyRow) emptyRow.closest('tr')?.remove();

  const tr = document.createElement('tr');
  tr.className = 'live-new-row';
  tr.innerHTML = `
    <td class="mono">${l.id}</td>
    <td style="white-space:nowrap; color:var(--text-muted);">${formatTime(l.created_at)}</td>
    <td><code style="font-size:12px;">${escHtml(l.agent_id)}</code></td>
    <td><span class="badge badge-low">${escHtml(l.tool)}</span></td>
    <td class="mono">${escHtml(l.action)}</td>
    <td>${riskScoreCell(l.risk_score)}</td>
    <td>${decisionBadge(l.policy_decision)}</td>
  `;
  tbody.insertBefore(tr, tbody.firstChild);

  // Trim to MAX_LIVE_ROWS
  const rows = tbody.querySelectorAll('tr');
  if (rows.length > MAX_LIVE_ROWS) {
    rows[rows.length - 1].remove();
  }

  // Fade-in animation
  requestAnimationFrame(() => tr.classList.add('live-row-visible'));
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  // SSE handles real-time overview updates; poll other pages every 30s
  refreshTimer = setInterval(() => {
    if (currentPage !== 'overview') {
      const indicator = document.getElementById('refresh-indicator');
      if (indicator) indicator.classList.add('spinning');
      loadPage(currentPage);
      setTimeout(() => { if (indicator) indicator.classList.remove('spinning'); }, 800);
    }
  }, 30000);
  initSSE();
}

// ── Toasts ───────────────────────────────────────────────────

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: '✓', error: '✕', warning: '⚠' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type] || '•'}</span><span>${escHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 350);
  }, 3500);
}

// ── Helpers ──────────────────────────────────────────────────

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function formatTime(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return isoStr; }
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    return new Date(isoStr).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return isoStr; }
}

function riskLevel(score) {
  if (score >= 81) return 'CRITICAL';
  if (score >= 61) return 'HIGH';
  if (score >= 31) return 'MEDIUM';
  return 'LOW';
}

function riskColorClass(score) {
  if (score >= 81) return 'text-red';
  if (score >= 61) return 'text-orange';
  if (score >= 31) return 'text-yellow';
  return 'text-green';
}

function riskBadgeClass(score) {
  if (score >= 81) return 'badge-critical';
  if (score >= 61) return 'badge-high';
  if (score >= 31) return 'badge-medium';
  return 'badge-low';
}

function riskBarColor(score) {
  if (score >= 81) return 'var(--risk-critical)';
  if (score >= 61) return 'var(--risk-high)';
  if (score >= 31) return 'var(--risk-medium)';
  return 'var(--risk-low)';
}

function riskScoreCell(score) {
  const s = score ?? 0;
  const color = riskBarColor(s);
  const textColor = riskColorClass(s);
  return `
    <div class="risk-bar-wrap">
      <div class="risk-bar">
        <div class="risk-bar-fill" style="width:${s}%; background-color:${color};"></div>
      </div>
      <span class="risk-score-text ${textColor}">${s.toFixed(0)}</span>
    </div>`;
}

function decisionBadge(decision) {
  const map = { allow: 'badge-allow', block: 'badge-block', alert: 'badge-alert' };
  const cls = map[decision] || 'badge-low';
  return `<span class="badge ${cls}">${escHtml(decision || 'allow')}</span>`;
}

function severityBadge(severity) {
  return `<span class="badge badge-severity-${severity || 'low'}">${escHtml(severity || 'low')}</span>`;
}

function severityIcon(severity) {
  const icons = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' };
  return icons[severity] || '⚪';
}

// ── Close modals on overlay click ─────────────────────────────

document.getElementById('policy-modal-overlay').addEventListener('click', function(e) {
  if (e.target === this) closePolicyModal();
});

document.getElementById('agent-modal-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeAgentModal();
});

document.getElementById('apikey-modal-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeApiKeyModal();
});

document.getElementById('agent-detail-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeAgentDetail();
});

// ── Init ──────────────────────────────────────────────────────

loadOverview();
startAutoRefresh();

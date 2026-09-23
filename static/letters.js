const state = { user: null };
const $ = (selector) => document.querySelector(selector);
const message = (text = '', type = '') => {
  const target = $('#workspace').classList.contains('hidden') ? $('#login-message') : $('#message');
  target.textContent = text;
  target.className = `message ${type}`;
};
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character])); }
function nextStep(status) {
  return { intake: 'Awaiting department assignment', assigned: 'Assigned to team member', in_progress: 'Response being prepared', submitted_for_review: 'Awaiting PA review', md_review: 'Awaiting MD decision', changes_requested: 'Changes requested', finalized: 'Completed and locked' }[status] || 'Workflow in progress';
}
function rolePanel(role) {
  const panels = {
    front_desk: ['Front desk intake', 'Register incoming agency correspondence and track it after handoff.', 'Your action: capture the scan and send it into the department queue.'],
    department_head: ['Department assignment desk', 'Review letters for your department and assign each one to an accountable team member.', 'Your action: assign ownership before work begins.'],
    team_member: ['My execution queue', 'Prepare responses for the letters assigned directly to you.', 'Your action: draft the response and submit it for review.'],
    md_pa: ['MD review desk', 'Coordinate the final review queue and route completed departmental responses to the MD.', 'Your action: route submitted responses to the MD.'],
    md: ['Executive approval desk', 'Review every letter requiring executive attention and close approved correspondence.', 'Your action: approve and lock the final PDF, or request changes.']
  };
  const panel = panels[role];
  $('#role-panel').innerHTML = `<div class="role-panel-icon">◈</div><div><p class="eyebrow">Your workspace</p><h2>${panel[0]}</h2><p>${panel[1]}</p><strong>${panel[2]}</strong></div>`;
}
async function loadTeamMembers() {
  if (!['department_head', 'md', 'md_pa'].includes(state.user.role)) return [];
  return api('/team-members');
}
function actionMarkup(letter, teamMembers) {
  const role = state.user.role;
  if ((role === 'front_desk' || role === 'md_pa') && ['intake', 'changes_requested'].includes(letter.status)) {
    return `<div class="card-action assign-action"><select data-department><option value="">Route to department</option>${state.departments.map((department) => `<option value="${department.id}" ${department.id === letter.department_id ? 'selected' : ''}>${escapeHtml(department.name)}</option>`).join('')}</select><button class="small-button" data-action="route-department" data-id="${letter.id}">Route</button></div>`;
  }
  if ((role === 'department_head' || role === 'md_pa') && ['intake', 'changes_requested'].includes(letter.status)) {
    return `<div class="card-action assign-action"><select data-assignee><option value="">Assign to team member</option>${teamMembers.filter((member) => member.department_id === letter.department_id).map((member) => `<option value="${member.id}">${escapeHtml(member.display_name)}</option>`).join('')}</select><button class="small-button" data-action="assign" data-id="${letter.id}">Assign</button></div>`;
  }
  if (role === 'team_member' && ['assigned', 'in_progress', 'changes_requested'].includes(letter.status)) {
    return `<div class="card-action response-action"><textarea data-response placeholder="Write the response...">${escapeHtml(letter.response_text || '')}</textarea><div><button class="secondary-button small-button" data-action="save" data-id="${letter.id}">Save draft</button><button class="small-button" data-action="submit" data-id="${letter.id}">Submit</button></div></div>`;
  }
  if (role === 'md_pa' && letter.status === 'submitted_for_review') return `<div class="card-action"><button class="small-button full-action" data-action="route" data-id="${letter.id}">Route to MD →</button></div>`;
  if (role === 'md' && letter.status === 'md_review') return `<div class="card-action approval-actions"><button class="small-button" data-action="approve" data-id="${letter.id}">Approve & lock</button><button class="secondary-button small-button" data-action="changes" data-id="${letter.id}">Request changes</button></div>`;
  return '';
}
function letterCard(letter, teamMembers) {
  return `<article class="letter"><header><span class="letter-reference">${escapeHtml(letter.reference)}</span><span class="status">${escapeHtml(letter.status.replaceAll('_', ' '))}</span></header>
    <h3>${escapeHtml(letter.subject)}</h3><p>${escapeHtml(letter.sender)} · Received ${escapeHtml(letter.received_date)}</p><div class="workflow-next"><span class="workflow-dot"></span><span><strong>Current stage</strong>${escapeHtml(nextStep(letter.status))}</span></div>
    <div class="letter-actions"><a href="/letters/${letter.id}/source">Original scan</a><a href="/letters/${letter.id}/editable">Editable Word</a>${letter.status === 'finalized' ? `<a href="/letters/${letter.id}/pdf">Final PDF</a>` : ''}</div>${actionMarkup(letter, teamMembers)}</article>`;
}
async function loadWorkspace() {
  const params = new URLSearchParams({ q: $('#search')?.value || '', status: $('#status-filter')?.value || '', priority: $('#priority-filter')?.value || '' });
  const [letters, departments, teamMembers] = await Promise.all([api(`/letters?${params}`), api('/departments'), loadTeamMembers()]);
  state.departments = departments;
  $('#letters').innerHTML = letters.map((letter) => letterCard(letter, teamMembers)).join('') || '<p class="card empty-state">No letters in your scope yet. New records will appear here.</p>';
  $('#department').innerHTML = departments.map((department) => `<option value="${department.id}">${escapeHtml(department.name)}</option>`).join('');
  $('#total-count').textContent = letters.length;
  $('#pending-count').textContent = letters.filter((letter) => letter.status !== 'finalized').length;
  $('#finalized-count').textContent = letters.filter((letter) => letter.status === 'finalized').length;
}
async function runAction(action, letterId, card) {
  const payload = action === 'assign' ? { assignee_id: card.querySelector('[data-assignee]').value } : action === 'route-department' ? { department_id: card.querySelector('[data-department]').value } : action === 'save' || action === 'submit' ? { response_text: card.querySelector('[data-response]').value } : action === 'changes' ? { details: 'Please review and revise the response.' } : {};
  const requests = { assign: ['POST', `/letters/${letterId}/assign`], 'route-department': ['POST', `/letters/${letterId}/route`], save: ['PUT', `/letters/${letterId}/response`], submit: ['POST', `/letters/${letterId}/submit`], route: ['POST', `/letters/${letterId}/route-to-md`], approve: ['POST', `/letters/${letterId}/approve`], changes: ['POST', `/letters/${letterId}/request-changes`] };
  const [method, url] = requests[action];
  await api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  await loadWorkspace();
  message('Workflow updated successfully.', 'success');
}
$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault(); message('');
  const button = $('#login-button'); button.disabled = true; button.textContent = 'Signing in...';
  try {
    const data = await api('/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    state.user = data; $('#login-card').classList.add('hidden'); $('#workspace').classList.remove('hidden');
    $('#identity').textContent = data.username; $('#identity-role').textContent = data.role.replaceAll('_', ' '); $('#identity-name').textContent = data.username; $('#avatar').textContent = data.username.charAt(0).toUpperCase(); rolePanel(data.role);
    if (data.role === 'front_desk') $('#intake-card').classList.remove('hidden'); await loadWorkspace();
  } catch (error) { message(error.message); } finally { button.disabled = false; button.textContent = 'Sign in'; }
});
$('#intake-form').addEventListener('submit', async (event) => {
  event.preventDefault(); message('');
  try { const letter = await api('/letters/upload', {method: 'POST', body: new FormData(event.target)}); event.target.reset(); await loadWorkspace(); message(`Intake record ${letter.reference} created. It is now awaiting department assignment.`, 'success'); document.querySelector('.letters-section').scrollIntoView({ behavior: 'smooth', block: 'start' }); const firstCard = document.querySelector('.letter'); if (firstCard) { firstCard.classList.add('new-record'); setTimeout(() => firstCard.classList.remove('new-record'), 2600); } } catch (error) { message(error.message, 'error'); }
});
$('#refresh').addEventListener('click', () => loadWorkspace().catch((error) => message(error.message, 'error')));
['search', 'status-filter', 'priority-filter'].forEach((id) => document.getElementById(id)?.addEventListener('input', () => loadWorkspace().catch((error) => message(error.message, 'error'))));
$('#logout').addEventListener('click', async () => { await api('/logout', {method: 'POST'}); location.reload(); });
$('#letters').addEventListener('click', async (event) => { const button = event.target.closest('[data-action]'); if (!button) return; try { button.disabled = true; await runAction(button.dataset.action, button.dataset.id, button.closest('.letter')); } catch (error) { message(error.message, 'error'); button.disabled = false; } });

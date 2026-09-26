'use strict';

/* ================================================================
   SIGL Letter Desk — role-based workspace
   ================================================================ */

const state = { user: null, departments: [], letters: null, notifications: [], teamMembers: null, pollTimer: null, route: 0 };
// Each navigation bumps state.route; a view that finishes loading after the user has moved on must not draw.
const stale = (token) => token !== state.route;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

const ICONS = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  chart: '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
  settings: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  menu: '<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
  tick: '<polyline points="20 6 9 17 4 12"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  returned: '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;

const STATUS = {
  intake: 'New intake', assigned: 'Assigned', in_progress: 'Drafting', submitted_for_review: 'Awaiting PA review',
  md_review: 'With the MD', changes_requested: 'Returned for changes', approved: 'Approved', finalized: 'Finalised',
};
const ROLE_NAMES = { front_desk: 'Front desk', department_head: 'Department head', team_member: 'Team member', md_pa: 'MD personal assistant', md: 'Managing Director' };
const PRIORITY_RANK = { urgent: 0, high: 1, normal: 2, low: 3 };
const CATEGORIES = ['General correspondence', 'Request for quotation', 'Invoice / payment', 'Contract / legal', 'Government / regulatory', 'Complaint', 'Invitation / event', 'Other'];
const OPEN_WORK = ['assigned', 'in_progress', 'changes_requested'];
const IN_REVIEW = ['submitted_for_review', 'md_review'];

/* ---------------- Utilities ---------------- */
async function api(url, options = {}) {
  const init = { credentials: 'same-origin', ...options, headers: { ...(options.headers || {}) } };
  if (options.json !== undefined) {
    init.body = JSON.stringify(options.json);
    init.headers['Content-Type'] = 'application/json';
    delete init.json;
  }
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && state.user && url !== '/login') {
    sessionEnded();
    throw new Error('Your session has ended. Please sign in again.');
  }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function parseTs(value) {
  if (!value) return null;
  let text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return new Date(`${text}T00:00:00`);
  text = text.replace(' ', 'T');
  if (!/[zZ]$|[+-]\d\d:?\d\d$/.test(text)) text += 'Z';
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}
const localISO = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const todayISO = () => localISO(new Date());
const fmtDate = (value) => { const d = parseTs(value); return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'; };
const fmtDateTime = (value) => { const d = parseTs(value); return d ? d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'; };
function timeAgo(value) {
  const d = parseTs(value);
  if (!d) return '';
  const seconds = Math.round((Date.now() - d.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} d ago`;
  return fmtDate(value);
}
const initials = (name) => String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('');
const cap = (text) => (text ? text[0].toUpperCase() + text.slice(1) : '');
const isOpen = (letter) => letter.status !== 'finalized';
const isOverdue = (letter) => Boolean(letter.due_date) && isOpen(letter) && letter.due_date < todayISO();
function dueInfo(letter) {
  if (!letter.due_date || !isOpen(letter)) return null;
  const days = Math.round((parseTs(letter.due_date) - parseTs(todayISO())) / 86400000);
  if (days < 0) return { cls: 'overdue', text: `Overdue ${-days}d` };
  if (days === 0) return { cls: 'soon', text: 'Due today' };
  if (days <= 2) return { cls: 'soon', text: `Due in ${days}d` };
  return { cls: '', text: `Due ${fmtDate(letter.due_date)}` };
}
function byUrgency(a, b) {
  return (isOverdue(b) - isOverdue(a))
    || (PRIORITY_RANK[a.priority] ?? 2) - (PRIORITY_RANK[b.priority] ?? 2)
    || String(a.due_date || '9999').localeCompare(String(b.due_date || '9999'))
    || String(b.created_at).localeCompare(String(a.created_at));
}
const statusPill = (status) => `<span class="pill st-${esc(status)}">${esc(STATUS[status] || status)}</span>`;
function priorityChip(priority) {
  if (priority === 'urgent') return `<span class="chip prio-urgent">${icon('alert')}Urgent</span>`;
  if (priority === 'high') return '<span class="chip prio-high">High</span>';
  return '';
}
function dueChip(letter) {
  const due = dueInfo(letter);
  return due ? `<span class="chip ${due.cls}">${icon('clock')}${esc(due.text)}</span>` : '';
}
const confChip = (letter) => (letter.confidentiality && letter.confidentiality !== 'internal' ? `<span class="chip conf">${icon('lock')}${esc(letter.confidentiality)}</span>` : '');

function toast(text, type = 'success') {
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.innerHTML = `${icon(type === 'error' ? 'alert' : 'check')}<span>${esc(text)}</span>`;
  $('#toasts').appendChild(node);
  setTimeout(() => node.remove(), type === 'error' ? 7000 : 4200);
}

async function busy(button, task) {
  button.disabled = true;
  button.classList.add('loading');
  try { return await task(); } finally { button.disabled = false; button.classList.remove('loading'); }
}

function modal({ title, body = '', confirmText = 'Confirm', confirmClass = 'btn-primary', input = null }) {
  return new Promise((resolve) => {
    const root = $('#modal-root');
    root.innerHTML = `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-body"><h3 id="modal-title">${esc(title)}</h3>${body ? `<p>${body}</p>` : ''}
      ${input ? `<textarea id="modal-input" placeholder="${esc(input.placeholder || '')}" rows="4"></textarea>` : ''}</div>
      <div class="modal-foot"><button class="btn btn-secondary" data-close>Cancel</button><button class="btn ${confirmClass}" data-ok>${esc(confirmText)}</button></div></div></div>`;
    const close = (value) => { root.innerHTML = ''; document.removeEventListener('keydown', onKey); resolve(value); };
    const onKey = (event) => { if (event.key === 'Escape') close(null); };
    document.addEventListener('keydown', onKey);
    $('[data-close]', root).onclick = () => close(null);
    $('.modal-backdrop', root).onclick = (event) => { if (event.target.classList.contains('modal-backdrop')) close(null); };
    $('[data-ok]', root).onclick = () => {
      if (!input) return close(true);
      const value = $('#modal-input', root).value.trim();
      if (input.required && !value) { $('#modal-input', root).focus(); return; }
      close(value);
    };
    ($('#modal-input', root) || $('[data-ok]', root)).focus();
  });
}

function empty(title, text, iconName = 'inbox') {
  return `<div class="empty">${icon(iconName)}<strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
}

/* ---------------- Data ---------------- */
async function loadLetters(force = false) {
  if (state.letters && !force) return state.letters;
  state.letters = await api('/letters');
  updateNavCounts();
  return state.letters;
}
async function loadTeamMembers() {
  if (!['department_head', 'md', 'md_pa'].includes(state.user.role)) return [];
  if (!state.teamMembers) state.teamMembers = await api('/team-members');
  return state.teamMembers;
}
const departmentName = (id) => (state.departments.find((d) => d.id === Number(id)) || {}).name || '—';

/* ---------------- Role configuration ---------------- */
function roleConfig(role) {
  const dept = state.user.department_name || 'your department';
  const configs = {
    front_desk: {
      nav: [['', 'home', 'Dashboard'], ['intake', 'upload', 'Register letter'], ['letters', 'layers', 'My registered letters']],
      hero: ['Front desk intake', 'Register incoming correspondence and send it to the right department. Letters can be re-routed until they are assigned.', 'upload', ['Register a letter', '#/intake']],
      action: (l) => l.status === 'intake',
      kpis: [
        { label: 'Registered today', icon: 'inbox', tone: 'wine', count: (ls) => ls.filter((l) => { const d = parseTs(l.created_at); return d && localISO(d) === todayISO(); }).length, hint: 'By you', link: '#/letters' },
        { label: 'Awaiting assignment', icon: 'clock', tone: 'amber', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Not yet picked up', link: '#/letters?status=intake' },
        { label: 'With departments', icon: 'edit', tone: 'blue', count: (ls) => ls.filter((l) => isOpen(l) && l.status !== 'intake').length, hint: 'Being handled', link: '#/letters?view=open' },
        { label: 'Finalised', icon: 'check', tone: 'green', count: (ls) => ls.filter((l) => l.status === 'finalized').length, hint: 'Closed', link: '#/letters?status=finalized' },
      ],
      queues: [
        { title: 'Awaiting assignment', sub: 'Still waiting for a department head. You can re-route these.', filter: (l) => l.status === 'intake', empty: ['All caught up', 'Every letter you registered has been picked up.'] },
        { title: 'Recently registered', sub: 'Where your letters are now.', filter: (l) => l.status !== 'intake', limit: 8, sort: 'recent', empty: ['Nothing in progress', 'Letters move here once a department takes them on.'] },
      ],
    },
    department_head: {
      nav: [['', 'home', 'Dashboard'], ['letters', 'layers', 'Department letters'], ['team', 'users', 'My team']],
      hero: [`${dept} desk`, `Assign new letters to your team and keep ${dept} correspondence moving.`, 'users', ['View my team', '#/team']],
      action: (l) => l.status === 'intake',
      kpis: [
        { label: 'Needs assignment', icon: 'inbox', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Waiting on you', link: '#/letters?status=intake' },
        { label: 'In progress', icon: 'edit', tone: 'blue', count: (ls) => ls.filter((l) => OPEN_WORK.includes(l.status)).length, hint: 'With your team', link: '#/letters?view=working' },
        { label: 'In review', icon: 'send', tone: 'amber', count: (ls) => ls.filter((l) => IN_REVIEW.includes(l.status)).length, hint: 'With the PA or MD', link: '#/letters?view=review' },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Past due date', link: '#/letters?view=overdue', alert: true },
      ],
      queues: [
        { title: 'Needs assignment', sub: 'New letters for your department. Open one to assign it.', filter: (l) => l.status === 'intake', empty: ['Nothing to assign', 'New letters for your department will appear here.'] },
        { title: 'In progress', sub: 'Letters your team is working on, most urgent first.', filter: (l) => OPEN_WORK.includes(l.status) || IN_REVIEW.includes(l.status), limit: 8, empty: ['No active letters', 'Assigned letters will be tracked here.'] },
      ],
    },
    team_member: {
      nav: [['', 'home', 'My tasks'], ['letters', 'layers', 'All my letters']],
      hero: ['My tasks', 'Draft responses for the letters assigned to you, then submit them for review.', 'edit', null],
      action: (l) => OPEN_WORK.includes(l.status),
      kpis: [
        { label: 'To do', icon: 'edit', tone: 'wine', count: (ls) => ls.filter((l) => ['assigned', 'in_progress'].includes(l.status)).length, hint: 'Assigned to you', link: '#/letters?view=working' },
        { label: 'Returned', icon: 'returned', tone: 'red', count: (ls) => ls.filter((l) => l.status === 'changes_requested').length, hint: 'Changes requested', link: '#/letters?status=changes_requested', alert: true },
        { label: 'In review', icon: 'send', tone: 'amber', count: (ls) => ls.filter((l) => IN_REVIEW.includes(l.status)).length, hint: 'Submitted', link: '#/letters?view=review' },
        { label: 'Completed', icon: 'check', tone: 'green', count: (ls) => ls.filter((l) => l.status === 'finalized').length, hint: 'Finalised', link: '#/letters?status=finalized' },
      ],
      queues: [
        { title: 'Returned for changes', sub: 'The MD asked for changes. These come first.', filter: (l) => l.status === 'changes_requested', hideWhenEmpty: true },
        { title: 'To do', sub: 'Open a letter to write or continue your response.', filter: (l) => ['assigned', 'in_progress'].includes(l.status), empty: ['You are all caught up', 'New assignments will appear here.'] },
        { title: 'Submitted for review', sub: 'Waiting on the MD PA or the MD.', filter: (l) => IN_REVIEW.includes(l.status), limit: 6, hideWhenEmpty: true },
      ],
    },
    md_pa: {
      nav: [['', 'home', 'Dashboard'], ['letters', 'layers', 'All letters'], ['reports', 'chart', 'Reports'], ['admin', 'settings', 'Users & departments']],
      hero: ['MD review desk', 'Check submitted responses and route them to the MD. You can also route and assign new letters.', 'send', null],
      action: (l) => l.status === 'submitted_for_review',
      kpis: [
        { label: 'Ready to route', icon: 'send', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'submitted_for_review').length, hint: 'Waiting on you', link: '#/letters?status=submitted_for_review' },
        { label: 'With the MD', icon: 'clock', tone: 'amber', count: (ls) => ls.filter((l) => l.status === 'md_review').length, hint: 'Awaiting decision', link: '#/letters?status=md_review' },
        { label: 'New intake', icon: 'inbox', tone: 'blue', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Not yet assigned', link: '#/letters?status=intake' },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Company-wide', link: '#/letters?view=overdue', alert: true },
      ],
      queues: [
        { title: 'Ready to route to the MD', sub: 'Responses submitted by departments.', filter: (l) => l.status === 'submitted_for_review', empty: ['Nothing to route', 'Submitted responses will appear here.'] },
        { title: 'New letters not yet assigned', sub: 'You can route or assign these on behalf of a department.', filter: (l) => l.status === 'intake', limit: 6, hideWhenEmpty: true },
        { title: 'Overdue', sub: 'Open letters past their due date.', filter: isOverdue, limit: 6, hideWhenEmpty: true },
      ],
    },
    md: {
      nav: [['', 'home', 'Dashboard'], ['letters', 'layers', 'All letters'], ['reports', 'chart', 'Reports'], ['admin', 'settings', 'Users & departments']],
      hero: ['Executive approval desk', 'Letters awaiting your decision are listed first. Approving produces the final, locked PDF.', 'lock', ['View reports', '#/reports']],
      action: (l) => l.status === 'md_review',
      kpis: [
        { label: 'Awaiting approval', icon: 'lock', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'md_review').length, hint: 'Waiting on you', link: '#/letters?status=md_review' },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Company-wide', link: '#/letters?view=overdue', alert: true },
        { label: 'Open letters', icon: 'layers', tone: 'blue', count: (ls) => ls.filter(isOpen).length, hint: 'All departments', link: '#/letters?view=open' },
        { label: 'Finalised this month', icon: 'check', tone: 'green', count: (ls) => ls.filter((l) => l.status === 'finalized' && String(l.finalized_at || '').slice(0, 7) === todayISO().slice(0, 7)).length, hint: 'Approved & locked', link: '#/letters?status=finalized' },
      ],
      queues: [
        { title: 'Awaiting your approval', sub: 'Open a letter to read the response, then approve or return it.', filter: (l) => l.status === 'md_review', empty: ['Nothing awaiting approval', 'Letters routed to you by the PA will appear here.'] },
        { title: 'Overdue across the company', sub: 'Open letters past their due date.', filter: isOverdue, limit: 6, hideWhenEmpty: true },
      ],
    },
  };
  return configs[role];
}

/* ---------------- Shell ---------------- */
function renderShell() {
  const user = state.user;
  const config = roleConfig(user.role);
  $('#nav').innerHTML = config.nav.map(([path, iconName, label]) =>
    `<a class="nav-item" href="#/${path}" data-path="${path}">${icon(iconName)}<span>${esc(label)}</span>${path === '' ? '<span class="nav-count hidden" id="nav-action-count"></span>' : ''}</a>`).join('');
  $('#sidebar-user').innerHTML = `<span class="avatar">${esc(initials(user.display_name))}</span><div><strong>${esc(user.display_name)}</strong><small>${esc(ROLE_NAMES[user.role])}${user.department_name ? ` · ${esc(user.department_name)}` : ''}</small></div>`;
  $('#logout').innerHTML = `${icon('logout')}<span>Sign out</span>`;
  $('#menu-toggle').innerHTML = icon('menu');
  $('#bell').innerHTML = `${icon('bell')}<span id="bell-count" class="badge hidden"></span>`;
}

function updateNavCounts() {
  const counter = $('#nav-action-count');
  if (!counter || !state.letters) return;
  const count = state.letters.filter(roleConfig(state.user.role).action).length;
  counter.textContent = count;
  counter.classList.toggle('hidden', count === 0);
}

function setPage(crumb, title, path) {
  $('#crumb').textContent = crumb;
  $('#page-title').textContent = title;
  document.title = `${title} · SIGL Letter Desk`;
  $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.path === path));
}

/* ---------------- Router ---------------- */
function parseRoute() {
  const [path, query] = (location.hash.replace(/^#\/?/, '') || '').split('?');
  return { parts: path.split('/').filter(Boolean), params: new URLSearchParams(query || '') };
}

async function router() {
  if (!state.user) return;
  $('#workspace').classList.remove('menu-open');
  state.route += 1;
  const { parts, params } = parseRoute();
  const role = state.user.role;
  const view = $('#view');
  const routes = {
    '': renderDashboard,
    letters: () => renderLetters(params),
    letter: () => renderDetail(Number(parts[1])),
    intake: role === 'front_desk' ? renderIntake : null,
    team: role === 'department_head' ? renderTeam : null,
    reports: ['md', 'md_pa'].includes(role) ? renderReports : null,
    admin: ['md', 'md_pa'].includes(role) ? renderAdmin : null,
  };
  const handler = routes[parts[0] || ''];
  if (!handler) { location.hash = '#/'; return; }
  window.scrollTo(0, 0);
  try {
    await handler();
  } catch (error) {
    view.innerHTML = `<div class="card">${empty('Something went wrong', error.message, 'alert')}</div>`;
  }
}

/* ---------------- Dashboard ---------------- */
function letterRow(letter, { showDept = true } = {}) {
  const who = letter.assignee_name ? ` · ${letter.assignee_name}` : '';
  return `<a class="row prio-${esc(letter.priority)}" href="#/letter/${letter.id}" style="text-decoration:none;color:inherit">
    <span class="row-stripe"></span>
    <span class="row-main"><span class="row-ref">${esc(letter.reference)}</span><span class="row-title">${esc(letter.subject)}</span>
    <span class="row-sub">${esc(letter.sender)}${showDept ? ` · ${esc(letter.department_name)}` : ''}${esc(who)}</span></span>
    <span class="row-side">${statusPill(letter.status)}<span class="row-meta">${priorityChip(letter.priority)}${dueChip(letter)}</span></span></a>`;
}

function skeleton() {
  return `<div class="kpis">${'<div class="skeleton sk-kpi"></div>'.repeat(4)}</div><div class="card">${'<div class="skeleton sk-row"></div>'.repeat(4)}</div>`;
}

async function renderDashboard() {
  const config = roleConfig(state.user.role);
  const hour = new Date().getHours();
  setPage(ROLE_NAMES[state.user.role], `Good ${hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'}, ${state.user.display_name}`, '');
  const view = $('#view');
  const token = state.route;
  if (!state.letters) view.innerHTML = skeleton();
  const letters = await loadLetters(true);
  if (stale(token)) return;
  const [heroTitle, heroText, heroIcon, heroCta] = config.hero;
  const kpis = config.kpis.map((kpi) => {
    const value = kpi.count(letters);
    return `<a class="kpi tone-${kpi.tone} ${kpi.alert && value ? 'alert' : ''}" href="${kpi.link}" style="text-decoration:none;color:inherit">
      <span class="kpi-top"><span>${esc(kpi.label)}</span><span class="kpi-icon">${icon(kpi.icon)}</span></span>
      <strong>${value}</strong><small>${esc(kpi.hint)}</small></a>`;
  }).join('');
  const queues = config.queues.map((queue) => {
    let items = letters.filter(queue.filter);
    items = queue.sort === 'recent' ? items.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))) : items.sort(byUrgency);
    if (!items.length && queue.hideWhenEmpty) return '';
    const total = items.length;
    if (queue.limit) items = items.slice(0, queue.limit);
    return `<section class="card section"><div class="card-head"><div><h2>${esc(queue.title)} <span class="count-note">(${total})</span></h2><p>${esc(queue.sub)}</p></div>
      ${queue.limit && total > queue.limit ? '<a class="btn btn-ghost btn-sm" href="#/letters">View all</a>' : ''}</div>
      <div class="rows">${items.length ? items.map((l) => letterRow(l, { showDept: state.user.role !== 'department_head' })).join('') : empty(...queue.empty)}</div></section>`;
  }).join('');
  view.innerHTML = `
    <div class="hero"><span class="hero-icon">${icon(heroIcon)}</span><div><h2>${esc(heroTitle)}</h2><p>${esc(heroText)}</p></div>
      ${heroCta ? `<a class="btn" href="${heroCta[1]}" style="text-decoration:none">${esc(heroCta[0])} ${icon('arrow')}</a>` : ''}</div>
    <div class="kpis">${kpis}</div>
    ${queues}`;
}

/* ---------------- Letters list ---------------- */
const LIST_VIEWS = {
  open: ['Open letters', isOpen],
  working: ['Being worked on', (l) => OPEN_WORK.includes(l.status)],
  review: ['In review', (l) => IN_REVIEW.includes(l.status)],
  overdue: ['Overdue', isOverdue],
};

async function renderLetters(params) {
  const role = state.user.role;
  const title = roleConfig(role).nav.find(([path]) => path === 'letters')[2];
  setPage('Correspondence', title, 'letters');
  const view = $('#view');
  const token = state.route;
  if (!state.letters) view.innerHTML = skeleton();
  const letters = await loadLetters(true);
  if (stale(token)) return;
  const wide = ['md', 'md_pa'].includes(role);
  const preset = params.get('view');
  view.innerHTML = `<section class="card">
    <div class="toolbar">
      <label class="search"><span class="sr-only">Search</span>${icon('search')}<input id="f-q" placeholder="Search reference, sender, subject or agency ref" value="${esc(params.get('q') || '')}"></label>
      <select id="f-status" aria-label="Status"><option value="">All statuses</option>${Object.entries(STATUS).filter(([k]) => k !== 'approved').map(([k, v]) => `<option value="${k}" ${params.get('status') === k ? 'selected' : ''}>${v}</option>`).join('')}</select>
      <select id="f-priority" aria-label="Priority"><option value="">All priorities</option>${['urgent', 'high', 'normal', 'low'].map((p) => `<option value="${p}">${p[0].toUpperCase() + p.slice(1)}</option>`).join('')}</select>
      ${wide ? `<select id="f-dept" aria-label="Department"><option value="">All departments</option>${state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('')}</select>` : ''}
      <select id="f-view" aria-label="Show"><option value="">Everything</option>${Object.entries(LIST_VIEWS).map(([k, [label]]) => `<option value="${k}" ${preset === k ? 'selected' : ''}>${label}</option>`).join('')}</select>
    </div>
    <div id="list-body"></div></section>`;
  const draw = () => {
    const q = $('#f-q').value.trim().toLowerCase();
    const status = $('#f-status').value;
    const priority = $('#f-priority').value;
    const dept = $('#f-dept')?.value;
    const extra = LIST_VIEWS[$('#f-view').value]?.[1];
    const rows = letters.filter((l) => (!q || [l.reference, l.sender, l.subject, l.agency_reference].some((v) => String(v || '').toLowerCase().includes(q)))
      && (!status || l.status === status) && (!priority || l.priority === priority) && (!dept || l.department_id === Number(dept)) && (!extra || extra(l)))
      .sort(byUrgency);
    const body = $('#list-body');
    if (!rows.length) { body.innerHTML = empty('No letters match', letters.length ? 'Try clearing a filter.' : 'Letters in your scope will appear here.', 'search'); return; }
    if (window.matchMedia('(max-width: 700px)').matches) { body.innerHTML = `<div class="rows">${rows.map((l) => letterRow(l)).join('')}</div>`; return; }
    body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Letter</th><th>Department</th><th>Assigned to</th><th>Due</th><th>Status</th></tr></thead><tbody>
      ${rows.map((l) => `<tr class="clickable" data-id="${l.id}" tabindex="0"><td class="mono">${esc(l.reference)}</td>
        <td><span class="title">${esc(l.subject)}</span><span class="sub">${esc(l.sender)} · received ${esc(fmtDate(l.received_date))}</span></td>
        <td>${esc(l.department_name)}</td><td>${l.assignee_name ? esc(l.assignee_name) : '<span class="sub">Unassigned</span>'}</td>
        <td><div class="chips">${priorityChip(l.priority)}${dueChip(l) || (l.due_date ? `<span class="sub">${esc(fmtDate(l.due_date))}</span>` : '<span class="sub">—</span>')}</div></td>
        <td>${statusPill(l.status)}</td></tr>`).join('')}</tbody></table></div>
      <div class="toolbar" style="border-top:1px solid var(--line);border-bottom:0"><span class="count-note">${rows.length} of ${letters.length} letters</span></div>`;
  };
  ['f-q', 'f-status', 'f-priority', 'f-dept', 'f-view'].forEach((id) => document.getElementById(id)?.addEventListener('input', draw));
  $('#list-body').addEventListener('click', (event) => { const tr = event.target.closest('tr[data-id]'); if (tr) location.hash = `#/letter/${tr.dataset.id}`; });
  $('#list-body').addEventListener('keydown', (event) => { const tr = event.target.closest('tr[data-id]'); if (tr && event.key === 'Enter') location.hash = `#/letter/${tr.dataset.id}`; });
  draw();
}

/* ---------------- Letter detail ---------------- */
const STEPS = [['intake', 'Received'], ['assigned', 'Assigned'], ['in_progress', 'Drafting'], ['submitted_for_review', 'PA review'], ['md_review', 'MD review'], ['finalized', 'Finalised']];
function stepper(status) {
  const order = { intake: 0, assigned: 1, in_progress: 2, changes_requested: 2, submitted_for_review: 3, md_review: 4, approved: 5, finalized: 5 };
  const current = order[status] ?? 0;
  return `<div class="card stepper">${STEPS.map(([, label], index) => {
    const done = index < current || status === 'finalized';
    const returned = status === 'changes_requested' && index === 2;
    const cls = done ? 'done' : index === current ? (returned ? 'current returned' : 'current') : '';
    return `<div class="step ${cls}"><span class="step-dot">${done ? icon('tick') : returned ? icon('returned') : index + 1}</span>${returned ? 'Returned' : label}</div>`;
  }).join('')}</div>`;
}

function describeEvent(event, letter) {
  let details = {};
  try { details = event.details ? JSON.parse(event.details) : {}; } catch { details = {}; }
  const who = esc(event.display_name);
  const map = {
    intake_created: ['inbox', 'wine', `Registered by ${who}`],
    routed_to_department: ['arrow', 'blue', `Routed to ${esc(departmentName(details.department_id))} by ${who}`],
    assigned: ['user', 'blue', `Assigned${details.assignee_id === letter.assigned_to && letter.assignee_name ? ` to ${esc(letter.assignee_name)}` : ''} by ${who}`],
    response_saved: ['edit', '', `Draft saved by ${who}`],
    submitted_for_review: ['send', 'blue', `Submitted for review by ${who}`],
    routed_to_md: ['arrow', 'wine', `Sent to the MD by ${who}`],
    changes_requested: ['returned', 'red', `Changes requested by ${who}`],
    approved_and_finalized: ['lock', 'green', `Approved and locked by ${who}`],
  };
  const [iconName, tone, text] = map[event.action] || ['clock', '', `${esc(event.action.replaceAll('_', ' '))} by ${who}`];
  return { iconName, tone, text, quote: details.details || '' };
}

function timeline(audit, letter) {
  const items = [];
  audit.forEach((event) => {
    const last = items[items.length - 1];
    if (event.action === 'response_saved' && last && last.action === 'response_saved' && last.actor_id === event.actor_id) { last.repeat += 1; last.created_at = event.created_at; return; }
    items.push({ ...event, repeat: 1 });
  });
  return `<ul class="timeline">${items.slice().reverse().map((event) => {
    const { iconName, tone, text, quote } = describeEvent(event, letter);
    return `<li><span class="tl-icon ${tone}">${icon(iconName)}</span><div><strong>${text}${event.repeat > 1 ? ` (${event.repeat}×)` : ''}</strong>
      <p>${esc(fmtDateTime(event.created_at))} · ${esc(timeAgo(event.created_at))}</p>${quote ? `<div class="quote">“${esc(quote)}”</div>` : ''}</div></li>`;
  }).join('')}</ul>`;
}

function latestFeedback(audit) {
  const event = [...audit].reverse().find((e) => e.action === 'changes_requested');
  if (!event) return '';
  try { return JSON.parse(event.details || '{}').details || ''; } catch { return ''; }
}

async function actionPanel(letter, audit) {
  const role = state.user.role;
  const s = letter.status;
  const card = (title, sub, body, eyebrow = 'Your action') => `<section class="card action-card"><div class="card-head"><div><p class="eyebrow">${eyebrow}</p><h3>${esc(title)}</h3>${sub ? `<p>${esc(sub)}</p>` : ''}</div></div><div class="action-body">${body}</div></section>`;
  const responseBox = letter.response_text ? `<div class="response-box">${esc(letter.response_text)}</div>` : '<p>No response has been written yet.</p>';
  const deptOptions = state.departments.map((d) => `<option value="${d.id}" ${d.id === letter.department_id ? 'selected' : ''}>${esc(d.name)}</option>`).join('');
  const routeBlock = `<label>Department<select id="a-dept">${deptOptions}</select></label><div class="btn-row"><button class="btn btn-secondary" data-act="route-department">${icon('arrow')}Route to department</button></div>`;
  const assignBlock = async () => {
    const members = (await loadTeamMembers()).filter((m) => m.department_id === letter.department_id);
    if (!members.length) return `<p>There are no active team members in ${esc(letter.department_name)}. Add one under Users &amp; departments.</p>`;
    return `<label>Assign to<select id="a-assignee"><option value="">Choose a team member…</option>${members.map((m) => `<option value="${m.id}" ${m.id === letter.assigned_to ? 'selected' : ''}>${esc(m.display_name)}</option>`).join('')}</select></label>
      <div class="btn-row"><button class="btn btn-primary" data-act="assign">${icon('user')}${letter.assigned_to ? 'Reassign' : 'Assign letter'}</button></div>`;
  };
  const feedback = s === 'changes_requested' ? `<div class="feedback"><strong>Changes requested by the MD</strong>${esc(latestFeedback(audit) || 'Please review and revise the response.')}</div>` : '';

  if (role === 'front_desk' && s === 'intake') return card('Route this letter', 'Change the department if it was sent to the wrong place.', routeBlock);
  if (role === 'department_head' && ['intake', 'changes_requested'].includes(s)) {
    return card(s === 'intake' ? 'Assign this letter' : 'Returned by the MD', s === 'intake' ? 'Choose who will prepare the response.' : 'The current assignee can revise it, or you can reassign it.', feedback + await assignBlock());
  }
  if (role === 'md_pa' && s === 'intake') return card('Route or assign', 'You can act on behalf of the department.', `${routeBlock}<hr style="border:0;border-top:1px solid var(--line);margin:4px 0">${await assignBlock()}`);
  if (role === 'md_pa' && s === 'submitted_for_review') return card('Review and route to the MD', 'Check the response below, then send it to the MD.', `${responseBox}<div class="btn-row"><button class="btn btn-primary" data-act="route-md">${icon('send')}Route to the MD</button></div>`);
  if (role === 'team_member' && letter.assigned_to === state.user.id && OPEN_WORK.includes(s)) {
    return card(s === 'changes_requested' ? 'Revise your response' : 'Write the response', 'Your draft saves when you click Save (or press Ctrl+S).', `${feedback}
      <textarea id="a-response" class="response-editor" placeholder="Write the response to this letter…">${esc(letter.response_text || '')}</textarea>
      <div class="btn-row" style="align-items:center"><button class="btn btn-secondary" data-act="save">${icon('edit')}Save draft</button><button class="btn btn-primary" data-act="submit">${icon('send')}Submit for review</button><span class="save-state" id="save-state">${letter.response_text ? `Last saved ${esc(timeAgo(letter.updated_at))}` : 'Not saved yet'}</span></div>`);
  }
  if (role === 'md' && s === 'md_review') {
    return card('Your decision', 'Approving produces the final PDF and locks the letter.', `${responseBox}<div class="btn-row"><button class="btn btn-success" data-act="approve">${icon('lock')}Approve &amp; lock</button><button class="btn btn-danger-outline" data-act="changes">${icon('returned')}Request changes</button></div>`);
  }
  if (s === 'finalized') return card('Finalised', `Approved on ${fmtDate(letter.finalized_at)}.`, `${responseBox}<div class="btn-row"><a class="btn btn-success" href="/letters/${letter.id}/pdf" style="text-decoration:none">${icon('download')}Download final PDF</a></div>`, 'Complete');
  const waiting = {
    intake: `Waiting for ${letter.department_name} to assign it.`, assigned: `${letter.assignee_name || 'The team member'} has not started yet.`,
    in_progress: `${letter.assignee_name || 'The team member'} is drafting the response.`, changes_requested: 'The MD returned it for changes.',
    submitted_for_review: 'Waiting for the MD PA to route it to the MD.', md_review: 'Waiting for the MD’s decision.',
  }[s] || '';
  return `<section class="card"><div class="card-head"><div><p class="eyebrow">Status</p><h3>${esc(STATUS[s] || s)}</h3><p>${esc(waiting)}</p></div></div>
    ${letter.response_text ? `<div class="action-body">${feedback}<p><strong>Response</strong></p>${responseBox}</div>` : feedback ? `<div class="action-body">${feedback}</div>` : ''}</section>`;
}

async function renderDetail(id) {
  setPage('Letter', 'Loading…', 'letters');
  const view = $('#view');
  view.innerHTML = `<div class="skeleton" style="height:120px;margin-bottom:20px"></div><div class="grid-2"><div class="skeleton" style="height:560px"></div><div class="skeleton" style="height:360px"></div></div>`;
  const token = state.route;
  const { letter, audit } = await api(`/letters/${id}`);
  const panel = await actionPanel(letter, audit);
  if (stale(token)) return;
  setPage('Letter', letter.reference, 'letters');
  const fact = (label, value) => `<dt>${esc(label)}</dt><dd>${value}</dd>`;
  view.innerHTML = `
    <a class="back" href="#/letters">${icon('back')}Back to letters</a>
    <div class="detail-head"><div style="min-width:0"><span class="row-sub">From ${esc(letter.sender)}</span><h2>${esc(letter.subject)}</h2>
      <div class="chips">${statusPill(letter.status)}${priorityChip(letter.priority)}${dueChip(letter)}${confChip(letter)}<span class="chip">${esc(letter.category || 'General correspondence')}</span></div></div></div>
    ${stepper(letter.status)}
    <div class="grid-2">
      <section class="card viewer"><div class="card-head"><div><h3>Original document</h3><p>${esc(letter.source_file)}</p></div>
        <div class="btn-row"><a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/source?inline=1" target="_blank" rel="noopener" style="text-decoration:none">${icon('external')}Open</a></div></div>
        <div class="viewer-body" id="viewer"><div class="skeleton" style="width:80%;height:80%"></div></div></section>
      <div class="stack">
        <div id="action-slot">${panel}</div>
        <section class="card"><div class="card-head"><h3>Details</h3></div><dl class="facts">
          ${fact('From', esc(letter.sender))}
          ${letter.agency_reference ? fact('Their reference', esc(letter.agency_reference)) : ''}
          ${fact('Received', esc(fmtDate(letter.received_date)))}
          ${fact('Due', letter.due_date ? esc(fmtDate(letter.due_date)) : 'No deadline')}
          ${fact('Department', esc(letter.department_name))}
          ${fact('Assigned to', letter.assignee_name ? esc(letter.assignee_name) : 'Not yet assigned')}
          ${fact('Registered by', esc(letter.created_by_name || '—'))}
          ${fact('Priority', esc(cap(letter.priority)))}
          ${fact('Confidentiality', esc(cap(letter.confidentiality)))}
          ${letter.notes ? fact('Notes', esc(letter.notes)) : ''}
        </dl></section>
        <section class="card"><div class="card-head"><h3>Files</h3></div><div class="files">
          <a class="file-link" href="/letters/${letter.id}/source">${icon('file')}Original scan<small>${esc(letter.source_file)}</small></a>
          <a class="file-link" href="/letters/${letter.id}/editable">${icon('edit')}Editable Word copy<small>.docx</small></a>
          ${letter.status === 'finalized' ? `<a class="file-link" href="/letters/${letter.id}/pdf">${icon('lock')}Final approved PDF<small>locked</small></a>` : ''}
        </div></section>
        <section class="card"><div class="card-head"><h3>History</h3></div>${timeline(audit, letter)}</section>
      </div>
    </div>`;
  bindActions(letter);
  loadPreview(letter.id);
}

async function loadPreview(id) {
  const viewer = $('#viewer');
  const unavailable = `<div class="viewer-note">${icon('file')}<p>A preview isn’t available for this file.<br>Use <strong>Open</strong> to view the original.</p></div>`;
  try {
    const response = await fetch(`/letters/${id}/page/0`, { credentials: 'same-origin' });
    if (!viewer.isConnected) return;
    if (!response.ok) { viewer.innerHTML = unavailable; return; }
    const pages = Math.min(Number(response.headers.get('X-Page-Count')) || 1, 40);
    const first = URL.createObjectURL(await response.blob());
    viewer.innerHTML = `<div class="pages">${Array.from({ length: pages }, (_, n) =>
      `<figure class="page"><img src="${n === 0 ? first : `/letters/${id}/page/${n}`}" loading="lazy" alt="Page ${n + 1} of the original letter"><figcaption>Page ${n + 1} of ${pages}</figcaption></figure>`).join('')}</div>`;
  } catch {
    viewer.innerHTML = unavailable;
  }
}

function bindActions(letter) {
  const slot = $('#action-slot');
  const run = async (button, method, url, json, success) => {
    await busy(button, async () => {
      try {
        await api(url, { method, json });
        state.letters = null;
        toast(success);
        await renderDetail(letter.id);
      } catch (error) { toast(error.message, 'error'); }
    });
  };
  const save = async (button, quiet) => {
    const text = $('#a-response').value;
    await api(`/letters/${letter.id}/response`, { method: 'PUT', json: { response_text: text } });
    letter.response_text = text;
    $('#save-state').textContent = `Saved ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`;
    if (!quiet) toast('Draft saved.');
  };
  slot.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-act]');
    if (!button) return;
    const act = button.dataset.act;
    if (act === 'route-department') return run(button, 'POST', `/letters/${letter.id}/route`, { department_id: $('#a-dept').value }, `Routed to ${departmentName($('#a-dept').value)}.`);
    if (act === 'assign') {
      if (!$('#a-assignee').value) { toast('Choose a team member first.', 'error'); return; }
      const name = $('#a-assignee').selectedOptions[0].textContent;
      return run(button, 'POST', `/letters/${letter.id}/assign`, { assignee_id: $('#a-assignee').value }, `Assigned to ${name}.`);
    }
    if (act === 'route-md') return run(button, 'POST', `/letters/${letter.id}/route-to-md`, {}, 'Sent to the MD for approval.');
    if (act === 'save') return busy(button, () => save(button).catch((error) => toast(error.message, 'error')));
    if (act === 'submit') {
      if (!$('#a-response').value.trim()) { toast('Write the response before submitting.', 'error'); return; }
      const ok = await modal({ title: 'Submit for review?', body: 'Your response will go to the MD PA and then the MD. You can’t edit it unless it is returned.', confirmText: 'Submit' });
      if (!ok) return;
      return busy(button, async () => {
        try { await save(button, true); await api(`/letters/${letter.id}/submit`, { method: 'POST', json: {} }); state.letters = null; toast('Submitted for review.'); await renderDetail(letter.id); } catch (error) { toast(error.message, 'error'); }
      });
    }
    if (act === 'approve') {
      const ok = await modal({ title: 'Approve and lock this letter?', body: 'This produces the final PDF on SIGL letterhead and locks the letter. It cannot be edited afterwards.', confirmText: 'Approve & lock', confirmClass: 'btn-success' });
      if (ok) return run(button, 'POST', `/letters/${letter.id}/approve`, {}, 'Approved. The final PDF is ready.');
    }
    if (act === 'changes') {
      const details = await modal({ title: 'Request changes', body: 'Tell the team member what to change. They will be notified.', confirmText: 'Send back', confirmClass: 'btn-primary', input: { placeholder: 'e.g. Please confirm the delivery dates and add our payment terms.', required: true } });
      if (details) return run(button, 'POST', `/letters/${letter.id}/request-changes`, { details }, 'Returned to the team member with your comments.');
    }
  });
  const editor = $('#a-response');
  if (editor) {
    editor.addEventListener('input', () => { $('#save-state').textContent = 'Unsaved changes'; });
    editor.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(null).catch((error) => toast(error.message, 'error')); }
    });
  }
}

/* ---------------- Intake (front desk) ---------------- */
function renderIntake() {
  setPage('Front desk', 'Register a letter', 'intake');
  const deptOptions = state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
  $('#view').innerHTML = `<div class="grid-2">
    <form class="card" id="intake-form" novalidate>
      <div class="form-grid">
        <p class="form-section-title">Document</p>
        <div class="wide" id="file-slot"></div>
        <p class="form-section-title">Letter details</p>
        <label>Sender *<input name="sender" required placeholder="Organisation or person" autocomplete="off"></label>
        <label><span>Their reference <span class="hint">(optional)</span></span><input name="agency_reference" placeholder="e.g. KBCS/PROC/2026/118" autocomplete="off"></label>
        <label class="wide">Subject *<input name="subject" required placeholder="What is the letter about?" autocomplete="off"></label>
        <label>Date received *<input name="received_date" type="date" required value="${todayISO()}" max="${todayISO()}"></label>
        <label>Category<select name="category">${CATEGORIES.map((c) => `<option>${esc(c)}</option>`).join('')}</select></label>
        <p class="form-section-title">Routing &amp; handling</p>
        <label>Department *<select name="department_id" required><option value="">Choose department…</option>${deptOptions}</select></label>
        <label>Priority<select name="priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option><option value="low">Low</option></select></label>
        <label><span>Response due by <span class="hint">(optional)</span></span><input name="due_date" type="date" min="${todayISO()}"></label>
        <label>Confidentiality<select name="confidentiality"><option value="internal">Internal</option><option value="confidential">Confidential</option><option value="restricted">Restricted</option></select></label>
        <label class="wide"><span>Notes for the department <span class="hint">(optional)</span></span><textarea name="notes" rows="3" placeholder="Anything the department should know"></textarea></label>
      </div>
      <div class="form-foot"><div class="progress-wrap hidden" id="progress"><span id="progress-text">Uploading…</span><div class="progress"><span id="progress-bar"></span></div></div>
        <button class="btn btn-primary" id="intake-submit">${icon('check')}Register letter</button></div>
    </form>
    <aside class="card"><div class="card-head"><h3>How intake works</h3></div><div class="tips">
      <div class="tip"><b>1</b><span>Scan or photograph the letter and upload it. PDF gives the best results; files up to 25 MB are accepted.</span></div>
      <div class="tip"><b>2</b><span>Pick the department that should respond. Its head is notified immediately.</span></div>
      <div class="tip"><b>3</b><span>Set a due date for anything time-sensitive. Overdue letters are flagged in red for everyone.</span></div>
      <div class="tip"><b>4</b><span>An editable Word copy is created automatically for the person who drafts the reply.</span></div>
    </div></aside></div>`;
  let file = null;
  const drawFile = () => {
    const slot = $('#file-slot');
    if (file) {
      slot.innerHTML = `<div class="file-chosen">${icon('file')}<div><strong>${esc(file.name)}</strong><small>${(file.size / 1048576).toFixed(file.size > 1048576 ? 1 : 2)} MB</small></div><button type="button" class="btn btn-ghost btn-sm" id="file-clear">${icon('x')}Remove</button></div>`;
      $('#file-clear').onclick = () => { file = null; drawFile(); };
      return;
    }
    slot.innerHTML = `<label class="dropzone" id="dropzone">${icon('upload')}<strong>Drop the scanned letter here, or click to browse</strong><small>PDF, PNG, JPG or TIFF · up to 25 MB</small><input type="file" id="file-input" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"></label>`;
    const zone = $('#dropzone');
    const pick = (chosen) => {
      if (!chosen) return;
      if (!/\.(pdf|png|jpe?g|tiff?)$/i.test(chosen.name)) { toast('Only PDF, PNG, JPG or TIFF files are supported.', 'error'); return; }
      if (chosen.size > 25 * 1048576) { toast('That file is larger than 25 MB.', 'error'); return; }
      file = chosen;
      drawFile();
    };
    $('#file-input').onchange = (event) => pick(event.target.files[0]);
    ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove('drag'); }));
    zone.addEventListener('drop', (event) => pick(event.dataTransfer.files[0]));
  };
  drawFile();

  $('#intake-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    if (!file) { toast('Add the scanned letter first.', 'error'); return; }
    const missing = ['sender', 'subject', 'received_date', 'department_id'].find((name) => !form.elements[name].value.trim());
    if (missing) { form.elements[missing].focus(); toast('Fill in the required fields marked *.', 'error'); return; }
    const fields = Object.fromEntries(new FormData(form));
    const button = $('#intake-submit');
    const progress = (fraction, text) => { $('#progress').classList.remove('hidden'); $('#progress-bar').style.width = `${Math.round(fraction * 100)}%`; $('#progress-text').textContent = text; };
    await busy(button, async () => {
      try {
        const sign = await api('/uploads/sign', { method: 'POST', json: { filename: file.name, size: file.size } });
        let letter;
        if (sign.mode === 'storage') {
          await xhr('PUT', sign.upload_url, file, { 'Content-Type': file.type || 'application/octet-stream', 'x-upsert': 'false' }, (f) => progress(f * 0.9, `Uploading… ${Math.round(f * 100)}%`));
          progress(0.95, 'Creating the Word copy…');
          letter = await api('/letters/upload-stored', { method: 'POST', json: { ...fields, storage_path: sign.path } });
        } else {
          const data = new FormData(form);
          data.append('document', file);
          const response = await xhr('POST', '/letters/upload', data, {}, (f) => progress(f * 0.9, f < 1 ? `Uploading… ${Math.round(f * 100)}%` : 'Creating the Word copy…'));
          letter = JSON.parse(response);
        }
        progress(1, 'Done');
        state.letters = null;
        toast(`${letter.reference} registered and sent to ${departmentName(letter.department_id)}.`);
        location.hash = `#/letter/${letter.id}`;
      } catch (error) {
        $('#progress').classList.add('hidden');
        toast(error.message, 'error');
      }
    });
  });
}

function xhr(method, url, body, headers, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(method, url);
    Object.entries(headers).forEach(([key, value]) => request.setRequestHeader(key, value));
    request.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) return resolve(request.responseText);
      let message = `Upload failed (${request.status})`;
      try { const data = JSON.parse(request.responseText); message = data.error || data.message || message; } catch { /* keep default */ }
      if (request.status === 413) message = 'That file is too large to upload.';
      reject(new Error(message));
    };
    request.onerror = () => reject(new Error('The upload was interrupted. Check your connection and try again.'));
    request.send(body);
  });
}

/* ---------------- Team (department head) ---------------- */
async function renderTeam() {
  setPage(state.user.department_name || 'Department', 'My team', 'team');
  const view = $('#view');
  view.innerHTML = skeleton();
  const token = state.route;
  const [letters, members] = await Promise.all([loadLetters(true), loadTeamMembers()]);
  if (stale(token)) return;
  const unassigned = letters.filter((l) => l.status === 'intake').length;
  const maxLoad = Math.max(1, ...members.map((m) => letters.filter((l) => l.assigned_to === m.id && OPEN_WORK.includes(l.status)).length));
  view.innerHTML = `
    <div class="kpis">
      <a class="kpi tone-wine" href="#/letters?status=intake" style="text-decoration:none;color:inherit"><span class="kpi-top"><span>Unassigned</span><span class="kpi-icon">${icon('inbox')}</span></span><strong>${unassigned}</strong><small>Waiting for you</small></a>
      <div class="kpi tone-blue"><span class="kpi-top"><span>Team members</span><span class="kpi-icon">${icon('users')}</span></span><strong>${members.length}</strong><small>Active</small></div>
      <div class="kpi tone-amber"><span class="kpi-top"><span>Open work</span><span class="kpi-icon">${icon('edit')}</span></span><strong>${letters.filter((l) => OPEN_WORK.includes(l.status)).length}</strong><small>Across the team</small></div>
      <div class="kpi tone-red ${letters.some(isOverdue) ? 'alert' : ''}"><span class="kpi-top"><span>Overdue</span><span class="kpi-icon">${icon('alert')}</span></span><strong>${letters.filter(isOverdue).length}</strong><small>Past due date</small></div>
    </div>
    ${members.length ? `<div class="people">${members.map((member) => {
      const mine = letters.filter((l) => l.assigned_to === member.id);
      const active = mine.filter((l) => OPEN_WORK.includes(l.status)).sort(byUrgency);
      const review = mine.filter((l) => IN_REVIEW.includes(l.status)).length;
      const done = mine.filter((l) => l.status === 'finalized').length;
      return `<section class="card person"><div class="person-head"><span class="avatar">${esc(initials(member.display_name))}</span><div><strong>${esc(member.display_name)}</strong><small>${active.length} active · ${mine.filter(isOverdue).length} overdue</small></div></div>
        <div class="load-bar" title="Workload"><span style="width:${(active.length / maxLoad) * 100}%"></span></div>
        <div class="mini-stats"><div><strong>${active.length}</strong><small>Active</small></div><div><strong>${review}</strong><small>In review</small></div><div><strong>${done}</strong><small>Done</small></div></div>
        ${active.length ? `<ul>${active.slice(0, 5).map((l) => `<li><a href="#/letter/${l.id}"><span>${esc(l.subject)}</span>${dueChip(l) || statusPill(l.status)}</a></li>`).join('')}</ul>` : '<p class="row-sub" style="margin:0">No active letters.</p>'}</section>`;
    }).join('')}</div>` : `<div class="card">${empty('No team members yet', 'Ask the MD or MD PA to add team members to your department.', 'users')}</div>`}`;
}

/* ---------------- Reports (MD, MD PA) ---------------- */
async function renderReports() {
  setPage('Insights', 'Reports', 'reports');
  const view = $('#view');
  view.innerHTML = skeleton();
  const token = state.route;
  const letters = await loadLetters(true);
  if (stale(token)) return;
  const finalized = letters.filter((l) => l.status === 'finalized' && l.finalized_at);
  const turnaround = finalized.length
    ? (finalized.reduce((sum, l) => sum + (parseTs(l.finalized_at) - parseTs(l.created_at)) / 86400000, 0) / finalized.length) : null;
  const byDept = state.departments.map((d) => {
    const mine = letters.filter((l) => l.department_id === d.id);
    return { name: d.name, open: mine.filter(isOpen).length, done: mine.filter((l) => !isOpen(l)).length, overdue: mine.filter(isOverdue).length };
  }).sort((a, b) => (b.open + b.done) - (a.open + a.done));
  const maxDept = Math.max(1, ...byDept.map((d) => d.open + d.done));
  const byStatus = Object.keys(STATUS).filter((k) => k !== 'approved').map((k) => [k, letters.filter((l) => l.status === k).length]);
  const maxStatus = Math.max(1, ...byStatus.map(([, n]) => n));
  const overdue = letters.filter(isOverdue).sort(byUrgency);
  view.innerHTML = `
    <div class="kpis">
      <div class="kpi tone-wine"><span class="kpi-top"><span>Total letters</span><span class="kpi-icon">${icon('layers')}</span></span><strong>${letters.length}</strong><small>All time</small></div>
      <div class="kpi tone-blue"><span class="kpi-top"><span>Open</span><span class="kpi-icon">${icon('edit')}</span></span><strong>${letters.filter(isOpen).length}</strong><small>Not yet finalised</small></div>
      <div class="kpi tone-red ${overdue.length ? 'alert' : ''}"><span class="kpi-top"><span>Overdue</span><span class="kpi-icon">${icon('alert')}</span></span><strong>${overdue.length}</strong><small>Past due date</small></div>
      <div class="kpi tone-green"><span class="kpi-top"><span>Avg. turnaround</span><span class="kpi-icon">${icon('clock')}</span></span><strong>${turnaround === null ? '—' : turnaround < 1 ? `${Math.max(1, Math.round(turnaround * 24))}h` : `${turnaround.toFixed(1)}d`}</strong><small>Received → finalised</small></div>
    </div>
    <div class="grid-2-even section">
      <section class="card"><div class="card-head"><div><h3>By department</h3><p>Open and finalised letters</p></div></div>
        <div class="bars">${byDept.map((d) => `<div class="bar-row"><span title="${esc(d.name)}">${esc(d.name)}</span><span class="bar-track"><i class="open" style="width:${(d.open / maxDept) * 100}%"></i><i class="done" style="width:${(d.done / maxDept) * 100}%"></i></span><b>${d.open + d.done}</b></div>`).join('')}</div>
        <div class="legend"><span><i style="background:var(--wine)"></i>Open</span><span><i style="background:#8fcfae"></i>Finalised</span></div></section>
      <section class="card"><div class="card-head"><div><h3>By stage</h3><p>Where letters are right now</p></div></div>
        <div class="bars">${byStatus.map(([k, n]) => `<div class="bar-row"><span>${esc(STATUS[k])}</span><span class="bar-track"><i class="open" style="width:${(n / maxStatus) * 100}%;background:var(--${k === 'finalized' ? 'green' : k === 'changes_requested' ? 'red' : 'wine'})"></i></span><b>${n}</b></div>`).join('')}</div></section>
    </div>
    <section class="card"><div class="card-head"><div><h3>Overdue letters</h3><p>Open letters past their due date, most urgent first</p></div></div>
      <div class="rows">${overdue.length ? overdue.map((l) => letterRow(l)).join('') : empty('Nothing overdue', 'Every open letter is within its due date.', 'check')}</div></section>`;
}

/* ---------------- Admin (MD, MD PA) ---------------- */
async function renderAdmin() {
  setPage('Administration', 'Users & departments', 'admin');
  const view = $('#view');
  view.innerHTML = skeleton();
  const token = state.route;
  const [users, letters] = await Promise.all([api('/users'), loadLetters()]);
  if (stale(token)) return;
  const deptOptions = state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
  view.innerHTML = `<div class="grid-2">
    <section class="card"><div class="card-head"><div><h3>Users</h3><p>${users.filter((u) => u.active).length} active of ${users.length}</p></div><button class="btn btn-primary btn-sm" id="toggle-user-form">${icon('plus')}Add user</button></div>
      <form class="inline-form hidden" id="user-form" autocomplete="off">
        <label>Full name *<input name="display_name" required placeholder="e.g. Ama Owusu"></label>
        <label>Username *<input name="username" required placeholder="e.g. aowusu"></label>
        <label>Role *<select name="role" required>${Object.entries(ROLE_NAMES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
        <label>Department<select name="department_id"><option value="">None</option>${deptOptions}</select></label>
        <label class="wide">Temporary password *<span style="display:flex;gap:8px"><input name="password" required minlength="8"><button type="button" class="btn btn-secondary" id="gen-pass">Generate</button></span></label>
        <div class="wide btn-row"><button class="btn btn-primary" id="create-user">Create user</button><button type="button" class="btn btn-secondary" id="cancel-user">Cancel</button></div>
      </form>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th class="hide-sm">Department</th><th>Status</th><th></th></tr></thead><tbody>
        ${users.map((u) => `<tr><td><span class="title">${esc(u.display_name)}</span><span class="sub mono">${esc(u.username)}</span></td>
          <td><span class="role-tag">${esc(ROLE_NAMES[u.role] || u.role)}</span></td><td class="hide-sm">${esc(u.department_name || '—')}</td>
          <td><span class="status-dot ${u.active ? '' : 'off'}">${u.active ? 'Active' : 'Inactive'}</span></td>
          <td style="text-align:right">${u.id === state.user.id ? '<span class="sub">You</span>' : `<button class="btn btn-ghost btn-sm" data-user="${u.id}" data-active="${u.active ? 0 : 1}">${u.active ? 'Deactivate' : 'Activate'}</button>`}</td></tr>`).join('')}
      </tbody></table></div></section>
    <section class="card"><div class="card-head"><div><h3>Departments</h3><p>${state.departments.length} departments</p></div></div>
      <ul class="dept-list">${state.departments.map((d) => {
        const people = users.filter((u) => u.department_id === d.id && u.active).length;
        const open = letters.filter((l) => l.department_id === d.id && isOpen(l)).length;
        return `<li><strong>${esc(d.name)}</strong><span>${people} people · ${open} open</span></li>`;
      }).join('')}</ul>
      <form class="inline-form" id="dept-form" style="border-top:1px solid var(--line)"><label class="wide">New department<span style="display:flex;gap:8px"><input name="name" required placeholder="e.g. Procurement"><button class="btn btn-primary">Add</button></span></label></form>
    </section></div>`;

  const userForm = $('#user-form');
  $('#toggle-user-form').onclick = () => { userForm.classList.toggle('hidden'); userForm.elements.display_name.focus(); };
  $('#cancel-user').onclick = () => { userForm.reset(); userForm.classList.add('hidden'); };
  $('#gen-pass').onclick = () => {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
    const values = crypto.getRandomValues(new Uint32Array(12));
    userForm.elements.password.value = [...values].map((v) => alphabet[v % alphabet.length]).join('');
  };
  userForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(userForm));
    if (!data.display_name.trim() || !data.username.trim() || data.password.length < 8) { toast('Name, username and a password of at least 8 characters are required.', 'error'); return; }
    if (['department_head', 'team_member'].includes(data.role) && !data.department_id) { toast('Department heads and team members need a department.', 'error'); return; }
    await busy($('#create-user'), async () => {
      try {
        await api('/users', { method: 'POST', json: { ...data, department_id: data.department_id ? Number(data.department_id) : null } });
        state.teamMembers = null;
        toast(`${data.display_name} can now sign in as “${data.username}”. Share the temporary password privately.`);
        await renderAdmin();
      } catch (error) { toast(error.message, 'error'); }
    });
  });
  $('.grid-2', view).addEventListener('click', async (event) => {
    const button = event.target.closest('[data-user]');
    if (!button) return;
    const activate = button.dataset.active === '1';
    if (!activate && !(await modal({ title: 'Deactivate this user?', body: 'They will no longer be able to sign in. Their history is kept.', confirmText: 'Deactivate', confirmClass: 'btn-primary' }))) return;
    await busy(button, async () => {
      try { await api(`/users/${button.dataset.user}`, { method: 'PATCH', json: { active: activate } }); state.teamMembers = null; toast(activate ? 'User activated.' : 'User deactivated.'); await renderAdmin(); } catch (error) { toast(error.message, 'error'); }
    });
  });
  $('#dept-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = event.target.elements.name.value.trim();
    if (!name) return;
    await busy(event.submitter || $('#dept-form button'), async () => {
      try { await api('/departments', { method: 'POST', json: { name } }); state.departments = await api('/departments'); toast(`${name} added.`); await renderAdmin(); } catch (error) { toast(error.message, 'error'); }
    });
  });
}

/* ---------------- Notifications ---------------- */
async function loadNotifications() {
  if (!state.user) return;
  try {
    const previousUnread = state.notifications.filter((n) => !n.read_at).length;
    state.notifications = await api('/notifications');
    const unread = state.notifications.filter((n) => !n.read_at).length;
    const badge = $('#bell-count');
    badge.textContent = unread > 9 ? '9+' : unread;
    badge.classList.toggle('hidden', unread === 0);
    if (unread > previousUnread) state.letters = null;
    if (!$('#notif-panel').classList.contains('hidden')) drawNotifications();
  } catch { /* polling is best-effort */ }
}
function drawNotifications() {
  const panel = $('#notif-panel');
  const unread = state.notifications.some((n) => !n.read_at);
  panel.innerHTML = `<div class="notif-head"><strong>Notifications</strong>${unread ? '<button class="btn btn-ghost btn-sm" id="read-all">Mark all read</button>' : ''}</div>
    <div class="notif-list">${state.notifications.length ? state.notifications.slice(0, 30).map((n) => `<button class="notif ${n.read_at ? '' : 'unread'}" data-n="${n.id}" data-letter="${n.letter_id || ''}"><span class="dot"></span><span><strong>${esc(n.title)}</strong><p>${esc(n.body)}</p><time>${esc(timeAgo(n.created_at))}</time></span></button>`).join('') : '<div class="notif-empty">You’re all caught up.</div>'}</div>`;
}
function toggleNotifications(open) {
  const panel = $('#notif-panel');
  const show = open ?? panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !show);
  $('#bell').setAttribute('aria-expanded', String(show));
  if (show) drawNotifications();
}

/* ---------------- Session ---------------- */
async function enterWorkspace(user) {
  state.user = user;
  state.letters = null;
  state.teamMembers = null;
  state.departments = await api('/departments');
  $('#login-card').classList.add('hidden');
  $('#workspace').classList.remove('hidden');
  renderShell();
  loadNotifications();
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(loadNotifications, 60000);
  if (!location.hash) location.hash = '#/';
  await router();
}
function showLogin() {
  state.user = null;
  clearInterval(state.pollTimer);
  $('#workspace').classList.add('hidden');
  $('#login-card').classList.remove('hidden');
  document.title = 'SIGL Letter Desk';
  setTimeout(() => $('#login-form input[name="username"]').focus(), 0);
}
function sessionEnded() {
  showLogin();
  $('#login-message').textContent = 'Your session has ended. Please sign in again.';
}

$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#login-button');
  const message = $('#login-message');
  message.textContent = '';
  button.disabled = true;
  button.innerHTML = 'Signing in…';
  try {
    await api('/login', { method: 'POST', json: Object.fromEntries(new FormData(event.target)) });
    event.target.reset();
    await enterWorkspace(await api('/me'));
  } catch (error) {
    message.textContent = error.message === 'Invalid credentials' ? 'That username and password don’t match. Please try again.' : error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Sign in securely <span>→</span>';
  }
});
$('#logout').addEventListener('click', async () => {
  try { await api('/logout', { method: 'POST' }); } catch { /* already signed out */ }
  location.hash = '';
  location.reload();
});
$('#menu-toggle').addEventListener('click', () => $('#workspace').classList.toggle('menu-open'));
$('#scrim').addEventListener('click', () => $('#workspace').classList.remove('menu-open'));
$('#bell').addEventListener('click', (event) => { event.stopPropagation(); toggleNotifications(); });
$('#notif-panel').addEventListener('click', async (event) => {
  event.stopPropagation();
  if (event.target.closest('#read-all')) {
    await api('/notifications/read-all', { method: 'POST' }).catch((error) => toast(error.message, 'error'));
    await loadNotifications();
    return;
  }
  const item = event.target.closest('[data-n]');
  if (!item) return;
  api(`/notifications/${item.dataset.n}/read`, { method: 'POST' }).then(loadNotifications).catch(() => {});
  toggleNotifications(false);
  if (item.dataset.letter) location.hash = `#/letter/${item.dataset.letter}`;
});
document.addEventListener('click', () => toggleNotifications(false));
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { toggleNotifications(false); $('#workspace').classList.remove('menu-open'); } });
window.addEventListener('hashchange', router);
window.addEventListener('focus', loadNotifications);

(async function start() {
  try {
    const response = await fetch('/me', { credentials: 'same-origin' });
    if (response.ok) { await enterWorkspace(await response.json()); return; }
  } catch { /* fall through to sign-in */ }
  showLogin();
}());

'use strict';

/* ================================================================
   SIGL Letter Desk — role-based workspace
   ================================================================ */

const state = { user: null, departments: [], letters: null, notifications: [], teamMembers: null, pollTimer: null, route: 0, editor: null };
// Each navigation bumps state.route; a view that finishes loading after the user has moved on must not draw.
const stale = (token) => token !== state.route;
const $ = (selector, root = document) => root.querySelector(selector);
const can = (capability) => Boolean(state.user && (state.user.capabilities || []).includes(capability));
// Pages and buttons that need a permission.
const PAGE_CAPABILITY = { intake: 'register_incoming', compose: 'create_outgoing', reports: 'view_reports', admin: 'manage_users' };
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
  md_review: 'With the MD', changes_requested: 'Returned for revision', approved: 'Approved', finalized: 'Approved',
  dept_review: 'With department head',
};
// A received letter moves through fewer, different stages than a letter being sent.
const INCOMING_STAGES = { intake: 'New intake', assigned: 'Assigned', in_progress: 'Reply being drafted', finalized: 'Responded' };
const DISPATCH = { pending: 'Awaiting dispatch', sent: 'Sent', delivered: 'Delivered', returned: 'Returned undelivered' };
const ROLE_NAMES = { front_desk: 'Front desk', department_head: 'Department head', team_member: 'Team member', md_pa: 'MD personal assistant', md: 'Managing Director' };
const PRIORITY_RANK = { urgent: 0, high: 1, normal: 2, low: 3 };
const CATEGORIES = ['General correspondence', 'Request for quotation', 'Invoice / payment', 'Contract / legal', 'Government / regulatory', 'Complaint', 'Invitation / event', 'Other'];
const MATTER = { open: 'Open', closed: 'Closed', responded: 'Responded' };
const RECEIVED_VIA = { hand_delivery: 'Hand delivery (physical)', post_courier: 'Post / courier (physical)', email: 'Email (soft copy)', other: 'Other' };
const ACTIONS = { reply: 'Reply required', action: 'Action required, no reply', information: 'For information only', other: 'Other' };
const DISPATCH_METHODS = { hand_delivery: 'Hand delivery', dispatch_rider: 'Dispatch rider', courier: 'Courier', post: 'Post', email: 'Email', other: 'Other' };
const DRAFTERS = ['team_member', 'department_head', 'md_pa', 'md'];
const REGISTER_LABELS = {
  subject: 'Subject', sender: 'Institution', letter_date: 'Date on letter', agency_reference: 'Reference on letter',
  signatory: 'Signed by', cc_parties: 'Copied parties', received_date: 'Date received', received_via: 'Received via',
  addressee: 'Addressee', recipient_address: 'Address',
};
const IN_REVIEW = ['dept_review', 'submitted_for_review', 'md_review'];

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
const isOutgoing = (letter) => letter.direction === 'outgoing';
const isSent = (letter) => ['sent', 'delivered'].includes(letter.dispatch_status);
// Open means someone still has something to do: reply, approve, send, or confirm delivery.
const isOpen = (letter) => (isOutgoing(letter)
  ? letter.matter_status !== 'closed' && letter.dispatch_status !== 'delivered'
  : letter.status !== 'finalized' && !['closed', 'responded'].includes(letter.matter_status));
const awaitingReply = (letter) => !isOutgoing(letter) && letter.status === 'assigned';
const drafting = (letter) => isOutgoing(letter) && ['in_progress', 'changes_requested'].includes(letter.status);
const isWorking = (letter) => awaitingReply(letter) || drafting(letter);
const toDispatch = (letter) => isOutgoing(letter) && letter.status === 'finalized' && ['pending', 'returned'].includes(letter.dispatch_status) && letter.matter_status !== 'closed';
const awaitingDelivery = (letter) => isOutgoing(letter) && letter.dispatch_status === 'sent';
const isOverdue = (letter) => Boolean(letter.due_date) && letter.due_date < todayISO() && (isOutgoing(letter) ? !isSent(letter) && letter.matter_status !== 'closed' : isOpen(letter));
function dueInfo(letter) {
  if (!letter.due_date || !(isOutgoing(letter) ? !isSent(letter) : isOpen(letter))) return null;
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
function stageOf(letter) {
  if (!isOutgoing(letter)) return [`st-${letter.status}`, INCOMING_STAGES[letter.status] || STATUS[letter.status] || letter.status];
  if (letter.status === 'finalized') return [`dispatch-${letter.dispatch_status || 'pending'}`, DISPATCH[letter.dispatch_status] || 'Approved'];
  if (letter.status === 'intake') return ['st-intake', 'Awaiting a writer'];
  return [`st-${letter.status}`, STATUS[letter.status] || letter.status];
}
const stageLabel = (letter) => stageOf(letter)[1];
const stagePill = (letter) => { const [cls, label] = stageOf(letter); return `<span class="pill ${esc(cls)}">${esc(label)}</span>`; };
function priorityChip(priority) {
  if (priority === 'urgent') return `<span class="chip prio-urgent">${icon('alert')}Urgent</span>`;
  if (priority === 'high') return '<span class="chip prio-high">High</span>';
  return '';
}
function dueChip(letter) {
  const due = dueInfo(letter);
  return due ? `<span class="chip ${due.cls}">${icon('clock')}${esc(due.text)}</span>` : '';
}
const matterPill = (letter) => `<span class="pill matter-${esc(letter.matter_status || 'open')}">${esc(MATTER[letter.matter_status] || 'Open')}</span>`;
const confChip = (letter) => (letter.confidentiality && letter.confidentiality !== 'internal' ? `<span class="chip conf">${icon('lock')}${esc(letter.confidentiality)}</span>` : '');
const registerOf = (letter) => (isOutgoing(letter) ? 'outgoing' : 'incoming');
// Status plus stage, without repeating a word (a responded letter's stage is also "Responded").
const statusPills = (letter) => matterPill(letter) + (stageLabel(letter) === (MATTER[letter.matter_status] || 'Open') ? '' : stagePill(letter));

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
  if (!can('assign_letters') && !can('all_letters')) return [];
  if (!state.teamMembers) state.teamMembers = await api('/team-members');
  return state.teamMembers;
}
const departmentName = (id) => (state.departments.find((d) => d.id === Number(id)) || {}).name || '—';

/* ---------------- Role configuration ---------------- */
const CREATE_INCOMING = ['Register incoming letter', '#/intake', 'inbox'];
const CREATE_OUTGOING = ['Create outgoing letter', '#/compose', 'send'];
const REGISTERS_NAV = [['incoming', 'inbox', 'Incoming register'], ['outgoing', 'send', 'Outgoing register'], ['verify', 'lock', 'Check a letter']];
const outgoingWaiting = (l) => isOutgoing(l) && l.status === 'finalized' && isOpen(l);

function roleConfig(role) {
  const dept = state.user.department_name || 'your department';
  const configs = {
    front_desk: {
      nav: [['', 'home', 'Dashboard'], ...REGISTERS_NAV],
      hero: ['Front desk', 'Register letters received and letters to be sent. Then dispatch approved letters and confirm delivery.', 'upload', [CREATE_INCOMING, CREATE_OUTGOING]],
      action: (l) => l.status === 'intake' || toDispatch(l) || awaitingDelivery(l),
      kpis: [
        { label: 'Registered today', icon: 'inbox', tone: 'wine', count: (ls) => ls.filter((l) => { const d = parseTs(l.created_at); return !isOutgoing(l) && d && localISO(d) === todayISO(); }).length, hint: 'By you', link: '#/incoming' },
        { label: 'Awaiting assignment', icon: 'clock', tone: 'amber', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Not yet picked up', link: '#/incoming?view=unassigned' },
        { label: 'Ready to dispatch', icon: 'send', tone: 'blue', count: (ls) => ls.filter(toDispatch).length, hint: 'Approved letters', link: '#/outgoing?view=dispatch', alert: true },
        { label: 'Confirm delivery', icon: 'check', tone: 'green', count: (ls) => ls.filter(awaitingDelivery).length, hint: 'Sent, not yet confirmed', link: '#/outgoing?view=sent' },
      ],
      queues: [
        { title: 'Ready to dispatch', sub: 'Approved by the MD. Print or email them, then record how they were sent.', filter: toDispatch, empty: ['Nothing to send', 'Approved letters will appear here.'] },
        { title: 'Sent: confirm delivery', sub: 'Record delivery once you have a stamped copy or acknowledgement.', filter: awaitingDelivery, hideWhenEmpty: true },
        { title: 'Awaiting assignment', sub: 'Still waiting for a department head. You can re-route these.', filter: (l) => l.status === 'intake', hideWhenEmpty: true },
        { title: 'Recently registered', sub: 'Where your letters are now.', filter: (l) => !isOutgoing(l) && l.status !== 'intake', limit: 6, sort: 'recent', hideWhenEmpty: true },
      ],
    },
    department_head: {
      nav: [['', 'home', 'Dashboard'], ...REGISTERS_NAV, ['team', 'users', 'My team']],
      hero: [`${dept} desk`, `Assign letters received and letters to be sent, then approve your team’s drafts before they go to the MD.`, 'users', [CREATE_OUTGOING]],
      action: (l) => l.status === 'intake' || l.status === 'dept_review' || (drafting(l) && l.assigned_to === state.user.id),
      kpis: [
        { label: 'Needs assignment', icon: 'inbox', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Waiting on you', link: '#/incoming?view=unassigned' },
        { label: 'Being worked on', icon: 'edit', tone: 'blue', count: (ls) => ls.filter(isWorking).length, hint: 'Replies and drafts', link: '#/incoming?view=working' },
        { label: 'Awaiting your approval', icon: 'check', tone: 'amber', count: (ls) => ls.filter((l) => l.status === 'dept_review').length, hint: 'Drafts from your team', link: '#/outgoing?view=head', alert: true },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Past deadline', link: '#/incoming?view=overdue', alert: true },
      ],
      queues: [
        { title: 'Awaiting your approval', sub: 'Drafts your team sent for approval. Approve them for the MD PA, or return them.', filter: (l) => l.status === 'dept_review', hideWhenEmpty: true },
        { title: 'Needs assignment', sub: 'Letters received and letters to be written for your department. Open one to assign it.', filter: (l) => l.status === 'intake', empty: ['Nothing to assign', 'New letters for your department will appear here.'] },
        { title: 'Being worked on', sub: 'Letters awaiting a reply and drafts in progress, most urgent first.', filter: (l) => isWorking(l) || IN_REVIEW.includes(l.status), limit: 8, empty: ['No active letters', 'Assigned letters will be tracked here.'] },
        { title: 'Approved, not yet delivered', sub: 'Letters your department sent that still need dispatch or delivery confirmation.', filter: outgoingWaiting, limit: 6, hideWhenEmpty: true },
      ],
    },
    team_member: {
      nav: [['', 'home', 'My tasks'], ...REGISTERS_NAV],
      hero: ['My tasks', 'Press Respond on a received letter, or write the outgoing letters assigned to you. Drafts go to your department head first.', 'edit', [CREATE_OUTGOING]],
      action: isWorking,
      kpis: [
        { label: 'To reply to', icon: 'inbox', tone: 'wine', count: (ls) => ls.filter(awaitingReply).length, hint: 'Assigned to you', link: '#/incoming?view=awaiting' },
        { label: 'My drafts', icon: 'edit', tone: 'blue', count: (ls) => ls.filter((l) => drafting(l) && l.status === 'in_progress').length, hint: 'Not yet submitted', link: '#/outgoing?view=drafting' },
        { label: 'Returned', icon: 'returned', tone: 'red', count: (ls) => ls.filter((l) => l.status === 'changes_requested').length, hint: 'Revise and resubmit', link: '#/outgoing?view=returned', alert: true },
        { label: 'In approval', icon: 'send', tone: 'amber', count: (ls) => ls.filter((l) => IN_REVIEW.includes(l.status)).length, hint: 'Submitted', link: '#/outgoing?view=review' },
      ],
      queues: [
        { title: 'Returned for revision', sub: 'The MD asked for changes. These come first.', filter: (l) => l.status === 'changes_requested', hideWhenEmpty: true },
        { title: 'Letters to reply to', sub: 'Open one and press Respond.', filter: awaitingReply, empty: ['You are all caught up', 'New assignments will appear here.'] },
        { title: 'My drafts', sub: 'Finish writing them in the editor and send them for approval.', filter: (l) => drafting(l) && l.status === 'in_progress', hideWhenEmpty: true },
        { title: 'In approval', sub: 'Waiting on the MD PA or the MD.', filter: (l) => IN_REVIEW.includes(l.status), limit: 6, hideWhenEmpty: true },
      ],
    },
    md_pa: {
      nav: [['', 'home', 'Dashboard'], ...REGISTERS_NAV, ['reports', 'chart', 'Reports'], ['admin', 'settings', 'Users & departments']],
      hero: ['MD review desk', 'Check letters submitted for approval and route them to the MD. You can also route and assign received letters.', 'send', null],
      action: (l) => l.status === 'submitted_for_review',
      kpis: [
        { label: 'Ready to route', icon: 'send', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'submitted_for_review').length, hint: 'Waiting on you', link: '#/outgoing?view=review' },
        { label: 'With the MD', icon: 'clock', tone: 'amber', count: (ls) => ls.filter((l) => l.status === 'md_review').length, hint: 'Awaiting decision', link: '#/outgoing?view=review' },
        { label: 'New intake', icon: 'inbox', tone: 'blue', count: (ls) => ls.filter((l) => l.status === 'intake').length, hint: 'Not yet assigned', link: '#/incoming?view=unassigned' },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Company-wide', link: '#/incoming?view=overdue', alert: true },
      ],
      queues: [
        { title: 'Ready to route to the MD', sub: 'Letters submitted by departments.', filter: (l) => l.status === 'submitted_for_review', empty: ['Nothing to route', 'Submitted letters will appear here.'] },
        { title: 'Received letters not yet assigned', sub: 'You can route or assign these on behalf of a department.', filter: (l) => l.status === 'intake', limit: 6, hideWhenEmpty: true },
        { title: 'Overdue', sub: 'Open letters past their deadline.', filter: isOverdue, limit: 6, hideWhenEmpty: true },
        { title: 'Approved, not yet delivered', sub: 'Waiting for dispatch or delivery confirmation.', filter: outgoingWaiting, limit: 6, hideWhenEmpty: true },
      ],
    },
    md: {
      nav: [['', 'home', 'Dashboard'], ...REGISTERS_NAV, ['reports', 'chart', 'Reports'], ['admin', 'settings', 'Users & departments']],
      hero: ['Executive approval desk', 'Letters awaiting your decision are listed first. Approving produces the final, locked PDF.', 'lock', ['View reports', '#/reports']],
      action: (l) => l.status === 'md_review',
      kpis: [
        { label: 'Awaiting approval', icon: 'lock', tone: 'wine', count: (ls) => ls.filter((l) => l.status === 'md_review').length, hint: 'Waiting on you', link: '#/outgoing?view=review' },
        { label: 'Overdue', icon: 'alert', tone: 'red', count: (ls) => ls.filter(isOverdue).length, hint: 'Company-wide', link: '#/incoming?view=overdue', alert: true },
        { label: 'Open received letters', icon: 'inbox', tone: 'blue', count: (ls) => ls.filter((l) => !isOutgoing(l) && isOpen(l)).length, hint: 'All departments', link: '#/incoming?view=open' },
        { label: 'Approved this month', icon: 'check', tone: 'green', count: (ls) => ls.filter((l) => isOutgoing(l) && l.status === 'finalized' && String(l.finalized_at || '').slice(0, 7) === todayISO().slice(0, 7)).length, hint: 'Letters sent out', link: '#/outgoing?view=approved' },
      ],
      queues: [
        { title: 'Awaiting your approval', sub: 'Open a letter to read it, then approve or return it.', filter: (l) => l.status === 'md_review', empty: ['Nothing awaiting approval', 'Letters routed to you by the PA will appear here.'] },
        { title: 'Overdue across the company', sub: 'Open letters past their deadline.', filter: isOverdue, limit: 6, hideWhenEmpty: true },
        { title: 'Other open letters', sub: 'Still with departments. Open one to approve a reply directly if it can’t wait.', filter: (l) => isOpen(l) && l.status !== 'md_review' && !(isOutgoing(l) && l.status === 'finalized'), limit: 8, hideWhenEmpty: true },
      ],
    },
  };
  return configs[role];
}

/* ---------------- Shell ---------------- */
function renderShell() {
  const user = state.user;
  const config = roleConfig(user.role);
  const creates = [CREATE_INCOMING, CREATE_OUTGOING].filter(([, href]) => can(PAGE_CAPABILITY[href.slice(2)]));
  const nav = [
    ...config.nav.filter(([path]) => !['reports', 'admin'].includes(path)),
    ...(can('view_reports') ? [['reports', 'chart', 'Reports']] : []),
    ...(can('manage_users') ? [['admin', 'settings', 'Users & departments']] : []),
  ];
  $('#nav').innerHTML = `<div class="side-actions">${creates.map(([label, href, iconName]) =>
    `<a class="nav-item side-action" href="${href}" data-path="${href.slice(2)}">${icon('plus')}<span>${esc(label)}</span>${icon(iconName, 'side-action-kind')}</a>`).join('')}</div>`
    + nav.map(([path, iconName, label]) =>
      `<a class="nav-item" href="#/${path}" data-path="${path}">${icon(iconName)}<span>${esc(label)}</span>${path === '' ? '<span class="nav-count hidden" id="nav-action-count"></span>' : ''}</a>`).join('');
  $('#sidebar-user').innerHTML = `<a href="#/account" class="sidebar-user-link" title="My account"><span class="avatar">${esc(initials(user.display_name))}</span><div><strong>${esc(user.display_name)}</strong><small>${esc(ROLE_NAMES[user.role])}${user.department_name ? ` · ${esc(user.department_name)}` : ''}</small></div>${icon('settings')}</a>`;
  $('#logout').innerHTML = `${icon('logout')}<span>Sign out</span>`;
  if (!$('#track-form .icon')) $('#track-form .search').insertAdjacentHTML('afterbegin', icon('search'));
  $('#menu-toggle').innerHTML = icon('menu');
  $('#bell').innerHTML = `${icon('bell')}<span id="bell-count" class="badge hidden"></span>`;
}

function updateNavCounts() {
  const counter = $('#nav-action-count');
  if (!counter || !state.letters) return;
  const action = roleConfig(state.user.role).action;
  const count = state.letters.filter(action).length;
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

function closeEditor() {
  if (state.editor) { state.editor.close(); state.editor = null; }
}

async function router() {
  if (!state.user) return;
  closeEditor();
  $('#workspace').classList.remove('menu-open');
  state.route += 1;
  const { parts, params } = parseRoute();
  const role = state.user.role;
  const view = $('#view');
  const routes = {
    '': renderDashboard,
    incoming: () => renderRegister('incoming', params),
    outgoing: () => renderRegister('outgoing', params),
    letters: () => { location.hash = `#/${params.get('dir') === 'outgoing' ? 'outgoing' : 'incoming'}`; },
    letter: () => renderDetail(Number(parts[1])),
    intake: can('register_incoming') ? renderIntake : null,
    compose: can('create_outgoing') ? () => renderCompose(params) : null,
    team: role === 'department_head' ? renderTeam : null,
    reports: can('view_reports') ? renderReports : null,
    admin: can('manage_users') ? renderAdmin : null,
    verify: renderVerify,
    account: renderAccount,
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
    <span class="row-main"><span class="row-ref">${isOutgoing(letter) ? `${icon('send', 'inline')} OUT · ` : `${icon('inbox', 'inline')} IN · `}${esc(letter.our_reference || letter.reference)}</span><span class="row-title">${esc(letter.subject)}</span>
    <span class="row-sub">${isOutgoing(letter) ? 'To ' : 'From '}${esc(letter.sender)}${showDept ? ` · ${esc(letter.department_name)}` : ''}${esc(who)}</span></span>
    <span class="row-side">${letter.matter_status === 'closed' ? matterPill(letter) : stagePill(letter)}<span class="row-meta">${letter.shared_with_me ? `<span class="chip out">${icon('users')}Shared with you</span>` : letter.collaborator_count ? `<span class="chip">${icon('users')}${letter.collaborator_count}</span>` : ''}${priorityChip(letter.priority)}${dueChip(letter)}</span></span></a>`;
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
  // Everyone, whatever their role, sees letters they were added to first.
  const inputQueue = { title: 'Shared with you', sub: 'Open letters you or your department were added to as collaborators.', filter: (l) => l.shared_with_me && isOpen(l), hideWhenEmpty: true };
  const queues = [inputQueue, ...config.queues].map((queue) => {
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
      ${heroCta ? `<div class="hero-actions">${(Array.isArray(heroCta[0]) ? heroCta : [heroCta]).filter(([, href]) => !PAGE_CAPABILITY[href.slice(2)] || can(PAGE_CAPABILITY[href.slice(2)])).map(([label, href]) => `<a class="btn" href="${href}" style="text-decoration:none">${esc(label)} ${icon('arrow')}</a>`).join('')}</div>` : ''}</div>
    <div class="kpis">${kpis}</div>
    ${queues}`;
}

/* ---------------- Registers ---------------- */
const REGISTER_VIEWS = {
  incoming: {
    open: ['Open', isOpen],
    unassigned: ['Awaiting assignment', (l) => l.status === 'intake'],
    awaiting: ['Awaiting a reply', awaitingReply],
    working: ['Being worked on', (l) => l.status === 'assigned' || l.status === 'in_progress'],
    overdue: ['Overdue', isOverdue],
    responded: ['Responded', (l) => l.status === 'finalized'],
  },
  outgoing: {
    open: ['Open', isOpen],
    unassigned: ['Awaiting a writer', (l) => l.status === 'intake'],
    head: ['With department head', (l) => l.status === 'dept_review'],
    drafting: ['Drafts', drafting],
    returned: ['Returned for revision', (l) => l.status === 'changes_requested'],
    review: ['In approval', (l) => IN_REVIEW.includes(l.status)],
    approved: ['Approved', (l) => l.status === 'finalized'],
    dispatch: ['Ready to dispatch', toDispatch],
    sent: ['Sent, delivery not confirmed', awaitingDelivery],
    delivered: ['Delivered', (l) => l.dispatch_status === 'delivered'],
    overdue: ['Overdue', isOverdue],
  },
};

async function renderRegister(direction, params) {
  const outgoing = direction === 'outgoing';
  setPage('Correspondence', outgoing ? 'Outgoing register' : 'Incoming register', direction);
  const view = $('#view');
  const token = state.route;
  if (!state.letters) view.innerHTML = skeleton();
  const all = await loadLetters(true);
  if (stale(token)) return;
  const letters = all.filter((l) => registerOf(l) === direction);
  const wide = can('all_letters');
  const views = REGISTER_VIEWS[direction];
  const preset = params.get('view');
  const matterOptions = outgoing ? { open: 'Open', closed: 'Closed' } : MATTER;
  view.innerHTML = `<section class="card">
    <div class="register-head"><div><h2>${outgoing ? 'Letters sent' : 'Letters received'}</h2><p>${outgoing ? 'New letters and replies: reference, approval, dispatch and delivery.' : 'Every letter received, who is handling it and how it was answered.'}</p></div>
      ${outgoing && can('create_outgoing') ? `<a class="btn btn-primary btn-sm" href="#/compose" style="text-decoration:none">${icon('plus')}New letter</a>` : ''}
      ${!outgoing && can('register_incoming') ? `<a class="btn btn-primary btn-sm" href="#/intake" style="text-decoration:none">${icon('plus')}Register letter</a>` : ''}</div>
    <div class="toolbar">
      <label class="search"><span class="sr-only">Search</span>${icon('search')}<input id="f-q" placeholder="Search subject, institution or any reference" value="${esc(params.get('q') || '')}"></label>
      <select id="f-view" aria-label="Show"><option value="">Everything</option>${Object.entries(views).map(([k, [label]]) => `<option value="${k}" ${preset === k ? 'selected' : ''}>${label}</option>`).join('')}</select>
      <select id="f-matter" aria-label="Status"><option value="">Any status</option>${Object.entries(matterOptions).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
      ${wide ? `<select id="f-dept" aria-label="Department"><option value="">All departments</option>${state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('')}</select>` : ''}
      <button class="btn btn-secondary btn-sm" id="export-csv" type="button">${icon('download')}Export</button>
    </div>
    <div id="list-body"></div></section>`;
  let rows = [];
  const draw = () => {
    const q = $('#f-q').value.trim().toLowerCase();
    const matter = $('#f-matter').value;
    const dept = $('#f-dept')?.value;
    const extra = views[$('#f-view').value]?.[1];
    rows = letters.filter((l) => (!q || [l.reference, l.our_reference, l.sender, l.subject, l.agency_reference, l.signatory, l.addressee, l.cc_parties, l.response_reference, l.in_reply_to_reference]
      .some((v) => String(v || '').toLowerCase().includes(q)))
      && (!matter || (l.matter_status || 'open') === matter) && (!dept || l.department_id === Number(dept)) && (!extra || extra(l)))
      .sort(byUrgency);
    const body = $('#list-body');
    if (!rows.length) { body.innerHTML = empty('No letters match', letters.length ? 'Try clearing a filter.' : 'Letters in your scope will appear here.', 'search'); return; }
    if (window.matchMedia('(max-width: 700px)').matches) { body.innerHTML = `<div class="rows">${rows.map((l) => letterRow(l)).join('')}</div>`; return; }
    body.innerHTML = `<div class="table-wrap"><table class="register">${outgoing ? outgoingTable(rows) : incomingTable(rows)}</table></div>
      <div class="toolbar" style="border-top:1px solid var(--line);border-bottom:0"><span class="count-note">${rows.length} of ${letters.length} letters</span></div>`;
  };
  ['f-q', 'f-matter', 'f-dept', 'f-view'].forEach((id) => document.getElementById(id)?.addEventListener('input', draw));
  $('#list-body').addEventListener('click', (event) => {
    if (event.target.closest('a')) return;
    const tr = event.target.closest('tr[data-id]');
    if (tr) location.hash = `#/letter/${tr.dataset.id}`;
  });
  $('#list-body').addEventListener('keydown', (event) => { const tr = event.target.closest('tr[data-id]'); if (tr && event.key === 'Enter') location.hash = `#/letter/${tr.dataset.id}`; });
  $('#export-csv').addEventListener('click', () => exportRegister(direction, rows));
  draw();
}

const sub = (text, cls = 'sub') => (text ? `<span class="${cls}">${text}</span>` : '');

function incomingTable(rows) {
  return `<thead><tr><th>Registered</th><th>Letter</th><th>On the letter</th><th>Handled by</th><th>Action &amp; deadline</th><th>Status</th><th>Reply</th></tr></thead><tbody>
    ${rows.map((l) => `<tr class="clickable" data-id="${l.id}" tabindex="0">
      <td><span class="mono">${esc(l.reference)}</span>${sub(esc(fmtDate(l.created_at)))}${sub(esc(RECEIVED_VIA[l.received_via] || ''))}</td>
      <td><span class="title">${esc(l.subject)}</span>${sub(`From ${esc(l.sender)}`)}</td>
      <td><span>${l.letter_date ? esc(fmtDate(l.letter_date)) : '—'}</span>${sub(esc(l.agency_reference || ''), 'sub mono')}${sub(l.signatory ? `Signed: ${esc(l.signatory)}` : '')}</td>
      <td><span>${esc(l.department_name)}</span>${sub(l.assignee_name ? esc(l.assignee_name) : 'Unassigned')}</td>
      <td><span>${esc(ACTIONS[l.action_required] || '—')}</span><div class="chips">${dueChip(l)}</div></td>
      <td><div class="chips">${statusPills(l)}</div>${sub(esc(l.status_remarks || ''), 'sub remarks')}</td>
      <td>${l.response_id ? `<a class="mono" href="#/letter/${l.response_id}">${esc(l.response_reference)}</a>${sub(esc(stageLabel({ direction: 'outgoing', status: l.response_status, dispatch_status: l.response_dispatch_status })))}` : '<span class="sub">—</span>'}</td></tr>`).join('')}</tbody>`;
}

function outgoingTable(rows) {
  return `<thead><tr><th>Our ref</th><th>Letter</th><th>From</th><th>In reply to</th><th>Stage</th><th>Dispatch</th><th>Delivery</th></tr></thead><tbody>
    ${rows.map((l) => `<tr class="clickable" data-id="${l.id}" tabindex="0">
      <td><span class="mono">${esc(l.our_reference)}</span>${sub(esc(fmtDate(l.finalized_at || l.created_at)))}</td>
      <td><span class="title">${esc(l.subject)}</span>${sub(`To ${l.addressee ? `${esc(l.addressee)}, ` : ''}${esc(l.sender)}`)}</td>
      <td><span>${esc(l.department_name)}</span>${sub(esc(l.assignee_name || ''))}</td>
      <td>${l.in_reply_to ? `<a class="mono" href="#/letter/${l.in_reply_to}">${esc(l.in_reply_to_reference)}</a>` : '<span class="sub">New letter</span>'}</td>
      <td><div class="chips">${l.matter_status === 'closed' ? matterPill(l) : ''}${stagePill(l)}${dueChip(l)}</div></td>
      <td>${l.dispatch_method ? `<span>${esc(DISPATCH_METHODS[l.dispatch_method] || l.dispatch_method)}</span>${sub(esc(fmtDate(l.dispatched_on)))}` : '<span class="sub">—</span>'}</td>
      <td>${['delivered', 'returned'].includes(l.dispatch_status) ? `<span>${l.dispatch_status === 'delivered' ? 'Delivered' : 'Returned'} ${esc(fmtDate(l.delivered_on))}</span>${sub(esc(l.delivery_note || ''))}` : '<span class="sub">—</span>'}</td></tr>`).join('')}</tbody>`;
}

function exportRegister(direction, rows) {
  const common = [['Department', (l) => l.department_name], ['Status', (l) => MATTER[l.matter_status] || 'Open'], ['Remarks', (l) => l.status_remarks], ['Stage', (l) => stageLabel(l)], ['Deadline', (l) => l.due_date]];
  const columns = direction === 'outgoing' ? [
    ['Our ref', (l) => l.our_reference], ['Date created', (l) => (l.created_at || '').slice(0, 10)], ['Date approved', (l) => (l.finalized_at || '').slice(0, 10)],
    ['Subject', (l) => l.subject], ['Addressee', (l) => l.addressee], ['Institution', (l) => l.sender], ['Written by', (l) => l.assignee_name],
    ['In reply to', (l) => l.in_reply_to_reference], ['Copied to', (l) => (l.cc_parties || '').replace(/\s*\n\s*/g, '; ')], ...common,
    ['Dispatch method', (l) => DISPATCH_METHODS[l.dispatch_method] || ''], ['Date sent', (l) => l.dispatched_on],
    ['Delivery', (l) => (['delivered', 'returned'].includes(l.dispatch_status) ? DISPATCH[l.dispatch_status] : '')], ['Delivery date', (l) => l.delivered_on], ['Delivery note', (l) => l.delivery_note],
  ] : [
    ['Register no.', (l) => l.reference], ['Date registered', (l) => (l.created_at || '').slice(0, 10)], ['Date received', (l) => l.received_date],
    ['Received via', (l) => RECEIVED_VIA[l.received_via] || ''], ['Subject', (l) => l.subject], ['Institution', (l) => l.sender],
    ['Date on letter', (l) => l.letter_date], ['Reference on letter', (l) => l.agency_reference], ['Signed by', (l) => l.signatory],
    ['Copied parties', (l) => (l.cc_parties || '').replace(/\s*\n\s*/g, '; ')], ['Assigned to', (l) => l.assignee_name],
    ['Action required', (l) => ACTIONS[l.action_required] || ''], ...common, ['Reply ref', (l) => l.response_reference],
  ];
  const cell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const csv = [columns.map(([label]) => cell(label)).join(','), ...rows.map((l) => columns.map(([, get]) => cell(get(l))).join(','))].join('\r\n');
  const link = document.createElement('a');
  // The byte-order mark makes Excel read the file as UTF-8.
  link.href = URL.createObjectURL(new Blob(['﻿', csv], { type: 'text/csv' }));
  link.download = `${direction}-register-${todayISO()}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

/* ---------------- Letter editor ---------------- */
// Mirrors workflow.can_edit: the writer while drafting, the department head while reviewing it, the MD until approval.
function canEdit(letter) {
  if (!isOutgoing(letter) || letter.status === 'finalized') return false;
  if (state.user.role === 'md') return true;
  if (letter.status === 'dept_review') return isHeadOf(letter);
  return handlesLetter(letter) && drafting(letter);
}

// The company letterhead, as it prints: header with Our Ref under the rule, watermark behind, footer at the end.
const letterheadPage = (letter, inner, cls = '') => `<div class="paper lh-paper ${cls}">
  <img class="lh-head" src="/static/letterhead/header.png" alt="Swami India Ghana Limited letterhead">
  <div class="lh-ref">Our Ref: <b>${esc(letter.our_reference || '')}</b></div>
  <div class="lh-body">${inner}</div>
  <img class="lh-foot" src="/static/letterhead/footer.png" alt=""></div>`;

// body_html is sanitised by the server before it is stored, so it can be shown as it is.
function closingPreview(letter) {
  const signer = letter.signatory;
  if (!signer || letter.status === 'finalized') return '';
  const enclosures = letter.enclosure_list || [];
  const copies = String(letter.cc_parties || '').split(/\n+/).map((line) => line.trim()).filter(Boolean);
  return `<div class="closing-preview" title="Added by the app from “Signed by”. Change the signatory to change it.">
    <div class="sign-space">${signer.has_signature ? 'Signature added on approval' : 'Signing space'}</div>
    <p><strong>${esc(signer.name)}</strong></p>${signer.title !== signer.name ? `<p>${esc(signer.title)}</p>` : ''}<p>For: Swami India Ghana Limited</p>
    ${enclosures.length ? `<p class="gap"><strong>Enc.:</strong></p><ol>${enclosures.map((e) => `<li>${esc(e.file_name)}</li>`).join('')}</ol>` : ''}
    ${copies.length ? `<p class="gap">cc:</p>${copies.map((c) => `<p>${esc(c)}</p>`).join('')}` : ''}</div>`;
}

function letterPaper(letter) {
  const body = letter.body_html ? `<div class="letter-body">${letter.body_html}</div>` : `<div class="paper-text">${esc(letter.response_text || '')}</div>`;
  return letterheadPage(letter, body + closingPreview(letter));
}

// Who signs: the MD, or a head of the sending department. Shown where the letter can be edited.
async function signatoryPicker(letter) {
  const choices = await api(`/signatories?department_id=${letter.department_id}`);
  const current = letter.signatory_id || 'md';
  return `<label class="signed-by">Signed by<select id="signatory-select">${choices.map((c) => `<option value="${c.id}" ${String(c.id) === String(current) ? 'selected' : ''}>${esc(c.name)}${c.title !== c.name ? ` · ${esc(c.title)}` : ''}</option>`).join('')}</select></label>`;
}

// Shown instead of the editor, so it is clear the letter is edited here and by whom right now.
function whoCanEdit(letter) {
  const writer = letter.assignee_name || 'the writer';
  return {
    finalized: 'Approved and locked. The PDF is the final copy.',
    intake: 'No one is writing it yet. The department head assigns a writer, who then edits it here.',
    in_progress: `${writer} is writing it here. Only they can edit it at this stage.`,
    changes_requested: `Returned to ${writer}, who is revising it here.`,
    dept_review: 'With the department head, who can edit it here before approving.',
    submitted_for_review: 'With the MD PA. The MD can still edit it here.',
    md_review: 'With the MD, who can edit it here before approving.',
  }[letter.status] || 'Read only at this stage.';
}

function editorCard(letter, picker = '') {
  return `<section class="card editor-card">
    <div class="card-head"><div><h3>The letter</h3><p>Write it here. It saves on its own every few seconds, and when you press Ctrl+S.</p></div>
      <div class="editor-head-side">${picker}<span class="save-state" id="save-state">All changes saved</span></div></div>
    <div id="editor-toolbar" class="editor-toolbar">
      <span class="ql-formats"><select class="ql-header" title="Paragraph style"><option value="1">Heading</option><option value="2">Subheading</option><option selected>Normal text</option></select>
        <select class="ql-size" title="Text size"><option value="small">Small</option><option selected>Normal</option><option value="large">Large</option></select></span>
      <span class="ql-formats"><button class="ql-bold" title="Bold (Ctrl+B)"></button><button class="ql-italic" title="Italic (Ctrl+I)"></button><button class="ql-underline" title="Underline (Ctrl+U)"></button><button class="ql-strike" title="Strikethrough"></button></span>
      <span class="ql-formats"><button class="ql-list" value="ordered" title="Numbered list"></button><button class="ql-list" value="bullet" title="Bullet list"></button><button class="ql-indent" value="-1" title="Decrease indent"></button><button class="ql-indent" value="+1" title="Increase indent"></button></span>
      <span class="ql-formats"><select class="ql-align" title="Alignment"></select><button class="ql-clean" title="Clear formatting"></button></span>
      <span class="ql-formats"><button type="button" class="ed-undo" title="Undo (Ctrl+Z)">${icon('returned')}</button><button type="button" class="ed-redo" title="Redo (Ctrl+Y)">${icon('refresh')}</button></span>
    </div>
    <div class="editor-desk">${letterheadPage(letter, `<div id="letter-editor"></div>${closingPreview(letter)}`, 'editor-page')}</div>
  </section>`;
}

function mountEditor(letter) {
  if (!window.Quill) { $('#letter-editor').innerHTML = '<p>The editor could not load. Refresh the page.</p>'; return null; }
  const quill = new Quill('#letter-editor', {
    theme: 'snow',
    modules: { toolbar: '#editor-toolbar', history: { delay: 800, maxStack: 300, userOnly: true } },
  });
  quill.clipboard.dangerouslyPasteHTML(letter.body_html || '');
  quill.history.clear();
  $('.ed-undo').onclick = () => quill.history.undo();
  $('.ed-redo').onclick = () => quill.history.redo();
  const status = (text, cls = '') => { const node = $('#save-state'); if (node) { node.textContent = text; node.className = `save-state ${cls}`; } };
  let dirty = false;
  let saving = null;
  const save = async () => {
    if (!dirty) return saving || Promise.resolve();
    dirty = false;
    status('Saving…');
    saving = api(`/letters/${letter.id}/response`, { method: 'PUT', json: { body_html: quill.getSemanticHTML() } })
      .then((saved) => { letter.body_html = saved.body_html; letter.response_text = saved.response_text; status(dirty ? 'Unsaved changes' : `Saved ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`, 'ok'); })
      .catch((error) => { dirty = true; status('Not saved', 'error'); throw error; });
    return saving;
  };
  quill.on('text-change', (delta, old, source) => { if (source === 'user') { dirty = true; status('Unsaved changes'); } });
  const timer = setInterval(() => save().catch((error) => toast(error.message, 'error')), 4000);
  quill.root.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save().then(() => toast('Saved.')).catch((error) => toast(error.message, 'error')); }
  });
  const warn = (event) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
  window.addEventListener('beforeunload', warn);
  return {
    save,
    // Leaving the page: save what is there and stop the timers.
    close: () => { clearInterval(timer); window.removeEventListener('beforeunload', warn); if (dirty) save().catch(() => toast('Your last changes could not be saved.', 'error')); },
  };
}

/* ---------------- Letter detail ---------------- */
const INCOMING_STEPS = ['Received', 'Assigned', 'Reply drafted', 'Responded'];
const OUTGOING_STEPS = ['Registered', 'Drafting', 'Dept. head', 'PA review', 'MD review', 'Sent', 'Delivered'];

function stepper(letter) {
  let labels;
  let current;
  let returned = -1;
  if (isOutgoing(letter)) {
    labels = OUTGOING_STEPS;
    // After MD approval the step in progress is sending (5), then delivery (6); delivered means all done.
    current = letter.status === 'finalized'
      ? { sent: 6, delivered: 7 }[letter.dispatch_status] ?? 5
      : { intake: 0, in_progress: 1, changes_requested: 1, dept_review: 2, submitted_for_review: 3, md_review: 4 }[letter.status] ?? 1;
    if (letter.status === 'changes_requested') returned = 1;
  } else {
    labels = INCOMING_STEPS;
    current = { intake: 0, assigned: 1, in_progress: 2, finalized: 4 }[letter.status] ?? 0;
  }
  return `<div class="card stepper">${labels.map((label, index) => {
    const done = index < current;
    const isReturned = index === returned;
    const cls = done ? 'done' : index === current ? (isReturned ? 'current returned' : 'current') : '';
    return `<div class="step ${cls}"><span class="step-dot">${done ? icon('tick') : isReturned ? icon('returned') : index + 1}</span>${isReturned ? 'Returned' : label}</div>`;
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
    response_started: ['file', 'blue', `Reply ${esc(details.our_reference || '')} started by ${who}`],
    response_approved: ['check', 'green', `Reply ${esc(details.our_reference || '')} approved by ${who}`],
    outgoing_created: ['send', 'wine', `Letter ${esc(details.our_reference || '')} registered by ${who}${details.assignee_id ? '' : ' · waiting for the department to assign a writer'}`],
    response_saved: ['edit', '', `Letter edited by ${who}`],
    response_uploaded: ['upload', '', `Edited Word draft uploaded by ${who}`],
    submitted_for_review: ['send', 'blue', `Sent for approval by ${who}${event.to_status === 'dept_review' ? ' to the department head' : ''}`],
    department_approved: ['check', 'blue', `Approved for the department by ${who}`],
    routed_to_md: ['arrow', 'wine', `Sent to the MD by ${who}`],
    changes_requested: ['returned', 'red', `Returned for revision by ${who}`],
    approved_and_finalized: ['lock', 'green', `Approved and locked by ${who}${details.word_copy_deleted ? ' · editable draft deleted' : details.word_copy_kept ? ' · approved Word copy kept' : ''}`],
    md_override: ['alert', 'wine', `MD override by ${who}: skipped from “${esc(STATUS[details.skipped_from] || details.skipped_from || 'an earlier stage')}”`],
    dispatched: ['send', 'blue', `Sent by ${esc(DISPATCH_METHODS[details.method] || details.method)} on ${esc(fmtDate(details.sent_on))} · recorded by ${who}`],
    delivery_recorded: ['check', details.outcome === 'delivered' ? 'green' : 'red', `${details.outcome === 'delivered' ? 'Delivered' : 'Returned undelivered'} on ${esc(fmtDate(details.date))} · recorded by ${who}${details.closed ? ' · correspondence closed' : ''}`],
    tracking_updated: ['check', '', `Tracking updated by ${who}: ${esc(Object.keys(details.changes || {}).map((f) => ({ matter_status: `status ${MATTER[details.to] || details.to}`, status_remarks: 'remarks', action_required: 'action required', due_date: 'deadline' }[f] || f)).join(', '))}`],
    collaborator_added: ['users', 'blue', `${esc(details.collaborator || '')} brought in by ${who}`],
    collaborator_removed: ['x', '', `${esc(details.collaborator || '')} taken off by ${who}`],
    enclosure_added: ['file', '', `Enclosure “${esc(details.file_name || '')}” added by ${who}`],
    enclosure_removed: ['x', '', `Enclosure “${esc(details.file_name || '')}” removed by ${who}`],
    register_details_edited: ['edit', 'wine', `Details corrected by ${who}: ${esc(Object.keys(details.changes || {}).map((f) => REGISTER_LABELS[f] || f).join(', '))}`],
  };
  const [iconName, tone, text] = map[event.action] || ['clock', '', `${esc(event.action.replaceAll('_', ' '))} by ${who}`];
  return { iconName, tone, text, quote: details.details || '' };
}

function timeline(audit, letter) {
  const items = [];
  audit.forEach((event) => {
    const last = items[items.length - 1];
    if (['response_saved', 'response_uploaded'].includes(event.action) && last && last.action === event.action && last.actor_id === event.actor_id) { last.repeat += 1; last.created_at = event.created_at; return; }
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
  if (!event) return { text: '', by: '' };
  let text = '';
  try { text = JSON.parse(event.details || '{}').details || ''; } catch { text = ''; }
  return { text, by: event.actor_role === 'md' ? 'the MD' : 'your department head' };
}

const isAdmin = () => can('all_letters');
const isHeadOf = (letter) => state.user.role === 'department_head' && state.user.department_id === letter.department_id;
// Collaborators share the control of the person the letter is assigned to.
const isCollaborator = (letter) => (letter.collaborators || []).some((c) => c.user_id === state.user.id || (c.department_id && c.department_id === state.user.department_id));
const handlesLetter = (letter) => letter.assigned_to === state.user.id || isCollaborator(letter);
const isWriter = (letter) => handlesLetter(letter) && drafting(letter);
// Drafts go to the department head first unless written by a head, the MD PA or the MD.
const goesToHead = () => !['department_head', 'md_pa', 'md'].includes(state.user.role);
const canTrack = (letter) => isAdmin() || handlesLetter(letter) || isHeadOf(letter);
const canRespond = () => can('create_outgoing');
const canDispatch = (letter) => can('dispatch_letters') || handlesLetter(letter) || isHeadOf(letter);
const mayRoute = () => can('route_letters');
const mayAssign = (letter) => can('assign_letters') && (can('all_letters') || state.user.department_id === letter.department_id);
const draftName = (letter) => `${String(letter.our_reference || letter.reference).replaceAll('/', '-')}.docx`;
const card = (title, sub, body, eyebrow = 'Your action') => `<section class="card action-card"><div class="card-head"><div><p class="eyebrow">${eyebrow}</p><h3>${esc(title)}</h3>${sub ? `<p>${esc(sub)}</p>` : ''}</div></div><div class="action-body">${body}</div></section>`;
const today = () => todayISO();

/* Shared by both registers: send a letter to another department, or pick who handles it. */
function routeBlock(letter) {
  const deptOptions = state.departments.map((d) => `<option value="${d.id}" ${d.id === letter.department_id ? 'selected' : ''}>${esc(d.name)}</option>`).join('');
  return `<label>Department<select id="a-dept">${deptOptions}</select></label><div class="btn-row"><button class="btn btn-secondary" data-act="route-department">${icon('arrow')}Route to department</button></div>`;
}

async function assignBlock(letter, { selfLabel } = {}) {
  const members = (await loadTeamMembers()).filter((m) => m.department_id === letter.department_id);
  const self = selfLabel ? `<button class="btn btn-secondary" data-act="assign-self">${icon('edit')}${esc(selfLabel)}</button>` : '';
  if (!members.length) return `<p>There are no active team members in ${esc(letter.department_name)}. Add one under Users &amp; departments.</p>${self ? `<div class="btn-row">${self}</div>` : ''}`;
  return `<label>${isOutgoing(letter) ? 'Who will write it' : 'Assign to'}<select id="a-assignee"><option value="">Choose a team member…</option>${members.map((m) => `<option value="${m.id}" ${m.id === letter.assigned_to ? 'selected' : ''}>${esc(m.display_name)}</option>`).join('')}</select></label>
    <div class="btn-row"><button class="btn btn-primary" data-act="assign">${icon('user')}${letter.assigned_to ? 'Reassign' : 'Assign'}</button>${self}</div>`;
}

/* Action panel for a received letter. */
async function incomingPanel(letter, responses) {
  const role = state.user.role;
  const s = letter.status;
  const open = responses.find((r) => r.status !== 'finalized');
  const done = responses.filter((r) => r.status === 'finalized');
  const respondButton = (label = 'Respond: write the reply') => `<button class="btn btn-primary" data-act="respond">${icon('file')}${esc(label)}</button>`;
  const replyLink = (r) => `<a class="reply-link" href="#/letter/${r.id}">${icon('send')}<span><strong class="mono">${esc(r.our_reference)}</strong><small>${esc(stageLabel({ ...r, direction: 'outgoing' }))}</small></span>${icon('arrow')}</a>`;

  if (s === 'intake' && !isHeadOf(letter) && (mayRoute() || mayAssign(letter))) {
    const blocks = [mayRoute() ? routeBlock(letter) : '', mayAssign(letter) ? await assignBlock(letter) : ''].filter(Boolean);
    const respond = canRespond(letter) ? `<hr class="sep"><div class="btn-row">${respondButton('Respond to it myself')}</div>` : '';
    return card(mayAssign(letter) ? 'Route or assign' : 'Route this letter', 'Send it to the right department, choose who handles it, or reply to it yourself.', blocks.join('<hr class="sep">') + respond);
  }
  if (isHeadOf(letter) && mayAssign(letter) && ['intake', 'assigned'].includes(s) && !open) {
    return card(s === 'intake' ? 'Assign this letter' : 'Assigned', s === 'intake' ? 'Choose who will prepare the reply.' : `${letter.assignee_name} is to reply. You can reassign it.`,
      `${await assignBlock(letter)}<hr class="sep"><div class="btn-row">${respondButton('Reply yourself')}</div>`);
  }
  if (open) return card('Reply in progress', 'The reply is a separate outgoing letter. Open it to write, approve or track it.', replyLink(open), 'Reply');
  if (s !== 'finalized' && canRespond(letter)) {
    return card('Respond to this letter', 'Opens the reply on SIGL letterhead, with its reference number, ready to write here in the app.',
      `<div class="btn-row">${respondButton()}</div>${role === 'md' ? mdQuickReply() : ''}`);
  }
  if (role === 'md' && s !== 'finalized') return card('Reply directly', 'Approve a reply now without waiting for the department. Recorded in the history.', mdQuickReply(), 'MD override');
  if (s === 'finalized') {
    // The replies themselves are listed in the "Replies sent" card below.
    return card('Responded', done.length ? `Replied on ${fmtDate(done[done.length - 1].finalized_at)}.` : 'Closed.', canRespond(letter) ? `<div class="btn-row">${respondButton('Send a further letter')}</div>` : '', 'Complete');
  }
  const waiting = { intake: `Waiting for ${letter.department_name} to assign it.`, assigned: `${letter.assignee_name || 'The assignee'} has not replied yet.`, in_progress: 'A reply is being drafted.' }[s] || '';
  return `<section class="card"><div class="card-head"><div><p class="eyebrow">Stage</p><h3>${esc(stageLabel(letter))}</h3><p>${esc(waiting)}</p></div></div></section>`;
}

const mdQuickReply = () => `<details class="quick-reply"><summary>Or type the reply and approve it now</summary>
  <textarea id="a-md-response" class="response-editor" placeholder="Write the reply that will go on the final letter…"></textarea>
  <div class="btn-row"><button class="btn btn-success" data-act="md-approve-incoming">${icon('lock')}Approve &amp; lock reply</button></div></details>`;

/* Action panel for a letter being sent: the same line as received letters, then approval and dispatch.
   The letter itself is on the left of the page, in the editor for whoever may change it. */
async function outgoingPanel(letter, audit) {
  const role = state.user.role;
  const s = letter.status;
  const returnedBy = latestFeedback(audit);
  const feedback = s === 'changes_requested' ? `<div class="feedback"><strong>Returned for revision by ${esc(returnedBy.by)}</strong>${esc(returnedBy.text || 'Please revise the letter.')}</div>` : '';
  const instructions = letter.notes ? `<div class="instructions"><strong>Instructions</strong>${esc(letter.notes)}</div>` : '';
  const editHint = canEdit(letter) ? '<p class="hint-text">You can correct the letter on the left before deciding. Changes save automatically.</p>' : '';

  if (s === 'finalized') return dispatchPanel(letter);
  if (s === 'intake') {
    if (isHeadOf(letter)) return card('Assign a writer', 'Choose who in your department will write this letter, or write it yourself.', `${instructions}${await assignBlock(letter, { selfLabel: 'Write it myself' })}`);
    if (mayRoute() || mayAssign(letter)) {
      const blocks = [mayRoute() ? routeBlock(letter) : '', mayAssign(letter) ? await assignBlock(letter) : ''].filter(Boolean);
      return card(mayAssign(letter) ? 'Route or assign' : 'Route this letter', 'Send it to the right department, or choose who writes it.', `${instructions}${blocks.join('<hr class="sep">')}`);
    }
  }
  if (role !== 'md' && isWriter(letter)) {
    const next = goesToHead() ? 'the department head, then the MD PA and the MD' : 'the MD PA and the MD';
    return card(s === 'changes_requested' ? 'Revise the letter' : 'Write the letter', `Write it in the editor on the left. When it is ready, send it for approval by ${next}.`,
      `${feedback}${instructions}<div class="btn-row"><button class="btn btn-primary" data-act="submit">${icon('send')}Send for approval</button></div>`);
  }
  if (s === 'dept_review' && isHeadOf(letter)) {
    return card('Approve for the department', `${letter.assignee_name || 'Your team'} sent this for approval. Approving passes it to the MD PA and the MD.`,
      `${editHint}<div class="btn-row"><button class="btn btn-success" data-act="dept-approve">${icon('check')}Approve</button><button class="btn btn-danger-outline" data-act="changes">${icon('returned')}Return for revision</button></div>`, 'Department approval');
  }
  if (role === 'md_pa' && s === 'submitted_for_review') return card('Review and route to the MD', 'Read the letter on the left, then send it to the MD.', `<div class="btn-row"><button class="btn btn-primary" data-act="route-md">${icon('send')}Route to the MD</button></div>`);
  if (role === 'md' && s === 'md_review') {
    return card('Your decision', `Approving makes the locked PDF${letter.in_reply_to ? ' and deletes the editable draft' : ' and an approved Word copy'}.`,
      `${editHint}<div class="btn-row"><button class="btn btn-success" data-act="approve">${icon('lock')}Approve &amp; lock</button><button class="btn btn-danger-outline" data-act="changes">${icon('returned')}Return for revision</button></div>`);
  }
  if (role === 'md') {
    const own = letter.assigned_to === state.user.id;
    return card('Approve directly', own ? 'You are writing this letter. Approve it when it is ready.' : `This letter is at “${stageLabel(letter)}”. You can approve it now. The override is recorded in its history.`,
      `${feedback}${instructions}${editHint}<div class="btn-row"><button class="btn btn-success" data-act="md-approve">${icon('lock')}Approve &amp; lock now</button></div>`, own ? 'Your letter' : 'MD override');
  }
  const waiting = {
    intake: `Waiting for ${letter.department_name} to assign a writer.`,
    in_progress: `${letter.assignee_name || 'The writer'} is drafting the letter.`, changes_requested: `Returned to ${letter.assignee_name || 'the writer'} for revision.`,
    dept_review: `Waiting for the ${letter.department_name} head to approve it.`,
    submitted_for_review: 'Waiting for the MD PA to route it to the MD.', md_review: 'Waiting for the MD’s decision.',
  }[s] || '';
  return `<section class="card"><div class="card-head"><div><p class="eyebrow">Stage</p><h3>${esc(stageLabel(letter))}</h3><p>${esc(waiting)}</p></div></div>
    ${feedback || instructions ? `<div class="action-body">${feedback}${instructions}</div>` : ''}</section>`;
}

function dispatchPanel(letter) {
  const files = `<div class="btn-row"><a class="btn btn-success" href="/letters/${letter.id}/pdf" style="text-decoration:none">${icon('download')}Final PDF</a>
    ${letter.has_word_draft ? `<a class="btn btn-secondary" href="/letters/${letter.id}/response-docx" style="text-decoration:none">${icon('file')}Approved Word</a>` : ''}</div>`;
  const methodOptions = Object.entries(DISPATCH_METHODS).map(([k, v]) => `<option value="${k}" ${letter.dispatch_method === k ? 'selected' : ''}>${v}</option>`).join('');
  const status = letter.dispatch_status || 'pending';
  const sentLine = letter.dispatch_method ? `<p class="fact-line">${icon('send', 'inline')} Sent by <b>${esc(DISPATCH_METHODS[letter.dispatch_method] || letter.dispatch_method)}</b> on ${esc(fmtDate(letter.dispatched_on))}${letter.dispatched_by_name ? ` · recorded by ${esc(letter.dispatched_by_name)}` : ''}${letter.dispatch_note ? `<br><span class="sub">${esc(letter.dispatch_note)}</span>` : ''}</p>` : '';
  if (!canDispatch(letter)) {
    return card(DISPATCH[status] || 'Approved', `Approved on ${fmtDate(letter.finalized_at)}.`, `${sentLine}${files}`, 'Approved');
  }
  if (['pending', 'returned'].includes(status) && letter.matter_status !== 'closed') {
    return card(status === 'returned' ? 'Returned undelivered: send again' : 'Dispatch this letter', 'Print or email the final PDF, then record how it was sent.', `${files}
      ${status === 'returned' ? `<div class="feedback"><strong>Returned on ${esc(fmtDate(letter.delivered_on))}</strong>${esc(letter.delivery_note || '')}</div>` : ''}
      <div class="form-pair"><label>Sent by<select id="d-method"><option value="">Choose…</option>${methodOptions}</select></label>
      <label>Date sent<input id="d-date" type="date" value="${today()}" max="${today()}"></label></div>
      <label><span>Note <span class="hint">(optional, e.g. rider’s name or tracking number)</span></span><input id="d-note" autocomplete="off"></label>
      <div class="btn-row"><button class="btn btn-primary" data-act="dispatch">${icon('send')}Mark as sent</button></div>`, 'Dispatch');
  }
  if (status === 'sent') {
    return card('Confirm delivery', 'Record when it arrived, ideally with the stamped or signed copy.', `${sentLine}
      <div class="form-pair"><label>Outcome<select id="v-outcome"><option value="delivered">Delivered</option><option value="returned">Returned undelivered</option></select></label>
      <label>Date<input id="v-date" type="date" value="${today()}" max="${today()}"></label></div>
      <label><span>Received by / note <span class="hint">(optional)</span></span><input id="v-note" placeholder="e.g. Received by A. Owusu, Registry" autocomplete="off"></label>
      <label><span>Proof of delivery <span class="hint">(optional: PDF, PNG or JPG)</span></span><input id="v-proof" type="file" accept=".pdf,.png,.jpg,.jpeg"></label>
      <label class="check"><input id="v-close" type="checkbox" checked> Close this correspondence once delivered</label>
      <div class="btn-row"><button class="btn btn-success" data-act="delivery">${icon('check')}Record delivery</button></div>${files}`, 'Delivery');
  }
  return card(status === 'delivered' ? 'Delivered' : DISPATCH[status] || 'Approved', status === 'delivered' ? `Delivered on ${fmtDate(letter.delivered_on)}.` : '', `${sentLine}
    ${letter.delivery_note ? `<p class="fact-line">${icon('check', 'inline')} ${esc(letter.delivery_note)}</p>` : ''}
    ${letter.has_delivery_proof ? `<div class="btn-row"><a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/delivery-proof" style="text-decoration:none">${icon('download')}Proof of delivery</a></div>` : ''}${files}`, 'Complete');
}

function trackingCard(letter) {
  const outgoing = isOutgoing(letter);
  const remarks = letter.status_remarks ? `<p class="remarks-text">${esc(letter.status_remarks)}</p>` : '';
  if (!canTrack(letter)) {
    return `<section class="card"><div class="card-head"><div><h3>Status &amp; remarks</h3><p>${outgoing ? '' : `${esc(ACTIONS[letter.action_required] || 'No action set')} · `}${letter.due_date ? `deadline ${esc(fmtDate(letter.due_date))}` : 'no deadline'}</p></div>${matterPill(letter)}</div>${remarks ? `<div class="action-body">${remarks}</div>` : ''}</section>`;
  }
  const matterOptions = outgoing ? { open: 'Open', closed: 'Closed' } : MATTER;
  return `<section class="card"><div class="card-head"><div><h3>Status &amp; remarks</h3><p>Can be updated at any time.${outgoing ? '' : ' Approval of the reply sets it to Responded.'}</p></div>${matterPill(letter)}</div>
    <div class="action-body">
      <div class="form-pair">
        <label>Status<select id="m-status">${Object.entries(matterOptions).map(([k, v]) => `<option value="${k}" ${(letter.matter_status || 'open') === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>${outgoing ? 'Send by' : 'Deadline'}<input id="m-due" type="date" value="${esc(letter.due_date || '')}"></label>
      </div>
      ${outgoing ? '' : `<label>Action required<select id="m-action"><option value="">Not set</option>${Object.entries(ACTIONS).map(([k, v]) => `<option value="${k}" ${letter.action_required === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>`}
      <label><span>Remarks</span><textarea id="m-remarks" rows="2" placeholder="e.g. Waiting for the quotation from the supplier">${esc(letter.status_remarks || '')}</textarea></label>
      <div class="btn-row"><button class="btn btn-secondary" data-act="tracking">${icon('check')}Save</button></div>
    </div></section>`;
}

/* ---------------- Tracking journey ---------------- */
function fmtDuration(ms) {
  const minutes = Math.max(0, Math.round(ms / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}

// Who the letter is waiting on right now, in words.
function holderOf(letter) {
  const head = `${letter.department_name} head`;
  const writer = letter.assignee_name || 'the writer';
  if (!isOutgoing(letter)) {
    return { intake: `${head}, to assign it`, assigned: `${writer}, to reply`, in_progress: `${writer}, writing the reply` }[letter.status] || null;
  }
  if (letter.matter_status === 'closed') return null;
  if (letter.status === 'finalized') {
    return { pending: 'Front desk, to dispatch it', returned: 'Front desk, to send it again', sent: 'In transit: waiting for delivery confirmation' }[letter.dispatch_status] || null;
  }
  return {
    intake: `${head}, to assign a writer`, in_progress: `${writer}, writing it`, changes_requested: `${writer}, revising it`,
    dept_review: `${head}, to approve it`, submitted_for_review: 'MD PA, to route it to the MD', md_review: 'Managing Director, to approve it',
  }[letter.status] || null;
}

const MILESTONES = new Set(['intake_created', 'outgoing_created', 'routed_to_department', 'assigned', 'response_started', 'submitted_for_review',
  'department_approved', 'changes_requested', 'routed_to_md', 'md_override', 'approved_and_finalized', 'response_approved', 'dispatched', 'delivery_recorded']);

function journeyCard(letter, audit) {
  const steps = audit.filter((event) => MILESTONES.has(event.action));
  const holder = holderOf(letter);
  const now = Date.now();
  const last = steps[steps.length - 1];
  const started = parseTs(letter.created_at);
  const done = !holder;
  const finishedAt = last ? parseTs(last.created_at) : started;
  const summary = done
    ? `Completed in ${fmtDuration(finishedAt - started)}.`
    : `With <strong>${esc(holder)}</strong> for ${fmtDuration(now - parseTs(last ? last.created_at : letter.created_at))}. Open ${fmtDuration(now - started)} in total.`;
  const due = letter.due_date ? `<span class="chip ${isOverdue(letter) ? 'overdue' : ''}">${icon('clock')}${isOverdue(letter) ? 'Overdue' : 'Deadline'} ${esc(fmtDate(letter.due_date))}</span>` : '';
  const rows = steps.map((event, index) => {
    const { text } = describeEvent(event, letter);
    const took = index ? fmtDuration(parseTs(event.created_at) - parseTs(steps[index - 1].created_at)) : '';
    return `<li class="${index === steps.length - 1 && !done ? 'latest' : ''}"><span class="j-dot"></span><div><strong>${text}</strong><small>${esc(fmtDateTime(event.created_at))}${took ? ` · after ${took}` : ''}</small></div></li>`;
  }).join('');
  return `<section class="card"><div class="card-head"><div><h3>Tracking</h3><p>${summary}</p></div>${due}</div>
    <ol class="journey">${rows}${done ? '' : `<li class="next"><span class="j-dot"></span><div><strong>Next: ${esc(holder)}</strong><small>Waiting now</small></div></li>`}</ol></section>`;
}

/* ---------------- Collaborators ---------------- */
const collabName = (c) => c.user_name || c.department_name;

function pickerHtml(people, { takenUsers = new Set(), takenDepartments = new Set(), message = true } = {}) {
  const option = (kind, id, label, detail) => `<label class="pick" data-search="${esc(`${label} ${detail}`.toLowerCase())}"><input type="checkbox" data-kind="${kind}" value="${id}"><span><strong>${esc(label)}</strong><small>${esc(detail)}</small></span></label>`;
  const departments = state.departments.filter((d) => !takenDepartments.has(d.id)).map((d) => option('department', d.id, d.name, 'Whole department'));
  const persons = people.filter((person) => !takenUsers.has(person.id) && person.id !== state.user.id)
    .map((person) => option('user', person.id, person.display_name, `${ROLE_NAMES[person.role] || ''}${person.department_name ? ` · ${person.department_name}` : ''}`));
  return `<div class="picker">
    <label class="search collab-search"><span class="sr-only">Find people or departments</span>${icon('search')}<input class="picker-filter" placeholder="Find a person or department" autocomplete="off"></label>
    <div class="pick-list">
      ${departments.length ? `<p class="pick-group">Departments</p>${departments.join('')}` : ''}
      ${persons.length ? `<p class="pick-group">People</p>${persons.join('')}` : ''}
    </div>
    ${message ? '<label><span>Message <span class="hint">(optional, included in their notification)</span></span><textarea class="picker-note" rows="2" placeholder="e.g. Please help with the figures in this letter."></textarea></label>' : ''}
    <span class="count-note picker-count">None selected</span></div>`;
}

function readPicker(root) {
  const ticked = $$('.pick-list input:checked', root);
  return {
    user_ids: ticked.filter((box) => box.dataset.kind === 'user').map((box) => Number(box.value)),
    department_ids: ticked.filter((box) => box.dataset.kind === 'department').map((box) => Number(box.value)),
    request_note: $('.picker-note', root)?.value || '',
    count: ticked.length,
  };
}

// Filtering and the "N selected" count work for every picker on the page.
document.addEventListener('input', (event) => {
  const picker = event.target.closest('.picker');
  if (!picker) return;
  if (event.target.classList.contains('picker-filter')) {
    const query = event.target.value.trim().toLowerCase();
    $$('.pick', picker).forEach((pick) => pick.classList.toggle('hidden', Boolean(query) && !pick.dataset.search.includes(query)));
  }
  const count = $$('.pick-list input:checked', picker).length;
  $('.picker-count', picker).textContent = count ? `${count} selected` : 'None selected';
});

// Adds the people and departments ticked in a form to the letter just created.
async function addPicked(letterId, root) {
  const picked = readPicker(root);
  if (!picked.count) return 0;
  await api(`/letters/${letterId}/collaborators`, { method: 'POST', json: picked });
  return picked.count;
}

async function collaborationCard(letter) {
  const parts = letter.collaborators || [];
  const manage = letter.may_manage_collaborators && !(letter.status === 'finalized' && letter.matter_status === 'closed');
  if (!parts.length && !manage) return '';
  const entry = (c) => `<li class="collab">
      <span class="avatar sm">${c.department_id ? icon('users') : esc(initials(c.user_name))}</span>
      <div class="collab-main"><p class="collab-who"><strong>${esc(collabName(c))}</strong> <span class="sub">${c.department_id ? 'Whole department' : `${esc(ROLE_NAMES[c.user_role] || '')}${c.user_department ? ` · ${esc(c.user_department)}` : ''}`}</span></p>
        <p class="sub">Added by ${esc(c.added_by_name)} · ${esc(timeAgo(c.created_at))}</p>
        ${c.request_note ? `<p class="collab-ask">“${esc(c.request_note)}”</p>` : ''}</div>
      ${manage ? `<button class="btn btn-ghost btn-sm" data-act="collab-remove" data-collab="${c.id}" data-name="${esc(collabName(c))}" title="Remove">${icon('x')}</button>` : ''}</li>`;
  let picker = '';
  if (manage) {
    const people = await api('/people').catch(() => []);
    const taken = { takenUsers: new Set([...parts.map((c) => c.user_id).filter(Boolean), letter.assigned_to]), takenDepartments: new Set(parts.map((c) => c.department_id).filter(Boolean)) };
    picker = `<details class="collab-add" ${parts.length ? '' : 'open'}><summary>${icon('plus')}Add collaborators</summary>
      ${pickerHtml(people, taken)}
      <div class="btn-row"><button class="btn btn-primary" data-act="collab-add">${icon('users')}Add selected</button></div></details>`;
  }
  return `<section class="card" id="collaboration"><div class="card-head"><div><h3>Collaborators</h3><p>Everyone added has the same access to this letter as whoever is handling it.</p></div>${parts.length ? `<span class="count-note">${parts.length}</span>` : ''}</div>
    <div class="action-body">${parts.length ? `<ul class="collab-list">${parts.map(entry).join('')}</ul>` : ''}${picker}</div></section>`;
}

/* ---------------- Enclosures ---------------- */
const fmtSize = (bytes) => (bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

function enclosuresCard(letter, enclosures) {
  if (!isOutgoing(letter)) return '';
  const editable = canEdit(letter);
  if (!enclosures.length && !editable) return '';
  const list = enclosures.map((e, index) => `<li><a href="/letters/${letter.id}/enclosures/${e.id}">${icon('file')}<span><strong>${index + 1}. ${esc(e.file_name)}</strong><small>${esc(fmtSize(e.size))} · added by ${esc(e.uploaded_by_name)}</small></span></a>
    ${editable ? `<button class="btn btn-ghost btn-sm" data-act="enc-remove" data-enc="${e.id}" title="Remove">${icon('x')}</button>` : ''}</li>`).join('');
  return `<section class="card"><div class="card-head"><div><h3>Enclosures</h3><p>${enclosures.length ? 'Listed as “Enc.” at the end of the letter.' : 'Attach anything that goes with the letter.'}</p></div>
      ${letter.status === 'finalized' && enclosures.length ? `<a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/pack.pdf" style="text-decoration:none" title="The letter followed by the PDF and image enclosures, for printing or emailing">${icon('download')}Letter + enclosures</a>` : ''}</div>
    <div class="action-body">${list ? `<ul class="enclosures">${list}</ul>` : ''}
      ${editable ? `<label class="btn btn-secondary file-btn">${icon('plus')}Add enclosure<input type="file" data-enclosure-upload hidden accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"></label><p class="hint-text">PDF, image, Word or Excel, up to 4 MB each.</p>` : ''}</div></section>`;
}

/* ---------------- Input and responses ---------------- */
function discussionCard(letter, comments) {
  const roots = comments.filter((c) => !c.parent_id);
  const replies = (id) => comments.filter((c) => c.parent_id === id);
  const entry = (c) => `<div class="c-entry"><span class="avatar sm">${esc(initials(c.author_name))}</span><div><p class="c-meta"><strong>${esc(c.author_name)}</strong> · ${esc(ROLE_NAMES[c.author_role] || '')} · ${esc(timeAgo(c.created_at))}</p><p class="c-body">${esc(c.body)}</p></div></div>`;
  const threads = roots.map((c) => `<li class="c-thread">${entry(c)}
    ${replies(c.id).length ? `<ul class="c-replies">${replies(c.id).map((r) => `<li>${entry(r)}</li>`).join('')}</ul>` : ''}
    <div class="c-respond"><button class="btn btn-ghost btn-sm" data-act="reply-toggle" data-parent="${c.id}">${icon('returned')}Respond</button>
      <div class="c-reply-box hidden" id="reply-box-${c.id}"><textarea rows="2" placeholder="Your response…"></textarea><div class="btn-row"><button class="btn btn-primary btn-sm" data-act="comment-reply" data-parent="${c.id}">${icon('send')}Send response</button></div></div></div></li>`).join('');
  return `<section class="card" id="discussion"><div class="card-head"><div><h3>Input &amp; responses</h3><p>Instructions, questions and answers about this letter. Everyone involved is notified.</p></div>${comments.length ? `<span class="count-note">${comments.length}</span>` : ''}</div>
    <div class="action-body">${threads ? `<ul class="c-list">${threads}</ul>` : '<p class="hint-text">No input yet.</p>'}
      <label><span>Add input</span><textarea id="c-new" rows="3" placeholder="e.g. Please confirm the amount with Finance before replying."></textarea></label>
      <div class="btn-row"><button class="btn btn-secondary" data-act="comment-add">${icon('send')}Post input</button></div></div></section>`;
}

/* ---------------- Digital signature ---------------- */
async function loadSignatureStatus(letter) {
  const slot = $('#sig-status');
  if (!slot) return;
  try {
    const result = await api(`/letters/${letter.id}/signature`);
    if (!slot.isConnected) return;
    slot.innerHTML = !result.signed
      ? `<p class="sig-line">${icon('alert', 'inline')} This PDF was approved before digital signing was added.</p>`
      : result.ours && result.intact
        ? `<p class="sig-line ok">${icon('lock', 'inline')} Digitally signed by SIGL Letter Desk${result.signed_at ? ` on ${esc(fmtDateTime(result.signed_at))}` : ''}. Unchanged since signing.</p>`
        : `<p class="sig-line bad">${icon('alert', 'inline')} The stored PDF no longer matches its signature. Report this to the administrator.</p>`;
  } catch { slot.innerHTML = ''; }
}

function registerCard(letter) {
  const fact = (label, value) => `<dt>${esc(label)}</dt><dd>${value}</dd>`;
  const outgoing = isOutgoing(letter);
  const lines = (text) => (text ? text.split(/\n+/).map((p) => esc(p.trim())).filter(Boolean).join('<br>') : '—');
  return `<section class="card"><div class="card-head"><div><h3>${outgoing ? 'Letter details' : 'Registered details'}</h3><p>${icon('lock', 'inline')} ${outgoing ? 'Set when the letter was started' : 'Locked after registration'}${can('edit_register_details') ? '' : '. Only people allowed to correct details can change them'}.</p></div>
    ${can('edit_register_details') ? `<button class="btn btn-ghost btn-sm" data-act="edit-details">${icon('edit')}Edit</button>` : ''}</div><dl class="facts">
    ${outgoing ? fact('Our reference', `<span class="mono">${esc(letter.our_reference)}</span>`) : fact('Register number', `<span class="mono">${esc(letter.reference)}</span>`)}
    ${fact(outgoing ? 'Created' : 'Date registered', esc(fmtDateTime(letter.created_at)))}
    ${fact('Subject', esc(letter.subject))}
    ${outgoing ? fact('Addressee', letter.addressee ? esc(letter.addressee) : '—') : ''}
    ${fact(outgoing ? 'To institution' : 'From institution', esc(letter.sender))}
    ${outgoing ? fact('Address', lines(letter.recipient_address)) : ''}
    ${outgoing ? '' : fact('Received via', esc(RECEIVED_VIA[letter.received_via] || '—'))}
    ${outgoing ? '' : fact('Date received', esc(fmtDate(letter.received_date)))}
    ${outgoing ? '' : fact('Date on letter', letter.letter_date ? esc(fmtDate(letter.letter_date)) : '—')}
    ${fact(outgoing ? 'Their reference' : 'Reference on letter', letter.agency_reference ? `<span class="mono">${esc(letter.agency_reference)}</span>` : '—')}
    ${outgoing ? '' : fact('Signed by', letter.signatory ? esc(letter.signatory) : '—')}
    ${fact(outgoing ? 'Copied to' : 'Copied parties', lines(letter.cc_parties))}
  </dl></section>`;
}

function linksCard(letter, responses, original) {
  if (isOutgoing(letter)) {
    if (!original) return '';
    return `<section class="card"><div class="card-head"><div><h3>In reply to</h3><p>The received letter this answers.</p></div></div><div class="action-body">
      <a class="reply-link" href="#/letter/${original.id}">${icon('inbox')}<span><strong class="mono">${esc(original.reference)}</strong><small>${esc(original.subject)} · from ${esc(original.sender)}</small></span>${icon('arrow')}</a></div></section>`;
  }
  if (!responses.length) return '';
  return `<section class="card"><div class="card-head"><div><h3>Replies sent</h3><p>Outgoing letters answering this one.</p></div></div><div class="action-body">
    ${responses.map((r) => `<a class="reply-link" href="#/letter/${r.id}">${icon('send')}<span><strong class="mono">${esc(r.our_reference)}</strong><small>${esc(stageLabel({ ...r, direction: 'outgoing' }))}${r.dispatched_on ? ` · sent ${esc(fmtDate(r.dispatched_on))}` : ''}</small></span>${icon('arrow')}</a>`).join('')}</div></section>`;
}

async function renderDetail(id) {
  closeEditor();
  setPage('Letter', 'Loading…', 'incoming');
  const view = $('#view');
  view.innerHTML = `<div class="skeleton" style="height:120px;margin-bottom:20px"></div><div class="grid-2"><div class="skeleton" style="height:560px"></div><div class="skeleton" style="height:360px"></div></div>`;
  const token = state.route;
  const { letter, audit, responses, in_reply_to_letter: original, enclosures = [], comments = [], signatory = null, collaborators = [], may_manage_collaborators: mayManage = false } = await api(`/letters/${id}`);
  letter.collaborators = collaborators;
  letter.may_manage_collaborators = mayManage;
  letter.signatory = signatory;
  letter.enclosure_list = enclosures;
  const outgoing = isOutgoing(letter);
  const panel = outgoing ? await outgoingPanel(letter, audit) : await incomingPanel(letter, responses);
  const collaboration = await collaborationCard(letter);
  if (stale(token)) return;
  setPage(outgoing ? 'Outgoing letter' : 'Received letter', letter.our_reference || letter.reference, registerOf(letter));
  const fact = (label, value) => `<dt>${esc(label)}</dt><dd>${value}</dd>`;
  const editable = canEdit(letter);
  const picker = editable ? await signatoryPicker(letter).catch(() => '') : '';
  if (stale(token)) return;
  const viewer = outgoing
    ? (editable ? editorCard(letter, picker) : `<section class="card editor-card"><div class="card-head"><div><h3>The letter</h3><p>${esc(whoCanEdit(letter))}</p></div>
        ${letter.status === 'finalized' ? `<div class="btn-row"><a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/pdf" style="text-decoration:none">${icon('download')}PDF</a></div>` : ''}</div>
        ${letter.status === 'finalized' ? '<div id="sig-status" class="sig-status"></div>' : ''}
        <div class="editor-desk">${letterPaper(letter)}</div></section>`)
    : `<section class="card viewer"><div class="card-head"><div><h3>Original document</h3><p>${esc(letter.source_file)}</p></div>
        <div class="btn-row"><a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/source?inline=1" target="_blank" rel="noopener" style="text-decoration:none">${icon('external')}Open</a></div></div>
        <div class="viewer-body" id="viewer"><div class="skeleton" style="width:80%;height:80%"></div></div></section>`;
  view.innerHTML = `
    <a class="back" href="#/${registerOf(letter)}">${icon('back')}Back to the ${outgoing ? 'outgoing' : 'incoming'} register</a>
    <div class="detail-head"><div style="min-width:0"><span class="row-sub">${outgoing ? `${icon('send', 'inline')} Outgoing · To ${letter.addressee ? `${esc(letter.addressee)}, ` : ''}${esc(letter.sender)}` : `${icon('inbox', 'inline')} Received · From ${esc(letter.sender)}`}</span><h2>${esc(letter.subject)}</h2>
      <div class="chips">${statusPills(letter)}${priorityChip(letter.priority)}${dueChip(letter)}${confChip(letter)}${outgoing ? '' : `<span class="chip">${esc(letter.category || 'General correspondence')}</span>`}</div></div></div>
    ${stepper(letter)}
    <div class="grid-2">
      ${viewer}
      <div class="stack" id="action-slot">
        ${panel}
        ${journeyCard(letter, audit)}
        ${collaboration}
        ${linksCard(letter, responses, original)}
        ${enclosuresCard(letter, enclosures)}
        ${trackingCard(letter)}
        ${registerCard(letter)}
        <section class="card"><div class="card-head"><h3>Handling</h3></div><dl class="facts">
          ${fact('Department', esc(letter.department_name))}
          ${fact(outgoing ? 'Written by' : 'Assigned to', letter.assignee_name ? esc(letter.assignee_name) : 'Not yet assigned')}
          ${fact(outgoing ? 'Started by' : 'Registered by', esc(letter.created_by_name || '—'))}
          ${outgoing ? '' : fact('Priority', esc(cap(letter.priority)))}
          ${outgoing ? '' : fact('Confidentiality', esc(cap(letter.confidentiality)))}
          ${letter.notes ? fact('Notes', esc(letter.notes)) : ''}
        </dl></section>
        <section class="card"><div class="card-head"><div><h3>Letter folder</h3><p>Everything kept for this letter.</p></div><a class="btn btn-secondary btn-sm" href="/letters/${letter.id}/folder.zip" style="text-decoration:none">${icon('download')}Download all</a></div><div class="files">
          ${outgoing ? '' : `<a class="file-link" href="/letters/${letter.id}/source">${icon('file')}Original scan<small>${esc(letter.source_file)}</small></a>`}
          ${outgoing ? '' : `<a class="file-link" href="/letters/${letter.id}/editable">${icon('edit')}Text of the scan (Word)<small>.docx</small></a>`}
          ${outgoing && letter.has_word_draft ? `<a class="file-link" href="/letters/${letter.id}/response-docx">${icon('edit')}${letter.status === 'finalized' ? 'Approved Word copy' : 'Word copy of the draft'}<small>${esc(draftName(letter))}</small></a>` : ''}
          ${outgoing && letter.status === 'finalized' ? `<a class="file-link" href="/letters/${letter.id}/pdf">${icon('lock')}Final approved PDF<small>locked</small></a>` : ''}
          ${letter.has_delivery_proof ? `<a class="file-link" href="/letters/${letter.id}/delivery-proof">${icon('check')}Proof of delivery<small>${esc(letter.delivery_proof_filename || '')}</small></a>` : ''}
        </div></section>
        ${discussionCard(letter, comments)}
        <section class="card"><div class="card-head"><h3>History</h3></div>${timeline(audit, letter)}</section>
      </div>
    </div>`;
  if (editable) state.editor = mountEditor(letter);
  if (outgoing && letter.status === 'finalized') loadSignatureStatus(letter);
  bindActions(letter);
  if (!outgoing) loadPreview(letter.id);
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

function editDetailsModal(letter) {
  return new Promise((resolve) => {
    const root = $('#modal-root');
    const outgoing = isOutgoing(letter);
    const field = (name, label, type = 'text') => `<label>${esc(label)}<input name="${name}" type="${type}" value="${esc(letter[name] || '')}"></label>`;
    root.innerHTML = `<div class="modal-backdrop"><form class="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-body"><h3 id="modal-title">Correct ${outgoing ? 'letter' : 'registered'} details</h3><p>Changes are recorded in the letter’s history.</p>
      <div class="form-grid">
        <label class="wide">Subject<input name="subject" value="${esc(letter.subject)}" required></label>
        ${outgoing ? field('addressee', 'Addressee') : ''}
        <label class="${outgoing ? '' : 'wide'}">${outgoing ? 'To institution' : 'From institution'}<input name="sender" value="${esc(letter.sender)}" required></label>
        ${outgoing ? `<label class="wide">Address<textarea name="recipient_address" rows="2">${esc(letter.recipient_address || '')}</textarea></label>` : ''}
        ${outgoing ? '' : field('letter_date', 'Date on letter', 'date')}
        ${field('agency_reference', outgoing ? 'Their reference' : 'Reference on letter')}
        ${outgoing ? '' : field('signatory', 'Signed by')}
        ${outgoing ? '' : field('received_date', 'Date received', 'date')}
        ${outgoing ? '' : `<label>Received via<select name="received_via"><option value="">Not set</option>${Object.entries(RECEIVED_VIA).map(([k, v]) => `<option value="${k}" ${letter.received_via === k ? 'selected' : ''}>${v}</option>`).join('')}</select></label>`}
        <label class="wide">${outgoing ? 'Copied to' : 'Copied parties'}<textarea name="cc_parties" rows="3">${esc(letter.cc_parties || '')}</textarea></label>
      </div></div>
      <div class="modal-foot"><button type="button" class="btn btn-secondary" data-close>Cancel</button><button class="btn btn-primary" data-ok>Save changes</button></div></form></div>`;
    const close = (value) => { root.innerHTML = ''; document.removeEventListener('keydown', onKey); resolve(value); };
    const onKey = (event) => { if (event.key === 'Escape') close(null); };
    document.addEventListener('keydown', onKey);
    $('[data-close]', root).onclick = () => close(null);
    $('form', root).onsubmit = (event) => { event.preventDefault(); close(Object.fromEntries(new FormData(event.target))); };
    $('input', root).focus();
  });
}

function bindActions(letter) {
  const slot = $('#action-slot');
  const reload = async (id = letter.id) => { state.letters = null; if (id === letter.id) await renderDetail(id); else location.hash = `#/letter/${id}`; };
  const run = async (button, method, url, json, success) => {
    await busy(button, async () => {
      try {
        // Send, approve or return exactly what is on screen.
        if (state.editor) await state.editor.save();
        const result = await api(url, { method, json });
        toast(success);
        await reload();
        return result;
      } catch (error) { toast(error.message, 'error'); }
    });
  };
  const form = async (button, url, data, success) => busy(button, async () => {
    try {
      await xhr('POST', url, data, {}, () => {});
      toast(success);
      await reload();
    } catch (error) { toast(error.message, 'error'); }
  });
  $('#signatory-select')?.addEventListener('change', async (event) => {
    const select = event.target;
    select.disabled = true;
    try {
      if (state.editor) await state.editor.save();
      await api(`/letters/${letter.id}/signatory`, { method: 'PUT', json: { signatory_id: select.value } });
      toast(`Signed by ${select.selectedOptions[0].textContent.split(' · ')[0]}.`);
      await reload();
    } catch (error) { toast(error.message, 'error'); select.disabled = false; }
  });
  slot.addEventListener('change', async (event) => {
    const input = event.target.closest('[data-enclosure-upload]');
    if (!input || !input.files[0]) return;
    const file = input.files[0];
    if (file.size > 4 * 1048576) { toast('Each enclosure must be 4 MB or smaller.', 'error'); input.value = ''; return; }
    const data = new FormData();
    data.append('file', file);
    await form(input.closest('label'), `/letters/${letter.id}/enclosures`, data, `${file.name} enclosed.`);
  });
  slot.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-act]');
    if (!button) return;
    const act = button.dataset.act;
    if (act === 'collab-add') {
      const { count, ...payload } = readPicker($('#collaboration'));
      if (!count) { toast('Tick at least one person or department.', 'error'); return; }
      return run(button, 'POST', `/letters/${letter.id}/collaborators`, payload, count === 1 ? 'Collaborator added and notified.' : `${count} collaborators added and notified.`);
    }
    if (act === 'collab-remove') {
      if (!(await modal({ title: `Remove ${button.dataset.name}?`, body: 'They will no longer have access to this letter, unless they handle it anyway.', confirmText: 'Remove' }))) return;
      return run(button, 'DELETE', `/letters/${letter.id}/collaborators/${button.dataset.collab}`, undefined, `${button.dataset.name} removed.`);
    }
    if (act === 'enc-remove') {
      if (!(await modal({ title: 'Remove this enclosure?', body: 'It will no longer go with the letter.', confirmText: 'Remove' }))) return;
      return run(button, 'DELETE', `/letters/${letter.id}/enclosures/${button.dataset.enc}`, undefined, 'Enclosure removed.');
    }
    if (act === 'reply-toggle') {
      const box = $(`#reply-box-${button.dataset.parent}`);
      box.classList.toggle('hidden');
      if (!box.classList.contains('hidden')) $('textarea', box).focus();
      return;
    }
    if (act === 'comment-add' || act === 'comment-reply') {
      const field = act === 'comment-add' ? $('#c-new') : $(`#reply-box-${button.dataset.parent} textarea`);
      const body = field.value.trim();
      if (!body) { toast('Write something first.', 'error'); field.focus(); return; }
      return busy(button, async () => {
        try {
          await api(`/letters/${letter.id}/comments`, { method: 'POST', json: { body, parent_id: button.dataset.parent || null } });
          toast(act === 'comment-add' ? 'Input posted. Everyone involved has been notified.' : 'Response sent.');
          await reload();
          $('#discussion')?.scrollIntoView({ block: 'nearest' });
        } catch (error) { toast(error.message, 'error'); }
      });
    }
    if (act === 'route-department') return run(button, 'POST', `/letters/${letter.id}/route`, { department_id: $('#a-dept').value }, `Routed to ${departmentName($('#a-dept').value)}.`);
    if (act === 'assign') {
      if (!$('#a-assignee').value) { toast('Choose a team member first.', 'error'); return; }
      const name = $('#a-assignee').selectedOptions[0].textContent;
      return run(button, 'POST', `/letters/${letter.id}/assign`, { assignee_id: $('#a-assignee').value }, `Assigned to ${name}.`);
    }
    if (act === 'assign-self') {
      return busy(button, async () => {
        try {
          await api(`/letters/${letter.id}/assign`, { method: 'POST', json: { assignee_id: state.user.id } });
          toast('It’s yours to write. The letter is open in the editor.');
          await reload();
        } catch (error) { toast(error.message, 'error'); }
      });
    }
    if (act === 'dept-approve') {
      const ok = await modal({ title: 'Approve for the department?', body: 'It goes to the MD PA, then the MD for final approval.', confirmText: 'Approve', confirmClass: 'btn-success' });
      if (ok) return run(button, 'POST', `/letters/${letter.id}/department-approve`, {}, 'Approved. It has gone to the MD PA.');
      return;
    }
    if (act === 'respond') {
      return busy(button, async () => {
        try {
          const reply = await api(`/letters/${letter.id}/respond`, { method: 'POST', json: {} });
          toast(`Reply ${reply.our_reference} created. Write it in the editor.`);
          await reload(reply.id);
        } catch (error) { toast(error.message, 'error'); }
      });
    }
    if (act === 'md-approve-incoming') {
      const text = $('#a-md-response').value.trim();
      if (!text) { toast('Write the reply first.', 'error'); $('#a-md-response').focus(); return; }
      if (!(await modal({ title: 'Approve this reply now?', body: 'It becomes the final locked PDF on letterhead, ready for dispatch. This is recorded in the history.', confirmText: 'Approve & lock', confirmClass: 'btn-success' }))) return;
      return busy(button, async () => {
        try {
          const reply = await api(`/letters/${letter.id}/md-approve`, { method: 'POST', json: { response_text: text } });
          toast(`Reply ${reply.our_reference} approved.`);
          await reload(reply.id);
        } catch (error) { toast(error.message, 'error'); }
      });
    }
    if (act === 'route-md') return run(button, 'POST', `/letters/${letter.id}/route-to-md`, {}, 'Sent to the MD for approval.');
    if (act === 'submit') {
      const ok = await modal({ title: 'Send for approval?', body: `The letter goes to ${goesToHead() ? 'the department head, then ' : ''}the MD PA and the MD. You can’t edit it unless it is returned.`, confirmText: 'Send' });
      if (ok) return run(button, 'POST', `/letters/${letter.id}/submit`, {}, 'Sent for approval.');
      return;
    }
    if (act === 'approve') {
      const ok = await modal({ title: 'Approve and lock this letter?', body: `This makes the final PDF on SIGL letterhead${letter.in_reply_to ? ' and permanently deletes the editable draft' : ' and keeps an approved Word copy'}. It cannot be edited afterwards.`, confirmText: 'Approve & lock', confirmClass: 'btn-success' });
      if (ok) return run(button, 'POST', `/letters/${letter.id}/approve`, {}, 'Approved. It is ready to dispatch.');
      return;
    }
    if (act === 'md-approve') {
      const own = letter.assigned_to === state.user.id;
      const ok = await modal({ title: 'Approve this letter now?', body: own ? 'It becomes the final locked PDF, ready for dispatch.' : `It will skip the remaining steps (currently “${esc(STATUS[letter.status] || letter.status)}”). This is recorded in the history.`, confirmText: 'Approve & lock now', confirmClass: 'btn-success' });
      if (ok) return run(button, 'POST', `/letters/${letter.id}/md-approve`, {}, 'Approved. It is ready to dispatch.');
      return;
    }
    if (act === 'changes') {
      const details = await modal({ title: 'Return for revision', body: 'Tell the writer what to change. They will be notified.', confirmText: 'Return', confirmClass: 'btn-primary', input: { placeholder: 'e.g. Please confirm the delivery dates and add our payment terms.', required: true } });
      if (details) return run(button, 'POST', `/letters/${letter.id}/request-changes`, { details }, 'Returned to the writer with your comments.');
      return;
    }
    if (act === 'dispatch') {
      if (!$('#d-method').value) { toast('Choose how the letter was sent.', 'error'); $('#d-method').focus(); return; }
      return run(button, 'POST', `/letters/${letter.id}/dispatch`, { method: $('#d-method').value, sent_on: $('#d-date').value, note: $('#d-note').value }, 'Marked as sent.');
    }
    if (act === 'delivery') {
      const data = new FormData();
      data.append('outcome', $('#v-outcome').value);
      data.append('delivered_on', $('#v-date').value);
      data.append('note', $('#v-note').value);
      if ($('#v-close').checked) data.append('close', '1');
      if ($('#v-proof').files[0]) data.append('proof', $('#v-proof').files[0]);
      return form(button, `/letters/${letter.id}/delivery`, data, $('#v-outcome').value === 'delivered' ? 'Delivery recorded.' : 'Recorded as returned. It can be sent again.');
    }
    if (act === 'tracking') {
      const payload = { matter_status: $('#m-status').value, remarks: $('#m-remarks').value, due_date: $('#m-due').value };
      if ($('#m-action')) payload.action_required = $('#m-action').value;
      return run(button, 'POST', `/letters/${letter.id}/matter-status`, payload, 'Status updated.');
    }
    if (act === 'edit-details') {
      const changes = await editDetailsModal(letter);
      if (changes) return run(button, 'PATCH', `/letters/${letter.id}/details`, changes, 'Details updated.');
    }
  });
}

/* ---------------- Intake (front desk) ---------------- */
function renderIntake() {
  setPage('Letters received', 'Register incoming letter', 'intake');
  const deptOptions = state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
  $('#view').innerHTML = `<div class="grid-2">
    <form class="card" id="intake-form" novalidate>
      <div class="form-grid">
        <p class="form-section-title">Document</p>
        <div class="wide" id="file-slot"></div>
        <p class="form-section-title">From the letter <span class="hint">${icon('lock', 'inline')} locked once registered; only the MD or MD PA can correct them</span></p>
        <label class="wide">Subject on letter *<input name="subject" required placeholder="What is the letter about?" autocomplete="off"></label>
        <label class="wide">Institute / organisation name on letter *<input name="sender" required placeholder="e.g. Ministry of Finance" autocomplete="off"></label>
        <label>Date on letter<input name="letter_date" type="date" max="${todayISO()}"></label>
        <label>Reference number on letter<input name="agency_reference" placeholder="e.g. MOF/TAX/2026/118" autocomplete="off"></label>
        <label>Name of signer<input name="signatory" placeholder="Who signed the letter" autocomplete="off"></label>
        <label>Date received *<input name="received_date" type="date" required value="${todayISO()}" max="${todayISO()}"></label>
        <label>Received via<select name="received_via">${Object.entries(RECEIVED_VIA).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
        <label>Category<select name="category">${CATEGORIES.map((c) => `<option>${esc(c)}</option>`).join('')}</select></label>
        <label class="wide"><span>Copied parties named in the letter <span class="hint">(one per line)</span></span><textarea name="cc_parties" rows="3" placeholder="e.g. Ghana Revenue Authority"></textarea></label>
        <p class="form-section-title">Routing &amp; handling</p>
        <label>Department *<select name="department_id" required><option value="">Choose department…</option>${deptOptions}</select></label>
        <label>Action required<select name="action_required">${Object.entries(ACTIONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
        <label><span>Deadline <span class="hint">(optional)</span></span><input name="due_date" type="date" min="${todayISO()}"></label>
        <label>Priority<select name="priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option><option value="low">Low</option></select></label>
        <label>Confidentiality<select name="confidentiality"><option value="internal">Internal</option><option value="confidential">Confidential</option><option value="restricted">Restricted</option></select></label>
        <label class="wide"><span>Notes for the department <span class="hint">(optional)</span></span><textarea name="notes" rows="3" placeholder="Anything the department should know"></textarea></label>
        <p class="form-section-title">Collaborators <span class="hint">optional · other people or departments who should work on this letter too</span></p>
        <div class="wide" id="intake-collaborators"><p class="hint-text">Loading people…</p></div>
      </div>
      <div class="form-foot"><div class="progress-wrap hidden" id="progress"><span id="progress-text">Uploading…</span><div class="progress"><span id="progress-bar"></span></div></div>
        <button class="btn btn-primary" id="intake-submit">${icon('check')}Register letter</button></div>
    </form>
    <aside class="card"><div class="card-head"><h3>How intake works</h3></div><div class="tips">
      <div class="tip"><b>1</b><span>Scan or photograph the letter and upload it. PDF gives the best results; files up to 25 MB are accepted.</span></div>
      <div class="tip"><b>2</b><span>Type the details exactly as they appear on the letter. They are locked once you press Register.</span></div>
      <div class="tip"><b>3</b><span>Pick the department that should respond. Its head is notified and assigns someone.</span></div>
      <div class="tip"><b>4</b><span>The scan and all details are saved in a folder for this letter. The reply gets its own reference, e.g. SIGL/MOF/AC/0001.</span></div>
    </div></aside></div>`;
  api('/people').then((people) => { $('#intake-collaborators').innerHTML = pickerHtml(people); }).catch(() => { $('#intake-collaborators').innerHTML = ''; });
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
        const added = await addPicked(letter.id, $('#intake-collaborators')).catch((error) => { toast(`Letter registered, but collaborators were not added: ${error.message}`, 'error'); return 0; });
        if (added) toast(`${added} collaborator${added > 1 ? 's' : ''} added and notified.`);
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

/* ---------------- Create outgoing letter ---------------- */
const instituteCode = (name) => (String(name).match(/[A-Za-z0-9]+/g) || []).map((word) => word[0]).join('').toUpperCase().slice(0, 8) || 'GEN';

async function renderCompose(params) {
  setPage('Letters sent', 'Create outgoing letter', 'compose');
  const token = state.route;
  const [letters, members] = await Promise.all([loadLetters(true), loadTeamMembers()]);
  if (stale(token)) return;
  const role = state.user.role;
  // The front desk, MD and MD PA choose the sending department; department staff send from their own.
  const choosesDept = ['front_desk', 'md', 'md_pa'].includes(role);
  const answerable = letters.filter((l) => !isOutgoing(l) && l.status !== 'finalized' && canRespond(l))
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const deptOptions = state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
  $('#view').innerHTML = `<div class="grid-2">
    <form class="card" id="compose-form" novalidate>
      <div class="form-grid">
        <p class="form-section-title">The letter</p>
        <label class="wide">Subject *<input name="subject" required placeholder="What is the letter about?" autocomplete="off"></label>
        ${answerable.length ? `<label class="wide">In reply to <span class="hint">(optional)</span><select name="in_reply_to"><option value="">Nothing: a new letter</option>${answerable.map((l) => `<option value="${l.id}">${esc(l.reference)} · ${esc(l.subject)} (${esc(l.sender)})</option>`).join('')}</select></label>` : ''}
        <p class="form-section-title">Who it is going to</p>
        <label>Institution / organisation *<input name="recipient" required placeholder="e.g. Ministry of Finance" autocomplete="off"></label>
        <label>Addressee<input name="addressee" placeholder="e.g. The Chief Director" autocomplete="off"></label>
        <label class="wide"><span>Address <span class="hint">(optional, one line each)</span></span><textarea name="recipient_address" rows="2" placeholder="P.O. Box M40&#10;Accra"></textarea></label>
        <label><span>Their reference <span class="hint">(optional)</span></span><input name="agency_reference" autocomplete="off"></label>
        <label class="wide"><span>Copy to <span class="hint">(one per line, printed as cc)</span></span><textarea name="cc_parties" rows="2"></textarea></label>
        <p class="form-section-title">Routing &amp; handling</p>
        ${choosesDept ? `<label>Sending department *<select name="department_id" required><option value="">Choose department…</option>${deptOptions}</select></label>` : `<label>Sending department<input value="${esc(state.user.department_name || '')}" disabled></label>`}
        <label id="writer-slot"></label>
        <label><span>Signed by</span><select name="signatory_id" id="signatory-choice"><option value="md">Managing Director</option></select></label>
        <label><span>Send by <span class="hint">(optional)</span></span><input name="due_date" type="date" min="${todayISO()}"></label>
        <label>Priority<select name="priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option><option value="low">Low</option></select></label>
        <label class="wide"><span>Instructions for the writer <span class="hint">(optional)</span></span><textarea name="notes" rows="2" placeholder="What the letter should say"></textarea></label>
        <p class="form-section-title">Collaborators <span class="hint">optional · everyone added has the same access to this letter</span></p>
        <div class="wide" id="compose-collaborators"><p class="hint-text">Loading people…</p></div>
      </div>
      <div class="form-foot"><span class="ref-preview">Our Ref: <b class="mono" id="ref-preview">SIGL/…</b></span>
        <button class="btn btn-primary" id="compose-submit">${icon('check')}Create outgoing letter</button></div>
    </form>
    <aside class="card"><div class="card-head"><h3>How sending works</h3></div><div class="tips">
      <div class="tip"><b>1</b><span>Create the letter and choose the sending department. It gets its reference number straight away.</span></div>
      <div class="tip"><b>2</b><span>The department head assigns a writer, who writes it here in the app on SIGL letterhead.</span></div>
      <div class="tip"><b>3</b><span>Approval: department head, then the MD PA and the MD. Each can return it for revision.</span></div>
      <div class="tip"><b>4</b><span>Once approved it becomes a locked PDF. The front desk dispatches it and records delivery.</span></div>
    </div></aside></div>`;
  const form = $('#compose-form');
  api('/people').then((people) => { $('#compose-collaborators').innerHTML = pickerHtml(people); }).catch(() => { $('#compose-collaborators').innerHTML = ''; });
  const deptId = () => Number(choosesDept ? form.elements.department_id.value : state.user.department_id);
  // Who writes it: team members write their own; heads, the MD and MD PA may pick; the front desk leaves it to the department.
  const drawWriter = () => {
    const slot = $('#writer-slot');
    if (role === 'team_member') { slot.innerHTML = 'Writer<input value="You" disabled>'; return; }
    if (role === 'front_desk') {
      slot.innerHTML = 'Writer<select name="writer"><option value="department">The department head assigns one</option><option value="self">Me</option></select>';
      return;
    }
    const team = members.filter((m) => m.department_id === deptId());
    slot.innerHTML = `Writer<select name="writer">
      <option value="department">${role === 'department_head' ? 'Decide later' : 'The department head assigns one'}</option>
      <option value="self">Me</option>
      ${team.map((m) => `<option value="${m.id}">${esc(m.display_name)}</option>`).join('')}</select>`;
  };
  const preview = () => {
    const dept = state.departments.find((d) => d.id === deptId());
    const recipient = form.elements.recipient.value.trim();
    $('#ref-preview').textContent = `SIGL/${recipient ? instituteCode(recipient) : '…'}/${dept ? dept.code : '…'}/####`;
  };
  const fillFromOriginal = () => {
    const original = answerable.find((l) => l.id === Number(form.elements.in_reply_to.value));
    if (!original) return;
    form.elements.recipient.value = original.sender;
    form.elements.subject.value = original.subject;
    form.elements.addressee.value = original.signatory || '';
    form.elements.agency_reference.value = original.agency_reference || '';
    if (choosesDept) { form.elements.department_id.value = original.department_id; drawWriter(); }
  };
  form.elements.in_reply_to?.addEventListener('change', fillFromOriginal);
  // The signatory is the MD or a head of the sending department, so the list follows the department.
  const drawSignatories = async () => {
    const department = deptId();
    const select = $('#signatory-choice');
    if (!department) { select.innerHTML = '<option value="md">Managing Director</option>'; return; }
    try {
      const choices = await api(`/signatories?department_id=${department}`);
      select.innerHTML = choices.map((c) => `<option value="${c.id}">${esc(c.name)}${c.title !== c.name ? ` · ${esc(c.title)}` : ''}</option>`).join('');
    } catch { /* keep the MD */ }
  };
  form.elements.department_id?.addEventListener('change', () => { drawWriter(); drawSignatories(); });
  drawSignatories();
  form.addEventListener('input', preview);
  drawWriter();
  if (params.get('reply') && form.elements.in_reply_to) { form.elements.in_reply_to.value = params.get('reply'); fillFromOriginal(); }
  preview();
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const missing = ['subject', 'recipient', ...(choosesDept ? ['department_id'] : [])].find((name) => !form.elements[name].value.trim());
    if (missing) { form.elements[missing].focus(); toast('Fill in the required fields marked *.', 'error'); return; }
    await busy($('#compose-submit'), async () => {
      try {
        const letter = await api('/letters/outgoing', { method: 'POST', json: Object.fromEntries(new FormData(form)) });
        state.letters = null;
        const added = await addPicked(letter.id, $('#compose-collaborators')).catch((error) => { toast(`Letter created, but collaborators were not added: ${error.message}`, 'error'); return 0; });
        if (added) toast(`${added} collaborator${added > 1 ? 's' : ''} added and notified.`);
        if (letter.assigned_to === state.user.id) toast(`${letter.our_reference} created. Write it in the editor.`);
        else toast(letter.assigned_to ? `${letter.our_reference} created and assigned.` : `${letter.our_reference} registered. The department head will assign a writer.`);
        location.hash = `#/letter/${letter.id}`;
      } catch (error) { toast(error.message, 'error'); }
    });
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
  const maxLoad = Math.max(1, ...members.map((m) => letters.filter((l) => l.assigned_to === m.id && isWorking(l)).length));
  view.innerHTML = `
    <div class="kpis">
      <a class="kpi tone-wine" href="#/letters?status=intake" style="text-decoration:none;color:inherit"><span class="kpi-top"><span>Unassigned</span><span class="kpi-icon">${icon('inbox')}</span></span><strong>${unassigned}</strong><small>Waiting for you</small></a>
      <div class="kpi tone-blue"><span class="kpi-top"><span>Team members</span><span class="kpi-icon">${icon('users')}</span></span><strong>${members.length}</strong><small>Active</small></div>
      <div class="kpi tone-amber"><span class="kpi-top"><span>Open work</span><span class="kpi-icon">${icon('edit')}</span></span><strong>${letters.filter((l) => isWorking(l)).length}</strong><small>Across the team</small></div>
      <div class="kpi tone-red ${letters.some(isOverdue) ? 'alert' : ''}"><span class="kpi-top"><span>Overdue</span><span class="kpi-icon">${icon('alert')}</span></span><strong>${letters.filter(isOverdue).length}</strong><small>Past due date</small></div>
    </div>
    ${members.length ? `<div class="people">${members.map((member) => {
      const mine = letters.filter((l) => l.assigned_to === member.id);
      const active = mine.filter((l) => isWorking(l)).sort(byUrgency);
      const review = mine.filter((l) => IN_REVIEW.includes(l.status)).length;
      const done = mine.filter((l) => l.status === 'finalized').length;
      return `<section class="card person"><div class="person-head"><span class="avatar">${esc(initials(member.display_name))}</span><div><strong>${esc(member.display_name)}</strong><small>${active.length} active · ${mine.filter(isOverdue).length} overdue</small></div></div>
        <div class="load-bar" title="Workload"><span style="width:${(active.length / maxLoad) * 100}%"></span></div>
        <div class="mini-stats"><div><strong>${active.length}</strong><small>Active</small></div><div><strong>${review}</strong><small>In review</small></div><div><strong>${done}</strong><small>Done</small></div></div>
        ${active.length ? `<ul>${active.slice(0, 5).map((l) => `<li><a href="#/letter/${l.id}"><span>${esc(l.subject)}</span>${dueChip(l) || stagePill(l)}</a></li>`).join('')}</ul>` : '<p class="row-sub" style="margin:0">No active letters.</p>'}</section>`;
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
  const received = letters.filter((l) => !isOutgoing(l));
  const sent = letters.filter(isOutgoing);
  const responded = received.filter((l) => l.status === 'finalized' && l.finalized_at);
  const turnaround = responded.length
    ? (responded.reduce((sum, l) => sum + (parseTs(l.finalized_at) - parseTs(l.created_at)) / 86400000, 0) / responded.length) : null;
  const byDept = state.departments.map((d) => {
    const mine = letters.filter((l) => l.department_id === d.id);
    return { name: d.name, open: mine.filter(isOpen).length, done: mine.filter((l) => !isOpen(l)).length };
  }).sort((a, b) => (b.open + b.done) - (a.open + a.done));
  const maxDept = Math.max(1, ...byDept.map((d) => d.open + d.done));
  const stages = (list, tone) => {
    const counts = new Map();
    list.forEach((l) => counts.set(stageLabel(l), (counts.get(stageLabel(l)) || 0) + 1));
    const max = Math.max(1, ...counts.values());
    return [...counts].map(([label, n]) => `<div class="bar-row"><span>${esc(label)}</span><span class="bar-track"><i class="open" style="width:${(n / max) * 100}%;background:var(--${tone})"></i></span><b>${n}</b></div>`).join('') || '<p class="row-sub" style="padding:0 20px">None yet.</p>';
  };
  const overdue = letters.filter(isOverdue).sort(byUrgency);
  view.innerHTML = `
    <div class="kpis">
      <div class="kpi tone-wine"><span class="kpi-top"><span>Letters received</span><span class="kpi-icon">${icon('inbox')}</span></span><strong>${received.length}</strong><small>${received.filter(isOpen).length} still open</small></div>
      <div class="kpi tone-blue"><span class="kpi-top"><span>Letters sent</span><span class="kpi-icon">${icon('send')}</span></span><strong>${sent.length}</strong><small>${sent.filter((l) => l.dispatch_status === 'delivered').length} delivered</small></div>
      <div class="kpi tone-red ${overdue.length ? 'alert' : ''}"><span class="kpi-top"><span>Overdue</span><span class="kpi-icon">${icon('alert')}</span></span><strong>${overdue.length}</strong><small>Past deadline</small></div>
      <div class="kpi tone-green"><span class="kpi-top"><span>Avg. reply time</span><span class="kpi-icon">${icon('clock')}</span></span><strong>${turnaround === null ? '—' : turnaround < 1 ? `${Math.max(1, Math.round(turnaround * 24))}h` : `${turnaround.toFixed(1)}d`}</strong><small>Received → reply approved</small></div>
    </div>
    <div class="grid-2-even section">
      <section class="card"><div class="card-head"><div><h3>Received letters by stage</h3><p>Where they are right now</p></div></div><div class="bars">${stages(received, 'wine')}</div></section>
      <section class="card"><div class="card-head"><div><h3>Sent letters by stage</h3><p>Approval, dispatch and delivery</p></div></div><div class="bars">${stages(sent, 'blue')}</div></section>
    </div>
    <section class="card section"><div class="card-head"><div><h3>By department</h3><p>Open and completed letters, received and sent</p></div></div>
      <div class="bars">${byDept.map((d) => `<div class="bar-row"><span title="${esc(d.name)}">${esc(d.name)}</span><span class="bar-track"><i class="open" style="width:${(d.open / maxDept) * 100}%"></i><i class="done" style="width:${(d.done / maxDept) * 100}%"></i></span><b>${d.open + d.done}</b></div>`).join('')}</div>
      <div class="legend"><span><i style="background:var(--wine)"></i>Open</span><span><i style="background:#8fcfae"></i>Completed</span></div></section>
    <section class="card"><div class="card-head"><div><h3>Overdue letters</h3><p>Open letters past their deadline, most urgent first</p></div></div>
      <div class="rows">${overdue.length ? overdue.map((l) => letterRow(l)).join('') : empty('Nothing overdue', 'Every open letter is within its deadline.', 'check')}</div></section>`;
}

/* ---------------- Admin (users and departments) ---------------- */
function userModal(user, catalogue) {
  const isMD = state.user.role === 'md';
  const self = user.id === state.user.id;
  const deptOptions = `<option value="">None</option>${state.departments.map((d) => `<option value="${d.id}" ${d.id === user.department_id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}`;
  const defaults = (role) => new Set(catalogue.role_defaults[role] || []);
  return new Promise((resolve) => {
    const root = $('#modal-root');
    root.innerHTML = `<div class="modal-backdrop"><form class="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-body"><h3 id="modal-title">${esc(user.display_name)}</h3><p class="mono">${esc(user.username)}</p>
      <div class="form-grid">
        <label>Full name<input name="display_name" value="${esc(user.display_name)}" required></label>
        <label>Email<input name="email" type="email" value="${esc(user.email || '')}"></label>
        <label>Role<select name="role" ${isMD && !self ? '' : 'disabled'}>${Object.entries(ROLE_NAMES).map(([k, v]) => `<option value="${k}" ${k === user.role ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>Department<select name="department_id">${deptOptions}</select></label>
        <label class="check wide"><input type="checkbox" name="active" ${user.active ? 'checked' : ''} ${self ? 'disabled' : ''}> Account is active (can sign in)</label>
      </div>
      <h4 class="perm-title">What ${esc(user.display_name.split(' ')[0])} can do</h4>
      <p class="hint-text">${isMD ? 'Ticked items are allowed. “Changed” marks a difference from the usual for their role.' : 'Only the MD can change these.'} Approval steps follow the person’s role.</p>
      <div class="perm-list" id="perm-list"></div></div>
      <div class="modal-foot"><button type="button" class="btn btn-secondary" data-close>Cancel</button><button class="btn btn-primary" data-ok>Save changes</button></div></form></div>`;
    const form = $('form', root);
    // Ticked state of each permission: what they have now; a new role brings its defaults, except deliberate changes.
    let allowed = Object.fromEntries(catalogue.capabilities.map((c) => [c.key, user.capabilities.includes(c.key)]));
    const drawPermissions = () => {
      const usual = defaults(form.elements.role.value);
      $('#perm-list', root).innerHTML = catalogue.capabilities.map((c) => {
        const on = allowed[c.key];
        const changed = on !== usual.has(c.key);
        return `<label class="perm ${changed ? 'changed' : ''}"><input type="checkbox" name="${c.key}" ${on ? 'checked' : ''} ${isMD ? '' : 'disabled'}>
          <span><strong>${esc(c.label)}</strong><small>${esc(c.description)}</small></span>${changed ? '<em>Changed</em>' : ''}</label>`;
      }).join('');
    };
    drawPermissions();
    form.elements.role.addEventListener('change', () => {
      const usual = defaults(form.elements.role.value);
      allowed = Object.fromEntries(catalogue.capabilities.map((c) => [c.key, c.key in user.overrides ? user.overrides[c.key] : usual.has(c.key)]));
      drawPermissions();
    });
    $('#perm-list', root).addEventListener('change', (event) => { allowed[event.target.name] = event.target.checked; drawPermissions(); });
    const close = (value) => { root.innerHTML = ''; document.removeEventListener('keydown', onKey); resolve(value); };
    const onKey = (event) => { if (event.key === 'Escape') close(null); };
    document.addEventListener('keydown', onKey);
    $('[data-close]', root).onclick = () => close(null);
    form.onsubmit = (event) => {
      event.preventDefault();
      const changes = { display_name: form.elements.display_name.value, email: form.elements.email.value, department_id: form.elements.department_id.value || null };
      if (!self) changes.active = form.elements.active.checked;
      if (isMD && !self && form.elements.role.value !== user.role) changes.role = form.elements.role.value;
      if (isMD) changes.permissions = allowed;
      close(changes);
    };
    form.elements.display_name.focus();
  });
}

async function renderAdmin() {
  setPage('Administration', 'Users & departments', 'admin');
  const view = $('#view');
  view.innerHTML = skeleton();
  const token = state.route;
  const [users, letters, catalogue] = await Promise.all([api('/users'), loadLetters(), api('/permissions')]);
  if (stale(token)) return;
  const isMD = state.user.role === 'md';
  const deptOptions = state.departments.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join('');
  const extras = (u) => {
    const changed = Object.keys(u.overrides || {}).length;
    return changed ? `<span class="chip perm-chip" title="Permissions differ from the usual for this role">${changed} custom permission${changed > 1 ? 's' : ''}</span>` : '';
  };
  view.innerHTML = `<div class="grid-2">
    <section class="card"><div class="card-head"><div><h3>Users</h3><p>${users.filter((u) => u.active).length} active of ${users.length}. ${isMD ? 'Open a user to change their role and what they can do.' : ''}</p></div><button class="btn btn-primary btn-sm" id="toggle-user-form">${icon('plus')}Add user</button></div>
      <form class="inline-form hidden" id="user-form" autocomplete="off">
        <label>Full name *<input name="display_name" required placeholder="e.g. Ama Owusu"></label>
        <label>Username *<input name="username" required placeholder="e.g. aowusu"></label>
        <label>Role *<select name="role" required>${Object.entries(ROLE_NAMES).filter(([k]) => isMD || k !== 'md').map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></label>
        <label>Department<select name="department_id"><option value="">None</option>${deptOptions}</select></label>
        <label class="wide"><span>Email <span class="hint">(for notifications)</span></span><input name="email" type="email" placeholder="e.g. a.owusu@swamiindiaghanaltd.com"></label>
        <label class="wide">Temporary password *<span style="display:flex;gap:8px"><input name="password" required minlength="8"><button type="button" class="btn btn-secondary" id="gen-pass">Generate</button></span></label>
        <div class="wide btn-row"><button class="btn btn-primary" id="create-user">Create user</button><button type="button" class="btn btn-secondary" id="cancel-user">Cancel</button></div>
      </form>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th class="hide-sm">Department</th><th>Status</th><th></th></tr></thead><tbody>
        ${users.map((u) => `<tr><td><span class="title">${esc(u.display_name)}</span><span class="sub mono">${esc(u.username)}</span>${u.email ? `<span class="sub">${esc(u.email)}</span>` : ''}</td>
          <td><span class="role-tag">${esc(ROLE_NAMES[u.role] || u.role)}</span>${extras(u)}${u.microsoft_linked ? '<span class="chip ms-chip" title="Signs in with Microsoft">Microsoft</span>' : ''}</td><td class="hide-sm">${esc(u.department_name || '—')}</td>
          <td><span class="status-dot ${u.active ? '' : 'off'}">${u.active ? 'Active' : 'Inactive'}</span></td>
          <td style="text-align:right"><div class="row-actions">
            ${(u.role === 'md' && !isMD) ? '' : `<button class="btn btn-ghost btn-sm" data-edit="${u.id}">${icon('edit')}Edit</button>`}
            ${u.id === state.user.id || (u.role === 'md' && !isMD) ? '' : `<button class="btn btn-ghost btn-sm" data-reset="${u.id}" data-name="${esc(u.display_name)}">Reset password</button>`}
            ${isMD && u.id !== state.user.id ? `<button class="btn btn-ghost btn-sm danger" data-delete="${u.id}" data-name="${esc(u.display_name)}">${icon('x')}Delete</button>` : ''}
            ${u.id === state.user.id ? '<span class="sub">You</span>' : ''}</div></td></tr>`).join('')}
      </tbody></table></div></section>
    <section class="card"><div class="card-head"><div><h3>Departments</h3><p>${state.departments.length} departments · the short code goes in reference numbers, e.g. SIGL/MOF/<b>AC</b>/0001</p></div></div>
      <ul class="dept-list">${state.departments.map((d) => {
        const people = users.filter((u) => u.department_id === d.id && u.active).length;
        const open = letters.filter((l) => l.department_id === d.id && isOpen(l)).length;
        return `<li><div><strong>${esc(d.name)}</strong><span>${people} people · ${open} open</span></div>
          <form class="code-form" data-dept="${d.id}"><label><span class="sr-only">Short code for ${esc(d.name)}</span><input name="code" value="${esc(d.code)}" maxlength="6" size="5" class="mono" title="${d.code_is_default ? 'Suggested code. Save to confirm it.' : 'Short code'}"></label><button class="btn btn-ghost btn-sm">${d.code_is_default ? 'Set' : 'Save'}</button></form></li>`;
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
    const edit = event.target.closest('[data-edit]');
    if (edit) {
      const user = users.find((u) => u.id === Number(edit.dataset.edit));
      const changes = await userModal(user, catalogue);
      if (!changes) return;
      try {
        await api(`/users/${user.id}`, { method: 'PATCH', json: changes });
        state.teamMembers = null;
        toast(`${changes.display_name || user.display_name} updated.`);
        await renderAdmin();
      } catch (error) { toast(error.message, 'error'); }
      return;
    }
    const reset = event.target.closest('[data-reset]');
    if (reset) {
      const password = await modal({ title: `New password for ${reset.dataset.name}`, body: 'At least 8 characters. Share it with them privately; they can change it under My account.', confirmText: 'Set password', input: { placeholder: 'New password', required: true } });
      if (!password) return;
      if (password.length < 8) { toast('The password must be at least 8 characters.', 'error'); return; }
      await busy(reset, async () => {
        try { await api(`/users/${reset.dataset.reset}`, { method: 'PATCH', json: { password } }); toast(`Password changed for ${reset.dataset.name}.`); } catch (error) { toast(error.message, 'error'); }
      });
      return;
    }
    const remove = event.target.closest('[data-delete]');
    if (remove) {
      const ok = await modal({ title: `Delete ${remove.dataset.name}?`, body: 'They will no longer be able to sign in and will disappear from the user list. Letters they worked on keep their name in the history. This cannot be undone.', confirmText: 'Delete user', confirmClass: 'btn-danger' });
      if (!ok) return;
      await busy(remove, async () => {
        try {
          const result = await api(`/users/${remove.dataset.delete}`, { method: 'DELETE' });
          state.teamMembers = null;
          toast(result.kept_on_history ? `${remove.dataset.name} deleted. Their name stays on past letters.` : `${remove.dataset.name} deleted.`);
          await renderAdmin();
        } catch (error) { toast(error.message, 'error'); }
      });
    }
  });
  $$('.code-form', view).forEach((codeForm) => codeForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const code = codeForm.elements.code.value.trim();
    await busy(event.submitter || $('button', codeForm), async () => {
      try {
        await api(`/departments/${codeForm.dataset.dept}`, { method: 'PATCH', json: { code } });
        state.departments = await api('/departments');
        toast(`Short code set to ${code.toUpperCase()}.`);
        await renderAdmin();
      } catch (error) { toast(error.message, 'error'); }
    });
  }));
  $('#dept-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = event.target.elements.name.value.trim();
    if (!name) return;
    await busy(event.submitter || $('#dept-form button'), async () => {
      try { await api('/departments', { method: 'POST', json: { name } }); state.departments = await api('/departments'); toast(`${name} added.`); await renderAdmin(); } catch (error) { toast(error.message, 'error'); }
    });
  });
}

/* ---------------- Check a letter ---------------- */
function renderVerify() {
  setPage('Tools', 'Check a letter', 'verify');
  $('#view').innerHTML = `<div class="grid-2">
    <section class="card"><div class="card-head"><div><h3>Is this letter genuine?</h3><p>Choose a PDF of a letter sent by SIGL. The app checks its digital signature and whether anything was changed.</p></div></div>
      <div class="action-body"><label class="dropzone" id="verify-zone">${icon('lock')}<strong>Choose or drop the PDF here</strong><small>Letters approved in Letter Desk carry a digital signature</small><input type="file" id="verify-input" accept=".pdf"></label>
      <div id="verify-result"></div></div></section>
    <aside class="card"><div class="card-head"><h3>What the check tells you</h3></div><div class="tips">
      <div class="tip"><b>1</b><span>Whether the PDF was digitally signed by SIGL Letter Desk when the MD approved it.</span></div>
      <div class="tip"><b>2</b><span>Whether anything has been changed since, even one character.</span></div>
      <div class="tip"><b>3</b><span>Which letter it is, and whether it is the exact copy on record.</span></div>
    </div></aside></div>`;
  const check = async (file) => {
    if (!file) return;
    const result = $('#verify-result');
    result.innerHTML = '<p class="hint-text">Checking…</p>';
    try {
      const data = new FormData();
      data.append('document', file);
      const r = JSON.parse(await xhr('POST', '/verify', data, {}, () => {}));
      const letter = r.letter ? `<a class="reply-link" href="#/letter/${r.letter.id}">${icon('send')}<span><strong class="mono">${esc(r.letter.our_reference)}</strong><small>${esc(r.letter.subject)} · to ${esc(r.letter.sender)}</small></span>${icon('arrow')}</a>` : '';
      const [tone, title, text] = !r.signed ? ['bad', 'Not signed by SIGL', 'This PDF has no Letter Desk signature. It may be a scan, a draft or a copy made elsewhere.']
        : !r.ours ? ['bad', 'Signed by someone else', 'The signature is not SIGL Letter Desk’s.']
          : !r.intact ? ['bad', 'Changed after signing', 'This PDF was signed by SIGL, but has been altered since. Do not rely on it.']
            : ['ok', 'Genuine and unchanged', r.matches_record ? 'Signed by SIGL Letter Desk and identical to the copy on record.' : 'Signed by SIGL Letter Desk and unchanged since signing.'];
      result.innerHTML = `<div class="verify-result ${tone}">${icon(tone === 'ok' ? 'check' : 'alert')}<div><strong>${title}</strong><p>${text}</p></div></div>${letter}`;
    } catch (error) { result.innerHTML = ''; toast(error.message, 'error'); }
  };
  const zone = $('#verify-zone');
  $('#verify-input').onchange = (event) => check(event.target.files[0]);
  ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove('drag'); }));
  zone.addEventListener('drop', (event) => check(event.dataTransfer.files[0]));
}

/* ---------------- My account ---------------- */
async function renderAccount() {
  setPage('My account', state.user.display_name, 'account');
  const view = $('#view');
  view.innerHTML = skeleton();
  const token = state.route;
  const me = await api('/me');
  if (stale(token)) return;
  const desktop = !('Notification' in window) ? 'Not supported by this browser.' : { granted: 'On', denied: 'Blocked in browser settings' }[Notification.permission] || 'Off';
  view.innerHTML = `<div class="grid-2-even">
    <section class="card"><div class="card-head"><div><h3>Notifications</h3><p>Everything appears under the bell. You can also get it by email and as desktop alerts.</p></div></div>
      <form class="action-body" id="email-form"><label><span>Email address</span><input name="email" type="email" value="${esc(me.email || '')}" placeholder="you@swamiindiaghanaltd.com"></label>
        ${me.email_enabled ? '' : '<p class="hint-text">Email sending is not switched on yet. Your address is saved for when it is.</p>'}
        <div class="btn-row"><button class="btn btn-secondary">${icon('check')}Save email</button></div>
        <p class="fact-line">Desktop alerts: <strong>${esc(desktop)}</strong>${'Notification' in window && Notification.permission === 'default' ? ' · <button type="button" class="btn btn-ghost btn-sm" id="account-desktop">Turn on</button>' : ''}</p></form></section>
    <section class="card"><div class="card-head"><div><h3>Password</h3><p>At least 8 characters.</p></div></div>
      <form class="action-body" id="password-form" autocomplete="off"><label>Current password<input name="current" type="password" autocomplete="current-password" required></label>
        <label>New password<input name="new" type="password" autocomplete="new-password" minlength="8" required></label>
        <div class="btn-row"><button class="btn btn-secondary">${icon('lock')}Change password</button></div></form></section>
    ${(me.capabilities || []).includes('sign_letters') ? `<section class="card"><div class="card-head"><div><h3>My signature</h3><p>Printed on every letter you are chosen to sign. A photo or scan of your signature on white paper works; the white is made transparent.</p></div></div>
      <div class="action-body">${me.has_signature ? `<div class="signature-preview"><img src="/me/signature?${Date.now()}" alt="Your signature"></div>` : '<p class="hint-text">No signature yet. Letters are still digitally signed, with a blank signing space.</p>'}
        <div class="btn-row"><label class="btn btn-secondary file-btn">${icon('upload')}${me.has_signature ? 'Replace signature' : 'Upload signature'}<input type="file" id="signature-input" accept=".png,.jpg,.jpeg" hidden></label>
          ${me.has_signature ? `<button class="btn btn-ghost" id="signature-remove">${icon('x')}Remove</button>` : ''}</div></div></section>` : ''}
  </div>`;
  $('#email-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    await busy(event.submitter, async () => {
      try { await api('/me', { method: 'PATCH', json: { email: event.target.elements.email.value } }); toast('Email saved.'); } catch (error) { toast(error.message, 'error'); }
    });
  });
  $('#account-desktop')?.addEventListener('click', () => Notification.requestPermission().then(() => renderAccount()));
  $('#password-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    await busy(event.submitter, async () => {
      try { await api('/me/password', { method: 'POST', json: { current: form.elements.current.value, new: form.elements.new.value } }); form.reset(); toast('Password changed.'); } catch (error) { toast(error.message, 'error'); }
    });
  });
  $('#signature-input')?.addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const data = new FormData();
    data.append('signature', file);
    try { await xhr('PUT', '/me/signature', data, {}, () => {}); toast('Signature saved.'); renderAccount(); } catch (error) { toast(error.message, 'error'); }
  });
  $('#signature-remove')?.addEventListener('click', async () => {
    if (!(await modal({ title: 'Remove your signature?', body: 'Letters you approve will no longer show it.', confirmText: 'Remove' }))) return;
    try { await api('/me/signature', { method: 'DELETE' }); toast('Signature removed.'); renderAccount(); } catch (error) { toast(error.message, 'error'); }
  });
}

/* ---------------- Notifications ---------------- */
async function loadNotifications() {
  if (!state.user) return;
  try {
    const previousUnread = state.notifications.filter((n) => !n.read_at).length;
    const known = new Set(state.notifications.map((n) => n.id));
    const firstLoad = !state.notificationsLoaded;
    state.notifications = await api('/notifications');
    state.notificationsLoaded = true;
    if (!firstLoad) desktopAlert(state.notifications.filter((n) => !n.read_at && !known.has(n.id)));
    const unread = state.notifications.filter((n) => !n.read_at).length;
    const badge = $('#bell-count');
    badge.textContent = unread > 9 ? '9+' : unread;
    badge.classList.toggle('hidden', unread === 0);
    if (unread > previousUnread) state.letters = null;
    if (!$('#notif-panel').classList.contains('hidden')) drawNotifications();
  } catch { /* polling is best-effort */ }
}
function desktopAlert(fresh) {
  if (!fresh.length || !('Notification' in window) || Notification.permission !== 'granted') return;
  fresh.slice(0, 3).forEach((n) => {
    const alert = new Notification(n.title, { body: n.body, tag: `sigl-${n.id}` });
    alert.onclick = () => { window.focus(); if (n.letter_id) location.hash = `#/letter/${n.letter_id}`; alert.close(); };
  });
}

function drawNotifications() {
  const panel = $('#notif-panel');
  const unread = state.notifications.some((n) => !n.read_at);
  const askDesktop = 'Notification' in window && Notification.permission === 'default';
  panel.innerHTML = `<div class="notif-head"><strong>Notifications</strong>${unread ? '<button class="btn btn-ghost btn-sm" id="read-all">Mark all read</button>' : ''}</div>
    ${askDesktop ? `<button class="notif-desktop" id="desktop-alerts">${icon('bell')}Turn on desktop alerts</button>` : ''}
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
  // A failed Microsoft sign-in comes back with the reason in the address.
  const params = new URLSearchParams(location.search);
  if (params.get('login_error')) {
    $('#login-message').textContent = params.get('login_error');
    history.replaceState(null, '', location.pathname + location.hash);
  }
  fetch('/auth/options', { credentials: 'same-origin' }).then((r) => r.json()).then((options) => {
    $('#microsoft-sign-in').classList.toggle('hidden', !options.microsoft);
    $('#login-or').classList.toggle('hidden', !options.password);
    $('#login-form').classList.toggle('hidden', !options.password);
    if (options.password) $('#login-form input[name="username"]').focus();
  }).catch(() => $('#login-form input[name="username"]').focus());
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
  if (event.target.closest('#desktop-alerts')) {
    Notification.requestPermission().then((permission) => { toast(permission === 'granted' ? 'Desktop alerts are on.' : 'Desktop alerts stay off.'); drawNotifications(); });
    return;
  }
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
$('#track-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = $('#track-input');
  const query = input.value.trim();
  if (!query) return;
  try {
    const found = await api(`/letters?q=${encodeURIComponent(query)}`);
    const exact = found.find((l) => [l.reference, l.our_reference].some((ref) => String(ref || '').toLowerCase() === query.toLowerCase()));
    const match = exact || (found.length === 1 ? found[0] : null);
    if (match) { input.value = ''; location.hash = `#/letter/${match.id}`; return; }
    if (!found.length) { toast(`No letter matches “${query}”.`, 'error'); return; }
    location.hash = `#/${registerOf(found[0])}?q=${encodeURIComponent(query)}`;
  } catch (error) { toast(error.message, 'error'); }
});
window.addEventListener('hashchange', router);
window.addEventListener('focus', loadNotifications);

(async function start() {
  try {
    const response = await fetch('/me', { credentials: 'same-origin' });
    if (response.ok) { await enterWorkspace(await response.json()); return; }
  } catch { /* fall through to sign-in */ }
  showLogin();
}());

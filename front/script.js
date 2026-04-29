'use strict';

const SEVERITY_COLORS = { 1:'#28a745', 2:'#ffc107', 3:'#fd7e14', 4:'#dc3545', 5:'#6f42c1' };

const EVENT_LABELS = {
  ehkaiseva_lastensuojelu:'Ehkäisevä ls.', lastensuojeluilmoitus:'Ilmoitus',
  lastensuojelutarpeen_selvitys:'Tarpeen selvitys', asiakkuuden_alkaminen:'Asiakkuus alkaa',
  avohuollon_tukitoimet:'Avohuolto', kiireellinen_sijoitus:'Kiir. sijoitus',
  huostaanotto:'Huostaanotto', sijaishuolto_perhehoito:'Perhehoito',
  sijaishuolto_laitoshoito:'Laitoshoito', sijaishuoltopaikan_muutos:'Sijoitusmuutos',
  jalkihuolto:'Jälkihuolto', psykiatrinen_hoito:'Psyk. hoito',
  perhevakivalta_epaily:'Perheväkivalta', paihdekaytto:'Päihteet',
  rikosepaily:'Rikosepäily', koulupoissaolot_vakavat:'Koulupoissaolot',
  muu_kriittinen:'Muu kriittinen',
};

let currentPatientId = null;
let currentTimeline  = [];
let pendingFiles     = [];

document.addEventListener('DOMContentLoaded', () => { loadPatientList(); initDropZone(); });

// Dark mode
function toggleDark() {
  document.body.classList.toggle('dark-mode');
  localStorage.setItem('dark', document.body.classList.contains('dark-mode'));
}
if (localStorage.getItem('dark') === 'true') {
  document.body.classList.add('dark-mode');
  const cb = document.getElementById('dark-toggle-cb');
  if (cb) cb.checked = true;
}

// Patient list
async function loadPatientList() {
  try {
    const res  = await fetch('/api/patients/');
    const list = await res.json();
    const el   = document.getElementById('patient-list');
    if (!list.length) { el.innerHTML = '<div class="patient-list-empty">Ei potilaita vielä.</div>'; return; }
    el.innerHTML = list.map(p => `
      <div class="patient-item ${p.patient_id === currentPatientId ? 'active' : ''}" onclick="loadPatient('${p.patient_id}')">
        <div class="pi-id">👤 ${p.patient_id}</div>
        <div class="pi-meta">${p.doc_count} dok · ${p.event_count} tapah.</div>
      </div>`).join('');
  } catch(e) { console.error(e); }
}

function toggleNewPatient() { document.getElementById('new-patient-form').classList.toggle('hidden'); }

// Drag and drop
function initDropZone() {
  const zone = document.getElementById('drop-zone');
  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag-over'); onFileSelect(e.dataTransfer.files); });
}
function onFileSelect(files) {
  pendingFiles = [...pendingFiles, ...Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'))];
  renderFileList();
}
function renderFileList() {
  const el = document.getElementById('file-list');
  if (!pendingFiles.length) { el.innerHTML = ''; return; }
  el.innerHTML = pendingFiles.map((f,i) => `
    <div class="file-item">
      <span class="file-name">📄 ${f.name}</span>
      <span class="file-size">${(f.size/1024).toFixed(0)} KB</span>
      <button class="file-remove" onclick="removeFile(${i})">✕</button>
    </div>`).join('');
}
function removeFile(idx) { pendingFiles.splice(idx,1); renderFileList(); }

// Upload + analyze
async function uploadAndAnalyze() {
  const patientId = document.getElementById('new-patient-id').value.trim();
  if (!patientId) { showStatus('Anna ensin potilaan ID.','error'); return; }
  if (!pendingFiles.length) { showStatus('Lisää vähintään yksi PDF-tiedosto.','error'); return; }
  setLoading(true,'Ladataan tiedostoja...');
  try {
    const form = new FormData();
    pendingFiles.forEach(f => form.append('documents', f));
    const upRes  = await fetch(`/api/patients/${patientId}/documents/`, { method:'POST', body:form });
    const upData = await upRes.json();
    if (!upRes.ok) throw new Error(upData.error || 'Upload failed');
    pendingFiles = []; renderFileList();
    document.getElementById('new-patient-form').classList.add('hidden');
    setLoading(true, `Analysoidaan ${upData.uploaded} asiakirjaa — tämä voi kestää minuutteja...`);
    await runAnalysis(patientId);
    await loadPatientList();
  } catch(e) { showStatus(e.message,'error'); } finally { setLoading(false); }
}

async function addDocuments(files) {
  if (!currentPatientId) return;
  const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!pdfs.length) return;
  setLoading(true,'Ladataan uusia asiakirjoja...');
  try {
    const form = new FormData();
    pdfs.forEach(f => form.append('documents', f));
    const res  = await fetch(`/api/patients/${currentPatientId}/documents/`, { method:'POST', body:form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload failed');
    setLoading(true,`Analysoidaan ${data.uploaded} uutta asiakirjaa...`);
    await runAnalysis(currentPatientId);
  } catch(e) { showStatus(e.message,'error'); } finally {
    setLoading(false);
    document.getElementById('add-doc-input').value = '';
  }
}

async function runAnalysis(patientId) {
  const res  = await fetch(`/api/patients/${patientId}/analyze/`, { method:'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Analysis failed');
  currentPatientId = patientId;
  currentTimeline  = data.top_10_timeline || [];
  showPatientView(patientId, currentTimeline, true);
  showStatus(`Löydettiin ${data.total_events_found} tapahtumaa. Top-10 alla — tarkista ja hyväksy.`,'info');
}

async function loadPatient(patientId) {
  setLoading(true,'Ladataan potilaan tietoja...');
  try {
    const res  = await fetch(`/api/patients/${patientId}/timeline/`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Load failed');
    currentPatientId = patientId;
    const events = data.approved.length ? data.approved : data.proposed;
    currentTimeline  = events;
    const needsApproval = data.proposed.length > 0;
    showPatientView(patientId, events, needsApproval, data.doc_count);
  } catch(e) { showStatus(e.message,'error'); } finally { setLoading(false); loadPatientList(); }
}

function showPatientView(patientId, events, needsApproval, docCount) {
  document.getElementById('empty-state').classList.add('hidden');
  ['patient-header','timeline-section','bottom-panels'].forEach(id => document.getElementById(id).classList.remove('hidden'));
  document.getElementById('patient-title-id').textContent = patientId;
  document.getElementById('meta-docs').textContent   = `📄 ${docCount ?? '—'} asiakirjaa`;
  document.getElementById('meta-events').textContent = `📋 ${events.length} tapahtumaa`;
  document.getElementById('approve-bar').classList.toggle('hidden', !needsApproval);
  renderTimeline(events);
  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('event-detail').innerHTML = '<p class="hint-text">Klikkaa tapahtumaa aikajanalta.</p>';
}

// ── Timeline ─────────────────────────────────────────────────────────────────

// Three stagger heights (px above the line) to avoid flag overlap
const STAGGER_HEIGHTS = [68, 120, 175];

function renderTimeline(events) {
  const track = document.getElementById('timeline-track');
  track.innerHTML = '<div class="timeline-line"></div>';
  if (!events || !events.length) { track.innerHTML += '<div class="tl-empty">Ei tapahtumia.</div>'; return; }

  const sorted = [...events].sort((a,b) => new Date(a.date) - new Date(b.date));
  const t0 = new Date(sorted[0].date).getTime();
  const t1 = new Date(sorted[sorted.length-1].date).getTime();
  const span = t1 - t0 || 86400000 * 365;

  // Year markers (aligned with line at 78% from top = 22% from bottom)
  for (let y = new Date(sorted[0].date).getFullYear(); y <= new Date(sorted[sorted.length-1].date).getFullYear(); y++) {
    const yt  = new Date(y, 0, 1).getTime();
    if (yt < t0) continue;
    const pct = Math.min(((yt - t0) / span) * 96, 96);
    const m   = document.createElement('div');
    m.className = 'year-marker';
    m.style.left = pct + '%';
    m.innerHTML = `<div class="year-tick"></div><div class="year-label">${y}</div>`;
    track.appendChild(m);
  }

  sorted.forEach((event, i) => {
    const pct   = Math.min(Math.max(((new Date(event.date).getTime() - t0) / span) * 96, 1), 96);
    const color = SEVERITY_COLORS[event.severity] || '#007bff';
    const h     = STAGGER_HEIGHTS[i % STAGGER_HEIGHTS.length];

    // Connector — rises from the line upward by h px
    const conn = document.createElement('div');
    conn.className = 'ev-connector';
    conn.style.left   = pct + '%';
    conn.style.height = h + 'px';
    conn.style.background = color;
    track.appendChild(conn);

    // Flag — bottom sits h px above the line (line is at bottom: 22%)
    const flag = document.createElement('div');
    flag.className = 'ev-flag';
    flag.style.left   = pct + '%';
    flag.style.bottom = `calc(22% + ${h}px)`;
    flag.style.setProperty('--flag-border-color', color);
    flag.innerHTML = `
      <div class="flag-date">${event.date}</div>
      <div class="flag-type">${EVENT_LABELS[event.event_type] || event.event_type}</div>
      <div class="flag-sev" style="color:${color}">${'●'.repeat(event.severity)}${'○'.repeat(5-event.severity)}</div>`;
    flag.addEventListener('click', () => selectEvent(event));
    track.appendChild(flag);

    // Dot — sits on the line
    const dot = document.createElement('div');
    dot.className = 'ev-dot';
    dot.style.left       = pct + '%';
    dot.style.background = color;
    dot.title = `${event.date} — ${EVENT_LABELS[event.event_type] || event.event_type}`;
    dot.addEventListener('click', () => selectEvent(event));
    track.appendChild(dot);
  });
}

// ── Event detail + Laws ───────────────────────────────────────────────────────

async function selectEvent(event) {
  const color = SEVERITY_COLORS[event.severity] || '#007bff';
  document.getElementById('event-detail').innerHTML = `
    <div class="ev-detail-card" style="border-left:4px solid ${color}">
      <div class="ev-detail-date">${event.date}</div>
      <div class="ev-detail-type">${EVENT_LABELS[event.event_type] || event.event_type}</div>
      <div class="ev-detail-sev" style="color:${color}">Vakavuus ${event.severity}/5 ${'●'.repeat(event.severity)}${'○'.repeat(5-event.severity)}</div>
      <div class="ev-detail-desc">${event.description}</div>
      <div class="ev-detail-source">📄 ${event.source_document}</div>
      <div class="ev-detail-legal">⚖️ ${event.legal_basis}</div>
    </div>
    <div class="law-section">
      <div class="law-section-title">📚 Relevantit lait</div>
      <div id="law-results" class="law-loading">Haetaan lakipykäliä...</div>
    </div>`;
  try {
    const q   = encodeURIComponent(event.description.slice(0,200));
    const res = await fetch(`/api/laws/?event_type=${event.event_type}&query=${q}`);
    const data = await res.json();
    const el  = document.getElementById('law-results');
    if (!el) return;
    if (!data.laws || !data.laws.length) {
      el.innerHTML = '<div class="law-empty">Lakikantaa ei ole ladattu. Aja <code>build_knowledge_base.py</code> ensiksi.</div>';
      return;
    }
    el.innerHTML = data.laws.map(law => `
      <div class="law-item">
        <div class="law-ref">📖 ${law.reference}${law.section ? ' § '+law.section : ''}</div>
        <div class="law-excerpt">${law.excerpt}</div>
      </div>`).join('');
  } catch(e) {
    const el = document.getElementById('law-results');
    if (el) el.innerHTML = '<div class="law-empty">Lakeja ei voitu hakea.</div>';
  }
}

// ── Approve ───────────────────────────────────────────────────────────────────

async function approveTL() {
  if (!currentPatientId) return;
  const workerId = document.getElementById('worker-id').value.trim() || 'unknown';
  try {
    const res = await fetch(`/api/patients/${currentPatientId}/approve/`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ worker_id: workerId, timeline: currentTimeline }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    document.getElementById('approve-bar').classList.add('hidden');
    showStatus('✅ Aikajana hyväksytty ja tallennettu.','success');
    loadPatientList();
  } catch(e) { showStatus(e.message,'error'); }
}

async function reanalyze() {
  if (!currentPatientId) return;
  setLoading(true,'Analysoidaan uudelleen...');
  try { await runAnalysis(currentPatientId); } finally { setLoading(false); }
}

// ── Chat ──────────────────────────────────────────────────────────────────────

function chatKeydown(e) { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg   = input.value.trim();
  if (!msg || !currentPatientId) return;
  appendChatMsg('user', msg);
  input.value = '';
  const thinking = appendChatMsg('bot','⏳ Haetaan asiakirjoista...');
  try {
    const res  = await fetch(`/api/patients/${currentPatientId}/chat/`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: msg }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    thinking.textContent = data.answer;
    try {
      const parsed = JSON.parse(data.answer);
      if (parsed.timeline) {
        const btn = document.createElement('button');
        btn.className = 'btn-secondary small'; btn.textContent = '📅 Näytä aikajanalla';
        btn.onclick = () => { currentTimeline = parsed.timeline; renderTimeline(parsed.timeline); };
        thinking.parentElement.appendChild(btn);
      }
    } catch(_) {}
  } catch(e) { thinking.textContent = `Virhe: ${e.message}`; }
}

function appendChatMsg(role, text) {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`; div.textContent = text;
  box.appendChild(div); box.scrollTop = box.scrollHeight;
  return div;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setLoading(on, text) {
  document.getElementById('loading-text').textContent = text || 'Ladataan...';
  document.getElementById('loading').classList.toggle('hidden', !on);
}
function showStatus(msg, type) {
  const el = document.getElementById('status-msg');
  el.textContent = msg; el.className = `status-msg status-${type}`;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 7000);
}

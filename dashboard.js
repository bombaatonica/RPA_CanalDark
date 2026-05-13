/* =============================================
   dashboard.js — Obsidian Pipeline
   ============================================= */

const API = 'http://localhost:8000/api';

// ---- State ----
let allEpisodes = [];
let currentFilter = 'all';
let searchQuery = '';
let selectedDuration = 60;
let pendingEpId = null;      // para modal de geração
let pendingAudioEpId = null; // para modal de áudio
let pendingYtEpId = null;    // para modal youtube
let pollIntervals = {};       // polling por ep_id

// ---- Boot ----
document.addEventListener('DOMContentLoaded', () => {
  checkServer();
  checkYoutubeAuth();
  loadEpisodes();
  bindStaticEvents();
  setInterval(checkServer, 30000);
  setInterval(checkYoutubeAuth, 60000);
});

// =============================================
// SERVER STATUS
// =============================================
async function checkServer() {
  const el = document.getElementById('serverStatus');
  try {
    const r = await fetch(`${API}/episodes`, { method: 'GET', signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      el.className = 'server-status online';
      el.querySelector('.status-label').textContent = 'Online';
    } else throw new Error();
  } catch {
    el.className = 'server-status offline';
    el.querySelector('.status-label').textContent = 'Offline';
  }
}

// =============================================
// YOUTUBE AUTH — GLOBAL STATUS
// =============================================
let ytIsAuthed = false;

async function checkYoutubeAuth() {
  const el = document.getElementById('ytGlobalAuth');
  try {
    const r = await fetch(`${API}/youtube/auth-status`, { signal: AbortSignal.timeout(4000) });
    const data = await r.json();
    ytIsAuthed = data.authenticated;
    if (ytIsAuthed) {
      el.className = 'yt-global-auth authed';
      el.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58 2.78 2.78 0 0 0 1.95 1.96C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.96-1.96A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z"/>
          <polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02" fill="#0a0a0f"/>
        </svg>
        YouTube ✓`;
    } else {
      el.className = 'yt-global-auth not-authed';
      el.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46A2.78 2.78 0 0 0 1.46 6.42 29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58 2.78 2.78 0 0 0 1.95 1.96C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.96-1.96A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z"/>
          <polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02" fill="#0a0a0f"/>
        </svg>
        Conectar YouTube`;
      el.onclick = () => window.open('/api/youtube/auth', '_blank');
    }
  } catch {
    ytIsAuthed = false;
    el.className = 'yt-global-auth';
    el.innerHTML = '';
  }
}

// =============================================
// LOAD EPISODES
// =============================================
async function loadEpisodes() {
  const list = document.getElementById('episodesList');
  try {
    const r = await fetch(`${API}/episodes`);
    if (!r.ok) throw new Error('API indisponível');
    allEpisodes = await r.json();
    renderEpisodes();
    // Inicia polling para episódios que estão rodando
    allEpisodes.forEach(ep => {
      if (ep.pipeline_running) startPolling(ep.id);
    });
  } catch (e) {
    list.innerHTML = `
      <div class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <p>Não foi possível conectar ao servidor.</p>
        <p style="font-size:0.72rem;color:var(--text3)">Verifique se a API está rodando em <code>localhost:8000</code></p>
        <button class="btn btn-ghost btn-sm" onclick="loadEpisodes()">Tentar novamente</button>
      </div>`;
  }
}

// =============================================
// RENDER
// =============================================
function renderEpisodes() {
  const list = document.getElementById('episodesList');
  const counter = document.getElementById('epCount');

  let filtered = allEpisodes.filter(ep => {
    const matchSearch = ep.titulo.toLowerCase().includes(searchQuery) ||
                        ep.id.toLowerCase().includes(searchQuery);
    const matchFilter =
      currentFilter === 'all'     ? true :
      currentFilter === 'pending' ? (!ep.raw_video_exists && !ep.final_video_exists) :
      currentFilter === 'raw'     ? (ep.raw_video_exists && !ep.final_video_exists) :
      currentFilter === 'done'    ? ep.final_video_exists : true;
    return matchSearch && matchFilter;
  });

  counter.textContent = `${filtered.length} episódio${filtered.length !== 1 ? 's' : ''}`;

  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state"><p>Nenhum episódio encontrado.</p></div>`;
    return;
  }

  list.innerHTML = filtered.map(ep => renderEpRow(ep)).join('');
}

function renderEpRow(ep) {
  const statusChip = ep.final_video_exists
    ? `<span class="status-chip done">✓ Pronto</span>`
    : ep.raw_video_exists
      ? `<span class="status-chip raw">⬡ Raw</span>`
      : `<span class="status-chip pending">◌ Pendente</span>`;

  const audioChip = ep.audio_exists
    ? `<span class="audio-chip">♪ ${shortPath(ep.arquivo_audio)}</span>`
    : `<span class="audio-chip missing">✗ Sem áudio</span>`;

  const rawVideoHtml = ep.raw_video_exists
    ? `<div class="video-preview">
         <video src="${ep.raw_video_url}" muted playsinline
                onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0;"></video>
       </div>
       <span class="vid-meta">${ep.raw_video_size_mb} MB</span>`
    : ep.pipeline_running
      ? `<div class="phase-badge"><span class="mini-spin"></span>${ep.pipeline_phase || 'Processando...'}</div>`
      : ep.pipeline_error
        ? `<div class="phase-badge error">✗ ${ep.pipeline_error}</div>`
        : `<div class="video-preview">
             <div class="no-video">
               <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                 <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>
               </svg>
               <span>Nenhum vídeo raw</span>
             </div>
           </div>
           <span class="vid-meta">${ep.prompt_animacao}</span>`;

  const finalVideoHtml = ep.final_video_exists
    ? `<div class="video-preview">
         <video src="${ep.final_video_url}" muted playsinline
                onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0;"></video>
       </div>
       <span class="vid-meta">${ep.final_video_size_mb} MB</span>`
    : `<div class="video-preview">
         <div class="no-video">
           <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
             <circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>
           </svg>
           <span>Aguardando pipeline</span>
         </div>
       </div>`;

  const generateBtn = ep.pipeline_running
    ? `<button class="btn btn-ghost btn-sm" disabled style="opacity:0.5;cursor:not-allowed;">⟳ Rodando...</button>`
    : `<button class="btn btn-primary btn-sm" onclick="openConfirmGenerate('${ep.id}')">
         ▶ Gerar Vídeo
       </button>`;

  const ytBtn = ep.final_video_exists
    ? `<button class="btn btn-ghost btn-sm" onclick="openYoutube('${ep.id}')">
         📅 Agendar YT
       </button>`
    : '';

  const editBtn = `<button class="btn btn-ghost btn-sm" onclick="openEditEpisode('${ep.id}')">
    ✏ Prompts
  </button>`;

  return `
  <div class="ep-row${ep.pipeline_running ? ' running' : ''}" id="row-${ep.id}">
    <!-- Col: ID -->
    <div class="ep-id">
      <span class="ep-badge">${ep.id.replace('ep_', '#')}</span>
      ${statusChip}
    </div>

    <!-- Col: Áudio -->
    <div class="ep-cell audio-cell">
      <span class="ep-title">${ep.titulo}</span>
      ${audioChip}
      <div class="audio-url-display" onclick="openAudioModal('${ep.id}')" title="Clique para definir URL do áudio">
        <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span class="audio-url-text">${ep.arquivo_audio || 'Definir URL do YouTube...'}</span>
      </div>
    </div>

    <!-- Col: Raw Video -->
    <div class="ep-cell">${rawVideoHtml}</div>

    <!-- Col: Final Video -->
    <div class="ep-cell">${finalVideoHtml}</div>

    <!-- Col: Actions -->
    <div class="ep-actions">
      ${generateBtn}
      ${editBtn}
      ${ytBtn}
    </div>
  </div>`;
}

function shortPath(p) {
  if (!p) return 'N/A';
  const parts = p.split(/[\/\\]/);
  return parts[parts.length - 1];
}

// =============================================
// POLLING
// =============================================
function startPolling(epId) {
  if (pollIntervals[epId]) return;
  pollIntervals[epId] = setInterval(async () => {
    try {
      const r = await fetch(`${API}/status/${epId}`);
      const data = await r.json();
      // Atualiza o ep no array
      const idx = allEpisodes.findIndex(e => e.id === epId);
      if (idx !== -1) allEpisodes[idx] = data;
      // Re-renderiza a row
      const rowEl = document.getElementById(`row-${epId}`);
      if (rowEl) {
        const tmp = document.createElement('div');
        tmp.innerHTML = renderEpRow(data);
        rowEl.replaceWith(tmp.firstElementChild);
      }
      // Para o polling se terminou
      if (!data.pipeline_running) {
        clearInterval(pollIntervals[epId]);
        delete pollIntervals[epId];
        const msg = data.pipeline_error
          ? `Erro no ${epId}: ${data.pipeline_error}`
          : `Pipeline ${epId} concluída! ✓`;
        showToast(msg, data.pipeline_error ? 'error' : 'success');
      }
    } catch {
      clearInterval(pollIntervals[epId]);
      delete pollIntervals[epId];
    }
  }, 4000);
}

// =============================================
// STATIC EVENT BINDINGS
// =============================================
function bindStaticEvents() {
  // Refresh
  document.getElementById('btnRefresh').addEventListener('click', () => loadEpisodes());

  // Search
  document.getElementById('searchInput').addEventListener('input', e => {
    searchQuery = e.target.value.toLowerCase().trim();
    renderEpisodes();
  });

  // Filter tabs
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentFilter = tab.dataset.filter;
      renderEpisodes();
    });
  });

  // Edit ALL JSON
  document.getElementById('btnEditJson').addEventListener('click', openEditAll);

  // ----- Modal JSON -----
  document.getElementById('closeModalJson').addEventListener('click', () => closeModal('modalJson'));
  document.getElementById('cancelModalJson').addEventListener('click', () => closeModal('modalJson'));
  document.getElementById('saveModalJson').addEventListener('click', saveJson);

  // ----- Modal Confirm Generate -----
  document.getElementById('closeModalConfirmGenerate').addEventListener('click', () => closeModal('modalConfirmGenerate'));
  document.getElementById('cancelGenerate').addEventListener('click', () => closeModal('modalConfirmGenerate'));
  document.getElementById('confirmGenerate').addEventListener('click', triggerGenerate);
  document.querySelectorAll('.dur-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dur-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedDuration = parseInt(btn.dataset.secs);
    });
  });

  // ----- Modal Audio -----
  document.getElementById('closeModalAudio').addEventListener('click', () => closeModal('modalAudio'));
  document.getElementById('cancelAudio').addEventListener('click', () => closeModal('modalAudio'));
  document.getElementById('confirmAudio').addEventListener('click', downloadAudio);

  // ----- Modal YouTube -----
  document.getElementById('closeModalYoutube').addEventListener('click', () => closeModal('modalYoutube'));
  document.getElementById('cancelYoutube').addEventListener('click', () => closeModal('modalYoutube'));
  document.getElementById('confirmYoutube').addEventListener('click', scheduleYoutube);

  // Close on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });
}

// =============================================
// MODAL HELPERS
// =============================================
function openModal(id)  { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// =============================================
// MODAL: EDIT JSON
// =============================================
async function openEditAll() {
  document.getElementById('jsonModalEpId').textContent = 'Todos os Episódios';
  try {
    const r = await fetch(`${API}/metadata/raw`);
    const data = await r.json();
    document.getElementById('jsonEditor').value = JSON.stringify(data, null, 2);
    openModal('modalJson');
  } catch {
    showToast('Erro ao carregar JSON da API', 'error');
  }
}

async function openEditEpisode(epId) {
  document.getElementById('jsonModalEpId').textContent = epId;
  try {
    const r = await fetch(`${API}/metadata/raw`);
    const data = await r.json();
    // Mostra apenas o episódio selecionado para edição focada
    const single = { [epId]: data[epId] };
    document.getElementById('jsonEditor').value = JSON.stringify(single, null, 2);
    document.getElementById('jsonEditor').dataset.mode = 'single';
    document.getElementById('jsonEditor').dataset.epId = epId;
    openModal('modalJson');
  } catch {
    showToast('Erro ao carregar JSON', 'error');
  }
}

async function saveJson() {
  const editor = document.getElementById('jsonEditor');
  const mode = editor.dataset.mode;
  let parsed;
  try {
    parsed = JSON.parse(editor.value);
  } catch {
    showToast('JSON inválido! Verifique a sintaxe.', 'error');
    return;
  }

  try {
    let payload;
    if (mode === 'single') {
      // Mescla com o JSON completo
      const r = await fetch(`${API}/metadata/raw`);
      const full = await r.json();
      payload = { ...full, ...parsed };
    } else {
      payload = parsed;
    }

    const r = await fetch(`${API}/metadata/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: payload })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'Erro ao salvar');
    showToast('Metadados salvos com sucesso! ✓', 'success');
    closeModal('modalJson');
    editor.dataset.mode = '';
    loadEpisodes();
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

// =============================================
// MODAL: CONFIRM GENERATE
// =============================================
function openConfirmGenerate(epId) {
  pendingEpId = epId;
  const ep = allEpisodes.find(e => e.id === epId);
  document.getElementById('confirmEpInfo').innerHTML = ep
    ? `<strong>${ep.titulo}</strong><br>
       🎨 ${ep.prompt_imagem}<br>
       🎬 ${ep.prompt_animacao}`
    : epId;
  openModal('modalConfirmGenerate');
}

async function triggerGenerate() {
  if (!pendingEpId) return;
  closeModal('modalConfirmGenerate');
  try {
    const r = await fetch(`${API}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: pendingEpId, duration: selectedDuration })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail);
    showToast(`Pipeline iniciada para ${pendingEpId}! 🚀`, 'info');
    // Atualiza localmente e começa polling
    const idx = allEpisodes.findIndex(e => e.id === pendingEpId);
    if (idx !== -1) {
      allEpisodes[idx].pipeline_running = true;
      allEpisodes[idx].pipeline_phase = 'Iniciando...';
    }
    renderEpisodes();
    startPolling(pendingEpId);
  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
  }
}

// =============================================
// MODAL: AUDIO DOWNLOAD
// =============================================
function openAudioModal(epId) {
  pendingAudioEpId = epId;
  const ep = allEpisodes.find(e => e.id === epId);
  document.getElementById('audioEpLabel').textContent = epId;
  document.getElementById('audioUrlInput').value = '';
  document.getElementById('audioStatusMsg').textContent = '';
  document.getElementById('audioStatusMsg').className = 'audio-status';
  openModal('modalAudio');
}

async function downloadAudio() {
  const url = document.getElementById('audioUrlInput').value.trim();
  const statusEl = document.getElementById('audioStatusMsg');
  if (!url) { showToast('Digite uma URL', 'warning'); return; }

  statusEl.textContent = '⟳ Iniciando download...';
  statusEl.className = 'audio-status loading';

  try {
    const r = await fetch(`${API}/download-audio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: pendingAudioEpId, url })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail);
    statusEl.textContent = '✓ Download iniciado! Isso pode levar alguns segundos.';
    statusEl.className = 'audio-status ok';
    showToast('Download de áudio iniciado!', 'info');
    // Poll audio status
    const audioPoller = setInterval(async () => {
      try {
        const sr = await fetch(`${API}/audio-status/${pendingAudioEpId}`);
        const sdata = await sr.json();
        if (!sdata.running) {
          clearInterval(audioPoller);
          if (sdata.error) {
            statusEl.textContent = `✗ Erro: ${sdata.error}`;
            statusEl.className = 'audio-status error';
          } else {
            statusEl.textContent = `✓ ${sdata.phase}`;
            statusEl.className = 'audio-status ok';
            showToast('Áudio baixado com sucesso! ♪', 'success');
            loadEpisodes();
          }
        } else {
          statusEl.textContent = `⟳ ${sdata.phase}`;
        }
      } catch { clearInterval(audioPoller); }
    }, 2000);
  } catch (e) {
    statusEl.textContent = `✗ ${e.message}`;
    statusEl.className = 'audio-status error';
  }
}

// =============================================
// MODAL: YOUTUBE SCHEDULE
// =============================================
let ytUploadPoller = null;

async function openYoutube(epId) {
  pendingYtEpId = epId;
  const ep = allEpisodes.find(e => e.id === epId);

  // Reseta progress
  document.getElementById('ytUploadProgress').style.display = 'none';
  document.getElementById('ytProgressBar').style.width = '0%';
  document.getElementById('ytProgressLabel').textContent = 'Aguardando...';
  document.getElementById('ytSuccessLink').style.display = 'none';
  document.getElementById('ytSuccessLink').innerHTML = '';

  // Preenche campos com dados do episódio
  document.getElementById('ytEpPreview').innerHTML =
    ep ? `<span style="color:var(--text3);font-size:0.7rem;">📼 Episódio</span><br><strong>${ep.titulo}</strong>` : epId;
  document.getElementById('ytTitle').value = ep ? ep.titulo : '';
  document.getElementById('ytDescription').value = ep ? ep.descricao : '';
  document.getElementById('ytTags').value = 'dark ambient, dark fantasy, ambiance, relax, study music, sleep music, medieval';

  // Default: amanhã às 15h
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(15, 0, 0, 0);
  document.getElementById('ytScheduledTime').value = tomorrow.toISOString().slice(0, 16);

  // Habilita/desabilita botão baseado no estado global de auth
  document.getElementById('confirmYoutube').disabled = !ytIsAuthed;

  openModal('modalYoutube');
}

async function scheduleYoutube() {
  const tagsRaw = document.getElementById('ytTags').value;
  const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);

  // Converte datetime-local para ISO 8601 com timezone UTC
  const localDt = document.getElementById('ytScheduledTime').value;
  const scheduledISO = new Date(localDt).toISOString();

  try {
    const r = await fetch(`${API}/youtube/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        episode_id: pendingYtEpId,
        title: document.getElementById('ytTitle').value,
        description: document.getElementById('ytDescription').value,
        tags,
        category_id: '24',
        scheduled_time: scheduledISO
      })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'Erro no upload');

    // Mostra progress e desabilita botão
    document.getElementById('confirmYoutube').disabled = true;
    document.getElementById('ytUploadProgress').style.display = 'block';
    showToast('Upload iniciado! Acompanhe o progresso no modal.', 'info');

    // Polling do progresso
    if (ytUploadPoller) clearInterval(ytUploadPoller);
    ytUploadPoller = setInterval(async () => {
      try {
        const sr = await fetch(`${API}/youtube/upload-status/${pendingYtEpId}`);
        const sd = await sr.json();

        document.getElementById('ytProgressLabel').textContent = sd.phase || 'Processando...';
        document.getElementById('ytProgressBar').style.width = `${sd.progress || 0}%`;

        if (!sd.running) {
          clearInterval(ytUploadPoller);
          ytUploadPoller = null;
          if (sd.error) {
            document.getElementById('ytProgressLabel').textContent = `✗ Erro: ${sd.error}`;
            document.getElementById('ytProgressBar').style.background = 'var(--red)';
            showToast(`Erro no upload: ${sd.error}`, 'error');
          } else if (sd.video_id) {
            document.getElementById('ytProgressLabel').textContent = '✓ Upload concluído!';
            const linkEl = document.getElementById('ytSuccessLink');
            linkEl.style.display = 'block';
            linkEl.innerHTML = `
              <a href="${sd.video_url}" target="_blank" class="btn btn-yt btn-sm" style="text-decoration:none;width:100%;justify-content:center;margin-top:8px;">
                Abrir no YouTube Studio →
              </a>`;
            showToast(`Vídeo agendado com sucesso! ID: ${sd.video_id}`, 'success');
          }
        }
      } catch { clearInterval(ytUploadPoller); ytUploadPoller = null; }
    }, 3000);

  } catch (e) {
    showToast(`Erro: ${e.message}`, 'error');
    document.getElementById('confirmYoutube').disabled = false;
  }
}

// =============================================
// TOAST
// =============================================
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 350);
  }, 4000);
}

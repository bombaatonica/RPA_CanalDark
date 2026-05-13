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
let pollIntervals = {};          // pipeline polling por ep_id
let audioDownloadPollers = {};   // audio download polling por ep_id

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
      if (ep.audio_download_running) startAudioPolling(ep.id);
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

  const audioChip = ep.audio_download_running
    ? `<span class="audio-chip downloading">⧳ ${ep.audio_download_phase || 'Baixando...'}</span>`
    : ep.audio_exists
      ? `<span class="audio-chip">♪ ${shortPath(ep.arquivo_audio)}</span>`
      : `<span class="audio-chip missing">✗ Sem áudio</span>`;

  const audioMiniBar = ep.audio_download_running
    ? `<div class="audio-mini-bar-wrap">
         <div class="audio-mini-bar-fill" style="width:${ep.audio_download_progress || 0}%"></div>
       </div>
       <span class="audio-mini-meta">${[ep.audio_download_speed, ep.audio_download_eta ? `ETA ${ep.audio_download_eta}` : ''].filter(Boolean).join(' · ')}</span>`
    : '';

  const isRunning = ep.pipeline_running;

  const progressHtml = isRunning
    ? `<div class="pipeline-progress-wrap" style="margin-top: 8px;">
         <div class="pipeline-progress-header">
           <span class="mini-spin-inline"></span>
           <span class="pipeline-phase-text">${ep.pipeline_phase || 'Processando...'}</span>
           <span class="pipeline-pct">${ep.pipeline_progress || 0}%</span>
         </div>
         <div class="pipeline-bar-track">
           <div class="pipeline-bar-fill" style="width:${ep.pipeline_progress || 0}%"></div>
         </div>
       </div>`
    : (ep.pipeline_error ? `<div class="phase-badge error" style="margin-top: 8px;">✗ ${ep.pipeline_error}</div>` : '');

  const btnCancel = isRunning 
    ? `<button class="btn btn-danger btn-sm" style="margin-top:8px; width:100%" onclick="cancelPipeline('${ep.id}')">🛑 Cancelar Processo</button>` 
    : '';

  const editBtn = `<button class="btn btn-ghost btn-sm" style="margin-top:8px; width:100%" onclick="openEditEpisode('${ep.id}')">✏️ Editar Prompts</button>`;

  // Imagem Base
  const rawImageHtml = ep.raw_image_exists
    ? `<div class="video-preview">
         <img src="${ep.raw_image_url}" style="width:100%; height:100%; object-fit:cover; border-radius:8px;" />
       </div>
       <span class="vid-meta">${ep.raw_image_size_mb} MB</span>`
    : `<div class="video-preview">
         <div class="no-video">
           <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
           <span>Sem imagem</span>
         </div>
       </div>
       <span class="vid-meta prompt" title="${ep.prompt_imagem}">${ep.prompt_imagem || 'Sem prompt'}</span>`;

  // Vídeo Raw
  const rawVideoHtml = (ep.raw_video_exists && !isRunning)
    ? `<div class="video-preview">
         <video src="${ep.raw_video_url}?t=${Date.now()}" muted playsinline
                onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0;"></video>
       </div>
       <span class="vid-meta">${ep.raw_video_size_mb} MB</span>`
    : `<div class="video-preview">
         <div class="no-video">
           <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
             <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>
           </svg>
           <span>${isRunning ? 'Processando...' : 'Nenhum vídeo raw'}</span>
         </div>
       </div>
       <span class="vid-meta prompt" title="${ep.prompt_animacao}">${ep.prompt_animacao || 'Sem prompt'}</span>`;

  // Vídeo Final
  const finalVideoHtml = (ep.final_video_exists && !isRunning)
    ? `<div class="video-preview">
         <video src="${ep.final_video_url}?t=${Date.now()}" muted playsinline
                onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0;"></video>
       </div>
       <span class="vid-meta">${ep.final_video_size_mb} MB</span>`
    : `<div class="video-preview">
         <div class="no-video">
           <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
             <circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>
           </svg>
           <span>${isRunning ? 'Em processamento...' : 'Aguardando render'}</span>
         </div>
       </div>`;

  const btnImg = isRunning ? '' : `<button class="btn btn-primary btn-sm" style="margin-top:4px; width:100%" onclick="openConfirmGenerate('${ep.id}', 'image')">🎨 Gerar Foto</button>`;
  const btnVid = isRunning ? '' : `<button class="btn btn-primary btn-sm" style="margin-top:4px; width:100%" onclick="openConfirmGenerate('${ep.id}', 'video')">🎬 Gerar Vídeo</button>`;
  const btnFinal = isRunning ? '' : `<button class="btn btn-primary btn-sm" style="margin-top:4px; width:100%" onclick="openConfirmGenerate('${ep.id}', 'final')">⚙️ Renderizar Final</button>`;

  const ytBtn = (!isRunning && ep.final_video_exists)
    ? `<button class="btn btn-ghost btn-sm" style="margin-top:4px; width:100%" onclick="openYoutube('${ep.id}')">📅 Agendar YT</button>`
    : '';

  return `
  <div class="ep-row${ep.pipeline_running ? ' running' : ''}" id="row-${ep.id}">
    <!-- Col: ID -->
    <div class="ep-id">
      <span class="ep-badge">${ep.id.replace('ep_', '#')}</span>
      ${statusChip}
    </div>

    <!-- Col: Áudio e Status Geral -->
    <div class="ep-cell audio-cell">
      <span class="ep-title">${ep.titulo}</span>
      ${audioChip}
      ${audioMiniBar}
      <div class="audio-url-display" onclick="openAudioModal('${ep.id}')" title="Clique para definir URL do áudio">
        <svg class="icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span class="audio-url-text">${ep.arquivo_audio || 'Definir URL do YouTube...'}</span>
      </div>
      ${editBtn}
      ${progressHtml}
      ${btnCancel}
    </div>

    <!-- Col: Imagem Base -->
    <div class="ep-cell">
      ${rawImageHtml}
      ${btnImg}
    </div>

    <!-- Col: Raw Video -->
    <div class="ep-cell">
      ${rawVideoHtml}
      ${btnVid}
    </div>

    <!-- Col: Final Video -->
    <div class="ep-cell">
      ${finalVideoHtml}
      ${btnFinal}
      ${ytBtn}
    </div>
  </div>`;
}

async function cancelPipeline(epId) {
  if (!confirm(`Deseja realmente cancelar a pipeline do episódio ${epId}? O cancelamento pode não ser imediato caso o navegador já esteja processando a ação na Adobe.`)) return;
  try {
    const r = await fetch(`${API}/generate/cancel/${epId}`, { method: 'POST' });
    const res = await r.json();
    showToast(res.message, res.ok ? 'success' : 'error');
  } catch (e) {
    showToast('Erro ao cancelar: ' + e.message, 'error');
  }
}

async function cancelYtUpload() {
  if (!pendingYtEpId) return;
  if (!confirm('Deseja realmente cancelar este upload?')) return;
  
  try {
    const r = await fetch(`${API}/youtube/cancel/${pendingYtEpId}`, { method: 'POST' });
    const res = await r.json();
    showToast(res.message, res.ok ? 'success' : 'error');
    if (res.ok) {
      document.getElementById('btnCancelYtUpload').disabled = true;
      document.getElementById('btnCancelYtUpload').innerText = 'Cancelando...';
    }
  } catch (e) {
    showToast('Erro ao cancelar upload: ' + e.message, 'error');
  }
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

function startAudioPolling(epId) {
  if (audioDownloadPollers[epId]) return;
  audioDownloadPollers[epId] = setInterval(async () => {
    try {
      const r = await fetch(`${API}/audio-status/${epId}`);
      const sdata = await r.json();

      const idx = allEpisodes.findIndex(e => e.id === epId);
      if (idx !== -1) {
        allEpisodes[idx].audio_download_running = sdata.running;
        allEpisodes[idx].audio_download_phase = sdata.phase;
        allEpisodes[idx].audio_download_progress = sdata.progress;
        allEpisodes[idx].audio_download_speed = sdata.speed;
        allEpisodes[idx].audio_download_eta = sdata.eta;
        
        // Re-renderiza a row
        const rowEl = document.getElementById(`row-${epId}`);
        if (rowEl) {
          const tmp = document.createElement('div');
          tmp.innerHTML = renderEpRow(allEpisodes[idx]);
          rowEl.replaceWith(tmp.firstElementChild);
        }
      }

      // Atualiza modal se estiver aberto para este ep
      if (pendingAudioEpId === epId) {
        const statusEl = document.getElementById('audioStatusMsg');
        const bar = document.getElementById('audioProgressBar');
        const metaEl = document.getElementById('audioMeta');

        if (statusEl && bar && metaEl) {
          statusEl.textContent = sdata.phase || 'Baixando...';
          bar.style.width = `${sdata.progress || 0}%`;

          if (sdata.speed || sdata.eta) {
            metaEl.textContent = [sdata.speed, sdata.eta ? `ETA ${sdata.eta}` : ''].filter(Boolean).join('  ·  ');
          }

          if (!sdata.running) {
            document.getElementById('confirmAudio').disabled = false;
            if (sdata.error) {
              statusEl.textContent = `✗ Erro: ${sdata.error}`;
              statusEl.className = 'audio-status error';
              bar.className = 'dl-progress-bar error';
            } else {
              statusEl.textContent = `✓ ${sdata.phase}`;
              statusEl.className = 'audio-status ok';
              bar.className = 'dl-progress-bar success';
              metaEl.textContent = '';
            }
          }
        }
      }

      if (!sdata.running) {
        clearInterval(audioDownloadPollers[epId]);
        delete audioDownloadPollers[epId];
        if (!sdata.error) {
          showToast(`Áudio do ${epId} baixado! ♪`, 'success');
          loadEpisodes(); // Puxa dados atualizados para resolver status/paths final
        } else {
          showToast(`Erro no áudio do ${epId}: ${sdata.error}`, 'error');
          loadEpisodes();
        }
      }
    } catch {
      clearInterval(audioDownloadPollers[epId]);
      delete audioDownloadPollers[epId];
    }
  }, 1000);
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
  document.getElementById('btnCancelYtUpload').addEventListener('click', cancelYtUpload);
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
let pendingStage = 'all';

function openConfirmGenerate(epId, stage = 'all') {
  pendingEpId = epId;
  pendingStage = stage;
  const ep = allEpisodes.find(e => e.id === epId);
  
  const stageLabels = {
    'image': 'Fase 1: Gerar Imagem Base (Firefly)',
    'video': 'Fase 2: Gerar Vídeo Animado (Firefly)',
    'final': 'Fase 3: Renderizar Final (FFmpeg)',
    'all': 'Pipeline Completa (Imagem → Vídeo → Render)'
  };

  document.getElementById('confirmEpInfo').innerHTML = ep
    ? `<strong>${ep.titulo}</strong><br>
       <span style="color: var(--accent2); margin-top: 8px; display: inline-block;">Ação selecionada: ${stageLabels[stage]}</span>`
    : epId;
    
  openModal('modalConfirmGenerate');
}

async function triggerGenerate() {
  if (!pendingEpId) return;
  closeModal('modalConfirmGenerate');
  try {
    const r = await fetch(`${API}/generate/${pendingStage}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: pendingEpId, duration: selectedDuration })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail);
    showToast(`Pipeline (${pendingStage}) iniciada para ${pendingEpId}! 🚀`, 'info');
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
  // Reseta barra de progresso
  document.getElementById('audioProgressWrap').style.display = 'none';
  document.getElementById('audioProgressBar').style.width = '0%';
  document.getElementById('audioProgressBar').className = 'dl-progress-bar';
  document.getElementById('audioMeta').textContent = '';
  document.getElementById('confirmAudio').disabled = false;
  
  // Auto-resume se estiver baixando
  if (ep && ep.audio_download_running) {
    document.getElementById('audioStatusMsg').textContent = ep.audio_download_phase || 'Baixando...';
    document.getElementById('audioStatusMsg').className = 'audio-status loading';
    document.getElementById('audioProgressWrap').style.display = 'block';
    document.getElementById('audioProgressBar').style.width = `${ep.audio_download_progress || 0}%`;
    document.getElementById('confirmAudio').disabled = true;
    if (ep.audio_download_speed || ep.audio_download_eta) {
      document.getElementById('audioMeta').textContent = [ep.audio_download_speed, ep.audio_download_eta ? `ETA ${ep.audio_download_eta}` : ''].filter(Boolean).join('  ·  ');
    }
  }

  openModal('modalAudio');
}

async function downloadAudio() {
  const url = document.getElementById('audioUrlInput').value.trim();
  const statusEl = document.getElementById('audioStatusMsg');
  if (!url) { showToast('Digite uma URL', 'warning'); return; }

  try {
    const r = await fetch(`${API}/download-audio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: pendingAudioEpId, url })
    });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail);

    // Atualiza estado local imediatamente para feedback na row
    const idx = allEpisodes.findIndex(e => e.id === pendingAudioEpId);
    if (idx !== -1) {
      allEpisodes[idx].audio_download_running = true;
      allEpisodes[idx].audio_download_phase = 'Iniciando download...';
      allEpisodes[idx].audio_download_progress = 0;
      allEpisodes[idx].audio_download_speed = '';
      allEpisodes[idx].audio_download_eta = '';
    }

    statusEl.textContent = '⧳ Iniciando download...';
    statusEl.className = 'audio-status loading';
    document.getElementById('audioProgressWrap').style.display = 'block';
    document.getElementById('audioProgressBar').style.width = '0%';
    document.getElementById('audioProgressBar').className = 'dl-progress-bar';
    document.getElementById('audioMeta').textContent = '';
    document.getElementById('confirmAudio').disabled = true;
    showToast('Download de áudio iniciado!', 'info');

    // Força update da row imediatamente
    const rowEl = document.getElementById(`row-${pendingAudioEpId}`);
    if (rowEl && idx !== -1) {
      const tmp = document.createElement('div');
      tmp.innerHTML = renderEpRow(allEpisodes[idx]);
      rowEl.replaceWith(tmp.firstElementChild);
    }

    // Inicia polling global
    startAudioPolling(pendingAudioEpId);
  } catch (e) {
    statusEl.textContent = `✗ ${e.message}`;
    statusEl.className = 'audio-status error';
    document.getElementById('confirmAudio').disabled = false;
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
          document.getElementById('btnCancelYtUpload').style.display = 'none';
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

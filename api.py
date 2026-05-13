"""
api.py - Backend local da Obsidian Pipeline
Roda em: uvicorn api:app --port 8000
"""

import os
import json
import subprocess
import threading
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# YouTube API
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

app = FastAPI(title="Obsidian Pipeline API")

# CORS para o frontend (localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caminhos base do projeto
BASE_DIR = Path(__file__).parent
METADATA_PATH = BASE_DIR / "metadados.json"
WORKSPACE_RAW = BASE_DIR / "workspace" / "videos_raw"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_AUDIO = BASE_DIR / "assets" / "musicas"

# Monta os arquivos estáticos (frontend, workspace, output)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/workspace", StaticFiles(directory=str(BASE_DIR / "workspace")), name="workspace")
app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")

# Caminhos YouTube OAuth
CLIENT_SECRETS = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "token.json"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Estado em memória para rastrear processos em execução
pipeline_status: dict[str, dict] = {}

# Estado dos uploads YouTube
youtube_uploads: dict[str, dict] = {}


# ----------- Modelos -----------

class GenerateRequest(BaseModel):
    episode_id: str
    duration: Optional[int] = 3600

class DownloadAudioRequest(BaseModel):
    episode_id: str
    url: str

class SaveMetadataRequest(BaseModel):
    data: dict

class YoutubeScheduleRequest(BaseModel):
    episode_id: str
    title: str
    description: str
    tags: Optional[list[str]] = []
    category_id: Optional[str] = "24"   # 24 = Entertainment
    scheduled_time: str                  # ISO 8601 (ex: 2026-05-15T15:00:00Z)


# ----------- Helpers -----------

def load_metadata() -> dict:
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_episode_status(ep_id: str, meta: dict) -> dict:
    """Retorna o estado completo de um episódio com caminhos de arquivo."""
    ep = meta.get(ep_id, {})

    raw_image = BASE_DIR / "workspace" / "imagens_raw" / f"{ep_id}_base.jpg"
    raw_video = WORKSPACE_RAW / f"{ep_id}_anim.mp4"
    final_video = OUTPUT_DIR / f"obsidian_{ep_id}.mp4"

    audio_path_rel = ep.get("arquivo_audio", "")

    # Normaliza caminhos sem diretório (ex: "musica.mp3" → "assets/musicas/musica.mp3")
    if audio_path_rel and "/" not in audio_path_rel and "\\" not in audio_path_rel:
        audio_path_rel = f"assets/musicas/{audio_path_rel}"
        # Corrige o JSON silenciosamente para evitar reincidência
        meta[ep_id]["arquivo_audio"] = audio_path_rel

    audio_exists = (BASE_DIR / audio_path_rel).exists() if audio_path_rel else False

    proc = pipeline_status.get(ep_id, {})
    audio_dl = pipeline_status.get(f"audio_{ep_id}", {})

    return {
        "id": ep_id,
        "titulo": ep.get("titulo", ""),
        "descricao": ep.get("descricao", ""),
        "prompt_imagem": ep.get("prompt_imagem", ""),
        "prompt_animacao": ep.get("prompt_animacao", ""),
        "arquivo_audio": audio_path_rel,
        "audio_url": f"/assets/musicas/{Path(audio_path_rel).name}" if audio_exists else None,
        "audio_exists": audio_exists,
        "audio_download_running": audio_dl.get("running", False),
        "audio_download_progress": audio_dl.get("progress", 0),
        "audio_download_phase": audio_dl.get("phase", None),
        "audio_download_speed": audio_dl.get("speed", ""),
        "audio_download_eta": audio_dl.get("eta", ""),
        "raw_image_exists": raw_image.exists(),
        "raw_image_url": f"/workspace/imagens_raw/{ep_id}_base.jpg" if raw_image.exists() else None,
        "raw_image_size_mb": round(raw_image.stat().st_size / 1_000_000, 2) if raw_image.exists() else None,
        "raw_video_exists": raw_video.exists(),
        "raw_video_url": f"/workspace/videos_raw/{ep_id}_anim.mp4" if raw_video.exists() else None,
        "raw_video_size_mb": round(raw_video.stat().st_size / 1_000_000, 2) if raw_video.exists() else None,
        "final_video_exists": final_video.exists(),
        "final_video_url": f"/output/obsidian_{ep_id}.mp4" if final_video.exists() else None,
        "final_video_size_mb": round(final_video.stat().st_size / 1_000_000, 2) if final_video.exists() else None,
        "pipeline_running": proc.get("running", False),
        "pipeline_phase": proc.get("phase", None),
        "pipeline_progress": proc.get("progress", 0),
        "pipeline_error": proc.get("error", None),
    }


# ----------- Rotas -----------

@app.get("/api/episodes")
def list_episodes():
    """Lista todos os episódios com seus status."""
    meta = load_metadata()
    return [get_episode_status(ep_id, meta) for ep_id in meta.keys()]


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str):
    """Retorna dados de um episódio específico."""
    meta = load_metadata()
    if episode_id not in meta:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")
    return get_episode_status(episode_id, meta)


@app.get("/api/metadata/raw")
def get_raw_metadata():
    """Retorna o JSON bruto de metadados para edição."""
    return load_metadata()


@app.post("/api/metadata/save")
def save_metadata(req: SaveMetadataRequest):
    """Salva o JSON de metadados editado."""
    try:
        # Validação básica: cada entrada deve ter os campos necessários
        required_fields = ["titulo", "descricao", "prompt_imagem", "prompt_animacao", "arquivo_audio"]
        for ep_id, ep_data in req.data.items():
            for field in required_fields:
                if field not in ep_data:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Campo '{field}' ausente no episódio '{ep_id}'"
                    )
        
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(req.data, f, ensure_ascii=False, indent=2)
        
        return {"ok": True, "message": "Metadados salvos com sucesso!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_stage(episode_id: str, stage: str, duration: int):
    """Executa uma etapa específica da pipeline em uma thread separada."""
    pipeline_status[episode_id] = {"running": True, "phase": f"Iniciando {stage}...", "progress": 0, "error": None, "cancel_requested": False}
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from core import config_loader, rpa_firefly, video_engine

        pipeline_status[episode_id].update({"phase": "Carregando configurações...", "progress": 5})
        metadata = config_loader.initialize(episode_id)

        img_out_path = str(BASE_DIR / "workspace" / "imagens_raw" / f"{episode_id}_base.jpg")
        vid_out_path = str(BASE_DIR / "workspace" / "videos_raw" / f"{episode_id}_anim.mp4")
        audio_path = str(BASE_DIR / metadata['arquivo_audio'])
        final_out_path = str(BASE_DIR / "output" / f"obsidian_{episode_id}.mp4")

        # Verifica se pediram cancelamento antes de começar o trabalho pesado
        if pipeline_status[episode_id].get("cancel_requested"):
            raise InterruptedError("Cancelado pelo usuário")

        if stage == "image":
            pipeline_status[episode_id].update({"phase": "Gerando imagem (Firefly)...", "progress": 30})
            rpa_firefly.generate_image(metadata['prompt_imagem'], img_out_path)
            pipeline_status[episode_id] = {"running": False, "phase": "Imagem gerada!", "progress": 100, "error": None}
            
        elif stage == "video":
            if not os.path.exists(img_out_path):
                raise Exception("Imagem base não encontrada! Gere a imagem primeiro.")
            pipeline_status[episode_id].update({"phase": "Gerando animação (Firefly)...", "progress": 30})
            rpa_firefly.generate_video(img_out_path, metadata['prompt_animacao'], vid_out_path)
            pipeline_status[episode_id] = {"running": False, "phase": "Vídeo bruto gerado!", "progress": 100, "error": None}
            
        elif stage == "final":
            if not os.path.exists(vid_out_path) or not os.path.exists(audio_path):
                raise Exception("Vídeo raw ou áudio não encontrados! Gere as etapas anteriores primeiro.")
            
            pipeline_status[episode_id].update({"phase": "Renderizando (FFmpeg)...", "progress": 10})
            
            def ffmpeg_progress(p):
                pipeline_status[episode_id].update({"progress": int(10 + (p * 0.90))})
                
            def check_cancel():
                return pipeline_status[episode_id].get("cancel_requested", False)
                
            video_engine.render_episode(vid_out_path, audio_path, final_out_path, duration=duration, progress_callback=ffmpeg_progress, cancel_check=check_cancel)
            pipeline_status[episode_id] = {"running": False, "phase": "Vídeo finalizado!", "progress": 100, "error": None}
            
        elif stage == "all":
            # Mantém a pipeline completa para compatibilidade ou se quiserem usar depois
            pipeline_status[episode_id].update({"phase": "Fase 1: Gerando imagem", "progress": 10})
            rpa_firefly.generate_image(metadata['prompt_imagem'], img_out_path)
            if pipeline_status[episode_id].get("cancel_requested"): raise InterruptedError()
            
            pipeline_status[episode_id].update({"phase": "Fase 2: Gerando animação", "progress": 40})
            rpa_firefly.generate_video(img_out_path, metadata['prompt_animacao'], vid_out_path)
            if pipeline_status[episode_id].get("cancel_requested"): raise InterruptedError()
            
            pipeline_status[episode_id].update({"phase": "Fase 3: Renderizando (FFmpeg)", "progress": 70})
            def ffmpeg_progress_all(p):
                pipeline_status[episode_id].update({"progress": int(70 + (p * 0.30))})
            def check_cancel_all():
                return pipeline_status[episode_id].get("cancel_requested", False)
            video_engine.render_episode(vid_out_path, audio_path, final_out_path, duration=duration, progress_callback=ffmpeg_progress_all, cancel_check=check_cancel_all)
            pipeline_status[episode_id] = {"running": False, "phase": "Pipeline completa!", "progress": 100, "error": None}

    except Exception as e:
        phase = "Cancelado" if isinstance(e, InterruptedError) else "Erro"
        pipeline_status[episode_id] = {"running": False, "phase": phase, "progress": 0, "error": str(e)}


@app.post("/api/generate/{stage}")
def trigger_generate_stage(stage: str, req: GenerateRequest):
    """Dispara uma etapa específica da pipeline ('image', 'video', 'final' ou 'all')."""
    if stage not in ["image", "video", "final", "all"]:
        raise HTTPException(status_code=400, detail="Estágio inválido")
        
    meta = load_metadata()
    if req.episode_id not in meta:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")
    
    status = pipeline_status.get(req.episode_id, {})
    if status.get("running"):
        raise HTTPException(status_code=409, detail="Pipeline já em execução para este episódio")
    
    # Limpa status anterior
    pipeline_status[req.episode_id] = {"running": True, "phase": "Iniciando", "progress": 0, "error": None}
    
    thread = threading.Thread(
        target=_run_stage,
        args=(req.episode_id, stage, req.duration),
        daemon=True
    )
    thread.start()
    
    return {"ok": True, "message": f"Pipeline ({stage}) iniciada para {req.episode_id}"}


@app.post("/api/generate/cancel/{episode_id}")
def cancel_generate(episode_id: str):
    """Solicita o cancelamento da pipeline em execução."""
    if episode_id in pipeline_status and pipeline_status[episode_id].get("running"):
        pipeline_status[episode_id]["cancel_requested"] = True
        return {"ok": True, "message": "Cancelamento solicitado. O processo irá parar em breve."}
    raise HTTPException(status_code=400, detail="Nenhuma pipeline em execução para cancelar.")


@app.get("/api/status/{episode_id}")
def get_pipeline_status(episode_id: str):
    """Retorna o status atual da pipeline para polling do frontend."""
    status = pipeline_status.get(episode_id, {"running": False, "phase": None, "error": None})
    meta = load_metadata()
    ep_status = get_episode_status(episode_id, meta)
    return {**status, **ep_status}


def _download_audio(episode_id: str, url: str, output_filename: str):
    """Baixa o áudio de uma URL do YouTube usando yt-dlp com progresso em tempo real."""
    import re
    pipeline_status[f"audio_{episode_id}"] = {
        "running": True, "phase": "Iniciando download...",
        "progress": 0, "speed": "", "eta": "", "error": None
    }
    try:
        ASSETS_AUDIO.mkdir(parents=True, exist_ok=True)
        output_path = str(ASSETS_AUDIO / output_filename)

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--newline",              # força uma linha por atualização de progresso
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_path,
            url
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in process.stdout:
            line = line.strip()
            if "[download]" in line and "%" in line:
                pct_match = re.search(r'(\d+\.?\d*)%', line)
                speed_match = re.search(r'at\s+([\d.]+\s*\w+/s)', line)
                eta_match = re.search(r'ETA\s+(\S+)', line)
                if pct_match:
                    pct = min(float(pct_match.group(1)), 99.0)  # reserva 100 p/ conclusão
                    pipeline_status[f"audio_{episode_id}"].update({
                        "phase": f"Baixando: {pct:.0f}%",
                        "progress": pct,
                        "speed": speed_match.group(1) if speed_match else "",
                        "eta": eta_match.group(1) if eta_match else ""
                    })
            elif "[ExtractAudio]" in line:
                pipeline_status[f"audio_{episode_id}"].update({
                    "phase": "Convertendo para MP3...", "progress": 99
                })

        process.wait()
        if process.returncode != 0:
            raise Exception(f"yt-dlp falhou (código {process.returncode})")

        # Atualiza o metadado do episódio com o novo áudio
        meta = load_metadata()
        if episode_id in meta:
            meta[episode_id]["arquivo_audio"] = f"assets/musicas/{output_filename}"
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

        pipeline_status[f"audio_{episode_id}"] = {
            "running": False, "phase": "Download concluído!",
            "progress": 100, "speed": "", "eta": "", "error": None
        }
    except Exception as e:
        pipeline_status[f"audio_{episode_id}"] = {
            "running": False, "phase": "Erro no download",
            "progress": 0, "speed": "", "eta": "", "error": str(e)
        }


@app.post("/api/download-audio")
def download_audio(req: DownloadAudioRequest):
    """Baixa o áudio de um URL do YouTube para um episódio."""
    # Cria um nome de arquivo baseado no episode_id
    output_filename = f"{req.episode_id}_audio.mp3"
    
    status = pipeline_status.get(f"audio_{req.episode_id}", {})
    if status.get("running"):
        raise HTTPException(status_code=409, detail="Download já em andamento")
    
    thread = threading.Thread(
        target=_download_audio,
        args=(req.episode_id, req.url, output_filename),
        daemon=True
    )
    thread.start()
    
    return {"ok": True, "message": f"Download iniciado para {req.episode_id}", "filename": output_filename}


@app.get("/api/audio-status/{episode_id}")
def get_audio_status(episode_id: str):
    """Retorna o status do download de áudio."""
    return pipeline_status.get(f"audio_{episode_id}", {"running": False, "phase": None, "error": None})


# ============================================================
# YOUTUBE — Helpers de autenticação
# ============================================================

def _load_yt_credentials() -> Optional["Credentials"]:
    """Carrega credenciais salvas em token.json e as renova se necessário."""
    if not YOUTUBE_AVAILABLE:
        return None
    if not TOKEN_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), YT_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            return None
    return creds if (creds and creds.valid) else None


def _build_yt_service():
    """Constrói o serviço YouTube autenticado."""
    creds = _load_yt_credentials()
    if not creds:
        raise HTTPException(
            status_code=401,
            detail="YouTube não autenticado. Acesse /api/youtube/auth para conectar."
        )
    return build("youtube", "v3", credentials=creds)


# ============================================================
# YOUTUBE — Rotas de Autenticação (OAuth2)
# ============================================================

@app.get("/api/youtube/auth-status")
def yt_auth_status():
    """Verifica se o YouTube está autenticado."""
    if not YOUTUBE_AVAILABLE:
        return {"authenticated": False, "error": "google-api-python-client não instalado"}
    if not CLIENT_SECRETS.exists():
        return {
            "authenticated": False,
            "error": "client_secrets.json não encontrado. Baixe em console.cloud.google.com"
        }
    creds = _load_yt_credentials()
    return {"authenticated": creds is not None}


# Armazena temporariamente os estados e code_verifiers (PKCE) do OAuth do Google
oauth_states = {}

@app.get("/api/youtube/auth")
def yt_auth():
    """
    Inicia o fluxo OAuth2 para o YouTube e redireciona o usuário.
    """
    if not YOUTUBE_AVAILABLE:
        raise HTTPException(status_code=500, detail="google-api-python-client não instalado")
    if not CLIENT_SECRETS.exists():
        raise HTTPException(
            status_code=400,
            detail="client_secrets.json não encontrado. Baixe em console.cloud.google.com e coloque na raiz do projeto."
        )
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        scopes=YT_SCOPES,
        redirect_uri="http://localhost:8000/api/youtube/callback"
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    
    # Salva o code_verifier (se existir) para o fluxo PKCE exigido pelo Google
    if hasattr(flow, 'code_verifier'):
        oauth_states[state] = flow.code_verifier
        
    return RedirectResponse(url=auth_url)


@app.get("/api/youtube/callback")
def yt_auth_callback(code: str, state: Optional[str] = None):
    """
    Callback OAuth2 do Google. Salva o token e redireciona para o dashboard.
    """
    if not YOUTUBE_AVAILABLE:
        raise HTTPException(status_code=500, detail="google-api-python-client não instalado")
    try:
        flow = Flow.from_client_secrets_file(
            str(CLIENT_SECRETS),
            scopes=YT_SCOPES,
            state=state,   # necessário para validar o state do OAuth
            redirect_uri="http://localhost:8000/api/youtube/callback"
        )
        
        # Restaura o code_verifier salvo
        if state in oauth_states:
            flow.code_verifier = oauth_states.pop(state)
            
        flow.fetch_token(code=code)
        creds = flow.credentials
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return RedirectResponse(url="/?yt_auth=success")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro no callback OAuth: {str(e)}")


# ============================================================
# YOUTUBE — Upload e Agendamento
# ============================================================

def _upload_to_youtube(ep_id: str, video_path: str, title: str,
                       description: str, tags: list, category_id: str,
                       scheduled_time: str):
    """Executa o upload do vídeo para o YouTube em thread separada."""
    youtube_uploads[ep_id] = {
        "running": True,
        "phase": "Iniciando upload...",
        "progress": 0,
        "error": None,
        "video_id": None,
        "video_url": None
    }
    try:
        youtube = _build_yt_service()

        # Bloco de Tags SEO solicitado pelo usuário (formatado como hashtags)
        seo_tags_block = (
            "#darkfantasy #ambience #gothicfantasy #music #medievalambience\n"
            "#darkambient #fantasysleepmusic #cathedralambience #dungeonsynth\n"
            "#medievalmusic #studying #reading #darkcathedral #rainambience\n"
            "#RPG #backgroundmusic #hauntedcathedral #sleepmusic\n"
            "#gothicambience #ObsidianRealm"
        )
        
        full_description = f"{description}{seo_tags_block}"

        body = {
            "snippet": {
                "title": title,
                "description": full_description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "pt"
            },
            "status": {
                "privacyStatus": "private",   # fica private até o horário agendado
                "publishAt": scheduled_time,   # ISO 8601 com timezone (ex: 2026-05-15T15:00:00Z)
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024  # 10MB por chunk
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        youtube_uploads[ep_id]["phase"] = "Enviando vídeo ao YouTube..."
        youtube_uploads[ep_id]["cancel_requested"] = False

        response = None
        while response is None:
            # Verifica cancelamento
            if youtube_uploads[ep_id].get("cancel_requested"):
                raise InterruptedError("Upload cancelado pelo usuário")

            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                youtube_uploads[ep_id]["progress"] = pct
                youtube_uploads[ep_id]["phase"] = f"Upload: {pct}%"

        video_id = response["id"]
        youtube_uploads[ep_id] = {
            "running": False,
            "phase": "Upload concluído!",
            "progress": 100,
            "error": None,
            "video_id": video_id,
            "video_url": f"https://studio.youtube.com/video/{video_id}/edit",
            "scheduled_time": scheduled_time
        }

    except HttpError as e:
        youtube_uploads[ep_id] = {
            "running": False, "phase": "Erro HTTP", "progress": 0,
            "error": f"YouTube API Error {e.resp.status}: {e.content.decode()}",
            "video_id": None, "video_url": None
        }
    except Exception as e:
        youtube_uploads[ep_id] = {
            "running": False, "phase": "Erro", "progress": 0,
            "error": str(e), "video_id": None, "video_url": None
        }


@app.post("/api/youtube/schedule")
def schedule_youtube(req: YoutubeScheduleRequest):
    """Inicia o upload do vídeo final para o YouTube com publicação agendada."""
    meta = load_metadata()
    if req.episode_id not in meta:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")

    final_video = OUTPUT_DIR / f"obsidian_{req.episode_id}.mp4"
    if not final_video.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Vídeo final não encontrado: {final_video.name}. Gere o vídeo primeiro."
        )

    current = youtube_uploads.get(req.episode_id, {})
    if current.get("running"):
        raise HTTPException(status_code=409, detail="Upload já em andamento para este episódio")

    thread = threading.Thread(
        target=_upload_to_youtube,
        args=(
            req.episode_id,
            str(final_video),
            req.title,
            req.description,
            req.tags,
            req.category_id,
            req.scheduled_time
        ),
        daemon=True
    )
    thread.start()

    return {"ok": True, "message": f"Upload iniciado para {req.episode_id}"}


@app.get("/api/youtube/upload-status/{episode_id}")
def get_upload_status(episode_id: str):
    """Retorna o status do upload YouTube para polling do frontend."""
    return youtube_uploads.get(
        episode_id,
        {"running": False, "phase": None, "progress": 0, "error": None,
         "video_id": None, "video_url": None}
    )


@app.post("/api/youtube/cancel/{episode_id}")
def cancel_youtube_upload(episode_id: str):
    """Solicita o cancelamento do upload YouTube em execução."""
    if episode_id in youtube_uploads and youtube_uploads[episode_id].get("running"):
        youtube_uploads[episode_id]["cancel_requested"] = True
        return {"ok": True, "message": "Cancelamento do upload solicitado."}
    raise HTTPException(status_code=400, detail="Nenhum upload em execução para cancelar.")


# Serve o frontend na raiz
@app.get("/")
def serve_frontend():
    return FileResponse(str(BASE_DIR / "dashboard.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

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
    
    raw_video = WORKSPACE_RAW / f"{ep_id}_anim.mp4"
    final_video = OUTPUT_DIR / f"obsidian_{ep_id}.mp4"
    
    audio_path_rel = ep.get("arquivo_audio", "")
    audio_exists = (BASE_DIR / audio_path_rel).exists() if audio_path_rel else False

    proc = pipeline_status.get(ep_id, {})

    return {
        "id": ep_id,
        "titulo": ep.get("titulo", ""),
        "descricao": ep.get("descricao", ""),
        "prompt_imagem": ep.get("prompt_imagem", ""),
        "prompt_animacao": ep.get("prompt_animacao", ""),
        "arquivo_audio": audio_path_rel,
        "audio_url": f"/assets/musicas/{Path(audio_path_rel).name}" if audio_exists else None,
        "audio_exists": audio_exists,
        "raw_video_exists": raw_video.exists(),
        "raw_video_url": f"/workspace/videos_raw/{ep_id}_anim.mp4" if raw_video.exists() else None,
        "raw_video_size_mb": round(raw_video.stat().st_size / 1_000_000, 2) if raw_video.exists() else None,
        "final_video_exists": final_video.exists(),
        "final_video_url": f"/output/obsidian_{ep_id}.mp4" if final_video.exists() else None,
        "final_video_size_mb": round(final_video.stat().st_size / 1_000_000, 2) if final_video.exists() else None,
        "pipeline_running": proc.get("running", False),
        "pipeline_phase": proc.get("phase", None),
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


def _run_pipeline(episode_id: str, duration: int):
    """Executa a pipeline em uma thread separada."""
    pipeline_status[episode_id] = {"running": True, "phase": "Iniciando...", "error": None}
    try:
        import sys
        # Adiciona o diretório base ao path para importar os módulos do projeto
        sys.path.insert(0, str(BASE_DIR))
        from core import config_loader, rpa_firefly, video_engine

        pipeline_status[episode_id]["phase"] = "Fase 1: Carregando configurações"
        metadata = config_loader.initialize(episode_id)

        img_out_path = str(BASE_DIR / "workspace" / "imagens_raw" / f"{episode_id}_base.jpg")
        vid_out_path = str(BASE_DIR / "workspace" / "videos_raw" / f"{episode_id}_anim.mp4")
        audio_path = str(BASE_DIR / metadata['arquivo_audio'])
        final_out_path = str(BASE_DIR / "output" / f"obsidian_{episode_id}.mp4")

        pipeline_status[episode_id]["phase"] = "Fase 2: Gerando imagem no Firefly"
        rpa_firefly.generate_image(metadata['prompt_imagem'], img_out_path)

        pipeline_status[episode_id]["phase"] = "Fase 3: Gerando animação no Firefly"
        rpa_firefly.generate_video(img_out_path, metadata['prompt_animacao'], vid_out_path)

        pipeline_status[episode_id]["phase"] = "Fase 4: Renderizando vídeo final (FFmpeg)"
        video_engine.render_episode(vid_out_path, audio_path, final_out_path, duration=duration)

        pipeline_status[episode_id] = {"running": False, "phase": "Concluído!", "error": None}
    except Exception as e:
        pipeline_status[episode_id] = {"running": False, "phase": "Erro", "error": str(e)}


@app.post("/api/generate")
def trigger_generate(req: GenerateRequest):
    """Dispara a pipeline de geração para um episódio."""
    meta = load_metadata()
    if req.episode_id not in meta:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")
    
    status = pipeline_status.get(req.episode_id, {})
    if status.get("running"):
        raise HTTPException(status_code=409, detail="Pipeline já em execução para este episódio")
    
    thread = threading.Thread(
        target=_run_pipeline,
        args=(req.episode_id, req.duration),
        daemon=True
    )
    thread.start()
    
    return {"ok": True, "message": f"Pipeline iniciada para {req.episode_id}"}


@app.get("/api/status/{episode_id}")
def get_pipeline_status(episode_id: str):
    """Retorna o status atual da pipeline para polling do frontend."""
    status = pipeline_status.get(episode_id, {"running": False, "phase": None, "error": None})
    meta = load_metadata()
    ep_status = get_episode_status(episode_id, meta)
    return {**status, **ep_status}


def _download_audio(episode_id: str, url: str, output_filename: str):
    """Baixa o áudio de uma URL do YouTube usando yt-dlp."""
    pipeline_status[f"audio_{episode_id}"] = {"running": True, "phase": "Baixando áudio...", "error": None}
    try:
        ASSETS_AUDIO.mkdir(parents=True, exist_ok=True)
        output_path = str(ASSETS_AUDIO / output_filename)
        
        cmd = [
            "yt-dlp",
            "--no-playlist",          # nunca baixar playlist inteira
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_path,
            url
        ]
        subprocess.run(cmd, check=True)
        
        # Atualiza o metadado do episódio com o novo áudio
        meta = load_metadata()
        if episode_id in meta:
            meta[episode_id]["arquivo_audio"] = f"assets/musicas/{output_filename}"
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        
        pipeline_status[f"audio_{episode_id}"] = {"running": False, "phase": "Download concluído!", "error": None}
    except Exception as e:
        pipeline_status[f"audio_{episode_id}"] = {"running": False, "phase": "Erro no download", "error": str(e)}


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


@app.get("/api/youtube/auth")
def yt_auth_start():
    """
    Inicia o fluxo OAuth2. Redireciona para o Google para autorização.
    Após autorizar, o Google redireciona para /api/youtube/callback.
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
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
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

        body = {
            "snippet": {
                "title": title,
                "description": description,
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

        response = None
        while response is None:
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


# Serve o frontend na raiz
@app.get("/")
def serve_frontend():
    return FileResponse(str(BASE_DIR / "dashboard.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

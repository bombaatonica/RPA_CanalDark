import time
import os
from core import config_loader
from core import rpa_firefly
from core import video_engine

def main():
    print("[*] Inicio da Obsidian Pipeline [*]\n")
    
    episode_id = "ep_001"
    
    try:
        # Fase 1: Configuração e Metadados
        print(">>> Fase 1: Carregando Configurações")
        metadata = config_loader.initialize(episode_id)
        print(f"Título do Episódio: {metadata['titulo']}")
        
        # Caminhos dos arquivos
        img_out_path = f"workspace/imagens_raw/{episode_id}_base.jpg"
        vid_out_path = f"workspace/videos_raw/{episode_id}_anim.mp4"
        audio_path = f"assets/musicas/{metadata['arquivo_audio']}"
        final_out_path = f"output/obsidian_{episode_id}.mp4"
        
        # Fase 2: Geração de Imagem (Text-to-Image)
        print("\n>>> Fase 2: Gerando Imagem Base no Firefly")
        # rpa_firefly.generate_image(metadata['prompt_imagem'], img_out_path)
        print("[Teste] Geração de imagem pulada para economizar créditos.")
        
        # Fase 3: Geração de Vídeo (Image-to-Video)
        print("\n>>> Fase 3: Gerando Animação no Firefly")
        rpa_firefly.generate_video(img_out_path, metadata['prompt_animacao'], vid_out_path, skip_generation=True)
        
        # Fase 4: Engenharia de Vídeo e Renderização
        print("\n>>> Fase 4: Montando o Episódio Final (FFmpeg)")
        if not os.path.exists(audio_path):
            print(f"[Aviso] Áudio '{audio_path}' não encontrado. Crie um arquivo de teste para continuar a simulação.")
            # Mocking audio file for testing if it doesn't exist
            import subprocess
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "10", "-c:a", "libmp3lame", audio_path], capture_output=True)
                
        # Duração default para testes reduzida (ex: 60s). Altere para 3600 (1 hora) na produção.
        test_duration = 60 
        video_engine.render_episode(vid_out_path, audio_path, final_out_path, duration=test_duration)
        
        print("\n[OK] Pipeline concluida com sucesso!")
        print(f"[+] Episodio pronto: {final_out_path}")
        
    except Exception as e:
        print(f"\n[ERROR] Erro critico na pipeline: {e}")
        print("Execucao abortada.")

if __name__ == "__main__":
    main()

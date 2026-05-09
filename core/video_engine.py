import subprocess
import os

def create_ping_pong_video(input_path, output_path):
    """
    Creates a ping-pong loop of the short video to avoid harsh cuts.
    (Normal play followed by reversed play)
    """
    print("[Video Engine] Criando loop reverso (ping-pong)...")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", "[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0[v]",
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    print("[Video Engine] Ping-pong criado com sucesso.")

def render_episode(video_path, audio_path, output_path, duration=3600):
    """
    Renders the final 1-hour video by looping a short video back-and-forth (ping-pong)
    and looping the background audio.
    """
    print(f"[Video Engine] Inciando renderização. Duração: {duration}s")
    print(f"  - Vídeo base: {video_path}")
    print(f"  - Áudio base: {audio_path}")
    print(f"  - Saída: {output_path}")

    # Ensure processing directory exists
    os.makedirs("workspace/processamento", exist_ok=True)
    temp_pingpong = "workspace/processamento/temp_pingpong.mp4"
    
    try:
        # Step 1: Create ping-pong video
        create_ping_pong_video(video_path, temp_pingpong)
        
        # Step 2: Loop the ping-pong and merge audio
        print("[Video Engine] Renderizando vídeo final de 1 hora...")
        cmd_final = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", temp_pingpong,
            "-stream_loop", "-1",
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration),
            "-shortest", # in case we want to stop exactly at duration
            output_path
        ]
        
        # In a real environment, you might want to stream output to capture progress.
        # Here we wait for it to finish.
        subprocess.run(cmd_final, check=True)
        print(f"[Video Engine] Concluído! Arquivo salvo em: {output_path}")
        
    except subprocess.CalledProcessError as e:
        print(f"[Video Engine] Erro durante a renderização: {e}")
        raise
    finally:
        # Cleanup temp file
        if os.path.exists(temp_pingpong):
            os.remove(temp_pingpong)
            print("[Video Engine] Limpeza de arquivos temporários concluída.")

if __name__ == "__main__":
    # Test script if executed standalone
    v_test = "workspace/videos_raw/test_video.mp4"
    a_test = "assets/musicas/test_audio.mp3"
    out_test = "output/test_obsidian_ep.mp4"
    
    if os.path.exists(v_test) and os.path.exists(a_test):
        # Para testes, renderizando apenas 60 segundos
        render_episode(v_test, a_test, out_test, duration=60)
    else:
        print("Para testar este módulo, forneça arquivos 'test_video.mp4' e 'test_audio.mp3' nas pastas corretas.")

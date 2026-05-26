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

def render_episode(video_path, audio_path, output_path, duration=3600, progress_callback=None, cancel_check=None):
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
    temp_final = output_path + ".tmp.mp4"
    
    try:
        # Step 1: Create ping-pong video
        if cancel_check and cancel_check():
            raise InterruptedError("Cancelado pelo usuário antes do ping-pong.")
            
        create_ping_pong_video(video_path, temp_pingpong)
        
        if cancel_check and cancel_check():
            raise InterruptedError("Cancelado pelo usuário após o ping-pong.")
            
        # Step 2: Loop the ping-pong and merge audio
        print("[Video Engine] Renderizando vídeo final de 1 hora...")
        cmd_final = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", temp_pingpong,
            "-stream_loop", "-1",
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration),
            "-shortest", # in case we want to stop exactly at duration
            temp_final
        ]
        
        import re
        process = subprocess.Popen(
            cmd_final,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8"
        )
        
        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        
        for line in process.stdout:
            if cancel_check and cancel_check():
                process.kill()
                raise InterruptedError("Processo FFmpeg cancelado pelo usuário.")
                
            # print(line, end="") # opcional: descomente para debug de log do ffmpeg
            match = time_pattern.search(line)
            if match and progress_callback:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                current_time = hours * 3600 + minutes * 60 + seconds
                
                percentage = (current_time / float(duration)) * 100
                progress_callback(min(99.9, percentage))
                
        process.wait()
        
        if process.returncode != 0 and process.returncode != -9: # -9 é SIGKILL
            raise subprocess.CalledProcessError(process.returncode, cmd_final)
            
        # Move o arquivo temporário para o destino final (evita acesso incompleto do uvicorn)
        if os.path.exists(temp_final) and not (cancel_check and cancel_check()):
            os.replace(temp_final, output_path)
            print(f"[Video Engine] Concluído! Arquivo salvo em: {output_path}")
        else:
            if os.path.exists(temp_final):
                os.remove(temp_final)
            print("[Video Engine] Cancelado antes de salvar.")
            
    except Exception as e:
        print(f"[Video Engine] Erro ou cancelamento durante a renderização: {e}")
        raise
    finally:
        # Cleanup temp file
        if os.path.exists(temp_pingpong):
            try:
                os.remove(temp_pingpong)
                print("[Video Engine] Limpeza de arquivos temporários concluída.")
            except:
                pass


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

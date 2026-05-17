import os
from pathlib import Path
from core.r2_storage import get_r2_client, R2_BUCKET

def migrate():
    client = get_r2_client()
    if not client:
        print("Erro: Credenciais R2 não configuradas.")
        return

    # Mapeamento: diretório local -> prefixo no R2
    folders_to_migrate = {
        "workspace/imagens_raw": "imagens_raw",
        "workspace/videos_raw": "videos_raw",
        "output": "output",
        "assets/musicas": "assets/musicas"
    }

    base_dir = Path(__file__).parent
    total_files = 0
    total_size = 0

    for local_folder, r2_prefix in folders_to_migrate.items():
        folder_path = base_dir / local_folder
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"Ignorando {local_folder} (não encontrado)")
            continue
            
        print(f"\n--- Migrando {local_folder} ---")
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(folder_path)
                r2_key = f"{r2_prefix}/{rel_path.as_posix()}"
                size = file_path.stat().st_size
                
                print(f"Fazendo upload de {file_path.name} ({round(size/1024/1024, 2)} MB) -> r2://{R2_BUCKET}/{r2_key}...")
                try:
                    client.upload_file(str(file_path), R2_BUCKET, r2_key)
                    total_files += 1
                    total_size += size
                    print(f" -> Sucesso!")
                    # Deletando arquivo local para liberar espaço como combinado
                    os.remove(file_path)
                except Exception as e:
                    print(f" -> Erro: {e}")

    print(f"\nMigração concluída! Foram migrados {total_files} arquivos (Total: {round(total_size/1024/1024, 2)} MB).")
    print("Os arquivos locais foram removidos para liberar espaço na sua máquina.")

if __name__ == "__main__":
    migrate()

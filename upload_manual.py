import sys
import os
from core.r2_storage import upload_file

def main():
    if len(sys.argv) < 2:
        print("Uso: python upload_manual.py <caminho_do_arquivo> [caminho_no_r2]")
        print("Exemplo: python upload_manual.py output/obsidian_ep_016.mp4")
        sys.exit(1)

    local_path = sys.argv[1]
    
    if not os.path.exists(local_path):
        print(f"Erro: O arquivo '{local_path}' não foi encontrado.")
        sys.exit(1)
        
    # Se o caminho no R2 não for fornecido, usa o mesmo caminho local (ex: output/arquivo.mp4)
    s3_key = sys.argv[2] if len(sys.argv) > 2 else local_path
    
    # Substitui barras invertidas por barras normais para o S3
    s3_key = s3_key.replace('\\', '/')
    
    # Remove o prefixo './' que causa o erro SignatureDoesNotMatch no boto3/Cloudflare R2
    if s3_key.startswith('./'):
        s3_key = s3_key[2:]

    print(f"Iniciando upload de '{local_path}' para o R2 como '{s3_key}'...")
    print("Isso pode demorar alguns minutos dependendo do tamanho do arquivo.")
    
    sucesso = upload_file(local_path, s3_key)
    
    if sucesso:
        print("Upload concluído com sucesso!")
    else:
        print("Falha no upload.")

if __name__ == "__main__":
    main()

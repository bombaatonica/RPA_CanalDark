import os
import random
import requests
from dotenv import load_dotenv

# Carrega o .env
load_dotenv()

FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY")

def baixar_audio_dark_ambient():
    """
    Busca um áudio de 'dark ambient drone' no Freesound que seja Domínio Público (CC0)
    e baixa o arquivo mp3 aleatoriamente entre os melhores resultados.
    """
    if not FREESOUND_API_KEY:
        print("[Erro] Chave FREESOUND_API_KEY nao encontrada no .env!")
        return None

    print("[Info] Buscando audios sombrios sem direitos autorais no Freesound...")
    
    url = "https://freesound.org/apiv2/search/text/"
    
    # Parâmetros da busca
    params = {
        "query": "dark ambient drone creepy",
        "filter": 'license:"Creative Commons 0"', # CC0 = Sem Copyright, Domínio Público
        "fields": "id,name,previews,duration",
        "token": FREESOUND_API_KEY,
        "page_size": 20 # Pega os 20 primeiros pra gente escolher um aleatório
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"[Erro] API do Freesound: {response.text}")
        return None
        
    dados = response.json()
    resultados = dados.get("results", [])
    
    if not resultados:
        print("[Erro] Nenhum audio encontrado!")
        return None
        
    # Escolhe um áudio aleatório da lista para seus vídeos não ficarem todos com o mesmo fundo
    audio_escolhido = random.choice(resultados)
    
    nome_audio = audio_escolhido['name']
    link_mp3 = audio_escolhido['previews']['preview-hq-mp3']
    
    print(f"[Info] Audio escolhido: {nome_audio}")
    print(f"[Info] Baixando arquivo mp3...")
    
    # Baixa o arquivo MP3
    resposta_mp3 = requests.get(link_mp3)
    
    if resposta_mp3.status_code == 200:
        nome_arquivo = "fundo_sombrio_freesound.mp3"
        with open(nome_arquivo, "wb") as f:
            f.write(resposta_mp3.content)
        print(f"[Sucesso] Salvo como {nome_arquivo}")
        return nome_arquivo
    else:
        print("[Erro] Falha ao baixar o arquivo MP3.")
        return None

if __name__ == "__main__":
    baixar_audio_dark_ambient()

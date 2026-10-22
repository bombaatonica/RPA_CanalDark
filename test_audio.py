import os
import time
import requests
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_API_KEY")

# API do modelo (estamos usando o small por ser mais leve e rápido pra API grátis)
API_URL = "https://api-inference.huggingface.co/models/facebook/musicgen-small"

headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

def generate_audio(prompt, output_filename="dark_ambient.wav"):
    print(f"Gerando áudio para: '{prompt}'...")
    print("Isso pode demorar alguns segundos. Se for a primeira vez do dia, o modelo pode estar 'dormindo' e demorar até 1 minuto para acordar...")
    
    payload = {
        "inputs": prompt,
    }
    
    # O servidor grátis pode retornar status 503 enquanto o modelo "liga" pela primeira vez.
    # Por isso, fazemos um loop tentando algumas vezes.
    for attempt in range(5):
        response = requests.post(API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            with open(output_filename, "wb") as f:
                f.write(response.content)
            print(f"✅ Sucesso absoluto! Áudio salvo como: {output_filename}")
            return True
        elif response.status_code == 503:
            print("O modelo está carregando nos servidores da Hugging Face. Aguardando 15 segundos...")
            time.sleep(15)
        else:
            print(f"❌ Erro da API: {response.status_code} - {response.text}")
            return False
            
    print("❌ Falha após várias tentativas. O servidor grátis pode estar sobrecarregado no momento.")
    return False

if __name__ == "__main__":
    # Prompt clássico pra canal dark
    meu_prompt = "dark ambient drone, scary, low frequency, horror movie background, continuous"
    
    generate_audio(meu_prompt, "fundo_sombrio.wav")

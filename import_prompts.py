import json
import os
import re

def main():
    prompts_file = 'Prompts.txt'
    metadata_file = 'metadados.json'
    
    if not os.path.exists(prompts_file):
        print(f"Erro: {prompts_file} nao encontrado.")
        return
        
    with open(prompts_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Extrair apenas o Bloco 1 (que vai ate o Bloco 2)
    block_1 = content.split("🔥 BLOCO 2")[0]
    
    suffix = "ultra detailed, cinematic lighting, volumetric fog, moody shadows, hyper realistic, dark fantasy atmosphere, 8k, masterpiece --ar 16:9"
    
    lines = block_1.split('\n')
    prompts = []
    
    for line in lines:
        line = line.strip()
        # Ignorar linhas vazias, headers com emojis ou instrucoes
        if not line or any(line.startswith(c) for c in ['🔥', '🏰', '🍺', '🌲', '⛪', '⚔️']):
            continue
        lower_line = line.lower()
        if lower_line.startswith('a regra') or lower_line.startswith('sempre gerar') or \
           lower_line.startswith('qualidade') or lower_line.startswith('estilo') or \
           lower_line.startswith('use sempre'):
            continue
        if line == suffix:
            continue
            
        # Limpar reticências e adicionar
        line = line.replace('...', '').strip()
        if len(line) > 10:
            prompts.append(line)
            
    # Carregar metadados existentes
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        metadata = {}
        
    # Manter os episodios que ja existem (ex: ep_001, ep_002)
    # e comecar a adicionar do ep_003 em diante
    start_ep = len(metadata) + 1
    
    for i, p in enumerate(prompts):
        ep_id = f"ep_{start_ep + i:03d}"
        full_prompt = f"{p}, {suffix}"
        
        # Gerar um título provisório a partir do prompt (pega a primeira parte antes da virgula)
        title_base = p.split(',')[0].title() if ',' in p else p.title()
        
        metadata[ep_id] = {
            "titulo": f"{title_base} - Dark Ambient Focus",
            "descricao": "Step Into The Shadows... Um reino esquecido. Fantasy ambience, medieval sleep music, RPG background, reading ambience, deep focus.",
            "prompt_imagem": full_prompt,
            "prompt_animacao": "Heavy rain falling outside, dynamic particles, subtle glow",
            "arquivo_audio": "assets/musicas/Ecco2k - Don't Ask.mp3"
        }
        
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        
    print(f"Sucesso! {len(prompts)} prompts importados para {metadata_file}.")

if __name__ == "__main__":
    main()

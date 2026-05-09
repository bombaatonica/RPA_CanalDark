import json
import os

def check_and_create_dirs():
    """Ensure that the necessary directories exist."""
    directories = [
        "assets/musicas",
        "workspace/imagens_raw",
        "workspace/videos_raw",
        "workspace/processamento",
        "output"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"[Config Loader] Checked directory: {directory}")

def load_metadata(episode_id):
    """Load metadata for a given episode ID."""
    try:
        with open('metadados.json', 'r', encoding='utf-8') as f:
            database = json.load(f)
            
        if episode_id not in database:
            raise ValueError(f"Episode ID '{episode_id}' not found in metadados.json")
            
        print(f"[Config Loader] Loaded metadata for: {episode_id}")
        return database[episode_id]
    except FileNotFoundError:
        print("[Config Loader] Error: metadados.json not found!")
        raise
    except json.JSONDecodeError:
        print("[Config Loader] Error: metadados.json is not a valid JSON!")
        raise

def initialize(episode_id):
    """Initialize configuration and return metadata."""
    check_and_create_dirs()
    return load_metadata(episode_id)

if __name__ == "__main__":
    # Test execution
    data = initialize("ep_001")
    print(json.dumps(data, indent=2, ensure_ascii=False))

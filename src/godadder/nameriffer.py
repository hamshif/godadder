import sqlite3
import requests
import pandas as pd
import requests


import os
import sys

if getattr(sys, 'frozen', False):
    # Support for PyInstaller or similar
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    try:
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

DB_FILE = os.path.join(SCRIPT_DIR, "domains.db")

def get_latest_domain():
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query(
            "SELECT name FROM domains WHERE conceived IS NOT NULL ORDER BY conceived DESC LIMIT 1",
            conn
        )
        if df.empty:
            raise Exception("No domains found in DB.")
        return df.iloc[0]['name']

def ollama_riff(model, base_domain, n=5, system_prompt=None):
    ollama_url = "http://localhost:11434/api/generate"
    prompt = f"Suggest {n} creative, catchy domain names inspired by '{base_domain}', but different. Output as a plain list, one per line."
    if system_prompt:
        prompt = system_prompt.format(base=base_domain, n=n)
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(ollama_url, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        output = data.get("response", "")
        return [line.strip("- ").strip() for line in output.strip().splitlines() if line.strip()]
    except requests.exceptions.Timeout:
        print("Ollama timed out.")
        return []
    except Exception as e:
        print("Ollama error:", e)
        return []

def warmup_model(model):
    url = "http://localhost:11434/api/generate"
    body = {
        "model": model,
        "prompt": "Ready?",
        "stream": False
    }
    try:
        print(f"Warming up model {model} ...")
        resp = requests.post(url, json=body, timeout=120)
        resp.raise_for_status()
        print(f"Model {model} is loaded.")
    except Exception as e:
        print(f"Warm-up failed for {model}:", e)


if __name__ == "__main__":
    # List models you want loaded in RAM
    for model in ["llama3.3:latest"]:
        warmup_model(model)
        
    ollama_model = "llama3.3:latest"
    # ollama_model = "deepseek-r1:latest"
    num_suggestions = 8

    latest = get_latest_domain()
    print(f"Latest domain: {latest}")

    suggestions = ollama_riff(ollama_model, latest, n=num_suggestions)
    print("\nOllama suggestions:")
    for s in suggestions:
        print(s)
        
        

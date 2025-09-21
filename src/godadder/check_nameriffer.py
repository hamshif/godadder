#!/usr/bin/env python


from godadder.nameriffer import *

if __name__ == "__main__":

    # List models you want loaded in RAM
    for model in ["llama3.3:latest"]:
        warmup_model(model)
        
    ollama_model = "llama3.3:latest"
    # ollama_model = "deepseek-r1:latest"
    num_suggestions = 3

    latest = get_latest_domain()
    print(f"Latest domain: {latest}")

    suggestions = ollama_riff(ollama_model, latest, n=num_suggestions)
    print("\nOllama suggestions:")
    for s in suggestions:
        print(s)
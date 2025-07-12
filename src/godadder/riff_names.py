#!/usr/bin/env python


from godadder.godadder_helper import *
from godadder.nameriffer import get_latest_domain, warmup_model, ollama_riff
from godadder.util import get_app_config
    
if __name__ == "__main__":

    app_conf = get_app_config()
    
    check_domains = ["magniv.ai", "uncomplexify.ai", "fantabulous.ai", "navhopper.ai", "falafel.com", "humanize.ai", "humanizer.ai"]
    investigate_domains(app_conf, check_domains)

    print("\n--- All domains (as table) ---")
    df_all = select_domains()
    print(df_all)

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

    investigate_domains(app_conf, check_domains=suggestions)
#!/usr/bin/env python


from godadder.godadder_helper import *
from godadder.nameriffer import get_latest_domain, warmup_model, ollama_riff
from godadder.util import get_app_config

import subprocess
import time
import atexit
import requests

# Global variable to hold the server process
ollama_process = None

def manage_ollama_server():
    """
    Checks if the Ollama server is running. If not, it starts the server 
    in a background process and registers a function to terminate it when 
    the script exits.
    """
    global ollama_process
    
    # 1. Check if the server is already accessible
    try:
        requests.get("http://localhost:11434")
        print("✅ Ollama server is already running.")
        return
    except requests.exceptions.ConnectionError:
        print("Ollama server not found. Starting it now...")

    # 2. Start the server as a background process
    try:
        # Use Popen to run the command in the background
        # stdout and stderr are piped to avoid printing to the console
        ollama_process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print("🚀 Starting Ollama server...")

        # 3. Register the cleanup function to run at script exit
        atexit.register(stop_ollama_server)

        # 4. Wait a few seconds for the server to initialize
        print("Waiting for Ollama server to be ready...")
        time.sleep(5)  # Adjust sleep time if needed
        print("✅ Ollama server is ready.")

    except FileNotFoundError:
        print("🛑 Error: 'ollama' command not found.")
        print("Please ensure Ollama is installed and in your system's PATH.")
        exit() # Exit the script if Ollama can't be started
    except Exception as e:
        print(f"🛑 An unexpected error occurred while starting Ollama: {e}")
        exit()

def stop_ollama_server():
    """Stops the Ollama server process if it was started by this script."""
    global ollama_process
    if ollama_process:
        print("\nShutting down Ollama server...")
        ollama_process.terminate() # Send termination signal
        ollama_process.wait()    # Wait for the process to terminate
        print("✅ Ollama server has been shut down.")
    
if __name__ == "__main__":
    
    app_conf = get_app_config()

    manage_ollama_server()

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

    # stop_ollama_server()

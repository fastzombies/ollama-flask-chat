#!/usr/bin/env python3

from flask import Flask, request
from jinja2 import Environment, FileSystemLoader
import ollama
import markdown
from pathlib import Path
import json
import logging
import sys
import os

# Get version
app_root    = os.path.dirname(os.path.abspath(__file__))
app_version = os.path.join(app_root, '.version')
with open(app_version, 'r') as f:
    __version__ = f.read().strip()

# Set up logging to stdout
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.handlers = []
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
l = logger

app = Flask(__name__)

# Default Ollama configuration from environment variable
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost:11434")

# Chat history directory
CHAT_DIR = Path.home() / ".ollama-flask-chat"
CHAT_DIR.mkdir(exist_ok=True)

# Set up Jinja2 environment
template_dir = Path(__file__).parent / "templates"
l.debug(f"Template directory set to: {template_dir}")
jj_env = Environment(loader=FileSystemLoader(template_dir))

def get_ollama_models(client):
    try:
        models = client.list()
        l.debug(f"Raw models response: {models}")
        model_list = models.models
        l.debug(f"Extracted model list: {model_list}")
        if not model_list:
            l.debug("Models list is empty")
            return ["No models available"]
        names = []
        for model in model_list:
            if hasattr(model, 'model'):
                names.append(model.model)
            else:
                l.debug(f"Skipping invalid model entry: {model}")
        l.debug(f"Final model names: {names}")
        return names if names else ["No valid models found"]
    except Exception as e:
        l.debug(f"Exception in get_ollama_models: {str(e)}")
        return ["Error fetching models: " + str(e)]

def save_chat_history(model, history):
    history_file = CHAT_DIR / f"{model.replace(':', '_')}.json"
    with open(history_file, 'w') as f:
        json.dump(history, f)
    l.debug(f"Saved chat history for model {model}: {history}")

def load_chat_history(model):
    history_file = CHAT_DIR / f"{model.replace(':', '_')}.json"
    if history_file.exists():
        with open(history_file, 'r') as f:
            history = json.load(f)
            l.debug(f"Loaded chat history for model {model}: {history}")
            return history
    l.debug(f"No chat history found for model {model}, returning empty list")
    return []

@app.route('/', methods=['GET', 'POST'])
def chat():
    l.debug(f"Received {request.method} request")
    
    # Get current configuration from form or use OLLAMA_HOST default
    host = request.form.get('host', OLLAMA_HOST)
    model = request.form.get('model', '')
    l.debug(f"Configuration - host: {host}, model: {model}")
    
    # Configure ollama client with error handling
    host_url = f"http://{host}" if not host.startswith("http://") else host
    try:
        client = ollama.Client(host=host_url)
        l.debug(f"Ollama client configured for {host_url}")
    except Exception as e:
        l.error(f"Failed to initialize Ollama client: {str(e)}")
        models = ["Error: Could not connect to Ollama"]
        model = "No models available"
        chat_history = []
        l.debug("Rendering template with error state due to client failure")
        jj_template = jj_env.get_template('chat.html')
        return jj_template.render(
            host=host,
            models=models,
            selected_model=model,
            chat_history=chat_history
        )
    
    # Get available models
    models = get_ollama_models(client)
    if not model and models and "Error" not in models[0]:
        model = models[0]
        l.debug(f"No model selected, using default: {model}")
    elif not model:
        model = "No models available"
        l.debug("No valid models found, setting model to 'No models available'")
    
    # Load chat history for selected model (always defined)
    chat_history = load_chat_history(model) if model != "No models available" else []
    l.debug(f"Initial chat history for {model}: {chat_history}")
    
    if request.method == 'POST' and 'prompt' in request.form:
        prompt = request.form['prompt'].strip()
        l.debug(f"Received prompt: '{prompt}'")
        if prompt:  # Only process non-empty prompts
            try:
                if "Error" not in model and model != "No models available":
                    l.debug(f"Sending prompt to Ollama: model={model}, prompt='{prompt}'")
                    response = client.generate(model=model, prompt=prompt)
                    l.debug(f"Full response from Ollama: {response}")
                    reply = response.get('response', 'No response field in reply')
                    l.debug(f"Extracted reply: '{reply}'")
                    formatted_reply = markdown.markdown(reply)
                    l.debug(f"Formatted reply: '{formatted_reply}'")
                    chat_history.append({"user": prompt, "bot": formatted_reply})
                    l.debug(f"Updated chat history: {chat_history}")
                    save_chat_history(model, chat_history)
                else:
                    chat_history.append({"user": prompt, "bot": "Cannot generate: No valid model selected"})
                    l.debug("No valid model, added error message to history")
            except Exception as e:
                l.error(f"Error during generation: {str(e)}")
                chat_history.append({"user": prompt, "bot": f"Error: {str(e)}"})
                save_chat_history(model, chat_history)
        else:
            l.debug("Empty prompt, reloading chat history for selected model")
            # No prompt, just reload history for the selected model
    
    # Log all variables before rendering
    l.debug("Rendering template with variables:")
    l.debug(f"host: {host}")
    l.debug(f"models: {models}")
    l.debug(f"selected_model: {model}")
    l.debug(f"chat_history: {chat_history}")
    
    # Load and render the template explicitly
    try:
        l.debug("Loading chat.html from templates directory")
        jj_template = jj_env.get_template('chat.html')
        l.debug("Rendering chat.html")
        rendered_html = jj_template.render(
            host=host,
            models=models,
            selected_model=model,
            chat_history=chat_history
        )
        l.debug("chat.html rendered successfully")
        return rendered_html
    except Exception as e:
        l.error(f"Failed to render chat.html: {str(e)}")
        return f"Error rendering template: {str(e)}", 500

if __name__ == '__main__':
    l.debug("Starting Flask application")
    app.run(debug=True, host='0.0.0.0', port=5000)
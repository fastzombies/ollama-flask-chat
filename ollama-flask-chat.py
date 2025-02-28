#!/usr/bin/env python3

import sys
import os
import argparse
import logging
from flask import Flask, request
from jinja2 import Environment, FileSystemLoader
import ollama
import markdown
from pathlib import Path
import json

__author__ = 'github@ryanhoke.net'
__license__ = 'GPL 3.0'
# Get version
app_root    = os.path.dirname(os.path.abspath(__file__))
app_version = os.path.join(app_root, '.version')
with open(app_version, 'r') as f:
    __version__ = f.read().strip()

app = Flask(__name__)

# Default Ollama configuration from environment variable
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost:11434")

# Chat history directory
CHAT_DIR = Path.home() / ".flask_chat"
CHAT_DIR.mkdir(exist_ok=True)

# Set up Jinja2 environment
template_dir = Path(__file__).parent / "templates"
jj_env = Environment(loader=FileSystemLoader(template_dir))

def get_ollama_models(client, logger):
    try:
        models = client.list()
        logger.debug(f"Raw models response: {models}")
        model_list = models.models
        logger.debug(f"Extracted model list: {model_list}")
        if not model_list:
            logger.debug("Models list is empty")
            return ["No models available"]
        names = []
        for model in model_list:
            if hasattr(model, 'model'):
                names.append(model.model)
            else:
                logger.debug(f"Skipping invalid model entry: {model}")
        logger.debug(f"Final model names: {names}")
        return names if names else ["No valid models found"]
    except Exception as e:
        logger.debug(f"Exception in get_ollama_models: {str(e)}")
        return ["Error fetching models: " + str(e)]

def save_chat_history(model, history, logger):
    history_file = CHAT_DIR / f"{model.replace(':', '_')}.json"
    with open(history_file, 'w') as f:
        json.dump(history, f)
    logger.debug(f"Saved chat history for model {model}: {history}")

def load_chat_history(model, logger):
    history_file = CHAT_DIR / f"{model.replace(':', '_')}.json"
    if history_file.exists():
        with open(history_file, 'r') as f:
            history = json.load(f)
            logger.debug(f"Loaded chat history for model {model}: {history}")
            return history
    logger.debug(f"No chat history found for model {model}, returning empty list")
    return []

@app.route('/', methods=['GET', 'POST'])
def chat():
    app.logger.debug(f"Received {request.method} request")
    
    # Get current configuration from form or use OLLAMA_HOST default
    host = request.form.get('host', OLLAMA_HOST)
    model = request.form.get('model', '')
    app.logger.debug(f"Configuration - host: {host}, model: {model}")
    
    # Configure ollama client with error handling
    host_url = f"http://{host}" if not host.startswith("http://") else host
    try:
        client = ollama.Client(host=host_url)
        app.logger.debug(f"Ollama client configured for {host_url}")
    except Exception as e:
        app.logger.error(f"Failed to initialize Ollama client: {str(e)}")
        models = ["Error: Could not connect to Ollama"]
        model = "No models available"
        chat_history = []
        app.logger.debug("Rendering template with error state due to client failure")
        jj_template = jj_env.get_template('chat.html')
        return jj_template.render(
            host=host,
            models=models,
            selected_model=model,
            chat_history=chat_history
        )
    
    # Get available models
    models = get_ollama_models(client, app.logger)
    if not model and models and "Error" not in models[0]:
        model = models[0]
        app.logger.debug(f"No model selected, using default: {model}")
    elif not model:
        model = "No models available"
        app.logger.debug("No valid models found, setting model to 'No models available'")
    
    # Load chat history for selected model (always defined)
    chat_history = load_chat_history(model, app.logger) if model != "No models available" else []
    app.logger.debug(f"Initial chat history for {model}: {chat_history}")
    
    if request.method == 'POST' and 'prompt' in request.form:
        prompt = request.form['prompt'].strip()
        app.logger.debug(f"Received prompt: '{prompt}'")
        if prompt:  # Only process non-empty prompts
            try:
                if "Error" not in model and model != "No models available":
                    app.logger.debug(f"Sending prompt to Ollama: model={model}, prompt='{prompt}'")
                    response = client.generate(model=model, prompt=prompt)
                    app.logger.debug(f"Full response from Ollama: {response}")
                    reply = response.get('response', 'No response field in reply')
                    app.logger.debug(f"Extracted reply: '{reply}'")
                    formatted_reply = markdown.markdown(reply)
                    app.logger.debug(f"Formatted reply: '{formatted_reply}'")
                    chat_history.append({"user": prompt, "bot": formatted_reply})
                    app.logger.debug(f"Updated chat history: {chat_history}")
                    save_chat_history(model, chat_history, app.logger)
                else:
                    chat_history.append({"user": prompt, "bot": "Cannot generate: No valid model selected"})
                    app.logger.debug("No valid model, added error message to history")
            except Exception as e:
                app.logger.error(f"Error during generation: {str(e)}")
                chat_history.append({"user": prompt, "bot": f"Error: {str(e)}"})
                save_chat_history(model, chat_history, app.logger)
        else:
            app.logger.debug("Empty prompt, reloading chat history for selected model")
            # No prompt, just reload history for the selected model
    
    # Log all variables before rendering
    app.logger.debug("Rendering template with variables:")
    app.logger.debug(f"host: {host}")
    app.logger.debug(f"models: {models}")
    app.logger.debug(f"selected_model: {model}")
    app.logger.debug(f"chat_history: {chat_history}")
    
    # Load and render the template explicitly
    try:
        app.logger.debug("Loading chat.html from templates directory")
        jj_template = jj_env.get_template('chat.html')
        app.logger.debug("Rendering chat.html")
        rendered_html = jj_template.render(
            host=host,
            models=models,
            selected_model=model,
            chat_history=chat_history
        )
        app.logger.debug("chat.html rendered successfully")
        return rendered_html
    except Exception as e:
        app.logger.error(f"Failed to render chat.html: {str(e)}")
        return f"Error rendering template: {str(e)}", 500

def main(args):
    app.logger.debug("Starting Flask application")
    app.run(debug=True, host='0.0.0.0', port=args.port)

if __name__ == "__main__":
    """ This is executed when run from the command line """
    
    description = """
    A simple Flask-based chat application interfacing with Ollama.
    """
    
    epilog = """
    GPL 3.0 License.
    """
    
    parser = argparse.ArgumentParser(description=description,
                                    epilog=epilog,
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # Optional verbosity counter (eg. -v, -vv, -vvv, etc.)
    parser.add_argument('-v', '--verbose',
                        action="count",
                        default=0,
                        help="Verbosity (-v, -vv, etc)")
    
    # Optional port argument
    parser.add_argument('-p', '--port',
                        action="store",
                        type=int,
                        default=5000,
                        help="Port to run the Flask app on")
    
    args = parser.parse_args()
    
    # Set up logging
    l = logging.getLogger()  # Root logger per your convention
    fmtdebug = logging.Formatter('%(levelname)s: [%(funcName)s():%(lineno)i] %(message)s')
    fmtinfo = logging.Formatter('%(levelname)s: %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    
    if args.verbose > 0:
        handler.setFormatter(fmtdebug)
        l.addHandler(handler)
        l.setLevel(logging.DEBUG)
        print(f'verbose = {args.verbose}')
    else:
        handler.setFormatter(fmtinfo)
        l.addHandler(handler)
        l.setLevel(logging.INFO)
    
    # Configure Flask app logger to use the same setup
    app.logger.handlers = []
    app.logger.addHandler(handler)
    app.logger.setLevel(l.level)
    
    main(args)
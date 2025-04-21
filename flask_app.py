#!/usr/bin/env python3
"""
Prover9-Mace4 Web GUI - Flask Integration
Allows running the app with Flask's development server or other WSGI servers
"""

import os
from flask import Flask, render_template_string, send_from_directory
from pywebio.platform.flask import webio_view
from waitress import serve

# Import the PyWebIO app
from web_app import prover9_mace4_app

# Create Flask app
app = Flask(__name__)

# Register the PyWebIO application
app.add_url_rule('/tool', 'webio_view', webio_view(prover9_mace4_app), methods=['GET', 'POST', 'OPTIONS'])

# Root route to redirect to the PyWebIO app
@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prover9-Mace4 Web UI</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background-color: #f5f5f5;
            }
            .container {
                text-align: center;
                padding: 2rem;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            h1 {
                color: #333;
            }
            .button {
                display: inline-block;
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                margin: 20px 0;
                border-radius: 4px;
                text-decoration: none;
                font-weight: bold;
            }
            .button:hover {
                background-color: #45a049;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Prover9-Mace4 Web UI</h1>
            <p>A modern browser-based interface for Prover9 and Mace4</p>
            <a href="/tool" class="button">Launch Application</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

# Serve static files
@app.route('/saved/<path:path>')
def send_saved(path):
    return send_from_directory('saved', path)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Prover9-Mace4 Web GUI - Flask Integration')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    parser.add_argument('--production', action='store_true', help='Run in production mode with Waitress')
    args = parser.parse_args()
    
    # Create saved directory if it doesn't exist
    os.makedirs('saved', exist_ok=True)
    
    if args.production:
        print(f"Running in production mode on http://localhost:{args.port}")
        print("Press Ctrl+C to quit")
        serve(app, host='0.0.0.0', port=args.port)
    else:
        print(f"Running in {'debug' if args.debug else 'development'} mode on http://localhost:{args.port}")
        print("Press Ctrl+C to quit")
        app.run(host='0.0.0.0', port=args.port, debug=args.debug) 
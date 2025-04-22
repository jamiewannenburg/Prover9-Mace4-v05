#!/usr/bin/env python3
"""
Prover9-Mace4 Web GUI - Flask Integration
Allows running the app with Flask's development server or other WSGI servers
"""

import os
from flask import Flask, render_template_string, send_from_directory
import argparse
from pywebio.platform.flask import webio_view
from waitress import serve

# Import the main application from web_app.py
from web_app import prover9_mace4_app, PROGRAM_NAME

# Create Flask app
app = Flask(__name__)

# Add PyWebIO route
app.add_url_rule('/', 'webio_view', webio_view(prover9_mace4_app), methods=['GET', 'POST', 'OPTIONS'])

# Add favicon route
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'Images'),
        'p9.ico', 
        mimetype='image/png'
    )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI (Flask)')
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
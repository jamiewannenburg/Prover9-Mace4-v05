#!/usr/bin/env python3
"""
Prover9-Mace4 Web GUI
A PyWebIO-based web interface for Prover9 and Mace4
"""

import os
import re
import sys
import time
import json
import requests
import argparse
from typing import Dict, List, Optional
from datetime import datetime
from PIL import Image

from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import *
from pywebio import config, start_server
from pywebio.platform.flask import webio_view

# Constants
PROGRAM_NAME = 'Prover9-Mace4'
PROGRAM_VERSION = '0.5 Web'
PROGRAM_DATE = 'May 2023'
BANNER = f'{PROGRAM_NAME} Version {PROGRAM_VERSION}, {PROGRAM_DATE}'

# API Configuration
API_URL = "http://localhost:8000"  # Default API URL
API_URL_KEY = "prover9_api_url"    # Key for storing API URL in session

# Output formats
PROVER9_FORMATS = [
    {'label': 'Text', 'value': 'text'},
    {'label': 'XML', 'value': 'xml'},
    {'label': 'TeX', 'value': 'tex'}
]

MACE4_FORMATS = [
    {'label': 'Text', 'value': 'text'},
    {'label': 'XML', 'value': 'xml'},
    {'label': 'Portable', 'value': 'portable'},
    {'label': 'Tabular', 'value': 'tabular'},
    {'label': 'Raw', 'value': 'raw'},
    {'label': 'Cooked', 'value': 'cooked'},
    {'label': 'Standard', 'value': 'standard'}
]

# Utility functions
def get_api_url() -> str:
    """Get the API URL from session or use default"""
    if API_URL_KEY in local:
        return local[API_URL_KEY]
    else:
        return API_URL

def set_api_url(url: str) -> None:
    """Set the API URL in session"""
    local[API_URL_KEY] = url

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string"""
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} minutes"
    hours = minutes / 60
    return f"{hours:.1f} hours"

def format_process_info(process: Dict) -> str:
    """Format process information for display"""
    start_time = datetime.fromisoformat(process['start_time'])
    duration = (datetime.now() - start_time).total_seconds()
    
    info = [
        f"Program: {process['program']}",
        f"Status: {process['state']}",
        f"Duration: {format_duration(duration)}"
    ]
    
    if process['stats']:
        stats = process['stats']
        if process['program'] == 'prover9':
            info.extend([
                f"Given: {stats.get('given', '?')}",
                f"Generated: {stats.get('generated', '?')}",
                f"Kept: {stats.get('kept', '?')}",
                f"Proofs: {stats.get('proofs', '?')}",
                f"CPU Time: {stats.get('cpu_time', '?')}s"
            ])
        elif process['program'] == 'mace4':
            info.extend([
                f"Domain Size: {stats.get('domain_size', '?')}",
                f"Models: {stats.get('models', '?')}",
                f"CPU Time: {stats.get('cpu_time', '?')}s"
            ])
        elif process['program'] in ['isofilter', 'isofilter2']:
            info.extend([
                f"Input Models: {stats.get('input_models', '?')}",
                f"Kept Models: {stats.get('kept_models', '?')}",
                f"Removed Models: {stats.get('removed_models', '?')}"
            ])
    
    if process['resource_usage']:
        usage = process['resource_usage']
        info.extend([
            f"CPU: {usage.get('cpu_percent', '?')}%",
            f"Memory: {usage.get('memory_percent', '?')}%"
        ])
    
    return "\n".join(info)

def update_process_list() -> None:
    """Update the process list display"""
    try:
        response = requests.get(f"{get_api_url()}/processes")
        processes = response.json()
        
        with use_scope('process_list', clear=True):
            put_table([
                ['ID', 'Program', 'Status', 'Start Time', 'Actions']
            ])
            
            for process in processes:
                start_time = datetime.fromisoformat(process['start_time'])
                actions = []
                
                if process['state'] in ['running', 'suspended']:
                    if process['state'] == 'running':
                        actions.append(put_button('Pause', onclick=lambda p=process: pause_process(p['pid'])))
                    else:
                        actions.append(put_button('Resume', onclick=lambda p=process: resume_process(p['pid'])))
                    actions.append(put_button('Kill', onclick=lambda p=process: kill_process(p['pid'])))
                
                if process['state'] == 'done' and process['output']:
                    actions.append(put_button('Download', onclick=lambda p=process: download_output(p['pid'])))
                
                put_table([
                    [
                        str(process['pid']),
                        process['program'],
                        process['state'],
                        start_time.strftime('%Y-%m-%d %H:%M:%S'),
                        put_buttons(actions)
                    ]
                ])
    except requests.exceptions.RequestException as e:
        toast(f"Error updating process list: {str(e)}", color='error')

def start_process(program: str, input_text: str, options: Optional[Dict] = None) -> None:
    """Start a new process"""
    try:
        response = requests.post(
            f"{get_api_url()}/start",
            json={
                "program": program,
                "input": input_text,
                "options": options
            }
        )
        if response.status_code == 200:
            toast(f"Started {program} process", color='success')
            update_process_list()
        else:
            toast(f"Error starting process: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error starting process: {str(e)}", color='error')

def kill_process(process_id: int) -> None:
    """Kill a running process"""
    try:
        response = requests.post(f"{get_api_url()}/kill/{process_id}")
        if response.status_code == 200:
            toast("Process killed", color='success')
            update_process_list()
        else:
            toast(f"Error killing process: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error killing process: {str(e)}", color='error')

def pause_process(process_id: int) -> None:
    """Pause a running process"""
    try:
        response = requests.post(f"{get_api_url()}/pause/{process_id}")
        if response.status_code == 200:
            toast("Process paused", color='success')
            update_process_list()
        else:
            toast(f"Error pausing process: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error pausing process: {str(e)}", color='error')

def resume_process(process_id: int) -> None:
    """Resume a paused process"""
    try:
        response = requests.post(f"{get_api_url()}/resume/{process_id}")
        if response.status_code == 200:
            toast("Process resumed", color='success')
            update_process_list()
        else:
            toast(f"Error resuming process: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error resuming process: {str(e)}", color='error')

def download_output(process_id: int) -> None:
    """Download process output"""
    try:
        response = requests.get(f"{get_api_url()}/status/{process_id}")
        if response.status_code == 200:
            process = response.json()
            if process['output']:
                # Determine file extension based on program
                ext = {
                    'prover9': 'proof',
                    'mace4': 'model',
                    'isofilter': 'filtered',
                    'isofilter2': 'filtered2',
                    'interpformat': 'formatted',
                    'prooftrans': 'transformed'
                }.get(process['program'], 'txt')
                
                # Create filename
                filename = f"{process['program']}_{process_id}.{ext}"
                
                # Provide file for download
                put_file(filename, process['output'].encode('utf-8'))
            else:
                toast("No output available", color='warn')
        else:
            toast(f"Error getting process status: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error downloading output: {str(e)}", color='error')

def show_process_details(process_id: int) -> None:
    """Show detailed information about a process"""
    try:
        response = requests.get(f"{get_api_url()}/status/{process_id}")
        if response.status_code == 200:
            process = response.json()
            
            with use_scope('process_details', clear=True):
                put_markdown(f"## Process {process_id} Details")
                put_text(format_process_info(process))
                
                if process['error']:
                    put_markdown("### Error")
                    put_text(process['error'])
                
                if process['output']:
                    put_markdown("### Output")
                    put_text(process['output'])
        else:
            toast(f"Error getting process details: {response.text}", color='error')
    except requests.exceptions.RequestException as e:
        toast(f"Error getting process details: {str(e)}", color='error')

def main():
    """Main application function"""
    # Set page title
    set_env(title=f"{PROGRAM_NAME} Web Interface")
    
    # API URL configuration
    with use_scope('api_config', clear=True):
        put_markdown("## API Configuration")
        api_url = input("API Server URL", type=TEXT, value=get_api_url())
        set_api_url(api_url)
    
    # Main interface
    with use_scope('main', clear=True):
        put_markdown(f"# {BANNER}")
        
        # Process list
        put_markdown("## Active and Completed Runs")
        put_scrollable(put_scope('process_list'), height=300)
        
        # Process details
        put_markdown("## Process Details")
        put_scope('process_details')
        
        # Start new process
        put_markdown("## Start New Process")
        program = select("Program", ['prover9', 'mace4', 'isofilter', 'isofilter2', 'interpformat', 'prooftrans'])
        input_text = textarea("Input", rows=10)
        
        if program in ['prover9', 'mace4']:
            options = None
        elif program in ['isofilter', 'isofilter2']:
            options = {
                'wrap': checkbox("Wrap output in list"),
                'ignore_constants': checkbox("Ignore constants"),
                'check': input("Check operations (comma-separated)"),
                'output': input("Output operations (comma-separated)")
            }
        elif program == 'interpformat':
            options = {
                'format': select("Output format", [
                    'standard', 'standard2', 'portable', 'tabular',
                    'raw', 'cooked', 'tex', 'xml'
                ])
            }
        elif program == 'prooftrans':
            options = {
                'format': select("Output format", [
                    'standard', 'parents_only', 'xml', 'ivy', 'hints'
                ]),
                'expand': checkbox("Expand proof"),
                'renumber': checkbox("Renumber proof"),
                'striplabels': checkbox("Remove labels")
            }
        
        put_button("Start", onclick=lambda: start_process(program, input_text, options))
    
    # Initial update
    update_process_list()
    
    # Periodic updates
    while True:
        time.sleep(1)
        update_process_list()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    parser.add_argument('--production', action='store_true', help='Run in production mode with Waitress')
    args = parser.parse_args()
    
    if args.production:
        print(f"Running in production mode on http://localhost:{args.port}")
        print("Press Ctrl+C to quit")
        serve(app, host='0.0.0.0', port=args.port)
    else:
        print(f"Running in {'debug' if args.debug else 'development'} mode on http://localhost:{args.port}")
        print("Press Ctrl+C to quit")
        start_server(main, port=args.port, debug=args.debug) 
#!/usr/bin/env python3
"""
Prover9-Mace4 Web GUI
A PyWebIO-based web interface for Prover9 and Mace4
"""

import os
import re
import sys
import tempfile
import subprocess
import time
import argparse
import threading
import signal
from functools import partial

from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import *
from pywebio import config, start_server
from pywebio.platform.flask import webio_view
from flask import Flask

# Constants
BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'bin')
SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'Samples')
PROGRAM_NAME = 'Prover9-Mace4'
PROGRAM_VERSION = '0.5 Web'
PROGRAM_DATE = 'May 2023'
BANNER = f'{PROGRAM_NAME} Version {PROGRAM_VERSION}, {PROGRAM_DATE}'

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

# Global process tracking
PROCESS = {
    'prover9': {'process': None, 'running': False, 'killed': False},
    'mace4': {'process': None, 'running': False, 'killed': False}
}

# Prover9 and Mace4 exit codes
PROVER9_EXITS = {
    0: 'Proof',
    1: 'Fatal Error',
    2: 'Exhausted',
    3: 'Memory Limit',
    4: 'Time Limit',
    5: 'Given Limit',
    6: 'Kept Limit',
    7: 'Action Exit',
    101: 'Interrupted',
    102: 'Crashed',
    -9: 'Killed', # Linux, Mac
    -1: 'Killed' # Win32
}

MACE4_EXITS = {
    0: 'Model Found',
    1: 'Fatal Error',
    2: 'Domain Too Small',
    3: 'Memory Limit',
    4: 'Time Limit',
    5: 'Max Models',
    6: 'Domain Size Limit',
    7: 'Action Exit',
    101: 'Interrupted',
    102: 'Crashed',
    -9: 'Killed', # Linux, Mac
    -1: 'Killed' # Win32
}

# Utility functions
def binary_ok(fullpath):
    """Check if binary exists and is executable"""
    return os.path.isfile(fullpath) and os.access(fullpath, os.X_OK)

def run_command(command, input_text='', callback=None):
    """Run a command and return the process object"""
    if isinstance(input_text, str):
        input_text = input_text.encode('utf-8')
    
    fin = tempfile.TemporaryFile('w+b')
    fout = tempfile.TemporaryFile('w+b')
    ferr = tempfile.TemporaryFile('w+b')
    
    if input_text:
        fin.write(input_text)
        fin.seek(0)
    
    process = subprocess.Popen(command, stdin=fin, stdout=fout, stderr=ferr)
    
    return process, fin, fout, ferr

def get_process_output(fout, ferr):
    """Get output from process file handles"""
    fout.seek(0)
    output = fout.read().decode('utf-8', errors='replace')
    
    ferr.seek(0)
    error = ferr.read().decode('utf-8', errors='replace')
    
    return output, error

def list_samples():
    """List sample files in the Samples directory"""
    samples = []
    if os.path.isdir(SAMPLE_DIR):
        for file in os.listdir(SAMPLE_DIR):
            if file.endswith('.in'):
                samples.append(file)
    return sorted(samples)

def read_sample(filename):
    """Read a sample file and return its contents"""
    path = os.path.join(SAMPLE_DIR, filename)
    if os.path.isfile(path):
        with open(path, 'r') as f:
            return f.read()
    return ""

def get_prover9_stats(stdout):
    """Extract statistics from prover9 stdout output"""
    stats = []
    
    # Extract CPU time
    match = re.search(r'User_CPU=(\d*\.\d*)', stdout)
    if match:
        stats.append(('CPU Time', f"{match.group(1)} seconds"))
    else:
        stats.append(('CPU Time', "?"))
    
    # Extract clause counts
    # Look for line like: "Given=67. Generated=519. Kept=169."
    match = re.search(r'Given=(\d+)\.\s+Generated=(\d+)\.\s+Kept=(\d+)', stdout)
    if match:
        stats.append(('Given', match.group(1)))
        stats.append(('Generated', match.group(2)))
        stats.append(('Kept', match.group(3)))
    else:
        stats.append(('Given', "?"))
        stats.append(('Generated', "?"))
        stats.append(('Kept', "?"))
    
    # Extract proof count
    match = re.search(r'proofs=(\d+)', stdout)
    if match:
        stats.append(('Proofs', match.group(1)))
    else:
        stats.append(('Proofs', "?"))
    
    return stats

def get_mace4_stats(stdout):
    """Extract statistics from mace4 stdout output"""
    stats = []
    
    # Extract domain size from the last domain size section
    domain_size_matches = re.findall(r'============================== DOMAIN SIZE (\d+) =========================', stdout)
    if domain_size_matches:
        stats.append(('Domain Size', domain_size_matches[-1]))  # Get the last one
    else:
        stats.append(('Domain Size', "?"))
    
    # Extract model count
    match = re.search(r'Exiting with (\d+) model', stdout)
    if match:
        stats.append(('Models', match.group(1)))
    else:
        stats.append(('Models', "?"))
    
    # Extract CPU time
    match = re.search(r'User_CPU=(\d*\.\d*)', stdout)
    if match:
        stats.append(('CPU Time', f"{match.group(1)} seconds"))
    else:
        stats.append(('CPU Time', "?"))
    
    return stats

# Main application function
@config(theme="dark", title=PROGRAM_NAME)
def prover9_mace4_app():
    """Main application function"""
    
    # Check if Prover9 and Mace4 binaries exist
    prover9_path = os.path.join(BIN_DIR, 'prover9')
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    
    if not binary_ok(prover9_path) or not binary_ok(mace4_path):
        put_error("Error: Prover9 or Mace4 binaries not found or not executable.")
        put_text("Please ensure the binaries are installed in the 'src/bin' directory.")
        return
    
    set_env(output_max_width='90%')
    
    # Header
    put_html(f"<h1 style='text-align:center'>{BANNER}</h1>")
    
    # Create layout with setup and run panels
    put_row([
        put_scope('setup_panel'),
        put_scope('run_panel')
    ], size='70% 30%')
    
    # Populate the panels
    setup_panel()
    run_panel()

def setup_panel():
    """Setup panel with formula input and options"""
    with use_scope('setup_panel', clear=True):
        put_tabs([
            {'title': 'Formulas', 'content': formula_panel()},
            {'title': 'Language Options', 'content': language_options_panel()},
            {'title': 'Prover9 Options', 'content': prover9_options_panel()},
            {'title': 'Mace4 Options', 'content': mace4_options_panel()},
            {'title': 'Additional Input', 'content': additional_input_panel()},
        ])

def formula_panel():
    """Panel for entering assumptions and goals"""
    content = put_column([
        put_row([
            put_button("Load Sample", onclick=load_sample),
            put_button("Load File", onclick=load_file),
            put_button("Save Input", onclick=save_input),
            put_button("Clear", onclick=lambda: [pin_update('assumptions', value=''), pin_update('goals', value='')]),
        ]),
        put_text("Assumptions:"),
        put_textarea('assumptions', rows=15, code={
            'mode': 'prolog',
            'theme': 'monokai'
        }),
        put_text("Goals:"),
        put_textarea('goals', rows=15, code={
            'mode': 'prolog',
            'theme': 'monokai'
        }),
    ], size="10% 5% 40% 5% 40%")
    
    return content

def language_options_panel():
    """Panel for language options"""
    content = put_row([
        put_checkbox('options', options=[
            {'label': 'Auto2', 'value': 'auto2'},
            {'label': 'Equality', 'value': 'equality'},
            {'label': 'Function Style', 'value': 'function_style'}
        ]),
    ])
    
    return content

def prover9_options_panel():
    """Panel for Prover9 options"""
    content = put_row([
        put_column([
            put_text("Basic Options:"),
            put_input('max_seconds', label='Max Seconds', type=NUMBER, value=60),
            put_input('max_megs', label='Max Memory (MB)', type=NUMBER, value=500),
            put_select('search_strategy', label='Search Strategy', options=[
                {'label': 'Auto', 'value': 'auto'},
                {'label': 'Breadth First', 'value': 'breadth_first'},
                {'label': 'Depth First', 'value': 'depth_first'},
                {'label': 'Iterative Depth First', 'value': 'iterative_depth_first'}
            ], value='auto')
        ], size='1/2'),
        put_column([
            put_text("Advanced Options:"),
            put_checkbox('prover_options', options=[
                {'label': 'Build Models', 'value': 'build_models'},
                {'label': 'Print Kept Clauses', 'value': 'print_kept'},
                {'label': 'Print Given Clauses', 'value': 'print_given'}
            ]),
        ], size='1/2')
    ])
    
    return content

def mace4_options_panel():
    """Panel for Mace4 options"""
    content = put_row([
        put_column([
            put_text("Basic Options:"),
            put_input('max_seconds_mace', label='Max Seconds', type=NUMBER, value=60),
            put_input('max_megs_mace', label='Max Memory (MB)', type=NUMBER, value=500),
            put_input('domain_size', label='Start Size', type=NUMBER, value=2),
            put_input('end_size', label='End Size', type=NUMBER, value=10),
            put_input('max_models', label='Max Models', type=NUMBER, value=1)
        ], size='1/2'),
        put_column([
            put_text("Advanced Options:"),
            put_checkbox('mace_options', options=[
                {'label': 'Print Models', 'value': 'print_models'},
                {'label': 'Print Models Portable', 'value': 'print_models_portable'},
                {'label': 'Iterate', 'value': 'iterate'}
            ]),
        ], size='1/2')
    ])
    
    return content

def additional_input_panel():
    """Panel for additional input"""
    content = put_textarea('additional_input', rows=15, placeholder="Additional input for Prover9 or Mace4...", code={
        'mode': 'prolog',
        'theme': 'monokai'
    })
    
    return content

def run_panel():
    """Run panel with controls and output display"""
    with use_scope('run_panel', clear=True):
        put_column([
            put_scope('prover9_run_panel'),
            put_scope('mace4_run_panel')
        ], size='40vh 40vh')
        
        prover9_run_panel()
        mace4_run_panel()

def prover9_run_panel():
    """Run panel for Prover9"""
    with use_scope('prover9_run_panel', clear=True):
        put_column([
            put_row([
                put_button("Start Prover9", onclick=run_prover9, color='primary'),
                put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger'),
                put_button("Save Output", onclick=save_prover9_output, color='success'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="prover9_status" style="color: green;">Idle</span>'),
            ]),
            put_text("Proof Search:"),
            put_scrollable(put_textarea('prover9_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="prover9_stats"></div>')
        ], size='10% 5% 40% 5% 40%')

def mace4_run_panel():
    """Run panel for Mace4"""
    with use_scope('mace4_run_panel', clear=True):
        put_column([
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary'),
                put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger'),
                put_button("Save Output", onclick=save_mace4_output, color='success'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="mace4_status" style="color: green;">Idle</span>'),
            ]),
            put_text("Model Search:"),
            put_scrollable(put_textarea('mace4_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="mace4_stats"></div>')
        ], size='10% 5% 40% 5% 40%')

# Event handlers
def load_sample():
    """Load a sample input file"""
    samples = list_samples()
    if not samples:
        toast("No sample files found")
        return
    
    sample = select("Select a sample file", options=samples)
    content = read_sample(sample)
    
    # Parse the sample to extract assumptions and goals
    assumptions = ""
    goals = ""
    section = None
    
    for line in content.splitlines():
        if "formulas(assumptions)." in line:
            section = "assumptions"
            continue
        elif "formulas(goals)." in line:
            section = "goals"
            continue
        elif "end_of_list." in line:
            section = None
            continue
        
        if section == "assumptions":
            assumptions += line + "\n"
        elif section == "goals":
            goals += line + "\n"
    
    pin_update('assumptions', value=assumptions)
    pin_update('goals', value=goals)

def load_file():
    """Load input from a user-uploaded file"""
    uploaded = file_upload("Select an input file", accept=".in,.txt")
    if not uploaded:
        return
    
    # Read file content
    content = uploaded['content'].decode('utf-8')
    
    # Parse the uploaded file to extract assumptions and goals
    assumptions = ""
    goals = ""
    section = None
    
    for line in content.splitlines():
        if "formulas(assumptions)." in line:
            section = "assumptions"
            continue
        elif "formulas(goals)." in line:
            section = "goals"
            continue
        elif "end_of_list." in line:
            section = None
            continue
        
        if section == "assumptions":
            assumptions += line + "\n"
        elif section == "goals":
            goals += line + "\n"
    
    # Update the text areas
    pin_update('assumptions', value=assumptions)
    pin_update('goals', value=goals)
    
    toast(f"File '{uploaded['filename']}' loaded successfully", color='success')

def save_input():
    """Save the current input to a file"""
    filename = input("Enter filename to save input", placeholder="input.in")
    
    assumptions = pin.assumptions
    goals = pin.goals
    
    content = "formulas(assumptions).\n"
    content += assumptions + "\n"
    content += "end_of_list.\n\n"
    content += "formulas(goals).\n"
    content += goals + "\n"
    content += "end_of_list.\n"
    
    with open(filename, 'w') as f:
        f.write(content)
    
    toast(f"Saved to {filename}")

def generate_input():
    """Generate input for Prover9/Mace4"""
    assumptions = pin.assumptions
    goals = pin.goals
    additional = pin.additional_input if hasattr(pin, 'additional_input') else ""
    
    content = "formulas(assumptions).\n"
    content += assumptions + "\n"
    content += "end_of_list.\n\n"
    content += "formulas(goals).\n"
    content += goals + "\n"
    content += "end_of_list.\n\n"
    content += additional
    
    return content

def run_prover9():
    """Run Prover9"""
    # Prevent starting if already running
    if PROCESS['prover9']['running']:
        toast("Prover9 is already running!", color='warn')
        return
    
    # Update UI to show running state
    pin_update('prover9_output', value="Starting Prover9...\n")
    run_js('document.getElementById("prover9_stats").innerHTML = "Waiting for statistics..."')
    run_js('document.getElementById("prover9_status").textContent = "Running"')
    run_js('document.getElementById("prover9_status").style.color = "orange"')
    
    # Disable start button, enable kill button
    with use_scope('prover9_run_panel'):
        clear('prover9_run_panel')
        put_column([
            put_row([
                put_button("Start Prover9", onclick=run_prover9, color='primary', disabled=True),
                put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger'),
                put_button("Save Output", onclick=save_prover9_output, color='success'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="prover9_status" style="color: orange;">Running</span>'),
            ]),
            put_text("Proof Search:"),
            put_scrollable(put_textarea('prover9_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="prover9_stats">Waiting for statistics...</div>')
        ], size='10% 5% 40% 5% 40%')
    
    # Generate input
    input_text = generate_input()
    
    # Get options
    max_seconds = pin.max_seconds
    max_megs = pin.max_megs
    
    # Build command
    prover9_path = os.path.join(BIN_DIR, 'prover9')
    command = [prover9_path, f"-t{max_seconds}", f"-m{max_megs}"]
    
    # Start the process
    def run_task():
        global PROCESS
        
        # Mark as running
        PROCESS['prover9']['running'] = True
        PROCESS['prover9']['killed'] = False
        
        start_time = time.time()
        process, fin, fout, ferr = run_command(command, input_text)
        PROCESS['prover9']['process'] = process
        
        try:
            # Update status periodically
            while process.poll() is None:
                # Check if killed
                if PROCESS['prover9']['killed']:
                    process.terminate()
                    break
                
                # Get output so far
                output, error = get_process_output(fout, ferr)
                
                # Update output display without recreating the element
                found_proof = "PROOF" in output
                result_header = "## PROOF FOUND ##\n\n" if found_proof else ""
                pin_update('prover9_output', value=f"{result_header}{output}")
                
                if found_proof:
                    run_js('document.getElementById("prover9_status").textContent = "Proof Found"')
                    run_js('document.getElementById("prover9_status").style.color = "green"')
                
                # Update stats display
                stats = get_prover9_stats(output)
                stats_html = '<table style="width:100%"><tbody>'
                for key, value in stats:
                    stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
                stats_html += '</tbody></table>'
                run_js('document.getElementById("prover9_stats").innerHTML = `' + stats_html + '`')
                
                # Sleep briefly to avoid high CPU usage
                time.sleep(0.5)
            
            # Process has finished, get final output
            exit_code = process.poll()
            output, error = get_process_output(fout, ferr)
            duration = time.time() - start_time
            
            # Determine the result status
            if "PROOF" in output:
                status_text = "Proof Found"
                status_color = "green"
                result_header = "## PROOF FOUND ##\n\n"
            else:
                status_text = exit_code in PROVER9_EXITS and PROVER9_EXITS[exit_code] or "Completed"
                status_color = "red"
                result_header = "## NO PROOF FOUND ##\n\n"
            
            # Update output and status
            pin_update('prover9_output', value=f"{result_header}{output}")
            run_js(f'document.getElementById("prover9_status").textContent = "{status_text}"')
            run_js(f'document.getElementById("prover9_status").style.color = "{status_color}"')
            
            # Update stats display
            stats = get_prover9_stats(output)
            stats.append(('Exit Code', f"{exit_code} ({PROVER9_EXITS.get(exit_code, 'Unknown')})"))
            stats.append(('Total Time', f"{duration:.2f} seconds"))
            
            stats_html = '<table style="width:100%"><tbody>'
            for key, value in stats:
                stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
            stats_html += '</tbody></table>'
            run_js('document.getElementById("prover9_stats").innerHTML = `' + stats_html + '`')
            
            # Update button state - enable start, disable kill
            with use_scope('prover9_run_panel'):
                clear('prover9_run_panel')
                put_column([
                    put_row([
                        put_button("Start Prover9", onclick=run_prover9, color='primary'),
                        put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger', disabled=True),
                        put_button("Save Output", onclick=save_prover9_output, color='success'),
                        None,  # Spacer
                        put_text("Status:"),
                        put_html(f'<span id="prover9_status" style="color: {status_color};">{status_text}</span>'),
                    ]),
                    put_text("Proof Search:"),
                    put_scrollable(put_textarea('prover9_output', rows=10, readonly=True, value=f"{result_header}{output}"), height=160),
                    put_text("Statistics:"),
                    put_html(f'<div id="prover9_stats">{stats_html}</div>')
                ], size='10% 5% 40% 5% 40%')
                
        finally:
            # Close file handles
            fin.close()
            fout.close()
            ferr.close()
            
            # Update process state
            PROCESS['prover9']['running'] = False
            PROCESS['prover9']['process'] = None
    
    t = threading.Thread(target=run_task)
    register_thread(t)
    t.start()

def run_mace4():
    """Run Mace4"""
    # Prevent starting if already running
    if PROCESS['mace4']['running']:
        toast("Mace4 is already running!", color='warn')
        return
    
    # Update UI to show running state
    pin_update('mace4_output', value="Starting Mace4...\n")
    run_js('document.getElementById("mace4_stats").innerHTML = "Waiting for statistics..."')
    run_js('document.getElementById("mace4_status").textContent = "Running"')
    run_js('document.getElementById("mace4_status").style.color = "orange"')
    
    # Disable start button, enable kill button
    with use_scope('mace4_run_panel'):
        clear('mace4_run_panel')
        put_column([
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary', disabled=True),
                put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger'),
                put_button("Save Output", onclick=save_mace4_output, color='success'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="mace4_status" style="color: orange;">Running</span>'),
            ]),
            put_text("Model Search:"),
            put_scrollable(put_textarea('mace4_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="mace4_stats">Waiting for statistics...</div>')
        ], size='10% 5% 40% 5% 40%')
    
    # Generate input
    input_text = generate_input()
    
    # Get options
    max_seconds = pin.max_seconds_mace
    max_megs = pin.max_megs_mace
    domain_size = pin.domain_size
    end_size = pin.end_size
    max_models = pin.max_models
    
    # Build command
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    command = [mace4_path, "-c", f"-t{max_seconds}", f"-b{max_megs}", 
              f"-n{domain_size}", f"-N{end_size}", f"-m{max_models}"]
    
    # Start the process
    def run_task():
        global PROCESS
        
        # Mark as running
        PROCESS['mace4']['running'] = True
        PROCESS['mace4']['killed'] = False
        
        start_time = time.time()
        process, fin, fout, ferr = run_command(command, input_text)
        PROCESS['mace4']['process'] = process
        
        try:
            # Update status periodically
            while process.poll() is None:
                # Check if killed
                if PROCESS['mace4']['killed']:
                    process.terminate()
                    break
                
                # Get output so far
                output, error = get_process_output(fout, ferr)
                
                # Update output display without recreating the element
                found_model = "interpretation" in output
                result_header = "## MODEL FOUND ##\n\n" if found_model else ""
                pin_update('mace4_output', value=f"{result_header}{output}")
                
                if found_model:
                    run_js('document.getElementById("mace4_status").textContent = "Model Found"')
                    run_js('document.getElementById("mace4_status").style.color = "green"')
                
                # Update stats display
                stats = get_mace4_stats(output)
                stats_html = '<table style="width:100%"><tbody>'
                for key, value in stats:
                    stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
                stats_html += '</tbody></table>'
                run_js('document.getElementById("mace4_stats").innerHTML = `' + stats_html + '`')
                
                # Sleep briefly to avoid high CPU usage
                time.sleep(0.5)
            
            # Process has finished, get final output
            exit_code = process.poll()
            output, error = get_process_output(fout, ferr)
            duration = time.time() - start_time
            
            # Determine the result status
            if "interpretation" in output:
                status_text = "Model Found"
                status_color = "green"
                result_header = "## MODEL FOUND ##\n\n"
            else:
                status_text = exit_code in MACE4_EXITS and MACE4_EXITS[exit_code] or "Completed"
                status_color = "red"
                result_header = "## NO MODEL FOUND ##\n\n"
            
            # Update output and status
            pin_update('mace4_output', value=f"{result_header}{output}")
            run_js(f'document.getElementById("mace4_status").textContent = "{status_text}"')
            run_js(f'document.getElementById("mace4_status").style.color = "{status_color}"')
            
            # Update stats display
            stats = get_mace4_stats(output)
            stats.append(('Exit Code', f"{exit_code} ({MACE4_EXITS.get(exit_code, 'Unknown')})"))
            stats.append(('Total Time', f"{duration:.2f} seconds"))
            
            stats_html = '<table style="width:100%"><tbody>'
            for key, value in stats:
                stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
            stats_html += '</tbody></table>'
            run_js('document.getElementById("mace4_stats").innerHTML = `' + stats_html + '`')
            
            # Update button state - enable start, disable kill
            with use_scope('mace4_run_panel'):
                clear('mace4_run_panel')
                put_column([
                    put_row([
                        put_button("Start Mace4", onclick=run_mace4, color='primary'),
                        put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger', disabled=True),
                        put_button("Save Output", onclick=save_mace4_output, color='success'),
                        None,  # Spacer
                        put_text("Status:"),
                        put_html(f'<span id="mace4_status" style="color: {status_color};">{status_text}</span>'),
                    ]),
                    put_text("Model Search:"),
                    put_scrollable(put_textarea('mace4_output', rows=10, readonly=True, value=f"{result_header}{output}"), height=160),
                    put_text("Statistics:"),
                    put_html(f'<div id="mace4_stats">{stats_html}</div>')
                ], size='10% 5% 40% 5% 40%')
        finally:
            # Close file handles
            fin.close()
            fout.close()
            ferr.close()
            
            # Update process state
            PROCESS['mace4']['running'] = False
            PROCESS['mace4']['process'] = None
    
    t = threading.Thread(target=run_task)
    register_thread(t)
    t.start()

def kill_process(program):
    """Kill the running process"""
    global PROCESS
    
    if program not in PROCESS:
        toast(f"Unknown program: {program}", color='error')
        return
    
    if not PROCESS[program]['running']:
        toast(f"{program.capitalize()} is not running", color='warn')
        return
    
    # Mark as killed
    PROCESS[program]['killed'] = True
    
    # Send termination signal
    process = PROCESS[program]['process']
    if process:
        try:
            # Send signal to terminate
            if hasattr(signal, 'SIGTERM'):
                process.send_signal(signal.SIGTERM)
            else:
                process.terminate()
            
            toast(f"{program.capitalize()} process terminated", color='success')
        except:
            toast(f"Failed to terminate {program} process", color='error')
    else:
        toast(f"No {program} process to kill", color='warn')

def save_prover9_output():
    """Save Prover9 output in the selected format"""
    output = pin.prover9_output
    if not output:
        toast("No output to save", color='warn')
        return
    
    format_value = select("Select output format", options=PROVER9_FORMATS)
    filename = input("Enter filename", placeholder="prover9_output.txt")
    
    if not filename:
        filename = "prover9_output.txt"
    
    try:
        if format_value == 'text':
            # Save as plain text
            content = output
        else:
            # Process with prooftrans
            prooftrans_path = os.path.join(BIN_DIR, 'prooftrans')
            if not binary_ok(prooftrans_path):
                toast("prooftrans binary not found or not executable", color='error')
                return
            
            result = subprocess.run(
                [prooftrans_path, format_value],
                input=output.encode('utf-8'),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                toast(f"Error converting output: {result.stderr}", color='error')
                return
            
            content = result.stdout
        
        # Ensure content is bytes
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        # Provide the file for download
        put_file(filename, content)
        toast(f"Output saved as {filename}", color='success')
        
    except Exception as e:
        toast(f"Error saving output: {str(e)}", color='error')

def save_mace4_output():
    """Save Mace4 output in the selected format"""
    output = pin.mace4_output
    if not output:
        toast("No output to save", color='warn')
        return
    
    format_value = select("Select output format", options=MACE4_FORMATS)
    
    # Add checkbox for removing isomorphic copies
    remove_isomorphic = checkbox("Options", options=[
        {'label': 'Remove isomorphic copies', 'value': 'remove_iso'}
    ])
    
    filename = input("Enter filename", placeholder="mace4_output.txt")
    
    if not filename:
        filename = "mace4_output.txt"
    
    try:
        # Make sure output is a string to start with
        if isinstance(output, bytes):
            output = output.decode('utf-8')
        
        # Remove any decorative headers we might have added for display
        # Strip out the "## MODEL FOUND ##" or similar headers
        if output.startswith("## MODEL FOUND ##"):
            output = output.replace("## MODEL FOUND ##\n\n", "", 1)
        elif output.startswith("## NO MODEL FOUND ##"):
            output = output.replace("## NO MODEL FOUND ##\n\n", "", 1)
        
        # For isofilter, we need to extract just the interpretation sections
        if 'remove_iso' in remove_isomorphic and format_value != 'text':
            # Parse out only the model parts of the output
            model_sections = []
            
            # Find all interpretation sections
            interpretation_matches = re.finditer(r'(interpretation\(\s*\d+,\s*\[\s*.*?\s*\]\s*\)\s*\.)', output, re.DOTALL)
            
            for match in interpretation_matches:
                model_sections.append(match.group(1))
            
            if model_sections:
                # Combine all models
                models_only = "\n".join(model_sections)
                toast(f"Found {len(model_sections)} model sections to filter", color='info')
                # Use this for isofilter
                processed_output = models_only
            else:
                # No models found
                toast("No model interpretations found in the output", color='warn')
                # Use raw output, but this might fail with isofilter
                processed_output = output
        else:
            # For text format or no filtering, use full output
            processed_output = output
        
        if format_value == 'text':
            # Save as plain text
            content = output  # Use original output for text, not the model-only version
        else:
            # Check for required binaries
            interpformat_path = os.path.join(BIN_DIR, 'interpformat')
            if not binary_ok(interpformat_path):
                toast("interpformat binary not found or not executable", color='error')
                return
            
            # Filter isomorphic models if requested
            if 'remove_iso' in remove_isomorphic:
                isofilter_path = os.path.join(BIN_DIR, 'isofilter')
                if not binary_ok(isofilter_path):
                    toast("isofilter binary not found or not executable", color='error')
                    return
                
                # Ensure we're passing string input as bytes to subprocess
                input_bytes = processed_output.encode('utf-8')
                
                # Run isofilter first
                isofilter_result = subprocess.run(
                    [isofilter_path],
                    input=input_bytes,
                    capture_output=True
                )
                
                if isofilter_result.returncode != 0:
                    stderr = isofilter_result.stderr
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode('utf-8')
                    toast(f"Error filtering isomorphic models: {stderr}", color='error')
                    return
                
                # Output from isofilter is in bytes
                processed_output = isofilter_result.stdout
                
                # Convert back to string for next step
                if isinstance(processed_output, bytes):
                    processed_output = processed_output.decode('utf-8')
            
            # Then run interpformat
            # Ensure we're passing string input as bytes to subprocess
            input_bytes = processed_output.encode('utf-8')
            
            interpformat_result = subprocess.run(
                [interpformat_path, format_value],
                input=input_bytes,
                capture_output=True
            )
            
            if interpformat_result.returncode != 0:
                stderr = interpformat_result.stderr
                if isinstance(stderr, bytes):
                    stderr = stderr.decode('utf-8')
                toast(f"Error converting output: {stderr}", color='error')
                return
            
            # Output from interpformat is in bytes
            content = interpformat_result.stdout
        
        # Always ensure content is bytes before putting file
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        # Provide the file for download
        put_file(filename, content)
        toast(f"Output saved as {filename}", color='success')
        
    except Exception as e:
        toast(f"Error saving output: {str(e)}", color='error')

# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    start_server(prover9_mace4_app, port=args.port, debug=args.debug) 
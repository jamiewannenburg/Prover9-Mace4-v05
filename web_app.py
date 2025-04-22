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

def get_prover9_stats(stderr):
    """Extract statistics from prover9 stderr output"""
    stats = []
    
    # Extract CPU time
    match = re.search(r'User_CPU=(\d*\.\d*)', stderr)
    if match:
        stats.append(('CPU Time', f"{match.group(1)} seconds"))
    else:
        stats.append(('CPU Time', "?"))
    
    # Extract clause counts
    match = re.search(r'Given=(\d+)\. Generated=(\d+)\. Kept=(\d+)', stderr)
    if match:
        stats.append(('Given', match.group(1)))
        stats.append(('Generated', match.group(2)))
        stats.append(('Kept', match.group(3)))
    else:
        stats.append(('Given', "?"))
        stats.append(('Generated', "?"))
        stats.append(('Kept', "?"))
    
    # Extract proof count
    match = re.search(r'proofs=(\d+)', stderr)
    if match:
        stats.append(('Proofs', match.group(1)))
    else:
        stats.append(('Proofs', "?"))
    
    return stats

def get_mace4_stats(stderr):
    """Extract statistics from mace4 stderr output"""
    stats = []
    
    # Extract domain size
    match = re.search(r'Domain_size=(\d+)', stderr)
    if match:
        stats.append(('Domain Size', match.group(1)))
    else:
        stats.append(('Domain Size', "?"))
    
    # Extract model count
    match = re.search(r'Models=(\d+)', stderr)
    if match:
        stats.append(('Models', match.group(1)))
    else:
        stats.append(('Models', "?"))
    
    # Extract CPU time
    match = re.search(r'User_CPU=(\d*\.\d*)', stderr)
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
        setup_panel(),
        run_panel()
    ],size='70% 30%')

def setup_panel():
    """Setup panel with formula input and options"""
    return put_tabs([
        {'title': 'Formulas', 'content': formula_panel()},
        {'title': 'Language Options', 'content': language_options_panel()},
        {'title': 'Prover9 Options', 'content': prover9_options_panel()},
        {'title': 'Mace4 Options', 'content': mace4_options_panel()},
        {'title': 'Additional Input', 'content': additional_input_panel()},
    ])

def formula_panel():
    """Panel for entering assumptions and goals"""
    put_scope('formula_panel')
    
    with use_scope('formula_panel', clear=True):
        return put_column([
            put_row([
                put_button("Load Sample", onclick=load_sample),
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
        ],size="10% 5% 40%  5% 40%")

def language_options_panel():
    """Panel for language options"""
    put_scope('language_options_panel')
    
    with use_scope('language_options_panel', clear=True):
        return put_row([
            put_checkbox('options', options=[
                {'label': 'Auto2', 'value': 'auto2'},
                {'label': 'Equality', 'value': 'equality'},
                {'label': 'Function Style', 'value': 'function_style'}
            ]),
        ])

def prover9_options_panel():
    """Panel for Prover9 options"""
    put_scope('prover9_options_panel')
    
    with use_scope('prover9_options_panel', clear=True):
        return put_row([
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

def mace4_options_panel():
    """Panel for Mace4 options"""
    put_scope('mace4_options_panel')
    
    with use_scope('mace4_options_panel', clear=True):
        return put_row([
            put_column([
                put_text("Basic Options:"),
                put_input('max_seconds_mace', label='Max Seconds', type=NUMBER, value=60),
                put_input('max_megs_mace', label='Max Memory (MB)', type=NUMBER, value=500),
                put_input('domain_size', label='Start Size', type=NUMBER, value=2),
                put_input('end_size', label='End Size', type=NUMBER, value=10)
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

def additional_input_panel():
    """Panel for additional input"""
    put_scope('additional_input_panel')
    
    with use_scope('additional_input_panel', clear=True):
        return put_textarea('additional_input', rows=15, placeholder="Additional input for Prover9 or Mace4...", code={
            'mode': 'prolog',
            'theme': 'monokai'
        })

def run_panel():
    """Run panel with controls and output display"""
    put_scope('run_panel')
    
    with use_scope('run_panel', clear=True):
        # Create tabs for Prover9 and Mace4
        return put_column([
            prover9_run_panel(), #TODO add label
            mace4_run_panel() #TODO add label
        ],size='40vh 40vh')

def prover9_run_panel():
    """Run panel for Prover9"""
    put_scope('prover9_run')
    
    with use_scope('prover9_run', clear=True):
        return put_column([
            put_row([
                put_button("Start Prover9", onclick=run_prover9, color='primary'),
                put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="prover9_status" style="color: green;">Idle</span>'),
            ]),
            put_text("Proof Search:"),
            put_scrollable(put_textarea('prover9_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="prover9_stats"></div>')
        ],size='10% 5% 40%  5% 40%')

def mace4_run_panel():
    """Run panel for Mace4"""
    put_scope('mace4_run')
    
    with use_scope('mace4_run', clear=True):
        return put_column([
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary'),
                put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="mace4_status" style="color: green;">Idle</span>'),
            ]),
            put_text("Model Search:"),
            put_scrollable(put_textarea('mace4_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="mace4_stats"></div>')
        ],size='10% 5% 40%  5% 40%')

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
    with use_scope('prover9_run'):
        clear('prover9_run')
        put_column([
            put_row([
                put_button("Start Prover9", onclick=run_prover9, color='primary', disabled=True),
                put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="prover9_status" style="color: orange;">Running</span>'),
            ]),
            put_text("Proof Search:"),
            put_scrollable(put_textarea('prover9_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="prover9_stats">Waiting for statistics...</div>')
        ],size='10% 5% 40%  5% 40%')
    
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
                stats = get_prover9_stats(error)
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
            stats = get_prover9_stats(error)
            stats.append(('Exit Code', f"{exit_code} ({PROVER9_EXITS.get(exit_code, 'Unknown')})"))
            stats.append(('Total Time', f"{duration:.2f} seconds"))
            
            stats_html = '<table style="width:100%"><tbody>'
            for key, value in stats:
                stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
            stats_html += '</tbody></table>'
            run_js('document.getElementById("prover9_stats").innerHTML = `' + stats_html + '`')
            
            # Update button state - enable start, disable kill
            with use_scope('prover9_run'):
                clear('prover9_run')
                put_column([
                    put_row([
                        put_button("Start Prover9", onclick=run_prover9, color='primary'),
                        put_button("Kill", onclick=lambda: kill_process('prover9'), color='danger', disabled=True),
                        None,  # Spacer
                        put_text("Status:"),
                        put_html(f'<span id="prover9_status" style="color: {status_color};">{status_text}</span>'),
                    ]),
                    put_text("Proof Search:"),
                    put_scrollable(put_textarea('prover9_output', rows=10, readonly=True, value=f"{result_header}{output}"), height=160),
                    put_text("Statistics:"),
                    put_html(f'<div id="prover9_stats">{stats_html}</div>')
                ],size='10% 5% 40%  5% 40%')
                
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
    with use_scope('mace4_run'):
        clear('mace4_run')
        put_column([
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary', disabled=True),
                put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_html('<span id="mace4_status" style="color: orange;">Running</span>'),
            ]),
            put_text("Model Search:"),
            put_scrollable(put_textarea('mace4_output', rows=10, readonly=True), height=160),
            put_text("Statistics:"),
            put_html('<div id="mace4_stats">Waiting for statistics...</div>')
        ],size='10% 5% 40%  5% 40%')
    
    # Generate input
    input_text = generate_input()
    
    # Get options
    max_seconds = pin.max_seconds_mace
    max_megs = pin.max_megs_mace
    domain_size = pin.domain_size
    end_size = pin.end_size
    
    # Build command
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    command = [mace4_path, f"-t{max_seconds}", f"-m{max_megs}", 
              f"-n{domain_size}", f"-N{end_size}"]
    
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
                stats = get_mace4_stats(error)
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
            stats = get_mace4_stats(error)
            stats.append(('Exit Code', f"{exit_code} ({MACE4_EXITS.get(exit_code, 'Unknown')})"))
            stats.append(('Total Time', f"{duration:.2f} seconds"))
            
            stats_html = '<table style="width:100%"><tbody>'
            for key, value in stats:
                stats_html += f'<tr><td>{key}</td><td>{value}</td></tr>'
            stats_html += '</tbody></table>'
            run_js('document.getElementById("mace4_stats").innerHTML = `' + stats_html + '`')
            
            # Update button state - enable start, disable kill
            with use_scope('mace4_run'):
                clear('mace4_run')
                put_column([
                    put_row([
                        put_button("Start Mace4", onclick=run_mace4, color='primary'),
                        put_button("Kill", onclick=lambda: kill_process('mace4'), color='danger', disabled=True),
                        None,  # Spacer
                        put_text("Status:"),
                        put_html(f'<span id="mace4_status" style="color: {status_color};">{status_text}</span>'),
                    ]),
                    put_text("Model Search:"),
                    put_scrollable(put_textarea('mace4_output', rows=10, readonly=True, value=f"{result_header}{output}"), height=160),
                    put_text("Statistics:"),
                    put_html(f'<div id="mace4_stats">{stats_html}</div>')
                ],size='10% 5% 40%  5% 40%')
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

# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    start_server(prover9_mace4_app, port=args.port, debug=args.debug) 
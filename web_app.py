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

# Utility functions
def binary_ok(fullpath):
    """Check if binary exists and is executable"""
    return os.path.isfile(fullpath) and os.access(fullpath, os.X_OK)

def run_command(command, input_text=''):
    """Run a command and return the output"""
    if isinstance(input_text, str):
        input_text = input_text.encode('utf-8')
    
    with tempfile.TemporaryFile('w+b') as fin, \
         tempfile.TemporaryFile('w+b') as fout, \
         tempfile.TemporaryFile('w+b') as ferr:
        
        if input_text:
            fin.write(input_text)
            fin.seek(0)
        
        process = subprocess.Popen(command, stdin=fin, stdout=fout, stderr=ferr)
        exit_code = process.wait()
        
        fout.seek(0)
        output = fout.read().decode('utf-8', errors='replace')
        
        ferr.seek(0)
        error = ferr.read().decode('utf-8', errors='replace')
        
    return exit_code, output, error

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
    # TODO to change the favicon
    # image_url="https://accerun.com/wp-content/uploads/2021/03/512px.png"
    # session.run_js("""
    # $('#favicon32,#favicon16').remove(); 
    # $('head').append('<link rel="icon" type="image/png" href="%s">')
    # """ % image_url)
    # Header
    # TODO to change the header to image
    put_html(f"<h1 style='text-align:center'>{BANNER}</h1>")
    
    # Create tabs for setup and run panels
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
                put_button("Clear", onclick=lambda: [pin_update('assumptions', ''), pin_update('goals', '')]),
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
                put_button("Kill", onclick=kill_process, color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_text("Idle").style('color: green'),
            ]),
            put_text("Proof Search:"),
            put_scrollable(put_scope('prover9_output'), height=160),
            put_text("Statistics:"),
            put_scope('prover9_stats')
        ],size='10% 5% 40%  5% 40%')

def mace4_run_panel():
    """Run panel for Mace4"""
    put_scope('mace4_run')
    
    with use_scope('mace4_run', clear=True):
        return put_column([
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary'),
                put_button("Kill", onclick=kill_process, color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_text("Idle").style('color: green'),
            ]),
            put_text("Model Search:"),
            put_scrollable(put_scope('mace4_output'), height=160),
            put_text("Statistics:"),
            put_scope('mace4_stats')
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
    
    pin_update('assumptions', assumptions)
    pin_update('goals', goals)

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
    with use_scope('prover9_output', clear=True):
        put_loading()
        put_text("Starting Prover9...")
    
    with use_scope('prover9_run'):
        # Update status
        clear('prover9_run')
        put_row([
            put_button("Start Prover9", onclick=run_prover9, color='primary', disabled=True),
            put_button("Kill", onclick=kill_process, color='danger'),
            None,  # Spacer
            put_text("Status:"),
            put_text("Running").style('color: orange'),
        ])
    
    # Generate input
    input_text = generate_input()
    
    # Get options
    max_seconds = pin.max_seconds
    max_megs = pin.max_megs
    
    # Build command
    prover9_path = os.path.join(BIN_DIR, 'prover9')
    command = [prover9_path, f"-t {max_seconds}", f"-m {max_megs}"]
    
    # Run asynchronously
    def run_task():
        start_time = time.time()
        exit_code, output, error = run_command(command, input_text)
        duration = time.time() - start_time
        
        # Display output
        with use_scope('prover9_output', clear=True):
            if "PROOF" in output:
                put_markdown("## PROOF FOUND").style('color: green')
            else:
                put_markdown("## NO PROOF FOUND").style('color: red')
            
            put_code(output, language='prolog')
        
        # Display stats
        with use_scope('prover9_stats', clear=True):
            put_table([
                ['CPU Time', f"{duration:.2f} seconds"],
                ['Exit Code', str(exit_code)],
                ['Memory Used', f"{max_megs} MB"]
            ])
        
        # Update status
        with use_scope('prover9_run'):
            clear('prover9_run')
            put_row([
                put_button("Start Prover9", onclick=run_prover9, color='primary'),
                put_button("Kill", onclick=kill_process, color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_text("Completed").style('color: green'),
            ])
    
    run_async(run_task)

def run_mace4():
    """Run Mace4"""
    with use_scope('mace4_output', clear=True):
        put_loading()
        put_text("Starting Mace4...")
    
    with use_scope('mace4_run'):
        # Update status
        clear('mace4_run')
        put_row([
            put_button("Start Mace4", onclick=run_mace4, color='primary', disabled=True),
            put_button("Kill", onclick=kill_process, color='danger'),
            None,  # Spacer
            put_text("Status:"),
            put_text("Running").style('color: orange'),
        ])
    
    # Generate input
    input_text = generate_input()
    
    # Get options
    max_seconds = pin.max_seconds_mace
    max_megs = pin.max_megs_mace
    domain_size = pin.domain_size
    end_size = pin.end_size
    
    # Build command
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    command = [mace4_path, f"-t {max_seconds}", f"-m {max_megs}", 
              f"-n {domain_size}", f"-N {end_size}"]
    
    # Run asynchronously
    def run_task():
        start_time = time.time()
        exit_code, output, error = run_command(command, input_text)
        duration = time.time() - start_time
        
        # Display output
        with use_scope('mace4_output', clear=True):
            if "Model" in output:
                put_markdown("## MODEL FOUND").style('color: green')
            else:
                put_markdown("## NO MODEL FOUND").style('color: red')
            
            put_code(output, language='prolog')
        
        # Display stats
        with use_scope('mace4_stats', clear=True):
            put_table([
                ['CPU Time', f"{duration:.2f} seconds"],
                ['Exit Code', str(exit_code)],
                ['Memory Used', f"{max_megs} MB"]
            ])
        
        # Update status
        with use_scope('mace4_run'):
            clear('mace4_run')
            put_row([
                put_button("Start Mace4", onclick=run_mace4, color='primary'),
                put_button("Kill", onclick=kill_process, color='danger'),
                None,  # Spacer
                put_text("Status:"),
                put_text("Completed").style('color: green'),
            ])
    
    run_async(run_task)

def kill_process():
    """Kill the running process"""
    toast("Killing process...")
    # We would need to keep track of the process ID to kill it properly
    # For now, this is a placeholder

# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    start_server(prover9_mace4_app, port=args.port, debug=args.debug) 
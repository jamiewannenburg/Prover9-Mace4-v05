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
from PIL import Image
import pyparsing as pp
from pyparsing import (
    Word, alphas, alphanums, Literal, Group, Optional, 
    OneOrMore, ZeroOrMore, ParseException, restOfLine,
    QuotedString, delimitedList, ParseResults, Regex, Keyword, OneOrMore, printables
)

from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import *
from pywebio.session import get_info
from pywebio import config, start_server
from pywebio.platform.flask import webio_view

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

def list_samples():
    """List sample files in the Samples directory"""
    samples = []
    if os.path.isdir(SAMPLE_DIR):
        # recursively list all .in files in the Samples directory
        for root, dirs, files in os.walk(SAMPLE_DIR):
            for file in files:
                if file.endswith('.in'):
                    samples.append(os.path.join(root, file))
    return sorted(samples)

def read_sample(filename):
    """Read a sample file and return its contents"""
    path = os.path.join(SAMPLE_DIR, filename)
    if os.path.isfile(path):
        with open(path, 'r') as f:
            return f.read()
    return ""

# Main application function
@config(theme="yeti", title=PROGRAM_NAME)
def prover9_mace4_app():
    """Main application function"""
    
    #TODO change for fastapi backend
    # Check if Prover9 and Mace4 binaries exist
    prover9_path = os.path.join(BIN_DIR, 'prover9')
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    
    if not binary_ok(prover9_path) or not binary_ok(mace4_path):
        put_error("Error: Prover9 or Mace4 binaries not found or not executable.")
        put_text("Please ensure the binaries are installed in the 'src/bin' directory.")
        return
    
    set_env(output_max_width='90%')

    # Create layout with setup and run panels
    put_row([
        put_scope('setup_panel'),
        put_scope('run_panel')
    ], size='70% 30%')
    
    # Populate the panels
    setup_panel()
    run_panel()

    # Set favicon using JavaScript - only when running under Flask
    if info.backend == 'flask':
        image_url = "/favicon.ico"
        run_js("""
        $('#favicon32,#favicon16').remove(); 
        $('head').append('<link rel="icon" type="image/png" href="%s">')
        """ % image_url)
    

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
            #'theme': 'monokai'
        }),
        put_text("Goals:"),
        put_textarea('goals', rows=15, code={
            'mode': 'prolog',
            #'theme': 'monokai'
        }),
    ], size="10% 5% 40% 5% 40%")
    
    return content

def language_options_panel():
    """Panel for language options"""
    content = put_row([
        put_checkbox('language_flags', options=[
            {'label': 'Prolog-Style Variables', 'value': 'prolog_style_variables'}
        ]),
        put_text("Language Options:"),
        put_textarea('language_options', rows=15, code={
            'mode': 'prolog',
            #'theme': 'monokai'
        }),
    ])
    
    return content

PROVER9_PARAMS = [
    'prover9_max_seconds',
    'prover9_max_weight',
    'prover9_pick_given_ratio',
    'prover9_order',
    'prover9_eq_defs',
]

PROVER9_FLAGS = [
    'expand_relational_defs',
    'restrict_denials',
]

def prover9_options_panel():
    """Panel for Prover9 options"""
    content = put_row([
        put_column([
            put_text("Basic Options:"),
            put_input('prover9_max_seconds', label='Max Seconds', type=NUMBER, value=120),
            put_input('prover9_max_weight', label='Max Weight', type=NUMBER, value=100),
            put_input('prover9_pick_given_ratio', label='Pick Given Ratio', type=NUMBER, value=-1),
            put_select('prover9_order', label='Order', options=['lpo','rpo','kb'], value='lpo'),
            put_select('prover9_eq_defs', label='Equality Defs', options=['unfold','fold','pass'], value='unfold'),
            put_checkbox('prover9_flags', label='Prover9 Flags', options=['expand_relational_defs','restrict_denials'], value=False),
        ], size='1/2'),
        # TODO Advanced Options, to many for now
    ])
    
    return content

MACE4_PARAMS = [
    'mace4_max_seconds',
    'mace4_start_size',
    'mace4_end_size',
    'mace4_max_models',
    'mace4_max_seconds_per_model',
    'mace4_increment',
    'mace4_iterate',
]

MACE4_FLAGS = [
]

def mace4_options_panel():
    """Panel for Mace4 options"""
    content = put_row([
        put_column([
            put_text("Basic Options:"),
            put_input('mace4_max_seconds', label='Max Seconds', type=NUMBER, value=60),
            put_input('mace4_start_size', label='Start Size', type=NUMBER, value=2),
            put_input('mace4_end_size', label='End Size', type=NUMBER, value=10),
            put_input('mace4_max_models', label='Max Models', type=NUMBER, value=1),
            put_input('mace4_max_seconds_per_model', label='Max Seconds Per Model', type=NUMBER, value=-1),
            put_input('mace4_increment', label='Increment', type=NUMBER, value=1),
            put_select('mace4_iterate', label='Iterate', options=['all','evens','odds','primes','nonprimes'], value='all'),

        ]),
        # put_column([
        #     put_text("Experimental Options:"),
        #     put_checkbox('mace4_experimental_flags', options=[
        #         'lnh','negprop','neg_assign','neg_assign_near','neg_elim','neg_elim_near'
        #     ],value=True),
        #     put_input('mace4_selection_order', label='Selection Order', type=NUMBER, value=2),
        #     put_input('mace4_selection_measure', label='Selection Measure', type=NUMBER, value=4),
        # ]),
        # put_column([
        #     put_text("Other Options:"),
        #     put_input('mace4_max_megs', label='Max Memory (MB)', type=NUMBER, value=200),
        #     put_checkbox('mace4_other_flags', label='Other Mace4 Options', options=['integer_ring','skolems_last','print_models'], value=False),
        # ]),
        
    ])
    
    return content

def additional_input_panel():
    """Panel for additional input"""
    content = put_textarea('additional_input', rows=15, placeholder="Additional input for Prover9 or Mace4...", code={
        'mode': 'prolog',
        #'theme': 'monokai'
    })
    
    return content

def run_panel():
    """Run panel with controls and output display"""
    with use_scope('run_panel', clear=True):
        put_column([
            put_image(Image.open('src/Images/prover9-5a-128t.gif'), format='gif', title=BANNER),
            put_button("Start", onclick=run_prover9, color='primary'),
            None,
            put_image(Image.open('src/Images/mace4-90t.gif'), format='gif', title=BANNER),
            put_button("Start", onclick=run_mace4, color='primary'),

        ])
        

def parse_file(content):
    """Parse the input file to extract assumptions, goals, and options using pyparsing"""
    # Define basic tokens
    period = Literal(".")
    identifier = Word(alphanums+"_")
    quoted_string = QuotedString('"', escChar='\\')
    
    # Define comment
    comment = Group(Literal("%") + restOfLine)
    
    # Define option patterns
    set_option = Group(Literal("set")+ Literal("(").suppress() + (identifier | quoted_string) + Literal(")").suppress() + period)+Optional(comment)
    clear_option = Group(Literal("clear")+ Literal("(").suppress() + (identifier | quoted_string) + Literal(")").suppress() + period)+Optional(comment)
    assign_option = Group(Literal("assign")+ Literal("(").suppress() + (identifier | quoted_string) + Literal(",").suppress() + (Word(alphanums+"_"+'-') | quoted_string) + Literal(")").suppress() + period)+Optional(comment)
    language_option = Group(Literal("op")+ Literal("(").suppress() + (identifier | quoted_string) + ZeroOrMore(Literal(",").suppress() + (Word(alphanums+"_"+'-') | quoted_string)) + Literal(")").suppress() + period)+Optional(comment)

    # Define section markers
    formulas_assumptions = Group(Literal("formulas(assumptions)") + period)+Optional(comment)
    formulas_goals = Group(Literal("formulas(goals)") + period)+Optional(comment)
    end_of_list = Group(Literal("end_of_list") + period)+Optional(comment)
    
    # Define program blocks
    if_prover9 = Group(Literal("if(Prover9)") + period)+Optional(comment)
    if_mace4 = Group(Literal("if(Mace4)") + period)+Optional(comment)
    end_if = Group(Literal("end_if") + period)+Optional(comment)
    
    # Define formula (anything ending with period, excluding comments and special markers)
    formula =  Group(~(end_of_list)+Word(printables)+restOfLine) #| if_prover9 | if_mace4 | end_if formulas_assumptions | formulas_goals |
    
    # Define sections
    assumptions_section = formulas_assumptions + ZeroOrMore(formula, stop_on=end_of_list) + end_of_list
    goals_section = formulas_goals + ZeroOrMore(formula, stop_on=end_of_list) + end_of_list
    
    # Define program blocks
    prover9_block = if_prover9 + ZeroOrMore(set_option | assign_option | clear_option) + end_if
    mace4_block = if_mace4 + ZeroOrMore(set_option | assign_option | clear_option) + end_if
    
    # Define global options
    global_options = ZeroOrMore(set_option | assign_option | clear_option)
    
    # Define the complete grammar 
    grammar = Optional(ZeroOrMore(comment)) + Optional(global_options) + Optional(ZeroOrMore(comment)) + Optional(ZeroOrMore(language_option)) + Optional(ZeroOrMore(comment)) + Optional(prover9_block) + Optional(ZeroOrMore(comment)) + Optional(mace4_block) + Optional(ZeroOrMore(comment)) + Optional(assumptions_section) + Optional(ZeroOrMore(comment)) + Optional(goals_section)
    
    # TODO: leave room for additional input

    # Parse the content
    try:
        result = grammar.parseString(content)
    except ParseException as e:
        print(f"Parse error: {e}")
        toast("Parse error: " + str(e), color='danger')
        return {
            'assumptions': '',
            'goals': '',
            'prover9_options': set(),
            'mace4_options': set(),
            'global_options': set(),
            'global_assigns': {},
            'language_options': set(),
            'prover9_assigns': {},
            'mace4_assigns': {}
        }
    
    # Initialize result containers
    parsed = {
        'assumptions': '',
        'goals': '',
        'prover9_options': set(),
        'mace4_options': set(),
        'language_options': set(),
        'global_options': set(),
        'global_assigns': {},
        'prover9_assigns': {},
        'mace4_assigns': {}
    }
    
    # Process the parsed results
    current_section = None
    current_program = None
    
    for item in result:
        if item[0] == "formulas(assumptions)":
            current_section = "assumptions"
        elif item[0] == "formulas(goals)":
            current_section = "goals"
        elif item[0] == "end_of_list":
            current_section = None
        elif item[0] == "if(Prover9)":
            current_program = "prover9"
        elif item[0] == "if(Mace4)":
            current_program = "mace4"
        elif item[0] == "end_if":
            current_program = None
        elif item[0] == "set":
            option = item[1]
            if current_program == "prover9":
                parsed['prover9_options'].add((option, True))
            elif current_program == "mace4":
                parsed['mace4_options'].add((option, True))
            else:
                parsed['global_options'].add((option, True))
        elif item[0] == "clear":
            option = item[1]
            if current_program == "prover9":
                parsed['prover9_options'].add((option, False))
            elif current_program == "mace4":
                parsed['mace4_options'].add((option, False))
            else:
                parsed['global_options'].add((option, False))
        elif item[0] == "assign":
            option_name = item[1]
            option_value = item[2]
            if current_program == "prover9":
                parsed['prover9_assigns'][option_name] = option_value
            elif current_program == "mace4":
                parsed['mace4_assigns'][option_name] = option_value
            else:
                parsed['global_assigns'][option_name] = option_value
        elif item[0] == "op":
            parsed['language_options'].add(item[1:])
        elif current_section == "assumptions":
            # concatenate the item list to a string
            parsed['assumptions'] += ''.join(item)+'\n'
        elif current_section == "goals":
            parsed['goals'] += ''.join(item)+'\n'
    return parsed

def update_options(parsed):
    # Update the text areas
    pin_update('assumptions', value=parsed['assumptions'])
    pin_update('goals', value=parsed['goals'])


    # Update language options
    language_input = ""
    for item in parsed['language_options']:
        language_input += "op(" + ', '.join(item) + ").\n"
    pin_update('language_options', value=language_input)

    additional_input = ""
    
    # Update global options
    for name in parsed['global_assigns']:
        if name == "domain_size":
            pin_update('mace4_start_size', value=int(parsed['global_assigns'][name]))
            pin_update('mace4_end_size', value=int(parsed['global_assigns'][name]))
        else:
            additional_input += f"assign({name}, {parsed['global_assigns'][name]}).\n"
    for name, value in parsed['global_options']:
        if name == "prolog_style_variables":
            if value:
                pin_update('language_flags', value=['prolog_style_variables'])
            else:
                pin_update('language_flags', value=[])
        else:
            if value:
                additional_input += f"set({name}).\n"
            else:
                additional_input += f"clear({name}).\n"

    # Update Prover9 assignments
    additional_input += "if(Prover9).\n"
    for name in parsed['prover9_assigns']:
        if 'prover9_'+name in PROVER9_PARAMS:
            try:
                pin_update('prover9_'+name, value=int(parsed['prover9_assigns'][name]))
            except ValueError:
                pin_update('prover9_'+name, value=parsed['prover9_assigns'][name])
            # TODO: see how pin_update fails
            # additional_input += f"assign({name}, {parsed['prover9_assigns'][name]}).\n"
        else:
            additional_input += f"assign({name}, {parsed['prover9_assigns'][name]}).\n"
    # Update Prover9 options
    p9_opt_list = []
    for name, value in parsed['prover9_options']:
        if name in PROVER9_FLAGS:
            if value:
                p9_opt_list.append(name)
        else:
            if value:
                additional_input += f"set({name}).\n"
            else:
                additional_input += f"clear({name}).\n"
    pin_update('prover9_flags', value=p9_opt_list)
    additional_input += "end_if.\n"
    # Update Mace4 options
    additional_input += "if(Mace4).\n"
    for name in parsed['mace4_assigns']:
        if 'mace4_'+name in MACE4_PARAMS:
            try:
                pin_update('mace4_'+name, value=int(parsed['mace4_assigns'][name]))
            except ValueError:
                pin_update('mace4_'+name, value=parsed['mace4_assigns'][name])
            # TODO: see how pin_update fails
            # additional_input += f"assign({name}, {parsed['mace4_assigns'][name]}).\n"
        else:
            additional_input += f"assign({name}, {parsed['mace4_assigns'][name]}).\n"
    additional_input += "end_if.\n"
    # update mace4 options
    mace4_opt_list = []
    for name, value in parsed['mace4_options']:
        if name in MACE4_FLAGS:
            if value:
                mace4_opt_list.append(name)
        else:
            if value:
                additional_input += f"set({name}).\n"
            else:
                additional_input += f"clear({name}).\n"
    #pin_update('mace4_flags', value=mace4_opt_list) #TODO not defined
    
    # update additional input
    pin_update('additional_input', value=additional_input)

# Event handlers
def load_sample():
    """Load a sample input file"""
    samples = list_samples()
    if not samples:
        toast("No sample files found")
        return
    
    sample = select("Select a sample file", options=samples)
    content = read_sample(sample)
    
    # Parse the sample to extract assumptions, goals, and options
    parsed = parse_file(content)
    update_options(parsed)
    toast(f"File '{sample}' loaded successfully", color='success')

def load_file():
    """Load input from a user-uploaded file"""
    uploaded = file_upload("Select an input file", accept=".in,.txt")
    if not uploaded:
        return
    
    # Read file content
    content = uploaded['content'].decode('utf-8')
    
    # Parse the uploaded file to extract assumptions, goals, and options
    parsed = parse_file(content)
    
    # Parse the sample to extract assumptions, goals, and options
    parsed = parse_file(content)
    update_options(parsed)
    toast(f"File '{uploaded['filename']}' loaded successfully", color='success')
    

def save_input():
    """Save the current input to a file"""
    filename = input("Enter filename to save input", placeholder="input.in")
    if not filename:
        filename = "input.in"
    
    content = generate_input()
    # Provide the file for download instead of saving server-side
    put_file(filename, content.encode('utf-8'))
    toast(f"Input file ready for download", color='success')

def generate_input():
    """Generate input for Prover9/Mace4"""
    assumptions = pin.assumptions
    goals = pin.goals
    additional = pin.additional_input if hasattr(pin, 'additional_input') else ""
    #TODO kill things that will be redefined

    # Start with optional settings
    content = "% Saved by Prover9-Mace4 Web GUI\n\n"
    content += "set(ignore_option_dependencies). % GUI handles dependencies\n\n"
    
    # Add language options
    if "prolog_style_variables" in pin.language_flags:
        content += "set(prolog_style_variables).\n"
    content += pin.language_options

    # Add Prover9 options
    content += "if(Prover9). % Options for Prover9\n"
    for name in PROVER9_PARAMS:
        pname = re.sub('prover9_', "", name)
        if hasattr(pin, pname):
            content += f"  assign({name}, {pin[pname]}).\n"
    for name in PROVER9_FLAGS:
        if name in pin.prover9_flags:
            content += f"  set({name}).\n"
    content += "end_if.\n\n"
    
    # Add Mace4 options
    content += "if(Mace4).   % Options for Mace4\n"
    for name in MACE4_PARAMS:
        pname = re.sub('mace4_', "", name)
        if hasattr(pin, pname):
            content += f"  assign({name}, {pin[pname]}).\n"
    for name in MACE4_FLAGS:
        if name in pin.mace4_flags:
            content += f"  set({name}).\n"
            
    content += "end_if.\n\n"
    
    # Add assumptions, goals and additional content
    content += "formulas(assumptions).\n"
    content += assumptions + "\n"
    content += "end_of_list.\n\n"
    content += "formulas(goals).\n"
    content += goals + "\n"
    content += "end_of_list.\n\n"
    content += additional
    return content

def run_prover9():
    """Run Prover9"""
    
    # Generate input
    input_text = generate_input()
    print(input_text)

def run_mace4():
    """Run Mace4"""
    
    # Generate input
    input_text = generate_input()
    print(input_text)

# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    
    # Use PyWebIO's start_server directly
    start_server(prover9_mace4_app, port=args.port, debug=args.debug) 
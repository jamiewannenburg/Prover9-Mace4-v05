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

def run_command(command, input_text='', callback=None):
    """Print the command and input that would be executed"""
    if isinstance(input_text, str):
        input_text = input_text.encode('utf-8')
    
    # Print the command that would be executed
    print("Command:", " ".join(command))
    print("\nInput text:")
    print(input_text.decode('utf-8'))
    print("\n" + "="*80 + "\n")
    
    # Return dummy values to maintain compatibility
    class DummyProcess:
        def poll(self): return 0
        def terminate(self): pass
        def send_signal(self, sig): pass
    
    return DummyProcess(), None, None, None

def get_process_output(fout, ferr):
    """Get output from process file handles"""
    # Since we're not actually running the process, return empty strings
    return "", ""

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
            put_checkbox('prover9_basic_flags', label='Prover9 Flags', options=['expand_relational_defs','restrict_denials'], value=False),
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
    print(parsed)
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
        print(name,'prover9_'+name,parsed['prover9_assigns'][name],PROVER9_PARAMS)
        if 'prover9_'+name in PROVER9_PARAMS:
            print(name,parsed['prover9_assigns'][name])
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
    
    assumptions = pin.assumptions
    goals = pin.goals
    additional = pin.additional_input if hasattr(pin, 'additional_input') else ""
    
    # Start with optional settings
    content = "% Saved by Prover9-Mace4 Web GUI\n\n"
    content += "set(ignore_option_dependencies). % GUI handles dependencies\n\n"
    
    # Add Prover9 options
    content += "if(Prover9). % Options for Prover9\n"
    if hasattr(pin, 'max_seconds'):
        content += f"  assign(max_seconds, {pin.max_seconds}).\n"
    if hasattr(pin, 'max_megs'):
        content += f"  assign(max_megs, {pin.max_megs}).\n"
    
    # Add search strategy if not auto
    if hasattr(pin, 'search_strategy') and pin.search_strategy != 'auto':
        content += f"  set({pin.search_strategy}).\n"
    
    # Add Prover9 checkbox options
    if hasattr(pin, 'prover_options'):
        for option in pin.prover_options:
            content += f"  set({option}).\n"
    
    content += "end_if.\n\n"
    
    # Add Mace4 options
    content += "if(Mace4).   % Options for Mace4\n"
    if hasattr(pin, 'max_seconds_mace'):
        content += f"  assign(max_seconds, {pin.max_seconds_mace}).\n"
    if hasattr(pin, 'max_megs_mace'):
        content += f"  assign(max_megs, {pin.max_megs_mace}).\n"
    if hasattr(pin, 'domain_size'):
        content += f"  assign(start_size, {pin.domain_size}).\n"
    if hasattr(pin, 'end_size'):
        content += f"  assign(end_size, {pin.end_size}).\n"
    if hasattr(pin, 'max_models'):
        content += f"  assign(max_models, {pin.max_models}).\n"
    
    # Add Mace4 checkbox options
    if hasattr(pin, 'mace_options'):
        for option in pin.mace_options:
            content += f"  set({option}).\n"
    
    content += "end_if.\n\n"
    
    # Add other language options if selected
    if hasattr(pin, 'options'):
        for option in pin.options:
            content += f"set({option}).\n\n"
    
    # Add assumptions, goals and additional content
    content += "formulas(assumptions).\n"
    content += assumptions + "\n"
    content += "end_of_list.\n\n"
    content += "formulas(goals).\n"
    content += goals + "\n"
    content += "end_of_list.\n\n"
    content += additional
    
    # Provide the file for download instead of saving server-side
    put_file(filename, content.encode('utf-8'))
    toast(f"Input file ready for download", color='success')

def generate_input():
    """Generate input for Prover9/Mace4"""
    assumptions = pin.assumptions
    goals = pin.goals
    additional = pin.additional_input if hasattr(pin, 'additional_input') else ""
    
    # Start with optional settings
    content = "% Generated by Prover9-Mace4 Web GUI\n\n"
    content += "set(ignore_option_dependencies). % GUI handles dependencies\n\n"
    
    # Add Prover9 options
    content += "if(Prover9). % Options for Prover9\n"
    if hasattr(pin, 'max_seconds'):
        content += f"  assign(max_seconds, {pin.max_seconds}).\n"
    if hasattr(pin, 'max_megs'):
        content += f"  assign(max_megs, {pin.max_megs}).\n"
    
    # Add search strategy if not auto
    if hasattr(pin, 'search_strategy') and pin.search_strategy != 'auto':
        content += f"  set({pin.search_strategy}).\n"
    
    # Add Prover9 checkbox options
    if hasattr(pin, 'prover_options'):
        for option in pin.prover_options:
            content += f"  set({option}).\n"
    
    content += "end_if.\n\n"
    
    # Add Mace4 options
    content += "if(Mace4).   % Options for Mace4\n"
    if hasattr(pin, 'max_seconds_mace'):
        content += f"  assign(max_seconds, {pin.max_seconds_mace}).\n"
    if hasattr(pin, 'max_megs_mace'):
        content += f"  assign(max_megs, {pin.max_megs_mace}).\n"
    if hasattr(pin, 'domain_size'):
        content += f"  assign(start_size, {pin.domain_size}).\n"
    if hasattr(pin, 'end_size'):
        content += f"  assign(end_size, {pin.end_size}).\n"
    if hasattr(pin, 'max_models'):
        content += f"  assign(max_models, {pin.max_models}).\n"
    
    # Add Mace4 checkbox options
    if hasattr(pin, 'mace_options'):
        for option in pin.mace_options:
            content += f"  set({option}).\n"
    
    content += "end_if.\n\n"
    
    # Add other language options if selected
    if hasattr(pin, 'options'):
        for option in pin.options:
            content += f"set({option}).\n\n"
    
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
    
    # Build command - no longer passing options on command line
    prover9_path = os.path.join(BIN_DIR, 'prover9')
    command = [prover9_path]
    
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
    
    # Build command - no longer passing options via command line
    mace4_path = os.path.join(BIN_DIR, 'mace4')
    command = [mace4_path, "-c"]  # Keep the -c flag to enable model output
    
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
            
            # Print the command that would be executed
            print(f"\nWould execute: {prooftrans_path} {format_value}")
            print("\nInput:")
            print(output)
            print("\n" + "="*80 + "\n")
            
            # Return dummy content
            content = f"[Would convert output to {format_value} format]"
        
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
                
                # Print the isofilter command that would be executed
                print(f"\nWould execute: {isofilter_path}")
                print("\nInput:")
                print(processed_output)
                print("\n" + "="*80 + "\n")
                
                # Simulate isofilter output
                processed_output = "[Would filter isomorphic models]"
            
            # Print the interpformat command that would be executed
            print(f"\nWould execute: {interpformat_path} {format_value}")
            print("\nInput:")
            print(processed_output)
            print("\n" + "="*80 + "\n")
            
            # Return dummy content
            content = f"[Would convert output to {format_value} format]"
        
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
    
    # Use PyWebIO's start_server directly
    start_server(prover9_mace4_app, port=args.port, debug=args.debug) 
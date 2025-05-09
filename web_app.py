#!/usr/bin/env python3
"""
Prover9-Mace4 Web GUI
A PyWebIO-based web interface for Prover9 and Mace4
"""

import os
import re
import argparse
from functools import partial
from PIL import Image
from pyparsing import (
    Word, alphas, alphanums, Literal, Group, Optional, 
    OneOrMore, ZeroOrMore, ParseException, restOfLine,
    QuotedString, delimitedList, ParseResults, Regex, Keyword, OneOrMore, printables
)

import time
import json
import requests
from typing import Dict, List
from typing import Optional as OptionalType
from datetime import datetime
import dotenv

from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import *
from pywebio.session import get_info
from pywebio import config, start_server
from pywebio.platform.flask import webio_view

# Constants
SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'Samples')
PROGRAM_NAME = 'Prover9-Mace4'
PROGRAM_VERSION = '0.5 Web'
PROGRAM_DATE = 'May 2025'
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

# TODO: is this not interpformat options?
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

    if API_URL_KEY in local: # API URL is stored in session
        return local[API_URL_KEY]
    elif 'PROVER9_API_URL' in os.environ: # API URL is stored in environment variable
        return os.environ['PROVER9_API_URL']
    else: # API URL is not stored in session or environment variable, use default
        return API_URL

def set_api_url(url: str) -> None:
    """Set the API URL in session"""
    local[API_URL_KEY] = url


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

# TODO: if docker folder is available, list files in docker folder


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
    prover9_block = if_prover9 + ZeroOrMore(comment | set_option | assign_option | clear_option) + end_if
    mace4_block = if_mace4 + ZeroOrMore(comment | set_option | assign_option | clear_option) + end_if
    
    # Define global options
    #global_options = ZeroOrMore(set_option | assign_option | clear_option)
    
    # Define the complete grammar 
    #grammar = Optional(ZeroOrMore(comment)) + Optional(global_options) + Optional(ZeroOrMore(comment)) + Optional(ZeroOrMore(language_option)) + Optional(ZeroOrMore(comment)) + Optional(prover9_block) + Optional(ZeroOrMore(comment)) + Optional(mace4_block) + Optional(ZeroOrMore(comment)) + Optional(assumptions_section) + Optional(ZeroOrMore(comment)) + Optional(goals_section)
    grammar = ZeroOrMore( comment | prover9_block | mace4_block | assumptions_section | goals_section | set_option | assign_option | clear_option | language_option)
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
            'language_options': '',
            'prover9_assigns': {},
            'mace4_assigns': {}
        }
    
    # Initialize result containers
    parsed = {
        'assumptions': '',
        'goals': '',
        'prover9_options': set(),
        'mace4_options': set(),
        'language_options': '',
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
            parsed['language_options']+='op('+', '.join(item[1:-1])+').\n'
        elif current_section == "assumptions":
            # concatenate the item list to a string
            parsed['assumptions'] += ''.join(item)+'\n'
        elif current_section == "goals":
            parsed['goals'] += ''.join(item)+'\n'
    return parsed

# Main application function
@config(theme="yeti", title=PROGRAM_NAME)
def prover9_mace4_app():
    """Main application function"""
    
    set_env(output_max_width='90%',title=f"{PROGRAM_NAME}")

    # Create layout with setup and run panels
    put_column([
        put_scope('run_panel'),
        put_scope('setup_panel'),
        put_row([
            put_scope('process_list'),
            put_scope('process_details'),
        ],size="60% 40%"),
        put_scope('api_config'),
    ], size="30px") #, size="5% 60% 37% 2%"
    
    # init api url
    dotenv.load_dotenv() # load environment variables from .env file
    if 'PROVER9_API_URL' in os.environ: # API URL is stored in environment variable
        set_api_url(os.environ['PROVER9_API_URL'])
    else:
        # API URL configuration screen
        with use_scope('api_config', clear=True):
            put_markdown("## API Configuration\n\nTo avoid this screen, set the `PROVER9_API_URL` environment variable.")
            api_url = input("API Server URL", type=TEXT, value=get_api_url())
            set_api_url(api_url)

    # Populate the panels
    run_panel()
    setup_panel()
    
    # Set favicon using JavaScript - only when running under Flask
    if info.backend == 'flask':
        image_url = "/favicon.ico"
        run_js("""
        $('#favicon32,#favicon16').remove(); 
        $('head').append('<link rel="icon" type="image/png" href="%s">')
        """ % image_url)

    
    # Initial update
    update_process_list()
    
    # Periodic updates
    while True:
        time.sleep(3)
        update_process_list()

    

def setup_panel():
    """Setup panel with formula input and options"""
    with use_scope('setup_panel'):
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
            put_button("💾 Save", onclick=save_input),
            put_button("📄 Open", onclick=load_file),
            put_button("Samples", onclick=load_sample),
            put_button("🧹 Clear", onclick=lambda: [pin_update('assumptions', value=''), pin_update('goals', value='')]),
        ]),
        put_text("Assumptions:"),
        put_textarea('assumptions', rows=15, code={
            'mode': 'matlab',
            #'theme': 'monokai'
        }),
        put_text("Goals:"),
        put_textarea('goals', rows=15, code={
            'mode': 'matlab',
            #'theme': 'monokai'
        }),
    ], size="10% 5% 40% 5% 40%")
    
    return content

def language_options_panel():
    """Panel for language options"""
    content = put_column([
        put_checkbox('language_flags', options=[
            {'label': 'Prolog-Style Variables', 'value': 'prolog_style_variables'}
        ]),
        put_textarea('language_options', rows=15, code={
            'mode': 'matlab',
            #'theme': 'monokai'
        }),
    ], size="2% 98%")
    
    return content

PROVER9_PARAMS = [
    'prover9_max_seconds',
    'prover9_max_weight',
    'prover9_pick_given_ratio',
    'prover9_order',
    'prover9_eq_defs',
]

PROVER9_FLAGS = [
    ('expand_relational_defs',True),
    ('restrict_denials',True),
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
        ]),
        # TODO Advanced Options, to many for now
    ])
    
    return content

MACE4_PARAMS = [
    'mace4_max_seconds',
    'mace4_start_size',
    'mace4_end_size',
    'mace4_max_models',
    'mace4_max_seconds_per',
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
            put_input('mace4_max_seconds_per', label='Max Seconds Per Model', type=NUMBER, value=-1),
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
        'mode': 'matlab',
        #'theme': 'monokai'
    })
    
    return content

def run_panel():
    """Run panel with controls and output display"""
    with use_scope('run_panel'):
        put_row([
            put_image(Image.open('src/Images/prover9-5a-128t.gif'), format='gif', title=BANNER ,height='30px'),
            put_button("▶️", onclick=run_prover9, color='primary'),
            None,
            put_image(Image.open('src/Images/mace4-90t.gif'), format='gif', title=BANNER ,height='30px'),
            put_button("▶️", onclick=run_mace4, color='primary'),

        ],size="80px 20px 100px 60px 20px")
        

def update_process_list() -> None:
    """Update the process list display"""
    try:
        # first get all the data
        
        response = requests.get(f"{get_api_url()}/processes")
        process_ids = response.json()
        processes = []
        table = [
            ['ID', 'Program', 'Status', 'Start Time', 'Actions']
        ]
        for process_id in process_ids:
            process = requests.get(f"{get_api_url()}/status/{process_id}").json()
            processes.append(process)
            for process in processes:
                start_time = datetime.fromisoformat(process['start_time'])
                actions = []
                clicks = []
                if process['state'] in ['running', 'suspended']:
                    if process['state'] == 'running':
                        # windows cannot pause a process
                        if os.name != 'nt':
                            actions.append({'label': 'Pause', 'value': str(process_id)+'pause', 'color': 'primary'})
                            clicks.append(lambda p=process_id: pause_process(p))
                    else:
                        # windows cannot resume a process
                        if os.name != 'nt':
                            actions.append({'label': 'Resume', 'value': str(process_id)+'resume', 'color': 'primary'})
                            clicks.append(lambda p=process_id: resume_process(p))
                    actions.append({'label': 'Kill', 'value': str(process_id)+'kill', 'color': 'danger'})
                    clicks.append(lambda p=process_id: kill_process(p))
                
                if process['state'] == 'done' and process['output']:
                    actions.append({'label': '📥', 'value': str(process_id)+'download', 'color': 'primary'})
                    clicks.append(lambda p=process_id: download_output(p))
                
                table.append([
                        put_button(label=str(process_id),onclick=lambda p=process_id: show_process_details(p), color='primary'),
                        process['program'],
                        process['state'],
                        start_time.strftime('%Y-%m-%d %H:%M:%S'),
                        put_buttons(actions, onclick=clicks)
                    ])
        with use_scope('process_list', clear=True):
            put_table(table)
            
    except requests.exceptions.RequestException as e:
        toast(f"Error updating process list: {str(e)}", color='error')

def show_process_details(process_id: int) -> None:
    """Show detailed information about a process"""
    try:
        response = requests.get(f"{get_api_url()}/status/{process_id}")
        if response.status_code == 200:
            process = response.json()
            
            with use_scope('process_details', clear=True):
                with put_scrollable():
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

def update_options(parsed):
    # Update the text areas
    pin_update('assumptions', value=parsed['assumptions'])
    pin_update('goals', value=parsed['goals'])


    # Update language options
    language_input = ""
    for item in parsed['language_options']:
        language_input += item
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
    additional_p9_assigns = ''
    for name in parsed['prover9_assigns']:
        if 'prover9_'+name in PROVER9_PARAMS:
            try:
                pin_update('prover9_'+name, value=int(parsed['prover9_assigns'][name]))
            except ValueError:
                pin_update('prover9_'+name, value=parsed['prover9_assigns'][name])
            # TODO: see how pin_update fails
            # additional_input += f"assign({name}, {parsed['prover9_assigns'][name]}).\n"
        else:
            additional_p9_assigns += f"assign({name}, {parsed['prover9_assigns'][name]}).\n"
    # Update Prover9 options
    p9_opt_list = []
    p9_opt_set = []
    additional_p9_flags = ''
    for name, value in parsed['prover9_options']:
        if name in PROVER9_FLAGS.map(lambda x: x[0]):
            p9_opt_set.append(name)
            if value:
                p9_opt_list.append(name)
        else:
            if value:
                additional_p9_flags += f"set({name}).\n"
            else:
                additional_p9_flags += f"clear({name}).\n"
    for name,default in PROVER9_FLAGS:
        if name not in p9_opt_set:
            if default:
                p9_opt_list.append(name)

    pin_update('prover9_flags', value=p9_opt_list)
    if len(additional_p9_assigns) > 0 or len(additional_p9_flags) > 0:
        additional_input += "if(Prover9).\n"
        additional_input += additional_p9_assigns
        additional_input += additional_p9_flags
        additional_input += "end_if.\n"
    # Update Mace4 options
    additional_m4_assigns = ''
    for name in parsed['mace4_assigns']:
        if 'mace4_'+name in MACE4_PARAMS:
            try:
                pin_update('mace4_'+name, value=int(parsed['mace4_assigns'][name]))
            except ValueError:
                pin_update('mace4_'+name, value=parsed['mace4_assigns'][name])
            # TODO: see how pin_update fails
            # additional_input += f"assign({name}, {parsed['mace4_assigns'][name]}).\n"
        else:
            if name == "domain_size":
                pin_update('mace4_start_size', value=int(parsed['mace4_assigns'][name]))
                pin_update('mace4_end_size', value=int(parsed['mace4_assigns'][name]))
            else:
                additional_m4_assigns += f"  assign({name}, {parsed['mace4_assigns'][name]}).\n"
            
    # update mace4 options
    m4_opt_list = []
    m4_opt_set = []
    additional_m4_flags = ''
    for name, value in parsed['mace4_options']:
        if name in MACE4_FLAGS.map(lambda x: x[0]):
            m4_opt_set.append(name)
            if value:
                m4_opt_list.append(name)
        else:
            if value:
                additional_m4_flags += f"set({name}).\n"
            else:
                additional_m4_flags += f"clear({name}).\n"
    for name,default in MACE4_FLAGS:
        if name not in m4_opt_set:
            if default:
                m4_opt_list.append(name)

    #pin_update('mace4_flags', value=m4_opt_list) #TODO not defined
    if len(additional_m4_assigns) > 0 or len(additional_m4_flags) > 0:
        additional_input += "if(Mace4).\n"
        additional_input += additional_m4_assigns
        additional_input += additional_m4_flags
        additional_input += "end_if.\n"
    
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
    parsed = parse_file(pin.additional_input)
    #TODO kill things that will be redefined

    # Start with optional settings
    content = "% Saved by Prover9-Mace4 Web GUI\n\n"
    #content += "set(ignore_option_dependencies). % GUI handles dependencies\n\n" #TODO: I'm not handling dependencies
    
    # Add language options
    if "prolog_style_variables" in pin.language_flags:
        content += "set(prolog_style_variables).\n"
    content += pin.language_options
    content += parsed['language_options']

    # Add Prover9 options
    content += "if(Prover9). % Options for Prover9\n"
    # TODO add default values?
    for name in PROVER9_PARAMS:
        pname = re.sub('prover9_', "", name)
        if pin[name] is not None:
            content += f"  assign({pname}, {pin[name]}).\n"
    for name in parsed['prover9_assigns']:
        content += f"  assign({name}, {parsed['prover9_assigns'][name]}).\n"
    for name,default in PROVER9_FLAGS:
        value = (name in pin.prover9_flags)
        if value != default:
            if value:
                content += f"  set({name}).\n"
            else:
                content += f"  clear({name}).\n"
    for name,value in parsed['prover9_options']:
        if value:
            content += f"  set({name}).\n"
        else:
            content += f"  clear({name}).\n"
    content += "end_if.\n\n"
    
    # Add Mace4 options
    content += "if(Mace4).   % Options for Mace4\n"
    for name in MACE4_PARAMS:
        pname = re.sub('mace4_', "", name)
        if pin[name] is not None:
            content += f"  assign({pname}, {pin[name]}).\n"
    for name in parsed['mace4_assigns']:
        content += f"  assign({name}, {parsed['mace4_assigns'][name]}).\n"
    for name,default in MACE4_FLAGS:
        value = (name in pin.mace4_flags)
        if value != default:
            if value:
                content += f"  set({name}).\n"
            else:
                content += f"  clear({name}).\n"
    for name,value in parsed['mace4_options']:
        if value:
            content += f"  set({name}).\n"
        else:
            content += f"  clear({name}).\n"
    content += "end_if.\n\n"
    
    # Add assumptions, goals and additional content
    
    parsed = {
        'assumptions': '',
        'goals': '',
        'prover9_options': set(),
        'mace4_options': set(),
        'language_options': '',
        'global_options': set(),
        'global_assigns': {},
        'prover9_assigns': {},
        'mace4_assigns': {}
    }
    for name in parsed['global_assigns']:
        content += f"assign({name}, {parsed['global_assigns'][name]}).\n"
    for name,value in parsed['global_options']:
        if value:
            content += f"set({name}).\n"
        else:
            content += f"clear({name}).\n"
        
    content += "formulas(assumptions).\n"
    content += assumptions + "\n"
    content += "end_of_list.\n\n"
    content += "formulas(goals).\n"
    content += goals + "\n"
    content += "end_of_list.\n\n"
    return content



def start_process(program: str, input_text: str, options: OptionalType[Dict] = None) -> None:
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
                    'mace4': 'out',
                    'isofilter': 'model',
                    'isofilter2': 'model',
                    'interpformat': 'model',
                    'prooftrans': 'proof'
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


def run_prover9():
    """Run Prover9"""
    
    # Generate input
    input_text = generate_input()
    print(input_text)
    start_process('prover9', input_text)

def run_mace4():
    """Run Mace4"""
    
    # Generate input
    input_text = generate_input()
    print(input_text)
    start_process('mace4', input_text)

# Run the app
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{PROGRAM_NAME} Web GUI')
    parser.add_argument('--port', type=int, default=8080, help='Port to run the web server on')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host to run the web server on')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    
    # Use PyWebIO's start_server directly
    start_server(prover9_mace4_app, port=args.port, debug=args.debug, host=args.host) 
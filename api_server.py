#!/usr/bin/env python3
"""
Prover9-Mace4 API Server
A FastAPI-based REST API for Prover9 and Mace4
"""

import os
import re
import sys
import time
import signal
import tempfile
import subprocess
import threading
import psutil
from typing import Dict, List, Optional, Union
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from enum import Enum

# Constants
BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'bin')

# Process tracking
class ProcessState(Enum):
    READY = "ready"
    RUNNING = "running"
    SUSPENDED = "suspended"
    DONE = "done"
    ERROR = "error"
    KILLED = "killed"

class ProgramType(Enum):
    PROVER9 = "prover9"
    MACE4 = "mace4"
    ISOFILTER = "isofilter"
    ISOFILTER2 = "isofilter2"
    INTERPFORMAT = "interpformat"
    PROOFTRANS = "prooftrans"

class ProcessInfo(BaseModel):
    pid: int
    start_time: datetime
    state: ProcessState
    program: ProgramType
    input: str
    output: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    stats: Optional[Dict] = None
    resource_usage: Optional[Dict] = None
    options: Optional[Dict] = None

# Global process tracking
processes: Dict[int, ProcessInfo] = {}
process_lock = threading.Lock()

# Program exit codes
PROGRAM_EXITS = {
    ProgramType.PROVER9: {
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
    },
    ProgramType.MACE4: {
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
    },
    ProgramType.ISOFILTER: {
        0: 'Success',
        1: 'Error',
        2: 'No Models'
    },
    ProgramType.ISOFILTER2: {
        0: 'Success',
        1: 'Error',
        2: 'No Models'
    },
    ProgramType.INTERPFORMAT: {
        0: 'Success',
        1: 'Error',
        2: 'Invalid Format'
    },
    ProgramType.PROOFTRANS: {
        0: 'Success',
        1: 'Error',
        2: 'Invalid Format'
    }
}

# Utility functions
def binary_ok(fullpath: str) -> bool:
    """Check if binary exists and is executable"""
    return os.path.isfile(fullpath) and os.access(fullpath, os.X_OK)

def get_program_path(program: ProgramType) -> Optional[str]:
    """Get the full path to a program binary"""
    program_map = {
        ProgramType.PROVER9: 'prover9',
        ProgramType.MACE4: 'mace4',
        ProgramType.ISOFILTER: 'isofilter',
        ProgramType.ISOFILTER2: 'isofilter2',
        ProgramType.INTERPFORMAT: 'interpformat',
        ProgramType.PROOFTRANS: 'prooftrans'
    }
    path = os.path.join(BIN_DIR, program_map[program])
    if os.path.isfile(path + '.bat'):
        return path + '.bat'
    elif os.path.isfile(path + '.sh'):
        return path + '.sh'
    elif os.path.isfile(path + '.exe'):
        return path + '.exe'
    else:
        return path

def get_process_stats(pid: int) -> Dict:
    """Get process resource usage statistics"""
    try:
        process = psutil.Process(pid)
        return {
            "cpu_percent": process.cpu_percent(),
            "memory_percent": process.memory_percent(),
            "memory_info": process.memory_info()._asdict(),
            "create_time": datetime.fromtimestamp(process.create_time()),
            "num_threads": process.num_threads(),
            "status": process.status()
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}

def get_prover9_stats(output: str) -> Dict:
    """Extract statistics from Prover9 output"""
    stats = {}
    if "Given=" in output:
        match = re.search(r'Given=(\d+)\. Generated=(\d+)\. Kept=(\d+)\. proofs=(\d+)\.User_CPU=(\d*\.\d*),', output)
        if match:
            stats = {
                "given": int(match.group(1)),
                "generated": int(match.group(2)),
                "kept": int(match.group(3)),
                "proofs": int(match.group(4)),
                "cpu_time": float(match.group(5))
            }
    return stats

def get_mace4_stats(output: str) -> Dict:
    """Extract statistics from Mace4 output"""
    stats = {}
    if "Domain_size=" in output:
        match = re.search(r'Domain_size=(\d+)\. Models=(\d+)\. User_CPU=(\d*\.\d*)\.', output)
        if match:
            stats = {
                "domain_size": int(match.group(1)),
                "models": int(match.group(2)),
                "cpu_time": float(match.group(3))
            }
    return stats

def get_isofilter_stats(output: str) -> Dict:
    """Extract statistics from Isofilter output"""
    stats = {}
    if "input=" in output:
        match = re.search(r'input=(\d+), kept=(\d+)', output)
        if match:
            stats = {
                "input_models": int(match.group(1)),
                "kept_models": int(match.group(2)),
                "removed_models": int(match.group(1)) - int(match.group(2))
            }
    return stats

def run_program(program: ProgramType, input_text: str, process_id: int, options: Optional[Dict] = None) -> None:
    """Run a program in a separate thread"""
    program_path = get_program_path(program)
    if not program_path or not binary_ok(program_path):
        with process_lock:
            processes[process_id].state = ProcessState.ERROR
            processes[process_id].error = f"{program.value} binary not found or not executable"
        return

    # Create temporary files
    fin = tempfile.TemporaryFile('w+b')
    fout = tempfile.TemporaryFile('w+b')
    ferr = tempfile.TemporaryFile('w+b')

    try:
        # Write input to stdin
        if isinstance(input_text, str):
            input_text = input_text.encode('utf-8')
        fin.write(input_text)
        fin.seek(0)

        # Build command
        command = [program_path]
        
        # Add program-specific options
        if program == ProgramType.MACE4:
            command.append("-c")
        elif program == ProgramType.ISOFILTER and options:
            if options.get("wrap"):
                command.append("wrap")
            if options.get("ignore_constants"):
                command.append("ignore_constants")
            if options.get("check"):
                command.append("check")
                command.append(options["check"])
            if options.get("output"):
                command.append("output")
                command.append(options["output"])
        elif program == ProgramType.INTERPFORMAT and options:
            if options.get("format"):
                command.append(options["format"])
        elif program == ProgramType.PROOFTRANS and options:
            if options.get("format"):
                command.append(options["format"])
            if options.get("expand"):
                command.append("expand")
            if options.get("renumber"):
                command.append("renumber")
            if options.get("striplabels"):
                command.append("striplabels")

        process = subprocess.Popen(
            command,
            stdin=fin,
            stdout=fout,
            stderr=ferr
        )

        # Update process info
        with process_lock:
            processes[process_id].pid = process.pid
            processes[process_id].state = ProcessState.RUNNING

        # Monitor process
        while process.poll() is None:
            # Update resource usage
            with process_lock:
                processes[process_id].resource_usage = get_process_stats(process.pid)
            
            # Check if process was killed
            if processes[process_id].state == ProcessState.KILLED:
                process.terminate()
                break

            time.sleep(0.5)

        # Process finished
        exit_code = process.poll()
        fout.seek(0)
        output = fout.read().decode('utf-8', errors='replace')
        ferr.seek(0)
        error = ferr.read().decode('utf-8', errors='replace')

        # Update process info
        with process_lock:
            processes[process_id].exit_code = exit_code
            processes[process_id].output = output
            processes[process_id].error = error
            processes[process_id].state = ProcessState.DONE
            
            # Update statistics
            if program == ProgramType.PROVER9:
                processes[process_id].stats = get_prover9_stats(output)
            elif program == ProgramType.MACE4:
                processes[process_id].stats = get_mace4_stats(output)
            elif program in [ProgramType.ISOFILTER, ProgramType.ISOFILTER2]:
                processes[process_id].stats = get_isofilter_stats(output)

    finally:
        # Cleanup
        fin.close()
        fout.close()
        ferr.close()

# FastAPI app
app = FastAPI(title="Prover9-Mace4 API")

class ProgramInput(BaseModel):
    program: ProgramType
    input: str
    options: Optional[Dict] = None

@app.post("/start")
async def start_program(input: ProgramInput, background_tasks: BackgroundTasks) -> Dict:
    """Start a new process"""
    # Generate process ID
    process_id = int(time.time() * 1000)

    # Create process info
    process_info = ProcessInfo(
        pid=0,
        start_time=datetime.now(),
        state=ProcessState.READY,
        program=input.program,
        input=input.input,
        options=input.options
    )

    # Add to tracking
    with process_lock:
        processes[process_id] = process_info

    # Start process in background
    background_tasks.add_task(run_program, input.program, input.input, process_id, input.options)

    return {"process_id": process_id}

@app.get("/status/{process_id}")
async def get_status(process_id: int) -> ProcessInfo:
    """Get the status of a process"""
    with process_lock:
        if process_id not in processes:
            raise HTTPException(status_code=404, detail="Process not found")
        return processes[process_id]

@app.get("/processes")
async def list_processes() -> List[int]:
    """List all tracked processes"""
    with process_lock:
        print(list(processes.keys()))
        return list(processes.keys())

@app.post("/kill/{process_id}")
async def kill_process(process_id: int) -> Dict:
    """Kill a running process"""
    with process_lock:
        if process_id not in processes:
            raise HTTPException(status_code=404, detail="Process not found")
        
        process_info = processes[process_id]
        if process_info.state not in [ProcessState.RUNNING, ProcessState.SUSPENDED]:
            raise HTTPException(status_code=400, detail="Process is not running or suspended")

        # Update state
        process_info.state = ProcessState.KILLED

        # Send termination signal
        try:
            os.kill(process_info.pid, signal.SIGTERM)
            return {"status": "success", "message": "Process termination signal sent"}
        except ProcessLookupError:
            return {"status": "error", "message": "Process not found"}

@app.post("/pause/{process_id}")
async def pause_process(process_id: int) -> Dict:
    """Pause a running process"""
    with process_lock:
        if process_id not in processes:
            raise HTTPException(status_code=404, detail="Process not found")
        
        process_info = processes[process_id]
        if process_info.state != ProcessState.RUNNING:
            raise HTTPException(status_code=400, detail="Process is not running")
        # windows cannot pause a process
        if os.name == 'nt':
            raise HTTPException(status_code=400, detail="Windows cannot pause a process")
        # Update state and send signal
        process_info.state = ProcessState.SUSPENDED
        os.kill(process_info.pid, signal.SIGSTOP)
        return {"status": "success", "message": "Process paused"}

@app.post("/resume/{process_id}")
async def resume_process(process_id: int) -> Dict:
    """Resume a paused process"""
    with process_lock:
        if process_id not in processes:
            raise HTTPException(status_code=404, detail="Process not found")
        
        process_info = processes[process_id]
        if process_info.state != ProcessState.SUSPENDED:
            raise HTTPException(status_code=400, detail="Process is not paused")
        # windows cannot resume a process
        if os.name == 'nt':
            raise HTTPException(status_code=400, detail="Windows cannot resume a process")
        # Update state and send signal
        process_info.state = ProcessState.RUNNING
        os.kill(process_info.pid, signal.SIGCONT)
        return {"status": "success", "message": "Process resumed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
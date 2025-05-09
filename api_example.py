import requests
from enum import Enum
import time

# Start a Prover9 process
response = requests.post("http://localhost:8000/start", json={
    "program": "prover9",
    "input": "formulas(assumptions).\nall x (P(x) -> Q(x)).\nP(a).\nend_of_list.\n\nformulas(goals).\nQ(a).\nend_of_list."
})
process_id = response.json()["process_id"]

time.sleep(1)
# Check status
status = requests.get(f"http://localhost:8000/status/{process_id}").json()
#print(status)

# List all processes
processes = requests.get("http://localhost:8000/processes").json()
#print(processes)

# Pause a process
requests.post(f"http://localhost:8000/pause/{process_id}")

# Resume a process
requests.post(f"http://localhost:8000/resume/{process_id}")

# Kill a process
requests.post(f"http://localhost:8000/kill/{process_id}")

# Start a Mace4 process
response = requests.post("http://localhost:8000/start", json={
    "program": "mace4",
    "input": "if(Mace4).\nassign(start_size, 8).\nassign(end_size, 8).\nassign(max_models, 5).\nend_if.\nformulas(assumptions).\n(x*y)*z=x*(y*z).\nend_of_list.\n\nformulas(goals).\n\nend_of_list."
})
process_mace4_id = response.json()["process_id"]

# wait for mace4 to finish
while requests.get(f"http://localhost:8000/status/{process_mace4_id}").json()["state"] != "done":
    time.sleep(1)

status_mace4 = requests.get(f"http://localhost:8000/status/{process_mace4_id}").json()
#print(status_mace4["output"])

# Example: Format a model
response = requests.post("http://localhost:8000/start", json={
    "program": "interpformat",
    "input": status_mace4["output"],
    "options": {
        "format": "standard"
    }
})
process_interpformat_id = response.json()["process_id"]

# wait for interpformat to finish
while requests.get(f"http://localhost:8000/status/{process_interpformat_id}").json()["state"] != "done":
    time.sleep(1)

status_interpformat = requests.get(f"http://localhost:8000/status/{process_interpformat_id}").json()
#print(status_interpformat["output"])

# Example: Run isofilter
response = requests.post("http://localhost:8000/start", json={
    "program": "isofilter",
    "input": status_interpformat["output"],
    "options": {
        "wrap": True,
        "ignore_constants": True,
    }
})
process_isofilter_id = response.json()["process_id"]

# wait for isofilter to finish
while requests.get(f"http://localhost:8000/status/{process_isofilter_id}").json()["state"] != "done":
    time.sleep(1)

status_isofilter = requests.get(f"http://localhost:8000/status/{process_isofilter_id}").json()
#print(status_isofilter["output"])

# Example: Transform a proof
response = requests.post("http://localhost:8000/start", json={
    "program": "prooftrans",
    "input": status["output"],
    "options": {
        "format": "xml",
        "expand": True,
        "renumber": True
    }
})
process_prooftrans_id = response.json()["process_id"]

# wait for prooftrans to finish
while requests.get(f"http://localhost:8000/status/{process_prooftrans_id}").json()["state"] != "done":
    time.sleep(1)

status_prooftrans = requests.get(f"http://localhost:8000/status/{process_prooftrans_id}").json()
#print(status_prooftrans["output"])

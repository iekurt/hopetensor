import subprocess
import sys
import time

def run(module, port):
    # stdout/devnull removed -> logs will be visible
    return subprocess.Popen([sys.executable, "-m", "uvicorn", module, "--port", str(port)])

procs = []
procs.append(run("reasoning_node.app:app", 8001))
procs.append(run("reasoning_node.app:app", 8002))
procs.append(run("verification_node:app", 8003))
procs.append(run("ethics_node:app", 8004))
procs.append(run("observer_node:app", 8005))
procs.append(run("coordinator:app", 8000))

time.sleep(2)
print("\nHOPETensor demo running.")
print("Test:\n")
print("curl -X POST http://127.0.0.1:8000/query -H \"Content-Type: application/json\" -d \"{\\\"query\\\":\\\"What is HOPE 2050?\\\"}\" \n")

try:
    for p in procs:
        p.wait()
except KeyboardInterrupt:
    print("\nStopping...")
    for p in procs:
        p.terminate()

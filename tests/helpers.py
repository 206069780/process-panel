import json
import subprocess
import sys


def listening_child():
    code = """
import json, socket, time
tcp = socket.socket()
tcp.bind(('127.0.0.1', 0))
tcp.listen()
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('127.0.0.1', 0))
print(json.dumps({'tcp': tcp.getsockname()[1], 'udp': udp.getsockname()[1]}), flush=True)
time.sleep(120)
"""
    child = subprocess.Popen(
        [getattr(sys, '_base_executable', sys.executable), "-u", "-c", code], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    ports = json.loads(child.stdout.readline())
    return child, ports


def cleanup_child(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=10)

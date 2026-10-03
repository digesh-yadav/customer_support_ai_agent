"""
One-command launcher for the Multi-Agent Support Desk.

    python run.py

Workflow
--------
  TASK 1  Check / install requirements.txt
  BREAK
  TASK 2  Load the backend (backend/app/main.py) on its own port
  ERROR CHECK  -> error: show it and stop   |   success: continue
  BREAK
  TASK 3  Serve the frontend (frontend/index.html) on a DIFFERENT port,
          pre-wired to the backend port, and open the browser.

Ports: the backend and frontend never share a port. Defaults are 8000 / 5500;
if one is busy the next free port is used automatically.
"""
import argparse
import http.server
import importlib.metadata as md
import os
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
REQUIREMENTS = ROOT / "requirements.txt"

HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 8000
BACKEND_APP = "app.main:app"      # module path, relative to backend/
BACKEND_START_TIMEOUT = 30        # seconds to wait for /api/health


# ----------------------------------------------------------------- helpers
def step(title):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def info(msg):
    print(f"  {msg}")


def fail(msg, backend=None):
    print(f"\n  ERROR: {msg}\n", file=sys.stderr)
    if backend is not None:
        stop_process(backend)
    sys.exit(1)


def brk(seconds=1.0):
    """The 'BREAK' between tasks: a short pause so each stage is readable."""
    time.sleep(seconds)


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def pick_port(preferred, taken=()):
    """First free port >= preferred that is not in `taken`."""
    for port in range(preferred, preferred + 100):
        if port not in taken and port_is_free(port):
            return port
    fail(f"No free port found near {preferred}.")


def stop_process(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def load_env_file(path):
    """Tiny .env reader (KEY=VALUE) so backend/.env works without extra packages."""
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if value.strip():
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env



# ------------------------------------------------------------- virtualenv
VENV_DIR = ROOT / ".venv"


def in_venv():
    return sys.prefix != sys.base_prefix


def venv_python():
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def rerun_in_venv():
    """Re-launch this same script using the project's .venv interpreter."""
    code = subprocess.call([str(venv_python()), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit(code)


def create_venv_and_rerun():
    info("System Python is 'externally managed' -> creating a local .venv instead...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        fail("Could not create .venv (on Debian/Ubuntu try: sudo apt install python3-venv).")
    rerun_in_venv()

# ------------------------------------------------------ TASK 1: requirements
def requirement_satisfied(line):
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
    if not m:
        return True
    name, spec = m.group(1), m.group(2).strip()
    try:
        installed = md.version(name)
    except md.PackageNotFoundError:
        return False
    if spec:
        try:
            from packaging.specifiers import SpecifierSet
            return SpecifierSet(spec).contains(installed, prereleases=True)
        except Exception:
            return True   # can't compare versions -> accept what's installed
    return True


def task1_requirements():
    step("TASK 1 - Checking requirements")
    if not REQUIREMENTS.exists():
        fail(f"{REQUIREMENTS.name} not found.")
    lines = [l.strip() for l in REQUIREMENTS.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    missing = [l for l in lines if not requirement_satisfied(l)]
    if not missing:
        info(f"All {len(lines)} requirements already satisfied.")
        return
    info("Missing / outdated: " + ", ".join(missing))
    info("Installing... (this can take a minute the first time)")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)],
        capture_output=True, text=True)
    if result.returncode != 0:
        if "externally-managed-environment" in result.stderr and not in_venv():
            create_venv_and_rerun()          # does not return
        print(result.stdout + result.stderr, file=sys.stderr)
        fail("pip install failed (see output above).")
    info("Requirements installed.")


# --------------------------------------------------------- TASK 2: backend
def task2_backend(port):
    step("TASK 2 - Loading backend")
    info(f"Entry point : backend/{BACKEND_APP.replace('.', '/').replace(':app', '')}.py")

    env = {**os.environ, **load_env_file(BACKEND_DIR / ".env"), "PYTHONUNBUFFERED": "1"}

    # Import check first: surfaces syntax / import / DB-init errors with a clean traceback.
    check = subprocess.run(
        [sys.executable, "-c", f"import {BACKEND_APP.split(':')[0]}"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    if check.returncode != 0:
        print(check.stderr, file=sys.stderr)
        fail("Backend failed to load (see traceback above).")
    info("Backend module imports cleanly.")

    info(f"Starting server on http://{HOST}:{port} ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", BACKEND_APP, "--host", HOST, "--port", str(port)],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1)

    tail = deque(maxlen=40)   # keep recent output so we can show it if startup fails

    def pump():
        for line in proc.stdout:
            tail.append(line.rstrip())
            print(f"  [backend] {line.rstrip()}")
    threading.Thread(target=pump, daemon=True).start()
    return proc, tail


def error_check(proc, tail, port):
    step("ERROR CHECK - Is the backend alive?")
    url = f"http://{HOST}:{port}/api/health"
    deadline = time.time() + BACKEND_START_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            time.sleep(0.3)
            print("\n".join(tail), file=sys.stderr)
            fail(f"Backend exited early with code {proc.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    info(f"OK - backend answered {url}")
                    return
        except Exception:
            time.sleep(0.4)
    print("\n".join(tail), file=sys.stderr)
    fail(f"Backend did not respond within {BACKEND_START_TIMEOUT}s.", proc)


# -------------------------------------------------------- TASK 3: frontend
def make_frontend_handler(backend_port):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(FRONTEND_DIR), **kw)

        def do_GET(self):
            # Serve config.js on the fly so the frontend always points at the
            # backend port chosen above (no file edits needed).
            if self.path.split("?")[0] == "/js/config.js":
                body = (f'// generated by run.py\n'
                        f'const API_BASE = "http://{HOST}:{backend_port}";\n').encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, fmt, *args):
            pass   # keep the console quiet

    return Handler


def task3_frontend(frontend_port, backend_port, open_browser):
    step("TASK 3 - Starting frontend")
    if not (FRONTEND_DIR / "index.html").exists():
        fail("frontend/index.html not found.")

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        server = Server((HOST, frontend_port), make_frontend_handler(backend_port))
    except OSError as e:
        fail(f"Could not start frontend on port {frontend_port}: {e}")
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://{HOST}:{frontend_port}"
    info(f"Frontend : {url}  (talks to backend on port {backend_port})")
    if open_browser:
        webbrowser.open(url)
    return server, url


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Start the Multi-Agent Support Desk")
    ap.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    ap.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    if sys.version_info < (3, 9):
        fail("Python 3.9+ is required.")
    if not in_venv() and venv_python().exists():
        rerun_in_venv()                      # use the project's .venv if it exists

    task1_requirements()
    brk()

    backend_port = pick_port(args.backend_port)
    frontend_port = pick_port(args.frontend_port, taken={backend_port})   # never the same port
    for label, wanted, got in (("Backend", args.backend_port, backend_port),
                               ("Frontend", args.frontend_port, frontend_port)):
        if wanted != got:
            info(f"{label} port {wanted} is busy -> using {got}")

    proc, tail = task2_backend(backend_port)
    error_check(proc, tail, backend_port)
    brk()

    server, url = task3_frontend(frontend_port, backend_port, not args.no_browser)

    step("RUNNING")
    info(f"App      : {url}")
    info(f"API docs : http://{HOST}:{backend_port}/docs")
    info("Press Ctrl+C to stop both servers.\n")

    try:
        while True:
            if proc.poll() is not None:
                print("\n".join(tail), file=sys.stderr)
                fail(f"Backend stopped unexpectedly (code {proc.returncode}).")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        server.shutdown()
        stop_process(proc)


if __name__ == "__main__":
    main()

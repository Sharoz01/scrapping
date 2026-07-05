import subprocess
import sys
import os
import time
import signal

def run_cmd(args, cwd=None, shell=False):
    print(f"Running: {' '.join(args)} in {cwd or '.'}")
    return subprocess.check_call(args, cwd=cwd, shell=shell)

def main():
    print("="*60)
    print("Starting Accelerator Lead Gen React + FastAPI App...")
    print("="*60)

    # 1. Install Backend Dependencies
    print("\n[Step 1/4] Checking/Installing FastAPI & Uvicorn...")
    run_cmd([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "pydantic"])

    # 2. Check/Install Playwright browser (in case they don't have it installed)
    print("\n[Step 2/4] Ensuring Playwright browser is ready...")
    try:
        run_cmd([sys.executable, "-m", "playwright", "install", "chromium"])
    except Exception as e:
        print(f"Playwright browser check/install skipped or encountered warning: {e}")

    # 3. Install Frontend NPM dependencies
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    print(f"\n[Step 3/4] Installing React NPM dependencies in {frontend_dir}...")
    try:
        # Detect if yarn or npm is used. We use npm
        if os.name == 'nt': # Windows
            run_cmd(["npm.cmd", "install"], cwd=frontend_dir)
        else: # macOS/Linux
            run_cmd(["npm", "install"], cwd=frontend_dir)
    except Exception as e:
        print(f"Error running npm install: {e}")
        print("Please make sure Node.js and npm are installed on your machine.")
        sys.exit(1)

    # 4. Launch Backend API and Frontend App concurrently
    print("\n[Step 4/4] Launching FastAPI Backend (Port 8000) & Vite React Frontend (Port 5173)...")
    
    # We will launch uvicorn on port 8000 and vite on standard dev port
    backend_cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    
    if os.name == 'nt':
        frontend_cmd = ["npm.cmd", "run", "dev"]
    else:
        frontend_cmd = ["npm", "run", "dev"]

    processes = []
    try:
        # Start backend
        backend_proc = subprocess.Popen(backend_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(backend_proc)
        
        # Start frontend
        frontend_proc = subprocess.Popen(frontend_cmd, cwd=frontend_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(frontend_proc)
        
        print("\n🚀 App is launching! Open your browser at:")
        print("   👉 Frontend UI: http://localhost:5173")
        print("   👉 Backend API: http://localhost:8000/docs")
        print("\nPress Ctrl+C to stop both servers at any time.\n")

        # Set stdout reading threads or simple polling print loop
        import threading
        
        def pipe_output(name, process):
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[{name}] {line.strip()}")
            process.stdout.close()

        threading.Thread(target=pipe_output, args=("API", backend_proc), daemon=True).start()
        threading.Thread(target=pipe_output, args=("Vite", frontend_proc), daemon=True).start()

        # Keep parent script alive and catch keyboard interrupt
        while True:
            # Check if any process exited
            for proc in processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"\n[SYSTEM] A subprocess has terminated (exit code {ret}). Exiting.")
                    return
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[SYSTEM] Terminating servers...")
    finally:
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        print("[SYSTEM] Both processes shutdown successfully.")

if __name__ == "__main__":
    main()

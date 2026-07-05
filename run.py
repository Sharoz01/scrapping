import subprocess
import sys
import os

def run_cmd(args):
    print(f"Running: {' '.join(args)}")
    subprocess.check_call(args)

def main():
    print("="*60)
    print("Initializing Accelerator Lead Gen Setup & Launch...")
    print("="*60)
    
    # 1. Install dependencies
    print("\n[Step 1/3] Installing Python dependencies...")
    run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # 2. Install Playwright browser
    print("\n[Step 2/3] Checking and installing Playwright Chromium browser...")
    run_cmd([sys.executable, "-m", "playwright", "install", "chromium"])
    
    # 3. Launch Streamlit app
    print("\n[Step 3/3] Launching Streamlit Web App...")
    run_cmd([sys.executable, "-m", "streamlit", "run", "app.py"])

if __name__ == "__main__":
    main()

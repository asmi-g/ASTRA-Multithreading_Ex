import subprocess
import threading
import time
import sys
import os
import signal
import platform
import numpy as np
import csv

DATA_DIR = "Data/"
TX_SCRIPT = "TX.py"
RX_SCRIPT = "RX.py"
MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds
FILE_WAIT_TIMEOUT = 30  # seconds

def install_requirements():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except subprocess.CalledProcessError:
        print("⚠️ Failed to install some packages. Continuing anyway...")

def run_flowgraph(script_path):
    if platform.system() == "Windows":
        return subprocess.Popen(["python", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        return subprocess.Popen(["python3", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)

def terminate_process(proc):
    if proc.poll() is None:  # still running
        if platform.system() == "Windows":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

def wait_for_data(file_path, timeout=FILE_WAIT_TIMEOUT):
    for _ in range(timeout):
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return True
        time.sleep(1)
    return False

def check_for_soapy_timeout(proc):
    try:
        stdout, stderr = proc.communicate(timeout=5)
        stderr_text = stderr.decode("utf-8").lower()
        return "soapy" in stderr_text and "timeout" in stderr_text
    except subprocess.TimeoutExpired:
        return False  # still running, assume no error

def save_to_csv(rx_file_path, tx_file_path, csv_file_path):
    rx_data = np.fromfile(open(rx_file_path), dtype=np.complex64)
    tx_data = np.fromfile(open(tx_file_path), dtype=np.complex64)

    tx_data_last = tx_data[-500000:] if len(tx_data) >= 500000 else tx_data
    rx_data_last = rx_data[-500000:] if len(rx_data) >= 500000 else rx_data

    with open(csv_file_path, mode='a', newline='') as file:  # 'a' to append
        writer = csv.writer(file)
        writer.writerow(["Index", 
                         "TX Real", "TX Imag", "TX Magnitude", 
                         "RX Real", "RX Imag", "RX Magnitude"])
        
        for i in range(len(tx_data_last)):
            tx = tx_data_last[i]
            rx = rx_data_last[i] if i < len(rx_data_last) else 0
            writer.writerow([
                i, 
                np.real(tx), np.imag(tx), np.abs(tx), 
                np.real(rx), np.imag(rx), np.abs(rx)
            ])

def main():
    install_requirements()

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n🚀 Attempt {attempt} of {MAX_RETRIES}...\n")

        tx_proc = run_flowgraph(TX_SCRIPT)
        rx_proc = run_flowgraph(RX_SCRIPT)

        print("⏳ Waiting for data files to be written...")
        time.sleep(5)  # give GNU Radio flowgraphs time to start

        # Check for early soapy sink timeouts
        if check_for_soapy_timeout(tx_proc) or check_for_soapy_timeout(rx_proc):
            print("⚠️ Soapy Sink Timeout detected. Restarting...")
            terminate_process(tx_proc)
            terminate_process(rx_proc)
            time.sleep(RETRY_DELAY)
            continue

        rx_ok = wait_for_data(os.path.join(DATA_DIR, "rxdata.dat"))
        tx_ok = wait_for_data(os.path.join(DATA_DIR, "txdata.dat"))

        if not (rx_ok and tx_ok):
            print("⚠️ Timeout waiting for signal files. Restarting...")
            terminate_process(tx_proc)
            terminate_process(rx_proc)
            time.sleep(RETRY_DELAY)
            continue

        print("✅ Data detected. Saving to CSV...")
        save_to_csv(os.path.join(DATA_DIR, "rxdata.dat"),
                    os.path.join(DATA_DIR, "txdata.dat"),
                    os.path.join(DATA_DIR, "signal.csv"))

        terminate_process(tx_proc)
        terminate_process(rx_proc)

        print("🎉 All tasks completed successfully.\n")
        break  # Exit loop

    else:
        print("❌ Maximum retries exceeded. Aborting.")

if __name__ == "__main__":
    main()
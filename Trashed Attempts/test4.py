import subprocess
import threading
import time
import sys
import os
import signal
import platform
import numpy as np
import csv

# Paths
DATA_DIR = "Data/"
TX_SCRIPT = "TX.py"
RX_SCRIPT = "RX.py"
CSV_PATH = os.path.join(DATA_DIR, "signal.csv")
RX_PATH = os.path.join(DATA_DIR, "rxdata.dat")
TX_PATH = os.path.join(DATA_DIR, "txdata.dat")

# Global read offsets
rx_offset = 0
tx_offset = 0

def install_requirements():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except subprocess.CalledProcessError:
        print("Failed to install some packages. Continuing anyway...")

def run_flowgraph(script_path):
    if platform.system() == "Windows":
        return subprocess.Popen(["python", script_path])
    else:
        return subprocess.Popen(["python3", script_path], preexec_fn=os.setsid)

def terminate_process(proc):
    if platform.system() == "Windows":
        proc.terminate()
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

def wait_for_data(file_path, timeout=60):
    for _ in range(timeout):
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return True
        time.sleep(1)
    return False

def incremental_save_to_csv(rx_file_path, tx_file_path, csv_file_path):
    global rx_offset, tx_offset

    try:
        with open(rx_file_path, "rb") as rx_file:
            rx_file.seek(rx_offset)
            rx_data = np.fromfile(rx_file, dtype=np.complex64)
            rx_offset += rx_data.nbytes

        with open(tx_file_path, "rb") as tx_file:
            tx_file.seek(tx_offset)
            tx_data = np.fromfile(tx_file, dtype=np.complex64)
            tx_offset += tx_data.nbytes
    except Exception as e:
        print(f"Error reading files: {e}")
        return

    if len(rx_data) == 0 or len(tx_data) == 0:
        return  # no new data

    try:
        with open(csv_file_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if os.stat(csv_file_path).st_size == 0:
                writer.writerow(["Index", "TX Real", "TX Imag", "TX Magnitude", 
                                 "RX Real", "RX Imag", "RX Magnitude"])

            for i in range(min(len(rx_data), len(tx_data))):
                tx = tx_data[i]
                rx = rx_data[i]
                writer.writerow([
                    i,
                    np.real(tx), np.imag(tx), np.abs(tx),
                    np.real(rx), np.imag(rx), np.abs(rx)
                ])
    except Exception as e:
        print(f"Error writing to CSV: {e}")

def log_csv_loop(interval_sec=5):
    while True:
        incremental_save_to_csv(RX_PATH, TX_PATH, CSV_PATH)
        time.sleep(interval_sec)

def main():
    install_requirements()

    print("Launching TX and RX scripts...")
    tx_proc = run_flowgraph(TX_SCRIPT)
    rx_proc = run_flowgraph(RX_SCRIPT)

    print("Waiting for data to be written...")
    if not (wait_for_data(RX_PATH) and wait_for_data(TX_PATH)):
        print("Timed out waiting for signal files.")
        terminate_process(tx_proc)
        terminate_process(rx_proc)
        return

    print("Data detected. Starting CSV logger...")
    csv_thread = threading.Thread(target=log_csv_loop, daemon=True)
    csv_thread.start()

    # Run system for a defined duration (e.g., 30 seconds)
    run_duration_sec = 30
    print(f"Running for {run_duration_sec} seconds...")
    time.sleep(run_duration_sec)

    print("Stopping flowgraphs...")
    terminate_process(tx_proc)
    terminate_process(rx_proc)

    # Final write after shutdown
    incremental_save_to_csv(RX_PATH, TX_PATH, CSV_PATH)
    print("CSV finalized. Done.")

if __name__ == "__main__":
    main()
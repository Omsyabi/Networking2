
from flask import Flask, jsonify, render_template
import subprocess
import re
import statistics
import socket
import ipaddress
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__, template_folder="../frontend")

TARGET = "google.com"
PING_COUNT = 5
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "network_history.json"
)



def run_latency_test():
    results = []

    for _ in range(PING_COUNT):
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", TARGET],
                capture_output=True,
                text=True,
                timeout=3
            )

            match = re.search(
                r"time[=<]\s*(\d+)ms",
                result.stdout,
                re.IGNORECASE
            )

            if match:
                results.append(float(match.group(1)))

        except (subprocess.TimeoutExpired, OSError):
            continue

    if not results:
        return {
            "success": False,
            "message": "No response received from " + TARGET
        }

    average = sum(results) / len(results)
    jitter = (
        statistics.pstdev(results)
        if len(results) > 1 else 0.0
    )

    return {
        "success": True,
        "target": TARGET,
        "count": len(results),
        "pings_ms": results,
        "average_ms": round(average, 2),
        "jitter_ms": round(jitter, 2),
        "stable": jitter < 20
    }




def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


def get_network_name():
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5
        )

        match = re.search(
            r"^\s*SSID\s*:\s*(.+)$",
            result.stdout,
            re.MULTILINE
        )

        if match:
            return match.group(1).strip()

    except (OSError, subprocess.SubprocessError):
        pass

    return "Ethernet or unidentified network"


def ping_device(ip):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "300", str(ip)],
            capture_output=True,
            text=True,
            timeout=2
        )

        return result.returncode == 0

    except (subprocess.TimeoutExpired, OSError):
        return False


def scan_devices():
    try:
        local_ip = get_local_ip()

        
        network = ipaddress.ip_network(
            f"{local_ip}/24",
            strict=False
        )

        addresses = [
            ip for ip in network.hosts()
            if str(ip) != local_ip
        ]

        with ThreadPoolExecutor(max_workers=50) as executor:
            list(executor.map(ping_device, addresses))

        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=5
        )

        devices = {}

        for line in result.stdout.splitlines():
            match = re.search(
                r"(\d+\.\d+\.\d+\.\d+)\s+"
                r"([0-9a-fA-F-]{17})\s+(\w+)",
                line
            )

            if not match:
                continue

            ip, mac, entry_type = match.groups()
            address = ipaddress.ip_address(ip)

            if address not in network or ip == local_ip:
                continue

            if mac.lower() == "ff-ff-ff-ff-ff-ff":
                continue

            devices[ip] = {
                "ip": ip,
                "mac": mac.upper().replace("-", ":"),
                "status": (
                    "Dynamic"
                    if entry_type.lower() == "dynamic"
                    else "Static"
                )
            }

        return {
            "success": True,
            "local_ip": local_ip,
            "network": str(network),
            "count": len(devices),
            "devices": list(devices.values())
        }

    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return {
            "success": False,
            "message": str(error),
            "count": 0,
            "devices": []
        }




def get_network_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            history = json.load(file)

        return history if isinstance(history, list) else []

    except (json.JSONDecodeError, OSError):
        return []


def save_network_record():
    record = {
        "network_name": get_network_name(),
        "local_ip": get_local_ip(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%I:%M:%S %p")
    }

    history = get_network_history()
    history.insert(0, record)

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=4)

    return record


# ---------------- FLASK ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan")
def scan():
    return jsonify(run_latency_test())


@app.route("/devices")
def devices():
    return jsonify(scan_devices())


@app.route("/record-network", methods=["POST"])
def record_network():
    try:
        record = save_network_record()

        return jsonify({
            "success": True,
            "record": record
        })

    except (OSError, ValueError) as error:
        return jsonify({
            "success": False,
            "message": str(error)
        }), 500


@app.route("/network-history")
def network_history():
    return jsonify({
        "success": True,
        "history": get_network_history()
    })


if __name__ == "__main__":
    app.run(debug=True)

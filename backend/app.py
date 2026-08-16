from flask import Flask, jsonify, render_template
import subprocess
import re
import statistics

app = Flask(__name__, template_folder="../frontend")

TARGET = "google.com"
PING_COUNT = 5


def run_latency_test():
    results = []

    for i in range(PING_COUNT):
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", TARGET],
            capture_output=True,
            text=True,
        )

        # Parse "time=XXms" or "time<1ms" out of Windows ping output
        match = re.search(r"time[=<](\d+)ms", result.stdout)
        if match:
            results.append(float(match.group(1)))

    if not results:
        return {
            "success": False,
            "message": "No response received",
        }

    avg_latency = sum(results) / len(results)
    jitter = statistics.pstdev(results) if len(results) > 1 else 0.0

    is_stable = jitter < 20

    return {
        "success": True,
        "target": TARGET,
        "count": len(results),
        "pings_ms": [round(r, 2) for r in results],
        "average_ms": round(avg_latency, 2),
        "jitter_ms": round(jitter, 2),
        "stable": is_stable,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan")
def scan():
    data = run_latency_test()
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)
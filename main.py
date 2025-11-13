#!/usr/bin/env python3
import os, sys
import time
import threading
import secrets
import uuid
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, render_template, abort, send_from_directory

try:
    import webview
except Exception:
    webview = None

from utils.backend import WalletChecker

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


GUI_DIR = os.path.join(BASE_DIR, "gui")
ASSETS_DIR = os.path.join(GUI_DIR, "assets")

if not os.path.isdir(GUI_DIR):
    raise RuntimeError("gui/ directory not found; ensure gui/index.html exists")

app = Flask(__name__, static_folder=ASSETS_DIR, static_url_path="/assets", template_folder=GUI_DIR)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 1
app.config["APP_TOKEN"] = secrets.token_urlsafe(20)

checker = WalletChecker()

# in-memory job store
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _is_positive(result: Dict[str, Any]) -> bool:
    typ = result.get("type", "")
    if typ == "EVM":
        for v in result.get("balances", {}).values():
            try:
                if float(v.get("balance", 0)) > 0:
                    return True
            except Exception:
                pass
        for chain_tokens in result.get("token_balances", {}).values():
            for tok in chain_tokens.values():
                try:
                    if float(tok.get("balance", 0)) > 0:
                        return True
                except Exception:
                    pass
        return False
    elif typ == "TRX":
        for tok_info in result.get("balances", {}).values():
            try:
                if float(tok_info.get("balance", 0)) > 0:
                    return True
            except Exception:
                pass
        return False
    elif typ == "SOL":
        try:
            if float(result.get("balance", 0)) > 0:
                return True
        except Exception:
            pass
        for tok_info in result.get("token_balances", {}).get("SOL", {}).values():
            try:
                if float(tok_info.get("balance", 0)) > 0:
                    return True
            except Exception:
                pass
        return False
    return False



def verify_token(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = None
        if request.is_json:
            payload = request.get_json(silent=True)
            if isinstance(payload, dict):
                token = payload.get("token")
        if not token:
            token = request.headers.get("X-APP-TOKEN")
        if token != app.config.get("APP_TOKEN"):
            return jsonify({"error": "authentication error"}), 401
        return f(*args, **kwargs)
    return wrapper


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/")
def index():
    return render_template("index.html", token=app.config.get("APP_TOKEN"))

@app.route("/_token", methods=["GET"])
def get_token():
    return jsonify({"token": app.config.get("APP_TOKEN")})

@app.route("/check", methods=["POST"])
@verify_token
def check():
    payload = request.get_json(force=True, silent=True) or {}
    addresses = payload.get("addresses")
    if not isinstance(addresses, list):
        return abort(400, "addresses must be a list")
    include_empty = bool(payload.get("include_empty", False))

    valid_addrs = []
    invalid = []
    for a in addresses:
        if not isinstance(a, str) or not a.strip():
            invalid.append(a)
            continue
        typ = checker.detect_wallet_type(a.strip())
        if typ == "UNKNOWN":
            invalid.append(a)
        else:
            valid_addrs.append(a.strip())

    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "addresses": valid_addrs,
        "include_empty": include_empty,
        "results": [],
        "invalid": invalid,
        "total": len(addresses),
        "valid": len(valid_addrs),
        "checked": 0,
        "errors": [],
        "status": "running",
        "started_at": time.time(),
    }
    with _jobs_lock:
        _jobs[job_id] = job

    def _run_job(j):
        try:
            max_workers = min(20, max(1, len(j["addresses"])))
            pending_results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(checker.get_balance, addr): addr for addr in j["addresses"]}
                for future in as_completed(futures):
                    addr = futures[future]
                    try:
                        res = future.result()
                    except Exception as e:
                        with _jobs_lock:
                            j["errors"].append({"address": addr, "error": str(e)})
                            j["checked"] += 1
                        continue

                    positive = _is_positive(res)
                    res["_positive"] = positive

                    with _jobs_lock:
                        j["checked"] += 1
                        if positive or j["include_empty"]:
                            j["results"].append(res)
            with _jobs_lock:
                j["status"] = "done"
                j["finished_at"] = time.time()
        except Exception as outer:
            with _jobs_lock:
                j["errors"].append({"error": f"job-failed: {outer}"})
                j["status"] = "done"
                j["finished_at"] = time.time()

    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "total": job["total"], "valid": job["valid"], "invalid": job["invalid"]})

@app.route("/jobs/<job_id>/poll", methods=["GET"])
@verify_token
def poll(job_id):
    since = int(request.args.get("since", 0))
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404

        results = job["results"][since:]
        stats = {
            "total": job["total"],
            "valid": job["valid"],
            "checked": job["checked"],
            "positive_shown": len(job["results"]),
            "status": job["status"],
            "errors_count": len(job["errors"]),
        }
        done = job["status"] == "done"

    return jsonify({"new_results": results, "stats": stats, "done": done})


@app.route("/jobs/<job_id>/status", methods=["GET"])
@verify_token
def job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        stats = {
            "total": job["total"],
            "valid": job["valid"],
            "checked": job["checked"],
            "positive_shown": len(job["results"]),
            "status": job["status"],
            "errors_count": len(job["errors"]),
        }
    return jsonify({"stats": stats, "invalid": job["invalid"]})


def start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)


def main():
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    time.sleep(0.25)
    url = "http://127.0.0.1:5000"
    if webview:
        window = webview.create_window("BALCHE", url, width=600, resizable=False)
        webview.start(debug=False)
    else:
        print(f"Open your browser at {url}")
        try:
            t.join()
        except KeyboardInterrupt:
            print("shutting down")


if __name__ == "__main__":
    main()

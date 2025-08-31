#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gann Decoder Flask App (Ready-to-run)
- Uses Twelve Data time_series endpoint for OHLC data
- Detects pivots (swing highs/lows), matches repeating time cycles to candidate Gann cycles,
  projects next turning dates, and streams progress via Server-Sent Events (SSE).
- Saves results to data/results.csv (updates existing rows by symbol+predicted_date)
"""

import os, time, json, traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file, abort
import requests
import pandas as pd
import numpy as np
import pytz

# ================= CONFIG =================
# Paste your Twelve Data API key here (or set TWELVE_DATA_API_KEY env var)
API_KEY = "PASTE_YOUR_TWELVE_API_KEY_HERE"
if os.environ.get("TWELVE_DATA_API_KEY"):
    API_KEY = os.environ.get("TWELVE_DATA_API_KEY")

# Candidate cycles we care about (Gann-like)
CANDIDATE_CYCLES = [30,45,60,72,84,90,108,120,126,144,168,180,216,240,252,270,288,300,315,324,336,360,420,450,480,500]

# Data/cache paths
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
RESULTS_CSV = os.path.join(os.path.dirname(__file__), "data", "results.csv")
os.makedirs(os.path.dirname(RESULTS_CSV), exist_ok=True)

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Full F&O list (example / common underlyings).
FNO_SYMBOLS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","AXISBANK","SBIN","LT","ITC","BHARTIARTL",
    "HINDUNILVR","HDFC","KOTAKBANK","BAJFINANCE","MARUTI","TITAN","POWERGRID","ASIANPAINT","ULTRACEMCO","WIPRO",
    "ADANIENT","ADANIPORTS","NTPC","ONGC","SUNPHARMA","TATASTEEL","TATAMOTORS","HCLTECH","M&M","TECHM",
    "BPCL","BRITANNIA","CIPLA","EICHERMOT","GRASIM","HDFCLIFE","JSWSTEEL","NESTLEIND","TATACONSUM","HINDALCO",
    "DIVISLAB","COALINDIA","DRREDDY","BAJAJFINSV","HEROMOTOCO","SBICARD","DLF","INDUSINDBK","ICICIPRULI","LUPIN",
    "SIEMENS","PIDILITIND","GODREJCP","LICHSGFIN","ACC","AMBUJACEM","DMART","BANDHANBNK","UPL","PNB",
    "CANBK","IDFCFIRSTB","BANKBARODA","IRCTC","GLENMARK","MUTHOOTFIN","MANAPPURAM","SRF","MFSL","BOSCHLTD",
    "MINDTREE","AUBANK","MCDOWELL-N","DABUR","PAGEIND","APOLLOHOSP","AUROPHARMA","BERGEPAINT","BIOCON","CHOLAFIN",
    "CONCOR","COLPAL","DEEPAKNTR","FEDERALBNK","GAIL","HAL","HAVELLS","ICICIGI","IGL","INDIGO",
    "JKCEMENT","JINDALSTEL","LTIM","NAUKRI","PIIND","PVR","INOXLEISUR","RECLTD","SHREECEM","TORNTPHARM",
    "TVSMOTOR","VEDL","VOLTAS","ZEEL","ZOMATO","ADANITRANS","ADANIGREEN","TATAPOWER","SBILIFE","HDFCAMC",
    "SRTRANSFIN","PEL","TATAELXSI","CROMPTON","BHEL","NMDC","EXIDEIND","POLYCAB","HINDPETRO"
]

def chunk_list(lst, n=20):
    return [lst[i:i+n] for i in range(0, len(lst), n)]

GROUPS = chunk_list(FNO_SYMBOLS, 20)

# ================= Helpers ==================

def ist_now():
    return datetime.now(IST)

def fetch_time_series(symbol: str, interval: str = "1day", outputsize: int = 800) -> pd.DataFrame:
    base_url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "exchange": "NSE",
        "interval": interval,
        "outputsize": outputsize,
        "order": "ASC",
        "apikey": API_KEY
    }
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_{interval}.json")
    try:
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                cached = json.load(f)
            vals = cached.get("values", [])
            if vals:
                latest = vals[-1]["datetime"]
                try:
                    start_date = (pd.to_datetime(latest) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                    p2 = dict(params); p2["start_date"] = start_date
                    r = requests.get(base_url, params=p2, timeout=20)
                    r.raise_for_status()
                    data = r.json()
                    if data.get("values"):
                        new_vals = sorted(data["values"], key=lambda x: x.get("datetime"))
                        merged = vals + [v for v in new_vals if v["datetime"] not in {x["datetime"] for x in vals}]
                        with open(cache_file, "w") as f:
                            json.dump({"values": merged}, f)
                        vals = merged
                except Exception:
                    pass
                df = pd.DataFrame(vals)
                if not df.empty:
                    df = df.rename(columns={"datetime":"date"})
                    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
                    for c in ["open","high","low","close","volume"]:
                        if c in df.columns:
                            df[c] = pd.to_numeric(df[c], errors="coerce")
                    df = df.dropna(subset=["open","high","low","close"])
                    return df.reset_index(drop=True)
        r = requests.get(base_url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        if "values" not in data:
            raise RuntimeError(f"Twelve Data returned no values for {symbol}: {data.get('message') or data}")
        vals = sorted(data["values"], key=lambda x: x.get("datetime"))
        with open(cache_file, "w") as f:
            json.dump({"values": vals}, f)
        df = pd.DataFrame(vals)
        df = df.rename(columns={"datetime":"date"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        for c in ["open","high","low","close","volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open","high","low","close"])
        return df.reset_index(drop=True)
    except Exception as e:
        raise RuntimeError(f"Fetch failed for {symbol}: {e}")

def find_pivots(df: pd.DataFrame, window: int = 3):
    highs=[]; lows=[]
    N = len(df)
    if N < 2*window+1:
        return highs, lows
    for i in range(window, N-window):
        seg = df.iloc[i-window:i+window+1]
        mid = df.iloc[i]
        if mid["high"] == seg["high"].max():
            highs.append(pd.to_datetime(mid["date"]).date())
        if mid["low"] == seg["low"].min():
            lows.append(pd.to_datetime(mid["date"]).date())
    return highs, lows

def evaluate_cycles_from_pivots(pivot_dates: List[pd.Timestamp], candidates: List[int], tol_days: int = 6, min_hits: int = 2):
    results = []
    if not pivot_dates or len(pivot_dates) < 2:
        return results
    pivot_dates = sorted(pivot_dates)
    for c in candidates:
        hits = 0; errors = []
        trials = max(1, len(pivot_dates)-1)
        for i in range(len(pivot_dates)-1):
            base = pivot_dates[i]
            expected = base + pd.Timedelta(days=c)
            window_start = expected - pd.Timedelta(days=tol_days)
            window_end = expected + pd.Timedelta(days=tol_days)
            for j in range(i+1, len(pivot_dates)):
                d = pivot_dates[j]
                if d < window_start: continue
                if d > window_end: break
                hits += 1
                errors.append(abs((d - expected).days))
                break
        if hits >= min_hits:
            mae = float(np.mean(errors)) if errors else None
            score = hits / (1 + (mae or 0))
            results.append({"cycle": int(c), "hits": int(hits), "trials": int(trials), "hit_rate": round(hits/trials,3), "mae": mae, "score": round(score,3)})
    results.sort(key=lambda x: (x["score"], x["hits"]), reverse=True)
    return results

def predict_from_last_pivot(last_pivot: datetime.date, cycle_days: int, count: int = 2):
    out = []
    for i in range(1, count+1):
        out.append((last_pivot + pd.Timedelta(days=cycle_days*i)).strftime("%Y-%m-%d"))
    return out

def save_result_row(row: Dict[str, Any]):
    file_exists = os.path.exists(RESULTS_CSV)
    rows = []
    if file_exists:
        try:
            rows = list(pd.read_csv(RESULTS_CSV).to_dict(orient="records"))
        except Exception:
            rows = []
    key = (row.get("symbol"), int(row.get("cycle") or 0), row.get("predicted_date"))
    updated = False
    for r in rows:
        try:
            if (r.get("symbol"), int(r.get("cycle") or 0), r.get("predicted_date")) == key:
                r.update(row)
                updated = True
                break
        except Exception:
            continue
    if not updated:
        rows.append(row)
    if rows:
        with open(RESULTS_CSV, "w", newline="") as f:
            writer = pd.DataFrame(rows)
            writer.to_csv(f, index=False)
    return True

def analyze_symbol(symbol: str, candidates=CANDIDATE_CYCLES, tolerance=6):
    out = {"symbol": symbol}
    try:
        df = fetch_time_series(symbol, interval="1day", outputsize=1000)
        if df is None or df.empty or len(df) < 60:
            return {"symbol": symbol, "status":"error", "error":"Insufficient data"}
        highs, lows = find_pivots(df, window=3)
        high_matches = evaluate_cycles_from_pivots(highs, candidates, tol_days=tolerance)
        low_matches = evaluate_cycles_from_pivots(lows, candidates, tol_days=tolerance)
        preds = []
        last_high = max(highs) if highs else None
        last_low = max(lows) if lows else None
        for m in high_matches[:3]:
            p_dates = predict_from_last_pivot(last_high, m["cycle"], count=2) if last_high else []
            preds.append({"type":"high", "cycle": m["cycle"], "hit_rate": m["hit_rate"], "mae": m["mae"], "preds": p_dates})
        for m in low_matches[:3]:
            p_dates = predict_from_last_pivot(last_low, m["cycle"], count=2) if last_low else []
            preds.append({"type":"low", "cycle": m["cycle"], "hit_rate": m["hit_rate"], "mae": m["mae"], "preds": p_dates})
        today = pd.to_datetime(datetime.now(IST).date())
        upcoming = []
        for p in preds:
            for pd_s in p["preds"]:
                dt = pd.to_datetime(pd_s)
                days_until = (dt - today).days
                upcoming.append((abs(days_until), days_until, p))
        upcoming.sort(key=lambda x: (x[0], - (x[2].get("hit_rate") or 0)))
        chosen = upcoming[0][2] if upcoming else None
        out.update({
            "status":"ok",
            "last_date": df["date"].max().strftime("%Y-%m-%d"),
            "num_high_pivots": len(highs),
            "num_low_pivots": len(lows),
            "high_matches": high_matches,
            "low_matches": low_matches,
            "predictions": preds,
            "chosen": chosen
        })
        if chosen:
            pred_date = None
            if chosen.get("preds"):
                pred_date = chosen["preds"][0]
            row = {
                "symbol": symbol,
                "cycle": chosen.get("cycle"),
                "type": chosen.get("type"),
                "predicted_date": pred_date,
                "hit_rate": chosen.get("hit_rate"),
                "mae": chosen.get("mae"),
                "saved_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
            }
            try:
                save_result_row(row)
            except Exception:
                pass
        return out
    except Exception as e:
        return {"symbol": symbol, "status":"error", "error": str(e), "trace": traceback.format_exc()}

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def index():
    labels = [f"List {i+1}" for i in range(len(GROUPS))]
    return render_template("index.html", groups=labels, default_group=0)

def sse_format(data: dict) -> str:
    return f"data: {json.dumps(data)}\\n\\n"

@app.route("/scan_stream", methods=["POST"])
def scan_stream():
    payload = request.get_json(silent=True) or {}
    group_idx = int(payload.get("group_idx", 0))
    tolerance = int(payload.get("tolerance", 6))
    symbols = GROUPS[group_idx]

    @stream_with_context
    def gen():
        yield sse_format({"event":"start", "message": f"Starting scan for group {group_idx+1} ({len(symbols)} symbols)"})
        for i, sym in enumerate(symbols, start=1):
            try:
                yield sse_format({"event":"progress", "symbol": sym, "index": i, "total": len(symbols), "message": f"Analyzing {sym}..."})
                res = analyze_symbol(sym, candidates=CANDIDATE_CYCLES, tolerance=tolerance)
                yield sse_format({"event":"result", "symbol": sym, "result": res})
            except Exception as e:
                yield sse_format({"event":"result", "symbol": sym, "result": {"symbol": sym, "status":"error", "error": str(e)}})
            time.sleep(0.6)
        yield sse_format({"event":"done", "message":"Scan complete"})
    return Response(gen(), mimetype="text/event-stream")

@app.route("/history", methods=["GET"])
def history():
    if not os.path.exists(RESULTS_CSV):
        return jsonify([])
    try:
        df = pd.read_csv(RESULTS_CSV)
        return df.to_dict(orient="records")
    except Exception:
        return jsonify([])

@app.route("/download_results", methods=["GET"])
def download_results():
    if not os.path.exists(RESULTS_CSV):
        return abort(404, description="No results yet")
    return send_file(RESULTS_CSV, as_attachment=True, download_name="gann_results.csv")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

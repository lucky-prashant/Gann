Gann Decoder - Ready-to-deploy Flask app
---------------------------------------

What's included:
- app.py: Flask backend implementing a Gann-style time-cycle decoder (pivot detection + cycle matching)
- templates/index.html: UI with dropdown lists (groups of 20 symbols) and a Scan button that displays live progress via SSE
- requirements.txt: pinned, wheel-friendly packages for Render
- runtime.txt: specifies Python 3.11 (recommended for Render)
- Procfile: for Render / Heroku (gunicorn)
- data/results.csv: will be created/updated by the app to store results

How to run locally:
1) unzip the package
2) python -m venv venv && source venv/bin/activate
3) pip install -r requirements.txt
4) (Optional) edit API_KEY in app.py to paste your Twelve Data API key directly
5) python app.py
6) open http://localhost:5000

How to deploy to Render:
1) Create a new Web Service on Render and connect your GitHub repo (or upload this repo)
2) Use the default build command (pip install -r requirements.txt)
3) Ensure runtime.txt exists (we set python-3.11.9)
4) Start command uses the Procfile

Notes about Gann decoder implementation:
- This app focuses on Gann-style time cycles (candidate cycles like 30,45,60,90,144,180,360,500 days)
- It detects swing highs/lows (pivots), measures repeating gaps, and matches to candidate cycles
- Next-turn predictions are projected from the last pivot for matched cycles
- A confluence/confidence score is calculated per symbol
- The UI streams progress so you can scan groups of 20 symbols without waiting silently

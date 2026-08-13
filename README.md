# Production-Ready Material Search Suggestion System

A lightweight, scalable, and production-quality material search suggestion engine built with **Python (FastAPI)**, **Typesense (Native macOS binary)**, and **Vanilla JavaScript/CSS**. 

This project provides Google/Amazon-style autocomplete suggestions across a material master dataset without requiring Docker.

---

## Architecture Overview

```text
material-search/
│
├── app.py                   # FastAPI Application (Endpoints & Static Mounting)
├── config.py                # Centralized Environment Configuration
├── requirements.txt         # Python Dependencies
├── .env                     # Local Environment Secrets & Host settings
├── README.md                # System Documentation & Runbook
│
├── data/                    # Storage for Raw and Cleaned CSV datasets
│   ├── materials_raw.csv
│   └── materials.csv
│
├── scripts/                 # Data Pipeline Scripts
│   ├── preprocess.py        # Deduplication & Cleaning Pipeline
│   ├── create_collection.py # Typesense Schema Definition
│   └── index_data.py        # Batch Indexing Script
│
├── search/                  # Isolated Search & Ranking Domain Logic
│   └── search.py
│
├── templates/               # Jinja2 Frontend Templates
│   └── index.html
│
├── static/                  # Client-Side Assets
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
│
└── logs/                    # Runtime Application Logs
    └── app.log



1. Prerequisites & Native Typesense Server Setup (macOS)
Option B: Direct Binary (Apple Silicon / Intel)
# Download for Apple Silicon (M1/M2/M3/M4)
curl -O [https://dl.typesense.org/releases/27.1/typesense-server-27.1-darwin-arm64.tar.gz](https://dl.typesense.org/releases/27.1/typesense-server-27.1-darwin-arm64.tar.gz)
tar -xzf typesense-server-27.1-darwin-arm64.tar.gz

# Start server
mkdir -p typesense-data
./typesense-server --data-dir=./typesense-data --api-key=xyz123secret --enable-cors

Verify Typesense is running:
curl http://localhost:8108/health
# Expected Output: {"ok":true}


2. Environment Setup
# 1. Clone or navigate to the project directory
cd material-search

# 2. Create a virtual environment
python3 -m venv venv

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt


3. Configuration (.env)
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=xyz123secret
TYPESENSE_COLLECTION_NAME=materials
DEBUG=True
PORT=8000


4. Running the Data Pipeline

1. Start Typesense Server (Terminal Tab 1)
./typesense-server --data-dir=./typesense-data --api-key=xyz123secret --enable-cors

2. Preprocess the Data (Terminal Tab 2)
Run your preprocessing script to clean materials.csv (or create the final processed CSV):
python -m scripts.preprocess

3. Create / Reset Collection Schema
python -m scripts.create_collection

4. Index the Preprocessed Data
python -m scripts.index_data

5. Run app.py/Search Evaluation
python -m scripts.evaluate_search


5. Starting the Application
python app.py
Open your browser and visit: http://localhost:8000

6. Search Behaviour & Ranking Logic
Text Match Strategy
The search engine queries across four material attributes with weighted importance:

productName (Weight: 4)

brandName (Weight: 3)

productSpecification (Weight: 2)

categoryName (Weight: 1)

It supports prefix matching (e.g., typing 3m ear finds 3M Ear Plug), typo tolerance (up to 2 typos), partial words, and tokenized multi-word search.

Ranking Order
Results are ranked strictly according to:

Typesense Textual Relevance (_text_match:desc)

Inventory/Usage Score (mat_qty:desc)

Material ID Tie-Breaker (materialId:desc)

Configured as:
'sort_by': '_text_match:desc,mat_qty:desc,materialId:desc'
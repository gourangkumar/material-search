# Production-Ready Material Search Suggestion System

A lightweight, scalable, and production-quality material search suggestion engine built with **Python (FastAPI)**, **Typesense (Native macOS binary)**, and **Vanilla JavaScript/CSS**.

This project provides Google/Amazon-style autocomplete suggestions across a material master dataset without requiring Docker.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites & Typesense Setup](#prerequisites--typesense-setup)
3. [Environment Setup](#environment-setup)
4. [Configuration](#configuration)
5. [Data Pipeline](#data-pipeline)
6. [Running the Application](#running-the-application)
7. [Search Behavior & Ranking Logic](#search-behavior--ranking-logic)

---

## Architecture Overview

```
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
```

---

## Prerequisites & Typesense Setup

### Option A: Docker (Recommended for Linux/Windows)

If using Docker, start Typesense as a container:

```bash
docker run -d \
  --name typesense \
  -p 8108:8108 \
  -v typesense-data:/data \
  typesense/typesense:27.1 \
  --data-dir /data \
  --api-key xyz123secret \
  --enable-cors
```

### Option B: Native Binary (macOS - Apple Silicon / Intel)

Download and run Typesense natively on macOS:

#### Apple Silicon (M1/M2/M3/M4)

```bash
curl -O https://dl.typesense.org/releases/27.1/typesense-server-27.1-darwin-arm64.tar.gz
tar -xzf typesense-server-27.1-darwin-arm64.tar.gz
```

#### Intel macOS

```bash
curl -O https://dl.typesense.org/releases/27.1/typesense-server-27.1-darwin-amd64.tar.gz
tar -xzf typesense-server-27.1-darwin-amd64.tar.gz
```

#### Start the Typesense Server

```bash
mkdir -p typesense-data
./typesense-server --data-dir=./typesense-data --api-key=xyz123secret --enable-cors
```

#### Verify Typesense is Running

```bash
curl http://localhost:8108/health
```

Expected output:
```json
{"ok":true}
```

---

## Environment Setup

### 1. Clone or Navigate to Project Directory

```bash
cd material-search
```

### 2. Create a Virtual Environment

```bash
python3 -m venv venv
```

### 3. Activate the Virtual Environment

```bash
# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file in the project root with the following environment variables:

```env
# Typesense Configuration
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=xyz123secret
TYPESENSE_COLLECTION_NAME=materials

# Application Configuration
DEBUG=True
PORT=8000
```

**Note:** Update values based on your Typesense server configuration and deployment environment.

---

## Data Pipeline

### Step 1: Preprocess and Clean Dataset

Runs deduplication and data cleaning on raw materials CSV:

```bash
python scripts/preprocess.py
```

**Output:** `data/materials.csv` (cleaned and deduplicated)

### Step 2: Create Typesense Collection Schema

Defines the collection structure and field indexes in Typesense:

```bash
python scripts/create_collection.py
```

**Output:** Typesense collection `materials` with optimized schema

### Step 3: Index Cleaned Records

Batch indexes all cleaned records into Typesense for search:

```bash
python scripts/index_data.py
```

**Output:** Indexed materials ready for search queries

---

## Running the Application

Start the FastAPI application:

```bash
python app.py
```

**Server Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Access the Application

Open your web browser and navigate to:

```
http://localhost:8000
```

The application will display the search interface with debounced real-time suggestions.

---

## Search Behavior & Ranking Logic

### Text Match Strategy

The search engine queries across four material attributes with weighted importance:

| Attribute | Weight | Description |
|-----------|--------|-------------|
| `productName` | 4 | Primary material name (highest priority) |
| `brandName` | 3 | Manufacturer or brand |
| `productSpecification` | 2 | Technical specifications |
| `categoryName` | 1 | Material category classification |

### Matching Features

- **Prefix Matching:** Typing `3m ear` finds `3M Ear Plug`
- **Typo Tolerance:** Automatically corrects up to 2 character typos
- **Partial Words:** Matches mid-word character sequences
- **Tokenized Search:** Multi-word queries split and matched independently

### Ranking Order

Results are ranked strictly according to the following priority:

1. **Typesense Textual Relevance** (`_text_match:desc`)
   - Primary ranking by relevance to query terms

2. **Inventory/Usage Score** (`mat_qty:desc`)
   - Secondary ranking by material quantity in stock/usage

3. **Material ID Tie-Breaker** (`materialId:desc`)
   - Final ordering for consistent result pagination

**Configuration:**
```python
'sort_by': '_text_match:desc,mat_qty:desc,materialId:desc'
```

---

## Logging & Monitoring

Application logs are written to `logs/app.log`. Monitor this file for:

- API request/response metrics
- Search query performance
- Data indexing progress
- Error conditions and exceptions

```bash
# Tail logs in real-time
tail -f logs/app.log
```

---

## Troubleshooting

### Typesense Connection Error

**Error:** `Connection refused on localhost:8108`

**Solution:** Verify Typesense server is running and accessible:
```bash
curl http://localhost:8108/health
```

### Missing Data

**Error:** No results returned for valid queries

**Solution:** Ensure data pipeline has been run in order:
```bash
python scripts/preprocess.py && \
python scripts/create_collection.py && \
python scripts/index_data.py
```

### CORS Issues

**Error:** Browser blocks API requests from frontend

**Solution:** Verify Typesense is started with `--enable-cors` flag

### Python Dependency Conflicts

**Error:** ImportError or version mismatch

**Solution:** Reinstall dependencies in clean virtual environment:
```bash
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Performance Considerations

- **Typesense Index Size:** ~290K materials (adjust batch sizes in `index_data.py` for large datasets)
- **API Response Time:** < 100ms for typical queries with proper indexing
- **CORS Enabled:** Required for frontend access to Typesense and FastAPI endpoints
- **Debounced Search:** Frontend uses 300ms debounce to reduce API calls

---

## Production Deployment Checklist

- [ ] Update `.env` with production Typesense credentials
- [ ] Set `DEBUG=False` in production
- [ ] Configure HTTPS for Typesense and FastAPI
- [ ] Enable persistent volume for Typesense data
- [ ] Set up log rotation for `logs/app.log`
- [ ] Configure reverse proxy (nginx/Apache) for FastAPI
- [ ] Run data pipeline with production dataset
- [ ] Test search performance with production load
- [ ] Enable monitoring and alerting for API endpoints
- [ ] Document API rate limits and quotas

---

## License & Support

Refer to the main `README.md` file for licensing information and support guidelines.

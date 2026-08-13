import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import config
from search.search import search_service

# Logging Setup
logging.basicConfig(
    filename='logs/app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("material-search")

# Resolve absolute path to project root directory
BASE_DIR = Path(__file__).resolve().parent

# Modern Lifespan Event Handler (replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI Application Server starting up...")
    yield
    logger.info("FastAPI Application Server shutting down...")

app = FastAPI(title="Material Search Suggestion Engine", lifespan=lifespan)

# Static & Template Mounts with Absolute Path Resolution
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Updated signature for modern FastAPI/Starlette versions
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/search")
async def search_endpoint(
    q: str = Query("", description="Query string for autocomplete"),
    limit: int = Query(5, ge=1, le=10, description="Number of results (default 5, max 10)")
):
    try:
        if not q or len(q.strip()) < 1:
            return JSONResponse(content=[])

        results = search_service.suggest(query=q, limit=limit)
        return JSONResponse(content=results)

    except Exception as e:
        logger.error(f"Error handling /search request: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal search engine error. Ensure Typesense is running."}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=config.DEBUG)
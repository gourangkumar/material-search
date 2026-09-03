import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import config
from search import search_service

BASE_DIR = Path(__file__).resolve().parent
(BASE_DIR / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(BASE_DIR / "logs" / "app.log"),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("material-search")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI Application Server starting up...")
    yield
    logger.info("FastAPI Application Server shutting down...")


app = FastAPI(
    title="Material Search Suggestion Engine",
    lifespan=lifespan,
)


app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
    )


@app.get("/search")
async def search_endpoint(
    q: str = Query(
        "",
        description="Query string for autocomplete/search",
    ),
    limit: int = Query(
        5,
        ge=1,
        le=10,
        description="Number of results (default 5, max 10)",
    ),
):
    try:
        query = q.strip()

        if not query:
            return JSONResponse(content=[])

        results = search_service.suggest(
            query=query,
            limit=limit,
        )

        return JSONResponse(content=results)

    except Exception:
        logger.exception(
            "Error handling /search request for query=%r",
            q,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": (
                    "Internal search engine error. "
                    "Ensure Typesense is running."
                )
            },
        )



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=config.DEBUG,
    )

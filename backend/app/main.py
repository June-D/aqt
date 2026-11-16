from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.core.auth import AuthMiddleware
from backend.app.core.config import ROOT_DIR, get_settings
from backend.app.core.db import init_db
from backend.app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    from backend.app.intel.scheduler import intel_scheduler

    intel_scheduler.start()
    yield
    intel_scheduler.stop()


app = FastAPI(title="AQT", version="0.3.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def api_not_found(full_path: str):  # noqa: ARG001
    """未知 /api 路径统一 404，避免落到 SPA GET 通配变成 405。"""
    raise HTTPException(status_code=404, detail="Not Found")


frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # React Router deep links; never shadow /api
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = frontend_dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    run()

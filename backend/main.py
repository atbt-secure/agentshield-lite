import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .config import settings
from .database import init_db, get_db, AsyncSessionLocal
from .proxy.interceptor import interceptor, InterceptRequest
from .api import logs, policies, dashboard, stream, metrics, agents
from .middleware.auth import require_api_key
from .middleware.rate_limit import proxy_rate_limit, api_rate_limit
from .seeder import seed_default_policies

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_default_policies(session)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Runtime security gateway for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers — protected by auth + rate limiting
app.include_router(logs.router, dependencies=[Depends(require_api_key), Depends(api_rate_limit)])
app.include_router(policies.router, dependencies=[Depends(require_api_key), Depends(api_rate_limit)])
app.include_router(dashboard.router, dependencies=[Depends(require_api_key), Depends(api_rate_limit)])
app.include_router(agents.router, dependencies=[Depends(require_api_key), Depends(api_rate_limit)])
app.include_router(stream.router)   # SSE — no auth (browser EventSource can't set headers)
app.include_router(metrics.router)  # Prometheus — no auth (scraped internally)


@app.post("/proxy/intercept", dependencies=[Depends(require_api_key), Depends(proxy_rate_limit)])
async def intercept_action(req: InterceptRequest, db=Depends(get_db)):
    return await interceptor.intercept(req, db)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}


# Serve dashboard static files if they exist
dashboard_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard")


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": "0.1.0", "docs": "/docs"}

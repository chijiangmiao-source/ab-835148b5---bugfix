"""冰川洞穴染料示踪 · 最小汇流树 API。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .arborescence import Channel, ProblemError, solve, validate_problem
from .models import SolveRequest

app = FastAPI(
    title="Glacier Dye Tracing Arborescence API",
    version="1.0.0",
    description="精确最小化总代价的有向汇流树（Edmonds），含可复算环收缩记录。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        loc = "/".join(str(part) for part in e.get("loc", []))
        errors.append(f"{loc}: {e.get('msg')}")
    return JSONResponse(
        status_code=422,
        content={"status": "invalid", "reason": "请求体不符合接口规范", "errors": errors},
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/solve")
def solve_endpoint(req: SolveRequest):
    channels = [Channel(id=c.id, u=c.from_, v=c.to, cost=c.cost) for c in req.channels]
    try:
        validate_problem(req.points, req.root, channels)
    except ProblemError as err:
        return JSONResponse(
            status_code=422,
            content={"status": "invalid", "reason": err.reason, "errors": err.errors},
        )
    return solve(req.points, req.root, channels)

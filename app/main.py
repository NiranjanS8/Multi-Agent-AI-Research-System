import os
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.schemas import StructuredReport
from app.storage import (
    create_research_job,
    get_research_job,
    get_research_run,
    init_db,
    list_research_runs,
    save_research_run,
    update_research_job,
    upsert_job_step,
)


load_dotenv()
init_db()

app = FastAPI(
    title="Research Agent Console",
    description="FastAPI backend for the multi-agent research system.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=240)


class ResearchResponse(BaseModel):
    topic: str
    search_results: str
    web_scrap_results: str
    report: str
    structured_report: StructuredReport | dict[str, Any] = Field(default_factory=dict)
    feedback: str
    error: str | None = None


class ResearchHistoryItem(BaseModel):
    id: int
    topic: str
    status: str
    sources: list[dict[str, Any]]
    report: str
    feedback: str
    error: str | None = None
    created_at: str


class ResearchJobResponse(BaseModel):
    job_id: int
    topic: str
    status: str


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/research/history", response_model=list[ResearchHistoryItem])
def research_history(limit: int = 20) -> list[dict[str, Any]]:
    return list_research_runs(limit=limit)


@app.get("/api/research/history/{run_id}")
def research_history_detail(run_id: int) -> dict[str, Any]:
    item = get_research_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return item


@app.post("/api/research/jobs", response_model=ResearchJobResponse)
def create_job(request: ResearchRequest) -> dict[str, Any]:
    validate_environment()
    job_id = create_research_job(request.topic)
    return {"job_id": job_id, "topic": request.topic, "status": "pending"}


@app.get("/api/research/jobs/{job_id}")
def research_job_detail(job_id: int) -> dict[str, Any]:
    item = get_research_job(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Research job not found.")
    return item


def validate_environment() -> None:
    load_dotenv(override=True)

    missing_keys = [
        key for key in ("TAVILY_API_KEY", "MISTRAL_API_KEY") if not os.getenv(key)
    ]
    if missing_keys:
        raise HTTPException(
            status_code=503,
            detail=(
                "Missing required environment variables: "
                f"{', '.join(missing_keys)}. Add them to .env and restart the server."
            ),
        )


@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> dict[str, Any]:
    validate_environment()

    try:
        from app.pipeline import ResearchPipelineError, run_research_pipeline

        state = await run_in_threadpool(run_research_pipeline, request.topic)
    except ResearchPipelineError as exc:
        state = exc.state
        state["error"] = str(exc)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The research pipeline could not reach an external service. "
                "Check your network access, firewall permissions, and whether the server "
                f"process is allowed to call Tavily/Mistral. Original error: {exc}"
            ),
        ) from exc
    except Exception as exc:
        if (
            "API key expired" in str(exc)
            or "API_KEY_INVALID" in str(exc)
            or "Unauthorized" in str(exc)
            or "invalid api key" in str(exc).lower()
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Mistral rejected the API key. Update MISTRAL_API_KEY in .env "
                    "with a valid key, save the file, and restart Uvicorn if the error "
                    f"continues. Original error: {exc}"
                ),
            ) from exc

        if "WinError 10013" in str(exc):
            raise HTTPException(
                status_code=503,
                detail=(
                    "The research pipeline was blocked from opening a network connection. "
                    "Allow Python/Uvicorn through your firewall or run the server in an "
                    f"environment with outbound access. Original error: {exc}"
                ),
            ) from exc

        raise HTTPException(
            status_code=500,
            detail=f"Research pipeline failed: {exc}",
        ) from exc

    response = {
        "topic": request.topic,
        "search_results": str(state.get("search_results", "")),
        "web_scrap_results": str(state.get("web_scrap_results", "")),
        "report": str(state.get("report", "")),
        "structured_report": state.get("structured_report", {}),
        "feedback": str(state.get("feedback", "")),
        "error": state.get("error"),
    }
    save_research_run(
        request.topic,
        state,
        status="partial" if state.get("error") else "completed",
    )
    return response


@app.post("/api/research/stream")
def research_stream(request: ResearchRequest) -> StreamingResponse:
    validate_environment()
    job_id = create_research_job(request.topic)
    return stream_job_response(job_id, request.topic)


@app.get("/api/research/jobs/{job_id}/stream")
def research_job_stream(job_id: int) -> StreamingResponse:
    validate_environment()
    job = get_research_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found.")
    if job["status"] not in {"pending", "failed"}:
        raise HTTPException(
            status_code=409,
            detail="This job has already started or completed. Create a new job to rerun.",
        )
    return stream_job_response(job_id, job["topic"])


def stream_job_response(job_id: int, topic: str) -> StreamingResponse:

    def stream_events():
        from app.pipeline import run_research_pipeline_events

        last_state = {}
        final_status = "completed"
        update_research_job(job_id, "running")
        try:
            for event in run_research_pipeline_events(topic):
                if event.get("event") == "step_started":
                    upsert_job_step(job_id, event["step"], "running")
                if event.get("event") == "step_completed":
                    upsert_job_step(
                        job_id,
                        event["step"],
                        "completed",
                        field=event.get("field"),
                        value=str(event.get("value", "")),
                    )
                last_state = event.get("state", last_state)
                if event.get("event") == "error":
                    last_state["error"] = event.get("error")
                    final_status = "partial"
                    upsert_job_step(
                        job_id,
                        event.get("step", "unknown"),
                        "failed",
                        field=event.get("field"),
                        value=str(event.get("value", "")),
                        error=event.get("error"),
                    )
                yield json.dumps(event, ensure_ascii=False) + "\n"
            if last_state:
                run_id = save_research_run(topic, last_state, status=final_status)
                update_research_job(job_id, final_status, run_id=run_id)
                yield json.dumps(
                    {
                        "event": "saved",
                        "job_id": job_id,
                        "run_id": run_id,
                        "status": final_status,
                    },
                    ensure_ascii=False,
                ) + "\n"
        except Exception as exc:
            if last_state:
                last_state["error"] = str(exc)
                run_id = save_research_run(topic, last_state, status="failed")
                update_research_job(job_id, "failed", error=str(exc), run_id=run_id)
            else:
                update_research_job(job_id, "failed", error=str(exc))
            yield json.dumps(
                {
                    "event": "error",
                    "job_id": job_id,
                    "step": "unknown",
                    "error": f"Research pipeline failed: {exc}",
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        stream_events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )

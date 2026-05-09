from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.services.auth import AuthUser, get_current_user, get_current_user_or_query_token, get_public_auth_config
from app.services.jobs import JobStore


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    from app.services.hwp_compat import log_pyhwp_stack_at_startup

    log_pyhwp_stack_at_startup()
    yield


app = FastAPI(title="PDF Converter & Merger", version="1.0.0", lifespan=_lifespan)

allowed_origins = [v.strip() for v in os.getenv("APP_ALLOWED_ORIGINS", "*").split(",") if v.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
store = JobStore(STORAGE_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    from app.services.hwp_compat import describe_pyhwp_stack

    return JSONResponse({"ok": True, "pyhwp": describe_pyhwp_stack()})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/pricing")
async def pricing() -> FileResponse:
    return FileResponse(STATIC_DIR / "pricing.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/signup")
async def signup_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "signup.html")


@app.get("/api/auth-config")
async def auth_config() -> JSONResponse:
    return JSONResponse(get_public_auth_config())


@app.get("/api/me")
async def me(current_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    return JSONResponse({"user_id": current_user.user_id, "email": current_user.email, "role": current_user.role})


@app.post("/api/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    output_name: str = Form(default=""),
    current_user: AuthUser = Depends(get_current_user),
) -> JSONResponse:
    raw_files: list[tuple[str, bytes]] = []
    for upload in files:
        raw_files.append((upload.filename or "unknown", await upload.read()))

    if not output_name:
        output_name = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    if not output_name.lower().endswith(".pdf"):
        output_name += ".pdf"

    try:
        job = await store.create_job(raw_files, output_name, owner_user_id=current_user.user_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    background_tasks.add_task(store.process_job, job.job_id)
    return JSONResponse({"job_id": job.job_id, "file_list": [task.original_name for task in job.tasks]})


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str, current_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    try:
        job = await store.get_owned(job_id, current_user.user_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return JSONResponse(job.as_dict())


@app.get("/api/progress-stream/{job_id}")
async def stream_progress(job_id: str, current_user: AuthUser = Depends(get_current_user_or_query_token)) -> StreamingResponse:
    try:
        await store.get_owned(job_id, current_user.user_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    async def event_gen():
        while True:
            try:
                job = await store.get_owned(job_id, current_user.user_id)
            except KeyError:
                break
            except PermissionError:
                break
            payload = json.dumps(job.as_dict(), ensure_ascii=False)
            yield f"data: {payload}\n\n"
            statuses = {task.status for task in job.tasks}
            if statuses.issubset({"done", "error", "skipped"}) and job.merge_status in {"done", "error", "idle"}:
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/api/skip/{job_id}/{file_id}")
async def skip_file(job_id: str, file_id: str, current_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    try:
        await store.get_owned(job_id, current_user.user_id)
        await store.skip_file(job_id, file_id)
        return JSONResponse({"ok": True})
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@app.post("/api/merge")
async def merge_pdfs(payload: dict, current_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    job_id = payload.get("job_id")
    output_name = payload.get("output_name")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    try:
        await store.get_owned(job_id, current_user.user_id)
        merged = await store.merge_job(job_id, output_name)
        return JSONResponse({"merge_id": job_id, "file_name": merged.name})
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/download/{merge_id}")
async def download_merged(merge_id: str, current_user: AuthUser = Depends(get_current_user_or_query_token)) -> FileResponse:
    try:
        job = await store.get_owned(merge_id, current_user.user_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Merge not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    if not job.merge_file or not job.merge_file.exists():
        raise HTTPException(status_code=404, detail="Merged file not ready")
    return FileResponse(job.merge_file, filename=job.merge_file.name, media_type="application/pdf")


@app.delete("/api/cleanup/{job_id}")
async def cleanup_job(job_id: str, current_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    try:
        await store.get_owned(job_id, current_user.user_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    await store.cleanup_job(job_id)
    return JSONResponse({"deleted": True})

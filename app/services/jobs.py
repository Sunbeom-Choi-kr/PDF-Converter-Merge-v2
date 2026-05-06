from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfWriter

from app.services.converter import convert_to_pdf


MAX_FILES = 20
MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024
MAX_TOTAL_FILE_SIZE = 200 * 1024 * 1024
TTL_SECONDS = 30 * 60


@dataclass
class FileTask:
    file_id: str
    original_name: str
    saved_path: Path
    pdf_path: Path
    size: int
    status: str = "waiting"
    error_message: str = ""


@dataclass
class Job:
    job_id: str
    session_dir: Path
    created_at: float = field(default_factory=time.time)
    tasks: list[FileTask] = field(default_factory=list)
    merge_status: str = "idle"
    merge_file: Path | None = None
    merge_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        done_count = sum(1 for t in self.tasks if t.status == "done")
        skipped_count = sum(1 for t in self.tasks if t.status == "skipped")
        error_count = sum(1 for t in self.tasks if t.status == "error")
        total = max(len(self.tasks), 1)
        progress = int(((done_count + skipped_count + error_count) / total) * 100)
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "overall_progress": progress,
            "merge_status": self.merge_status,
            "merge_error": self.merge_error,
            "download_ready": self.merge_status == "done" and self.merge_file and self.merge_file.exists(),
            "files": [
                {
                    "file_id": t.file_id,
                    "original_name": t.original_name,
                    "size": t.size,
                    "status": t.status,
                    "error_message": t.error_message,
                }
                for t in self.tasks
            ],
        }


class JobStore:
    def __init__(self, base_storage_dir: Path) -> None:
        self.base_storage_dir = base_storage_dir
        self.jobs: dict[str, Job] = {}
        self.lock = asyncio.Lock()

    async def create_job(self, files: list[tuple[str, bytes]], output_name: str) -> Job:
        if len(files) == 0:
            raise ValueError("At least one file is required.")
        if len(files) > MAX_FILES:
            raise ValueError(f"Maximum {MAX_FILES} files are allowed.")

        total_size = sum(len(content) for _, content in files)
        if total_size > MAX_TOTAL_FILE_SIZE:
            raise ValueError("Total size exceeds 200MB.")

        job_id = str(uuid.uuid4())
        session_dir = self.base_storage_dir / job_id
        session_dir.mkdir(parents=True, exist_ok=True)
        pdf_dir = session_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        tasks: list[FileTask] = []
        for idx, (name, content) in enumerate(files):
            if len(content) > MAX_SINGLE_FILE_SIZE:
                continue
            file_id = str(uuid.uuid4())
            source = session_dir / f"{idx:03d}_{file_id}_{name}"
            source.write_bytes(content)
            pdf_output = pdf_dir / f"{idx:03d}_{file_id}.pdf"
            tasks.append(
                FileTask(
                    file_id=file_id,
                    original_name=name,
                    saved_path=source,
                    pdf_path=pdf_output,
                    size=len(content),
                )
            )

        if not tasks:
            raise ValueError("All files were rejected by size constraints.")

        job = Job(job_id=job_id, session_dir=session_dir, tasks=tasks, merge_file=session_dir / output_name)
        async with self.lock:
            self.jobs[job_id] = job
        return job

    async def process_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        for task in job.tasks:
            if task.status == "skipped":
                continue
            task.status = "converting"
            try:
                await convert_to_pdf(task.saved_path, task.pdf_path)
                task.status = "done"
            except Exception as error:  # noqa: BLE001
                task.status = "error"
                task.error_message = str(error)

    async def skip_file(self, job_id: str, file_id: str) -> None:
        job = self.jobs[job_id]
        for task in job.tasks:
            if task.file_id == file_id and task.status == "error":
                task.status = "skipped"
                task.error_message = ""
                return
        raise ValueError("file_id not found or not in error state")

    async def merge_job(self, job_id: str, output_name: str | None = None) -> Path:
        job = self.jobs[job_id]
        if output_name:
            output = job.session_dir / output_name
            if output.suffix.lower() != ".pdf":
                output = output.with_suffix(".pdf")
            job.merge_file = output

        job.merge_status = "merging"
        merger = PdfWriter()
        try:
            added = 0
            for task in job.tasks:
                if task.status in {"done", "skipped"} and task.pdf_path.exists():
                    merger.append(str(task.pdf_path))
                    added += 1
            if added == 0:
                raise ValueError("No successful PDF files available for merge.")
            assert job.merge_file is not None
            merger.write(str(job.merge_file))
            job.merge_status = "done"
            return job.merge_file
        except Exception as error:  # noqa: BLE001
            job.merge_status = "error"
            job.merge_error = str(error)
            raise
        finally:
            merger.close()

    async def get(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise KeyError("job not found")
        return self.jobs[job_id]

    async def cleanup_job(self, job_id: str) -> None:
        async with self.lock:
            job = self.jobs.pop(job_id, None)
        if job and job.session_dir.exists():
            for path in sorted(job.session_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()

    async def cleanup_expired(self) -> None:
        now = time.time()
        job_ids = [job_id for job_id, job in self.jobs.items() if now - job.created_at > TTL_SECONDS]
        for job_id in job_ids:
            await self.cleanup_job(job_id)

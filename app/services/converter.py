from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from reportlab.pdfgen import canvas


OFFICE_EXTENSIONS = {".docx", ".doc", ".odt", ".rtf", ".xlsx", ".xls", ".ods", ".csv", ".pptx", ".ppt", ".odp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".svg", ".heic"}
HTML_EXTENSIONS = {".html", ".htm"}
MARKDOWN_EXTENSIONS = {".md", ".markdown", ".rst", ".latex", ".epub"}
TEXT_EXTENSIONS = {".txt", ".json"}


def _resolve_executable(cmd: str, windows_candidates: Optional[list[str]] = None) -> Optional[str]:
    resolved = shutil.which(cmd)
    if resolved:
        return resolved

    if os.name == "nt" and windows_candidates:
        for candidate in windows_candidates:
            expanded = os.path.expandvars(candidate)
            if Path(expanded).exists():
                return expanded
    return None


def _resolve_imagemagick() -> Optional[str]:
    magick = _resolve_executable(
        "magick",
        windows_candidates=[
            r"%ProgramFiles%\ImageMagick-7.1.2-Q16-HDRI\magick.exe",
            r"%ProgramFiles%\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
            r"%ProgramFiles(x86)%\ImageMagick-7.1.2-Q16-HDRI\magick.exe",
            r"%ProgramFiles(x86)%\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
        ],
    )
    if magick:
        return magick

    if os.name == "nt":
        roots = [Path(os.path.expandvars(r"%ProgramFiles%")), Path(os.path.expandvars(r"%ProgramFiles(x86)%"))]
        for root in roots:
            if not root.exists():
                continue
            for candidate_dir in root.glob("ImageMagick-*"):
                binary = candidate_dir / "magick.exe"
                if binary.exists():
                    return str(binary)
    return None


def _run_command(command: list[str], timeout_seconds: int = 60) -> None:
    subprocess.run(command, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _fallback_text_pdf(
    source_file: Path,
    output_pdf: Path,
    note: Optional[str] = None,
    include_preview: bool = True,
) -> None:
    c = canvas.Canvas(str(output_pdf))
    c.setTitle(source_file.name)
    text = c.beginText(40, 800)
    text.setFont("Helvetica", 11)
    text.textLine(f"Source: {source_file.name}")
    if note:
        text.textLine(note)
    text.textLine("")
    if include_preview:
        try:
            preview = source_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            preview = "[content preview unavailable]"
        for line in preview.splitlines()[:45]:
            text.textLine(line[:120])
    c.drawText(text)
    c.showPage()
    c.save()


async def convert_to_pdf(source_file: Path, output_pdf: Path) -> None:
    ext = source_file.suffix.lower()

    if ext == ".pdf":
        shutil.copy2(source_file, output_pdf)
        return

    if ext in OFFICE_EXTENSIONS:
        soffice = _resolve_executable(
            "soffice",
            windows_candidates=[
                r"%ProgramFiles%\LibreOffice\program\soffice.exe",
                r"%ProgramFiles(x86)%\LibreOffice\program\soffice.exe",
            ],
        )
        if not soffice:
            raise RuntimeError(
                "LibreOffice가 설치되어 있지 않거나 PATH에 없습니다. "
                "docx/xlsx/pptx 변환을 위해 LibreOffice 설치가 필요합니다."
            )
        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--nodefault",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_pdf.parent),
            str(source_file),
        ]
        await asyncio.to_thread(_run_command, command)
        generated = output_pdf.parent / f"{source_file.stem}.pdf"
        if generated != output_pdf and generated.exists():
            generated.replace(output_pdf)
        if output_pdf.exists():
            return
        raise RuntimeError("LibreOffice conversion did not produce an output PDF.")

    if ext in IMAGE_EXTENSIONS:
        magick = _resolve_imagemagick()
        if magick:
            await asyncio.to_thread(_run_command, [magick, str(source_file), str(output_pdf)])
            return
        raise RuntimeError("ImageMagick가 없어 이미지 변환을 수행할 수 없습니다.")

    if ext in HTML_EXTENSIONS:
        wkhtmltopdf = _resolve_executable("wkhtmltopdf")
        if wkhtmltopdf:
            await asyncio.to_thread(_run_command, [wkhtmltopdf, str(source_file), str(output_pdf)])
            return
        raise RuntimeError("wkhtmltopdf가 없어 HTML 변환을 수행할 수 없습니다.")

    if ext in MARKDOWN_EXTENSIONS:
        pandoc = _resolve_executable("pandoc")
        if pandoc:
            await asyncio.to_thread(_run_command, [pandoc, str(source_file), "-o", str(output_pdf)])
            return
        raise RuntimeError("pandoc가 없어 마크다운 변환을 수행할 수 없습니다.")

    if ext in TEXT_EXTENSIONS:
        _fallback_text_pdf(source_file, output_pdf)
        return

    raise ValueError(f"Unsupported extension: {ext}")

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from contextlib import closing
from functools import partial
from pathlib import Path
from typing import Optional

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# Legacy binary HWP v5 (.hwp) uses pyhwp → ODT → LibreOffice; .hwpx stays in OFFICE_EXTENSIONS.
OFFICE_EXTENSIONS = {".docx", ".doc", ".odt", ".rtf", ".xlsx", ".xls", ".ods", ".csv", ".pptx", ".ppt", ".odp", ".hwpx"}
HWP_LEGACY_EXTENSION = ".hwp"
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


def _resolve_imagemagick() -> Optional[list[str]]:
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
        return [magick]

    # Debian/Ubuntu environments often provide ImageMagick 6 as `convert`.
    convert_bin = _resolve_executable("convert")
    if convert_bin:
        return [convert_bin]

    if os.name == "nt":
        roots = [Path(os.path.expandvars(r"%ProgramFiles%")), Path(os.path.expandvars(r"%ProgramFiles(x86)%"))]
        for root in roots:
            if not root.exists():
                continue
            for candidate_dir in root.glob("ImageMagick-*"):
                binary = candidate_dir / "magick.exe"
                if binary.exists():
                    return [str(binary)]
    return None


def _run_command(command: list[str], timeout_seconds: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _resolve_soffice() -> str:
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
            "PDF 변환을 위해 LibreOffice 설치가 필요합니다."
        )
    return soffice


def _libreoffice_convert_to_pdf(source_file: Path, output_pdf: Path, timeout_seconds: int = 120) -> None:
    soffice = _resolve_soffice()
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
    try:
        _run_command(command, timeout_seconds=timeout_seconds)
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or b"").decode("utf-8", errors="ignore").strip()
        stdout = (error.stdout or b"").decode("utf-8", errors="ignore").strip()
        detail = stderr or stdout or "no stderr/stdout"
        raise RuntimeError(f"LibreOffice conversion failed: {detail}") from error
    generated = output_pdf.parent / f"{source_file.stem}.pdf"
    if generated != output_pdf and generated.exists():
        generated.replace(output_pdf)
    if output_pdf.exists():
        return
    raise RuntimeError(
        "LibreOffice conversion did not produce an output PDF. "
        f"source={source_file.name}, ext={source_file.suffix}. "
        "This environment may not support the document filter for this format."
    )


def _hwp_bin_to_odt_with_pyhwp(source_file: Path, odt_out: Path) -> None:
    from app.services.hwp_compat import assert_pyhwp_import_chain

    assert_pyhwp_import_chain()

    try:
        from hwp5.cli import init_with_environ
        from hwp5.dataio import ParseError
        from hwp5.errors import ImplementationNotAvailable, InvalidHwp5FileError
        from hwp5.hwp5odt import ODTTransform, open_odtpkg
        from hwp5.xmlmodel import Hwp5File
    except ImportError as error:
        raise RuntimeError(
            "pyhwp(hwp5) 기본 의존성 검사는 통과했으나 하위 모듈 로드에 실패했습니다. 배포 산출물이 오래된지 확인하세요. "
            f"원인: {error!s}"
        ) from error

    init_with_environ()

    try:
        odt_transform = ODTTransform()
    except ImplementationNotAvailable as error:
        raise RuntimeError(
            "pyhwp ODT 변환을 위한 XSLT 엔진(lxml 등)을 사용할 수 없습니다."
        ) from error

    odt_transform.embedbin = False
    transform = odt_transform.transform_hwp5_to_package
    open_dest = partial(open_odtpkg, str(odt_out))

    try:
        with closing(Hwp5File(str(source_file))) as hwp5file:
            with open_dest() as dest:
                transform(hwp5file, dest)
    except InvalidHwp5FileError as error:
        raise RuntimeError(
            "HWP 파일을 pyhwp로 열 수 없습니다. 암호화된 문서이거나 HWPX(.hwpx) 등 "
            f"지원하지 않는 형식일 수 있습니다: {error}"
        ) from error
    except ParseError as error:
        raise RuntimeError(f"pyhwp가 HWP 파싱에 실패했습니다: {error}") from error

    if not odt_out.exists():
        raise RuntimeError("pyhwp가 ODT 파일을 생성하지 않았습니다.")


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


def _fallback_image_pdf(source_file: Path, output_pdf: Path) -> None:
    image = ImageReader(str(source_file))
    img_width, img_height = image.getSize()

    # Keep a simple, predictable layout: one image per page at native size.
    c = canvas.Canvas(str(output_pdf), pagesize=(float(img_width), float(img_height)))
    c.drawImage(image, 0, 0, width=float(img_width), height=float(img_height), preserveAspectRatio=True, mask="auto")
    c.showPage()
    c.save()


async def convert_to_pdf(source_file: Path, output_pdf: Path) -> None:
    ext = source_file.suffix.lower()

    if ext == ".pdf":
        shutil.copy2(source_file, output_pdf)
        return

    if ext == HWP_LEGACY_EXTENSION:
        intermediate_odt = output_pdf.with_suffix(".odt")
        try:
            def _hwp_pipeline() -> None:
                _hwp_bin_to_odt_with_pyhwp(source_file, intermediate_odt)
                _libreoffice_convert_to_pdf(intermediate_odt, output_pdf, timeout_seconds=120)

            await asyncio.to_thread(_hwp_pipeline)
        finally:
            intermediate_odt.unlink(missing_ok=True)
        return

    if ext in OFFICE_EXTENSIONS:
        await asyncio.to_thread(_libreoffice_convert_to_pdf, source_file, output_pdf, 60)
        return

    if ext in IMAGE_EXTENSIONS:
        image_command = _resolve_imagemagick()
        if image_command:
            try:
                await asyncio.to_thread(_run_command, [*image_command, str(source_file), str(output_pdf)])
                return
            except subprocess.CalledProcessError:
                # Some container images ship restrictive ImageMagick policy.xml
                # that blocks PDF writing. Fall back to a pure-Python conversion.
                pass
        await asyncio.to_thread(_fallback_image_pdf, source_file, output_pdf)
        if output_pdf.exists():
            return
        raise RuntimeError("이미지 PDF 변환에 실패했습니다.")

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

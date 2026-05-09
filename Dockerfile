FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libreoffice \
    libreoffice-writer \
    libreoffice-java-common \
    default-jre \
    imagemagick \
    wkhtmltopdf \
    pandoc \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import importlib.metadata as m; print('pyhwp', m.version('pyhwp'))" \
    && python -c "from hwp5.cli import init_with_environ; from hwp5.hwp5odt import ODTTransform; init_with_environ(); ODTTransform(); print('hwp_odt_engine_ok')"

COPY app ./app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

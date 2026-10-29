FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.lock && useradd -m -u 10001 studio && mkdir /data && chown studio:studio /data
COPY app/ app/
USER studio
ENV STUDIO_DB_PATH=/data/studio.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8102
HEALTHCHECK --interval=20s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8102/health',timeout=3)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8102","--workers","1","--no-access-log"]

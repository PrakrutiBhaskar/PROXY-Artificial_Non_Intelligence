FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PROXY_DB=/data/proxy.db
WORKDIR /app
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt
COPY . .
RUN useradd -m app && mkdir /data && chown app /data
USER app
# Only 8000 is public. The six MCP servers (8765-8770) listen on 127.0.0.1 inside the container and must stay unpublished.
EXPOSE 8000
HEALTHCHECK --interval=30s CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

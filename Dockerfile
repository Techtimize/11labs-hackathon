FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/data/authrelay.db

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY api api
COPY core core
COPY database database
COPY dto dto
COPY errors errors
COPY integrations integrations
COPY interfaces interfaces
COPY mapper mapper
COPY policies policies
COPY security security
COPY services services
COPY utils utils
COPY agent agent
COPY data data

RUN useradd --system --uid 1001 authrelay \
    && mkdir -p /data \
    && chown -R authrelay:authrelay /srv /data
USER authrelay

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

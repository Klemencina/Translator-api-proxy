FROM python@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && python -m pip uninstall -y pip setuptools wheel

COPY app ./app
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

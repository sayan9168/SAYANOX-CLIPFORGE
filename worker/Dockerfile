FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir --upgrade "pip>=26.2.1" "setuptools>=84.0.0" \
    && pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt
COPY *.py ./
ENV CLIPFORGE_DATA=/data
ENV HF_HOME=/data/models
ENV CLIPFORGE_ALLOW_YTDLP=false
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]

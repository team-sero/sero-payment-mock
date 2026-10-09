# payment-mock 이미지. 로컬에서는 compose.yaml로 띄우고, 서버에서는 같은 이미지를 k3s의 pg-external에 올린다
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# 의존성을 먼저 깐다. 코드만 바뀌었을 때는 이 층을 캐시에서 다시 쓴다
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# root로 돌리지 않는다
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8090
CMD ["python", "-m", "app"]
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY requirements.txt .

ENV VIRTUAL_ENV=/opt/venv
RUN uv venv $VIRTUAL_ENV
RUN uv pip install --python $VIRTUAL_ENV --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl tzdata && rm -rf /var/lib/apt/lists/*

ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} march7_group && useradd -m -u ${UID} -g ${GID} march7_user
WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv
COPY --from=0 $VIRTUAL_ENV $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY twin/ /app/twin/
COPY gateway/ /app/gateway/
COPY memories/ /app/memories/
COPY config.py /app/config.py

USER march7_user
ENV PYTHONPATH=/app
CMD ["python", "-m", "twin.march7"]

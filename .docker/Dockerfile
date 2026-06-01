FROM python:3.14-slim-bookworm

ARG USER_ID=1000
ARG GROUP_ID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEVCONTAINER=true

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        make \
        curl \
        ca-certificates \
        libpq-dev \
        libssl-dev \
        libffi-dev \
        freetds-dev \
        unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir tox

RUN groupadd --gid ${GROUP_ID} dev \
    && useradd --uid ${USER_ID} --gid ${GROUP_ID} --create-home --shell /bin/bash dev

USER dev
WORKDIR /workspace

CMD ["bash"]

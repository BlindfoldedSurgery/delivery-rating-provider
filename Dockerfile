FROM python:3.12-slim

RUN apt-get update
RUN apt-get install -y vim

RUN useradd --system --create-home --home-dir /app -s /bin/bash app
USER app
ENV PATH=$PATH:/app/.local/bin

WORKDIR /app

RUN pip install pipx==1.4.3 --user --no-cache
RUN pipx install poetry==1.7.1
RUN poetry config virtualenvs.create false

COPY --chown=app:app [ "poetry.lock", "pyproject.toml", "README.md", "./" ]

COPY --chown=app:app src/provider ./src/provider

RUN poetry install --only main

ENTRYPOINT [ "poetry", "run", "python", "-m", "provider" ]

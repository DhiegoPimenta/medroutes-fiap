# Dockerfile do MedRoutes - imagem para Azure Container Apps
# Build multi-stage: instala dependencias com Poetry em uma camada separada
# da aplicacao para aproveitar cache do Docker entre builds.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# dependencias do sistema necessarias para compilar pacotes Python nativos
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.3

# copia apenas os manifestos primeiro para aproveitar cache de camadas
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --only main

# copia o restante do codigo da aplicacao
COPY app/ ./app/

# usuario nao-root por seguranca (boas praticas de containers em produção)
RUN useradd --create-home --shell /bin/bash medroutes \
    && chown -R medroutes:medroutes /app
USER medroutes

# porta usada pelo Streamlit. Deve coincidir com o target-port configurado
# no Container App (ver infra/resources.bicep, targetPort: 8501)
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app/main.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]

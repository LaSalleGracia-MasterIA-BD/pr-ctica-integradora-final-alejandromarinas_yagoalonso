"""Configuracion del dashboard que se lee de variables de entorno.

Tres constantes. Sin estado, sin logica. El dashboard es API-only:
nada aqui apunta a MongoDB, SQLite o MinIO directamente (todo pasa por
la capa REST de la API).
"""
from __future__ import annotations

import os


# URL base de la API REST. Dentro del docker-compose es `http://api:8000`
# (red interna). Cuando se ejecuta el dashboard en host (raro: solo para
# desarrollo) apuntar a `http://localhost:8000`.
API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://api:8000")

# Timeout para CADA peticion HTTP. La API real responde en ms; un timeout
# de 10s deja margen para el caso de cold-start del modelo en el predictor.
API_TIMEOUT_SECONDS: float = float(os.environ.get("API_TIMEOUT_SECONDS", "10"))

# TTL del `st.cache_data` que envolvera cada query GET. 10s mantiene la
# UI viva en una demo sin bombardear la API en cada interaccion de
# Streamlit (que re-ejecuta el script entero en cada click).
CACHE_TTL_SECONDS: int = int(os.environ.get("DASHBOARD_CACHE_TTL", "10"))

"""Thin sync httpx wrapper for the dashboard.

Every method returns a `(data, error)` tuple. The error is `None` on
success and an `ApiError` otherwise. Views never raise — they branch on
`error is not None` and render a banner via `components.error_banner`.

Why sync + tuple-style:
  * Streamlit reruns the script on every interaction. Async would force
    `asyncio.run()` per call, which is heavy and brittle.
  * Returning `(data, error)` makes the views read top-to-bottom without
    `try/except` everywhere.

`image_bytes` is the only method that returns raw bytes (PNG content);
the others return parsed JSON.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx

logger = logging.getLogger(__name__)


ErrorKind = Literal[
    "network",      # connection refused / timeout / DNS
    "not_found",    # HTTP 404
    "validation",   # HTTP 422
    "unavailable",  # HTTP 503
    "server",       # 4xx other / 5xx other
]


@dataclass(frozen=True)
class ApiError:
    """A typed error from the API client.

    `kind` drives the message shown in the banner; `status` and `detail`
    are surfaced for debugging.
    """
    kind: ErrorKind
    status: Optional[int]
    detail: str
    raw: Optional[dict] = None


# Result tuples for typing convenience
ResultJson = tuple[Optional[Any], Optional[ApiError]]
ResultBytes = tuple[Optional[bytes], Optional[ApiError]]


def _classify_status(status: int, detail: str, raw: Optional[dict]) -> ApiError:
    """Map an HTTP status code to an ApiError(kind, ...)."""
    if status == 404:
        return ApiError(kind="not_found", status=status, detail=detail, raw=raw)
    if status == 422:
        return ApiError(kind="validation", status=status, detail=detail, raw=raw)
    if status == 503:
        return ApiError(kind="unavailable", status=status, detail=detail, raw=raw)
    # 4xx other or 5xx: bucket "server"
    return ApiError(kind="server", status=status, detail=detail, raw=raw)


def _extract_detail(response: httpx.Response) -> tuple[str, Optional[dict]]:
    """Pull a human-readable detail string + raw json (if any)."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] if response.text else "", None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail, body
        # FastAPI Pydantic validation: detail is a list of dicts
        return str(detail) if detail is not None else "", body
    return str(body)[:300], body if isinstance(body, dict) else None


class ApiClient:
    """Read facade over the hospital API.

    One instance per Streamlit session (stored in `st.session_state`).
    Construct once; `httpx.Client` reuses connections.
    """

    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:  # pragma: no cover  (lifetime tied to process)
        self._client.close()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _request_json(self, method: str, url: str, **kwargs: Any) -> ResultJson:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            return None, ApiError(
                kind="network",
                status=None,
                detail=f"{type(exc).__name__}: {exc}",
            )

        if 200 <= response.status_code < 300:
            try:
                return response.json(), None
            except ValueError as exc:
                return None, ApiError(
                    kind="server",
                    status=response.status_code,
                    detail=f"Invalid JSON in response: {exc}",
                )

        detail, raw = _extract_detail(response)
        return None, _classify_status(response.status_code, detail, raw)

    def _request_bytes(self, method: str, url: str, **kwargs: Any) -> ResultBytes:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            return None, ApiError(
                kind="network",
                status=None,
                detail=f"{type(exc).__name__}: {exc}",
            )

        if 200 <= response.status_code < 300:
            return response.content, None

        detail, raw = _extract_detail(response)
        return None, _classify_status(response.status_code, detail, raw)

    # ------------------------------------------------------------------
    # /health
    # ------------------------------------------------------------------

    def health(self) -> ResultJson:
        return self._request_json("GET", "/api/v1/health")

    # ------------------------------------------------------------------
    # counts (overview)
    # ------------------------------------------------------------------

    def count_patients(self) -> ResultJson:
        """Return the `total` field of the patients listing."""
        data, err = self._request_json(
            "GET", "/api/v1/patients", params={"limit": 1, "offset": 0},
        )
        if err is not None:
            return None, err
        return data.get("total", 0), None

    def count_admissions(self) -> ResultJson:
        data, err = self._request_json(
            "GET", "/api/v1/admissions", params={"limit": 1, "offset": 0},
        )
        if err is not None:
            return None, err
        return data.get("total", 0), None

    def count_radiographies(self) -> ResultJson:
        data, err = self._request_json(
            "GET", "/api/v1/radiographies", params={"limit": 1, "offset": 0},
        )
        if err is not None:
            return None, err
        return data.get("total", 0), None

    # ------------------------------------------------------------------
    # patients
    # ------------------------------------------------------------------

    def list_patients(self, limit: int, offset: int) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/patients",
            params={"limit": limit, "offset": offset},
        )

    def list_admissions(self, limit: int, offset: int) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/admissions",
            params={"limit": limit, "offset": offset},
        )

    def get_patient(self, external_id: str) -> ResultJson:
        return self._request_json("GET", f"/api/v1/patients/{external_id}")

    # ------------------------------------------------------------------
    # radiographies + classification
    # ------------------------------------------------------------------

    def list_radiographies(self, limit: int, offset: int) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/radiographies",
            params={"limit": limit, "offset": offset},
        )

    def image_bytes(self, minio_object_key: str) -> ResultBytes:
        """Get PNG bytes of a radiography from the API proxy (RF-8)."""
        return self._request_bytes(
            "GET", "/api/v1/radiographies/image",
            params={"key": minio_object_key},
        )

    def classify(self, minio_object_key: str) -> ResultJson:
        return self._request_json(
            "POST", "/api/v1/radiographies/classify",
            json={"minio_object_key": minio_object_key},
        )

    def get_classification(self, minio_object_key: str) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/radiographies/classification",
            params={"key": minio_object_key},
        )

    # ------------------------------------------------------------------
    # pipeline
    # ------------------------------------------------------------------

    def latest_pipeline_run(self) -> ResultJson:
        return self._request_json("GET", "/api/v1/pipeline/status")

    def list_runs(self, limit: int, offset: int) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/pipeline/runs",
            params={"limit": limit, "offset": offset},
        )

    def latest_quality_summary(self) -> ResultJson:
        return self._request_json("GET", "/api/v1/pipeline/quality-summary")

    def quality_summary_history(
        self, dimension: str, limit: int, offset: int = 0,
    ) -> ResultJson:
        return self._request_json(
            "GET", "/api/v1/pipeline/quality-summary/history",
            params={"dimension": dimension, "limit": limit, "offset": offset},
        )

    # ------------------------------------------------------------------
    # model evaluation (RF-9)
    # ------------------------------------------------------------------

    def model_evaluation(self) -> ResultJson:
        """Read the offline metrics.json. 503 if missing (not the same as
        predictor_loaded=false — see ADR-007 and spec CB-4)."""
        return self._request_json("GET", "/api/v1/model/evaluation")

    # ------------------------------------------------------------------
    # triage (feature triage-pacientes)
    # ------------------------------------------------------------------

    def create_triage_patient(self, payload: dict) -> ResultJson:
        """POST /api/v1/triage/patients (alta manual con triaje).

        Mapea 201 -> (data, None) y 422 / 503 / 409 -> ApiError clasificado.
        """
        return self._request_json(
            "POST", "/api/v1/triage/patients", json=payload,
        )

    def get_triage_rules(self) -> ResultJson:
        """GET /api/v1/triage/rules (RF-8): definicion de las reglas vigentes."""
        return self._request_json("GET", "/api/v1/triage/rules")

    # ------------------------------------------------------------------
    # alerts + reports (Feature 15)
    # ------------------------------------------------------------------

    def get_alerts(
        self,
        since: str | None = None,
        severity: str | None = None,
    ) -> ResultJson:
        """GET /api/v1/alerts: alertas activas calculadas en tiempo real."""
        params: dict[str, str] = {}
        if since is not None:
            params["since"] = since
        if severity is not None:
            params["severity"] = severity
        return self._request_json(
            "GET", "/api/v1/alerts", params=params or None,
        )

    def get_daily_report(self, date: str | None = None) -> ResultJson:
        """GET /api/v1/reports/daily: informe del dia consultado (JSON)."""
        params = {"date": date} if date else None
        return self._request_json(
            "GET", "/api/v1/reports/daily", params=params,
        )

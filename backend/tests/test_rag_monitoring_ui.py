from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from parrilladas.admin import create_app
from parrilladas.core.config import AdminSettings
from parrilladas.modules.accounts.schemas import AccountView, SessionContext
from parrilladas.modules.assistant.monitoring.schemas import (
    EvalRunView,
    Metric,
    MonitoringReport,
    TraceDetail,
    TraceResult,
)
from parrilladas.modules.dashboard.client import ApiUnavailable
from parrilladas.modules.dashboard.dependencies import api_client


def monitoring_client(role="dev", report=None):
    service = Mock()
    service.session_context.return_value = SessionContext(
        id=uuid4(),
        csrf_token="synthetic-csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        account=AccountView(
            id=uuid4(),
            email="dev@example.com",
            display_name="Developer",
            roles=[role],
            is_active=True,
        ),
    )
    service.monitoring_report.return_value = report or MonitoringReport(
        days=7,
        generated_at=datetime.now(UTC),
        tenant_id="synthetic",
    )
    app = create_app(AdminSettings(app_env="test", _env_file=None))
    app.dependency_overrides[api_client] = lambda: service
    return TestClient(app), service


@pytest.mark.parametrize("path", ["", "/content"])
def test_monitoring_empty_render_and_accessible_filters(path):
    client, service = monitoring_client()
    with client:
        response = client.get("/dashboard/rag/monitoring" + path + "?days=30")
    assert response.status_code == 200
    assert 'name="days" value="30" aria-pressed="true"' in response.text
    assert 'hx-push-url="/dashboard/rag/monitoring?days=30"' in response.text
    assert 'hx-trigger="every 60s"' in response.text
    for title in (
        "Calidad de recuperación",
        "Calidad de generación",
        "Salud de la base vectorial",
        "Estructura del índice",
        "Trazas de recuperación",
        "Vigencia y cobertura",
        "Alertas",
    ):
        assert title in response.text
    assert "No hay trazas todavía" in response.text
    assert "Sin ejecutar" in response.text
    service.monitoring_report.assert_called_once_with(days=30)


@pytest.mark.parametrize("role", ["admin", "sales"])
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/content",
        "/traces/00000000-0000-0000-0000-000000000001",
        "/eval-runs/00000000-0000-0000-0000-000000000001",
    ],
)
def test_monitoring_all_views_require_dev(role, suffix):
    client, service = monitoring_client(role)
    with client:
        response = client.get("/dashboard/rag/monitoring" + suffix)
    assert response.status_code == 403
    service.monitoring_report.assert_not_called()
    service.monitoring_trace.assert_not_called()


def test_rag_vector_health_page_uses_live_refresh_and_keeps_unknowns_explicit():
    client, service = monitoring_client()
    with client:
        response = client.get("/dashboard/rag/health?days=1")
    assert response.status_code == 200
    assert "RAG &amp; Vector Health" in response.text
    assert 'hx-trigger="every 10s"' in response.text
    assert "No medido" in response.text
    service.monitoring_report.assert_called_once_with(days=1)


def test_monitoring_unavailable_has_safe_error_and_retry():
    client, service = monitoring_client()
    service.monitoring_report.side_effect = ApiUnavailable("SECRET CONFIG")
    with client:
        response = client.get("/dashboard/rag/monitoring/content")
    assert response.status_code == 503
    assert "No pudimos consultar" in response.text
    assert "SECRET" not in response.text


def test_monitoring_real_values_progress_sparkline_and_unknowns():
    report = MonitoringReport(
        days=7,
        generated_at=datetime.now(UTC),
        tenant_id="synthetic",
        kpis=[Metric(key="unknown", label="Sin medida", value=None, display="0")],
        retrieval_metrics=[
            Metric(key="recall", label="Recall@5", value=0.75, display="75%", status="watch")
        ],
        latency_series=[8, 12, 9],
        index={"mode": "exact"},
    )
    client, _ = monitoring_client(report=report)
    with client:
        response = client.get("/dashboard/rag/monitoring")
    assert "75%" in response.text
    assert 'aria-hidden="true"' in response.text
    assert 'role="img"' in response.text
    assert "Revisar" in response.text
    assert "recall del índice 100% por definición" in response.text
    assert "Ilustración: descenso" not in response.text
    assert '<p class="rag-kpi-value">No medido</p>' in response.text
    assert "/static/htmx.min.js" in response.text


def test_monitoring_trace_hides_online_text_and_escapes_source():
    client, service = monitoring_client()
    trace_id = uuid4()
    service.monitoring_trace.return_value = TraceDetail(
        id=trace_id,
        created_at=datetime.now(UTC),
        kind="online",
        decision="answer",
        used_count=1,
        total_ms=12,
        query_hash="synthetic",
        query_text="PRIVATE CUSTOMER TEXT",
        top_k=3,
        score_threshold=0.35,
        embedding_model="synthetic",
        embedding_dim=768,
        index_mode="exact",
        results=[
            TraceResult(
                chunk_id=uuid4(), rank=1, score=0.9, used=True, source="<script>private</script>"
            )
        ],
    )
    with client:
        response = client.get(f"/dashboard/rag/monitoring/traces/{trace_id}")
    assert response.status_code == 200
    assert "PRIVATE CUSTOMER TEXT" not in response.text
    assert "Texto de la consulta no almacenado" in response.text
    assert '<th scope="col">Puntuación</th>' in response.text
    assert "&lt;script&gt;private&lt;/script&gt;" in response.text


def test_monitoring_eval_csrf_and_status_polling():
    client, service = monitoring_client()
    run_id, set_id = uuid4(), uuid4()
    service.monitoring_start_eval.return_value = EvalRunView(id=run_id, status="running")
    service.monitoring_eval.return_value = EvalRunView(id=run_id, status="completed")
    with client:
        denied = client.post("/dashboard/rag/monitoring/eval-runs", data={"set_id": str(set_id)})
        assert denied.status_code == 403
        service.monitoring_start_eval.assert_not_called()
        started = client.post(
            "/dashboard/rag/monitoring/eval-runs",
            data={"set_id": str(set_id), "csrf_token": "synthetic-csrf"},
        )
        finished = client.get(f"/dashboard/rag/monitoring/eval-runs/{run_id}")
    assert started.status_code == 200
    assert 'hx-trigger="every 5s"' in started.text
    assert "hx-trigger" not in finished.text
    service.monitoring_start_eval.assert_called_once_with(set_id)

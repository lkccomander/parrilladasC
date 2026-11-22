from uuid import UUID

import httpx
from fastapi import HTTPException, Request

from parrilladas.modules.accounts.errors import (
    AccessDenied,
    AccountConflict,
    AccountNotFound,
    InvalidCredentials,
    LoginThrottled,
)
from parrilladas.modules.accounts.schemas import (
    AccountCreate,
    AccountUpdate,
    AccountView,
    SessionContext,
    SessionCreated,
)
from parrilladas.modules.assistant.monitoring.schemas import (
    EvalRunView,
    MonitoringHealth,
    MonitoringReport,
    TraceDetail,
)
from parrilladas.modules.assistant.rag_contracts import KnowledgeOverview
from parrilladas.modules.assistant.schemas import (
    AdvisorPreferencesView,
    AdvisorSettings,
    AssistantPreferencesUpdate,
    AssistantPreferencesView,
)
from parrilladas.modules.assistant.telemetry_contracts import TelemetryReport
from parrilladas.modules.conversations.schemas import InteractionFilters, InteractionPage
from parrilladas.modules.dashboard.cookies import cookie_name, refresh_cookie_name
from parrilladas.modules.integrations.schemas import WhatsAppIntegrationStatus


class ApiUnavailable(Exception):
    pass


class AdminApiClient:
    """Per-request HTTP adapter. The Admin never imports repositories or opens a database."""

    def __init__(self, request: Request):
        self.request = request
        self.http: httpx.Client = request.app.state.api_http
        self.token = request.cookies.get(cookie_name(request))

    def _call(self, method: str, path: str, *, data=None, params=None, allow_unauthorized=False):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        context = getattr(self.request.state, "auth_context", None)
        if context:
            headers["X-CSRF-Token"] = context.csrf_token
        try:
            response = self.http.request(method, path, json=data, headers=headers, params=params)
        except httpx.HTTPError:
            raise ApiUnavailable from None
        if response.status_code == 401 and allow_unauthorized:
            return None
        if response.status_code >= 500:
            raise ApiUnavailable
        if response.status_code >= 400:
            errors = {
                401: InvalidCredentials,
                403: AccessDenied,
                404: AccountNotFound,
                409: AccountConflict,
                429: LoginThrottled,
            }
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                raise ApiUnavailable from None
            message = detail if isinstance(detail, str) else "Revise los datos e intente de nuevo."
            if response.status_code in errors:
                raise errors[response.status_code](message)
            raise HTTPException(response.status_code, message)
        return response.json() if response.content else None

    def anonymous_session(self) -> SessionCreated:
        return SessionCreated.model_validate(self._call("POST", "/auth/sessions"))

    def session_context(self) -> SessionContext | None:
        data = self._call("GET", "/auth/me", allow_unauthorized=True) if self.token else None
        if data:
            return SessionContext.model_validate(data)
        refresh = self.request.cookies.get(refresh_cookie_name(self.request))
        if not refresh:
            return None
        data = self._call(
            "POST", "/auth/refresh", data={"refresh_token": refresh}, allow_unauthorized=True
        )
        if data is None:
            return None
        created = SessionCreated.model_validate(data)
        self.token = created.token
        self.request.state.pending_credentials = created
        return created.context

    def login(self, email: str, password: str) -> SessionCreated:
        return SessionCreated.model_validate(
            self._call("POST", "/auth/login", data={"email": email, "password": password})
        )

    def logout(self) -> None:
        self._call("POST", "/auth/logout")

    def list_interactions(self, filters: InteractionFilters) -> InteractionPage:
        return InteractionPage.model_validate(
            self._call(
                "GET", "/conversations/interactions", params=filters.model_dump(exclude_none=True)
            )
        )

    def list_accounts(self) -> list[AccountView]:
        return [AccountView.model_validate(item) for item in self._call("GET", "/accounts")]

    def whatsapp_status(self) -> WhatsAppIntegrationStatus:
        return WhatsAppIntegrationStatus.model_validate(self._call("GET", "/integrations/whatsapp"))

    def check_whatsapp(self) -> WhatsAppIntegrationStatus:
        return WhatsAppIntegrationStatus.model_validate(
            self._call("POST", "/integrations/whatsapp/check")
        )

    def assistant_preferences(self) -> AssistantPreferencesView:
        return AssistantPreferencesView.model_validate(self._call("GET", "/assistant/preferences"))

    def gemini_telemetry(self, *, days=7, operation=None, page=1) -> TelemetryReport:
        params = {"days": days, "page": page}
        if operation:
            params["operation"] = operation
        return TelemetryReport.model_validate(self._call("GET", "/rag/telemetry", params=params))

    def knowledge_overview(self) -> KnowledgeOverview:
        return KnowledgeOverview.model_validate(self._call("GET", "/rag/knowledge"))

    def advisor_settings(self) -> AdvisorPreferencesView:
        return AdvisorPreferencesView.model_validate(
            self._call("GET", "/assistant/preferences/advisor")
        )

    def update_advisor_settings(self, data: AdvisorSettings) -> AdvisorPreferencesView:
        return AdvisorPreferencesView.model_validate(
            self._call("PATCH", "/assistant/preferences/advisor", data=data.model_dump(mode="json"))
        )

    def update_assistant_preferences(
        self, data: AssistantPreferencesUpdate
    ) -> AssistantPreferencesView:
        return AssistantPreferencesView.model_validate(
            self._call("PATCH", "/assistant/preferences", data=data.model_dump(mode="json"))
        )

    def get_account(self, account_id: UUID) -> AccountView:
        return AccountView.model_validate(self._call("GET", f"/accounts/{account_id}"))

    @staticmethod
    def _payload(data: AccountCreate | AccountUpdate) -> dict:
        payload = data.model_dump(mode="json")
        if data.password:
            payload["password"] = data.password.get_secret_value()
        if data.dev_role_key:
            payload["dev_role_key"] = data.dev_role_key.get_secret_value()
        return payload

    def create_account(self, data: AccountCreate) -> AccountView:
        return AccountView.model_validate(self._call("POST", "/accounts", data=self._payload(data)))

    def update_account(self, account_id: UUID, data: AccountUpdate) -> AccountView:
        return AccountView.model_validate(
            self._call("PATCH", f"/accounts/{account_id}", data=self._payload(data))
        )

    def monitoring_report(self, *, days: int = 7) -> MonitoringReport:
        return MonitoringReport.model_validate(
            self._call("GET", "/rag/monitoring/summary", params={"days": days})
        )

    def monitoring_health(self, *, days: int = 1) -> MonitoringHealth:
        return MonitoringHealth.model_validate(
            self._call("GET", "/rag/monitoring/health", params={"days": days})
        )

    def monitoring_trace(self, trace_id: UUID) -> TraceDetail:
        return TraceDetail.model_validate(self._call("GET", f"/rag/monitoring/traces/{trace_id}"))

    def monitoring_start_eval(self, set_id: UUID) -> EvalRunView:
        return EvalRunView.model_validate(
            self._call("POST", "/rag/monitoring/eval-runs", data={"set_id": str(set_id)})
        )

    def monitoring_eval(self, run_id: UUID) -> EvalRunView:
        return EvalRunView.model_validate(self._call("GET", f"/rag/monitoring/eval-runs/{run_id}"))

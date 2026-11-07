from datetime import UTC, datetime

from parrilladas.core.config import ApiSettings
from parrilladas.integrations.whatsapp.client import MetaClient
from parrilladas.modules.integrations.schemas import (
    ConnectionResult,
    ConnectivityCheck,
    WhatsAppIntegrationStatus,
)


class IntegrationService:
    def __init__(self, settings: ApiSettings, meta: MetaClient):
        self.settings = settings
        self.meta = meta

    def status(self) -> WhatsAppIntegrationStatus:
        settings = self.settings
        return WhatsAppIntegrationStatus(
            webhook_url=(
                f"{settings.api_public_base_url}/webhooks/whatsapp"
                if settings.api_public_base_url
                else None
            ),
            webhook_enabled=settings.whatsapp_app_secret is not None,
            access_token_configured=settings.whatsapp_access_token is not None,
            graph_api_version=settings.whatsapp_graph_api_version,
            business_account_id=settings.whatsapp_business_account_id,
            phone_number_id=settings.whatsapp_phone_number_id,
        )

    def check(self) -> WhatsAppIntegrationStatus:
        report = self.status()
        if not all(
            (
                report.access_token_configured,
                report.graph_api_version,
                report.business_account_id,
                report.phone_number_id,
            )
        ):
            result = ConnectionResult(
                status="not_configured",
                message=(
                    "Configure el token de acceso, la versión de Graph API "
                    "y los IDs de cuenta y número."
                ),
            )
            report.check = ConnectivityCheck(
                checked_at=datetime.now(UTC), meta=result, whatsapp=result
            )
            return report
        lookup = self.meta.lookup_phone(
            report.graph_api_version,
            report.business_account_id,
            report.phone_number_id,
            self.settings.whatsapp_access_token.get_secret_value(),
        )
        messages = {
            "access_denied": (
                "Meta rechazó el acceso. Revise la vigencia del token "
                "y sus permisos de WhatsApp Business Management."
            ),
            "rate_limited": "Meta limitó las consultas. Intente de nuevo más tarde.",
            "unavailable": "No se pudo contactar con Meta. Intente de nuevo más tarde.",
            "invalid_response": (
                "Meta no devolvió una respuesta válida. "
                "Revise la versión de Graph API y la cuenta configurada."
            ),
        }
        if lookup.outcome != "ok":
            meta = ConnectionResult(status="error", message=messages[lookup.outcome])
            whatsapp = ConnectionResult(status="unknown", message="No se pudo comprobar el número.")
        else:
            meta = ConnectionResult(
                status="ok", message="Acceso confirmado a la cuenta de WhatsApp en Meta."
            )
            if lookup.phone_found is True:
                whatsapp = ConnectionResult(
                    status="ok",
                    message="El número configurado pertenece a esta cuenta y es accesible.",
                )
            elif lookup.phone_found is False:
                whatsapp = ConnectionResult(
                    status="error",
                    message=(
                        "El número configurado no aparece en esta cuenta. "
                        "Revise los IDs y permisos."
                    ),
                )
            else:
                whatsapp = ConnectionResult(
                    status="unknown",
                    message=(
                        "Meta devolvió una lista parcial. "
                        "No se pudo confirmar el número configurado."
                    ),
                )
        report.check = ConnectivityCheck(checked_at=datetime.now(UTC), meta=meta, whatsapp=whatsapp)
        return report

from fastapi import APIRouter, Request

from parrilladas.modules.accounts.dependencies import Admin

from .rag_contracts import KnowledgeOverview

router = APIRouter(prefix="/assistant/knowledge", tags=["assistant"])


@router.get("", response_model=KnowledgeOverview)
def knowledge(context: Admin, request: Request) -> KnowledgeOverview:
    # This installation has one business; clients cannot supply a different tenant.
    return request.app.state.knowledge.overview(tenant_id="parrilladas")

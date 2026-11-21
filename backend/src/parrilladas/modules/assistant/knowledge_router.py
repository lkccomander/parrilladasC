from fastapi import APIRouter, Request

from parrilladas.modules.accounts.dependencies import Dev

from .rag_contracts import KnowledgeOverview

router = APIRouter(tags=["rag"])


@router.get("/assistant/knowledge", response_model=KnowledgeOverview, include_in_schema=False)
@router.get("/rag/knowledge", response_model=KnowledgeOverview)
def knowledge(context: Dev, request: Request) -> KnowledgeOverview:
    # This installation has one business; clients cannot supply a different tenant.
    return request.app.state.knowledge.overview(tenant_id="parrilladas")

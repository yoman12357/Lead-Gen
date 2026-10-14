from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.services.company_intel.pdf import build_company_intel_pdf, company_intel_pdf_filename
from core.services.company_intel.service import CompanyIntelService
from core.services.company_intel.store import CompanyIntelRunStore


router = APIRouter()


class CompanyIntelChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    lead_count: int = Field(default=8, ge=1, le=15)
    session_id: Optional[str] = None


_store = CompanyIntelRunStore()
_company_intel_service = CompanyIntelService(store=_store)


def _service() -> CompanyIntelService:
    return _company_intel_service


def _run_store() -> CompanyIntelRunStore:
    return _store


@router.post("/chat")
async def chat(request: CompanyIntelChatRequest) -> Dict[str, Any]:
    try:
        return await _service().chat(
            prompt=request.prompt,
            lead_count=request.lead_count,
            session_id=request.session_id or "",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@router.get("/run/{run_id}/pdf")
async def download_run_pdf(run_id: str) -> Response:
    run = _run_store().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Company intel run not found")
    try:
        pdf_bytes = build_company_intel_pdf(run)
        filename = company_intel_pdf_filename(run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {type(exc).__name__}: {exc}") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


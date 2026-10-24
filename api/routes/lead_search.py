from typing import Annotated
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator

from core.services.lead_search_jobs import LeadSearchJobs, SearchBusy


router = APIRouter()
jobs = LeadSearchJobs()
SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


class SearchRequest(BaseModel):
    industry: SearchText
    location: SearchText
    target_count: int = Field(default=15, ge=1, le=100)
    mode: Literal['generic', 'velit'] = 'generic'
    target_role: str = Field(default="", max_length=100)
    request_key: str = Field(min_length=20, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")

    @model_validator(mode='after')
    def count_for_mode(self):
        if self.mode == 'generic' and self.target_count > 50:
            raise ValueError('Generic searches support at most 50 leads.')
        return self


@router.post("", status_code=202)
async def create_search(request: SearchRequest):
    try:
        return await jobs.create(request.model_dump(exclude={"request_key"}), request.request_key)
    except SearchBusy as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "10"})
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/{run_id}")
async def get_search(run_id: str):
    result = jobs.get(run_id)
    if not result:
        raise HTTPException(404, "Search not found.")
    return result


@router.post("/{run_id}/cancel")
async def cancel_search(run_id: str):
    result = await jobs.cancel(run_id)
    if not result:
        raise HTTPException(404, "Search not found.")
    return result

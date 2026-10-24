from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Any
import asyncio
import inspect
import json
import os
import re
from api.state import get_state
from core.services.lead_quality_service import score_lead
from core.services.lead_service import LeadService
from core.utils.email_verify import verify_email_legitimacy
from core.utils.lead_summary import build_plain_lead_summary
from core.utils.spam_scorer import calculate_spam_score

router = APIRouter()

EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
EMPTY_EMAIL_VALUES = {"", "-", "--", "—", "n/a", "na", "none", "null", "not found"}

class LeadExportRequest(BaseModel):
    leads: List[Dict[str, Any]]
    mode: str = "generic"

class LeadBulkVerifyRequest(BaseModel):
    leads: List[Dict[str, Any]]
    batch_size: int = Field(default=10, ge=1, le=50)
    max_concurrency: int = Field(default=5, ge=1, le=10)
    skip_already_verified: bool = False

class EmailVerifyRequest(BaseModel):
    email: str
    subject: str = ""
    body: str = ""
    lead: Dict[str, Any] = Field(default_factory=dict)

class LinkedInSessionRequest(BaseModel):
    cookie_value: str

@router.post("/export")
async def export_leads(request: LeadExportRequest):
    state = get_state()
    if not state.todo_store:
        raise HTTPException(status_code=500, detail="Google Sheets storage not configured")
    
    service = LeadService(state.todo_store)
    result = await service.export_leads(request.leads, mode=request.mode)
    return result


def _extract_email(value: Any) -> str:
    match = EMAIL_PATTERN.search(str(value or ""))
    return match.group(0).strip() if match else ""


def _lead_email(lead: Dict[str, Any]) -> str:
    for key in ("contact_email", "email", "Email", "Email (Required)", "Contact Email"):
        email = _extract_email(lead.get(key))
        if email and email.lower() not in EMPTY_EMAIL_VALUES:
            return email
    return ""


def _has_verification(lead: Dict[str, Any]) -> bool:
    verification = lead.get("email_verification")
    if isinstance(verification, dict) and (
        verification.get("status") or verification.get("normalized_email") or verification.get("message")
    ):
        return True
    return False


def _verification_error(email: str, exc: Exception) -> Dict[str, Any]:
    return {
        "email": email,
        "normalized_email": email,
        "status": "error",
        "confidence": 0,
        "message": f"Email verification failed internally: {type(exc).__name__}",
        "checks": [
            {
                "name": "verification_runtime",
                "status": "failed",
                "detail": str(exc),
            }
        ],
    }


def _verification_label(verification: dict) -> str:
    status = str(verification.get("status") or "").strip().lower()
    confidence = verification.get("confidence", 0)
    message = str(verification.get("message") or "").strip()

    if status == "valid":
        label = "verified"
    elif status == "risky":
        label = "needs manual review"
    elif status in {"invalid", "error"}:
        label = status
    else:
        label = status or "unknown"

    if confidence not in ("", None):
        label = f"{label} ({confidence}%)"
    if message:
        label = f"{label} - {message}"
    return label


def _ensure_lead_summary(lead: Dict[str, Any]) -> None:
    if not any(
        lead.get(key)
        for key in (
            "company_name",
            "specialty",
            "industry",
            "company_website",
            "website",
            "notes",
            "value_proposition",
        )
    ):
        return
    lead["lead_summary"] = build_plain_lead_summary(lead)


def _apply_email_verification(lead: Dict[str, Any], verification: Dict[str, Any], lead_quality: Dict[str, Any] | None = None) -> Dict[str, Any]:
    updated = dict(lead)
    updated["verifying"] = False
    checks = verification.get("checks") if isinstance(verification.get("checks"), list) else []
    status = verification.get("status") or updated.get("verification_status") or ""
    label = _verification_label(verification)

    updated["email_verification"] = verification
    updated["verification_checks"] = checks
    updated["verification_status"] = status
    updated["email_status"] = label
    updated["email_verification_status"] = label
    updated["verification_message"] = verification.get("message") or ""
    updated["verification_confidence"] = verification.get("confidence", updated.get("verification_confidence"))
    updated["email_provider_type"] = verification.get("provider_type") or ""
    updated["email_mx_found"] = bool(verification.get("mx_found"))
    updated["email_smtp_connected"] = bool(verification.get("smtp_connected"))
    updated["email_smtp_verified"] = bool(verification.get("smtp_verified"))
    updated["email_catch_all"] = bool(verification.get("catch_all"))
    updated["email_is_role"] = bool(verification.get("is_role_email"))
    updated["email_role_type"] = verification.get("role_email_type") or ""
    updated["email_recipient_code"] = verification.get("recipient_probe_code") or ""
    updated["email_verification_duration_ms"] = verification.get("duration_ms") or 0

    if lead_quality:
        updated["pipeline_disposition"] = "Rejected" if lead_quality.get("rejected") else "Approved" if lead_quality.get("quality_status") == "Strong" else "Needs_Review"
        updated["quality_score"] = lead_quality.get("quality_score", updated.get("quality_score"))
        updated["confidence"] = lead_quality.get("confidence") or updated.get("confidence")
        updated["quality_status"] = lead_quality.get("quality_status") or updated.get("quality_status")
        updated["usable"] = lead_quality.get("usable", updated.get("usable"))
        updated["rejected"] = lead_quality.get("rejected", updated.get("rejected"))
        updated["quality_notes"] = lead_quality.get("quality_notes") or updated.get("quality_notes")
        updated["quality_warnings"] = lead_quality.get("quality_warnings") or updated.get("quality_warnings")
        updated["acceptance_reason"] = (
            lead_quality.get("acceptance_reason")
            or lead_quality.get("confidence_explanation")
            or updated.get("acceptance_reason")
        )
        updated["confidence_explanation"] = updated["acceptance_reason"]
        updated["field_sources"] = lead_quality.get("field_sources") or updated.get("field_sources")

    _ensure_lead_summary(updated)
    return updated


async def _verify_export_lead(lead: Dict[str, Any], *, skip_already_verified: bool, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    updated = dict(lead)
    email = _lead_email(updated)
    if not email:
        verification = {
            "email": "",
            "normalized_email": "",
            "status": "no_email_found",
            "confidence": 0,
            "message": "No email address was found on this lead.",
            "checks": [],
        }
        return _apply_email_verification(updated, verification, score_lead(updated, verification))

    if skip_already_verified and _has_verification(updated):
        return _apply_email_verification(updated, updated["email_verification"], score_lead(updated))

    async with semaphore:
        try:
            verification = await run_in_threadpool(verify_email_legitimacy, email)
        except Exception as exc:
            verification = _verification_error(email, exc)

    lead_stub = dict(updated)
    lead_stub["contact_email"] = email
    lead_stub["verification_status"] = verification.get("status", "")
    lead_stub["verification_message"] = verification.get("message", "")
    lead_quality = score_lead(lead_stub, verification=verification)
    return _apply_email_verification(updated, verification, lead_quality=lead_quality)


@router.post("/verify-bulk")
async def verify_leads_for_export(request: LeadBulkVerifyRequest):
    """
    Verify visible leads in backend batches before the browser writes the Excel file.
    The endpoint intentionally waits for all batches so export receives final statuses.
    """
    batch_size = max(1, min(int(request.batch_size or 10), 50))
    max_concurrency = max(1, min(int(request.max_concurrency or 5), 10))
    leads = [dict(lead or {}) for lead in (request.leads or [])]
    semaphore = asyncio.Semaphore(max_concurrency)

    verified_leads: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}
    with_email = 0

    for start in range(0, len(leads), batch_size):
        batch = leads[start : start + batch_size]
        results = await asyncio.gather(
            *(
                _verify_export_lead(
                    lead,
                    skip_already_verified=request.skip_already_verified,
                    semaphore=semaphore,
                )
                for lead in batch
            )
        )
        for lead in results:
            if _lead_email(lead):
                with_email += 1
            status = str(lead.get("verification_status") or lead.get("email_status") or "unknown").lower()
            status_counts[status] = status_counts.get(status, 0) + 1
        verified_leads.extend(results)

    return {
        "leads": verified_leads,
        "summary": {
            "total": len(leads),
            "with_email": with_email,
            "without_email": len(leads) - with_email,
            "batch_size": batch_size,
            "max_concurrency": max_concurrency,
            "batches": (len(leads) + batch_size - 1) // batch_size if leads else 0,
            "status_counts": status_counts,
        },
    }

@router.post("/verify")
async def verify_lead(request: EmailVerifyRequest):
    try:
        verification = await run_in_threadpool(verify_email_legitimacy, request.email)
    except Exception as exc:
        verification = {
            "email": request.email,
            "status": "error",
            "confidence": 0,
            "message": f"Email verification failed internally: {type(exc).__name__}",
            "checks": [
                {
                    "name": "verification_runtime",
                    "status": "failed",
                    "detail": str(exc),
                }
            ],
        }
    lead_quality = {}
    if request.lead:
        lead_stub = dict(request.lead)
        lead_stub["contact_email"] = request.email
        lead_stub["verification_status"] = verification.get("status", "")
        lead_stub["verification_message"] = verification.get("message", "")
        lead_quality = score_lead(lead_stub, verification=verification)

    spam_analysis = {}
    if request.subject or request.body:
        spam_analysis = calculate_spam_score(request.subject, request.body)
    
    return {
        "verification": verification,
        "lead_quality": lead_quality,
        "spam_analysis": spam_analysis
    }

@router.get("/existing")
async def get_existing_leads(mode: str = "generic"):
    state = get_state()
    if not state.todo_store:
        return {"companies": []}
    
    service = LeadService(state.todo_store)
    try:
        companies = await service.get_existing_companies(mode=mode)
        return {"companies": companies}
    except Exception as e:
        import logging
        logging.getLogger("api.leads").warning(f"Failed to fetch existing companies: {e}")
        return {"companies": []}


@router.get("/details")
async def get_lead_details():
    state = get_state()
    if not state.todo_store:
        raise HTTPException(status_code=500, detail="Google Sheets storage not configured")

    list_leads = state.todo_store.list_leads
    if inspect.iscoroutinefunction(list_leads):
        return await list_leads()
    return await run_in_threadpool(list_leads)

@router.post("/linkedin_session")
async def update_linkedin_session(request: LinkedInSessionRequest):
    session_path = os.path.join(os.getcwd(), "linkedin_session.json")
    if os.getenv("VERCEL") == "1":
        session_path = os.path.join("/tmp", "linkedin_session.json")
    
    # Standard Playwright storage state format with the user-provided li_at cookie
    session_data = {
        "cookies": [
            {
                "name": "li_at",
                "value": request.cookie_value.strip(),
                "domain": ".linkedin.com",
                "path": "/",
                "expires": 1810667126.159561,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            },
            {
                "name": "JSESSIONID",
                "value": "ajax:0000000000000000000",
                "domain": ".linkedin.com",
                "path": "/",
                "expires": 1810667126.159561,
                "httpOnly": False,
                "secure": True,
                "sameSite": "None"
            }
        ],
        "origins": []
    }
    
    try:
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
        return {"status": "success", "message": "LinkedIn session updated successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save session: {str(e)}")

@router.get("/linkedin_session/status")
async def get_linkedin_session_status():
    session_path = os.path.join(os.getcwd(), "linkedin_session.json")
    if os.getenv("VERCEL") == "1":
        session_path = os.path.join("/tmp", "linkedin_session.json")
    if not os.path.exists(session_path):
        return {"status": "inactive", "message": "No saved session found"}
        
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            cookies = data.get("cookies", [])
            li_at = next((c for c in cookies if c.get("name") == "li_at"), None)
            if li_at and li_at.get("value"):
                return {"status": "active", "message": "Session is active"}
    except Exception:
        pass
        
    return {"status": "inactive", "message": "Invalid or expired session"}


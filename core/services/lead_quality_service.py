from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse
import logging
from core.utils.phone_quality import normalize_phone_candidate, phone_region_for_location

logger = logging.getLogger(__name__)

GENERIC_EMAIL_PREFIXES = {
    "info",
    "support",
    "contact",
    "hello",
    "sales",
    "admin",
    "office",
    "team",
    "help",
}

HIGH_PRIORITY_TITLES = {
    "founder",
    "co-founder",
    "owner",
    "ceo",
    "managing director",
    "director",
}


def _clean(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    return "" if text.lower() in {"—", "-", "--", "none", "null", "n/a", "not found"} else text


def _first_non_empty(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _domain_from_url(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower()


def _domain_from_email(email: str) -> str:
    parts = (email or "").split("@", 1)
    return parts[1].lower().strip() if len(parts) == 2 else ""


def _is_generic_email(email: str) -> bool:
    local = (email or "").split("@", 1)[0].lower().strip()
    return local in GENERIC_EMAIL_PREFIXES


def _acceptance_explanation(
    *,
    lead: Dict[str, Any],
    score: int,
    quality_status: str,
    rejected: bool,
    notes: List[str],
    warnings: List[str],
) -> str:
    company = _clean(lead.get("company_name")) or "This lead"
    website = _clean(lead.get("company_website"))
    email = _clean(lead.get("contact_email"))
    phone = _clean(lead.get("contact_phone"))
    linkedin_url = _clean(lead.get("linkedin_url"))
    contact_page = _clean(lead.get("contact_page"))
    value_prop = _clean(lead.get("value_proposition"))

    if rejected:
        reasons = []
        if not _clean(lead.get("company_name")):
            reasons.append("company name is missing")
        if not website:
            reasons.append("company website is missing")
        if not any((email, phone, linkedin_url, contact_page)):
            reasons.append("no contact path was found")
        if "email_invalid" in warnings:
            reasons.append("email verification marked the email invalid")
        return f"Rejected because {', '.join(reasons) or 'it did not pass the quality rules'}."

    signals = []
    if website:
        signals.append("official website")
    if email:
        signals.append("email")
    if phone:
        signals.append("phone")
    if linkedin_url:
        signals.append("LinkedIn")
    if contact_page:
        signals.append("contact page")
    if value_prop:
        signals.append("business description")

    signal_text = ", ".join(dict.fromkeys(signals)) or "basic company evidence"
    note_text = ""
    if notes:
        readable_notes = [note.replace("_", " ") for note in notes[:3]]
        note_text = f" Extra signals: {', '.join(readable_notes)}."
    display_score = max(0, min(int(score or 0), 100))
    warning_text = f" Review: {', '.join(w.replace('_', ' ') for w in warnings)}." if warnings else ""
    return f"{company}: {quality_status}. Evidence: {signal_text}. Quality score: {display_score}/100.{note_text}{warning_text}"


def _field_source_map(lead: Dict[str, Any]) -> Dict[str, str]:
    existing = lead.get("field_sources")
    if isinstance(existing, dict):
        normalized = {}
        for key, value in existing.items():
            cleaned = _clean(value)
            if cleaned:
                normalized[str(key)] = cleaned
        if normalized:
            return normalized

    source = _clean(lead.get("source")) or "unknown"
    field_sources: Dict[str, str] = {}

    if _clean(lead.get("company_name")):
        field_sources["company_name"] = source
    if _clean(lead.get("company_website")):
        field_sources["company_website"] = "website" if "website" in source or source == "unknown" else source
    if _clean(lead.get("contact_person_name")) or _clean(lead.get("founder_name")):
        field_sources["contact_person_name"] = "linkedin" if _clean(lead.get("linkedin_url")) else source
    if _clean(lead.get("contact_person_title")):
        field_sources["contact_person_title"] = "linkedin" if _clean(lead.get("linkedin_url")) else source
    if _clean(lead.get("contact_email")):
        field_sources["contact_email"] = "linkedin" if source == "linkedin" else source
    if _clean(lead.get("contact_phone")):
        field_sources["contact_phone"] = source
    if _clean(lead.get("linkedin_url")):
        field_sources["linkedin_url"] = "linkedin"
    if _clean(lead.get("contact_page")):
        field_sources["contact_page"] = "website"
    if _clean(lead.get("location")):
        field_sources["location"] = source
    return field_sources


def score_lead(lead: Dict[str, Any], verification: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        company_name = _clean(lead.get("company_name"))
        website = _clean(lead.get("company_website"))
        person_name = _first_non_empty(lead.get("contact_person_name"), lead.get("founder_name"))
        person_title = _clean(lead.get("contact_person_title"))
        email = _clean(lead.get("contact_email"))
        phone = _clean(lead.get("contact_phone"))
        linkedin_url = _clean(lead.get("linkedin_url"))
        contact_page = _clean(lead.get("contact_page"))
        value_prop = _clean(lead.get("value_proposition"))
        location = _clean(lead.get("location"))

        score = 0
        notes: List[str] = []
        warnings: List[str] = []
        if person_name.casefold() == company_name.casefold():
            person_name = ""
        verification = verification if verification is not None else lead.get("email_verification") or {}
        email_status = _clean(verification.get("status")).lower()
        verified_email = email_status == "valid" and bool(verification.get("smtp_verified"))
        phone_candidate = normalize_phone_candidate(phone, region=phone_region_for_location(location)) if phone else None
        valid_phone = bool(phone_candidate and phone_candidate.get("validation_status") == "valid")
        if phone and not valid_phone:
            warnings.append("phone_not_validated")
        if email and not verified_email:
            warnings.append("email_not_verified")
        if lead.get("location_match") is False:
            warnings.append("location_not_confirmed")
        if lead.get("industry_match") is False:
            warnings.append("industry_mismatch")

        if company_name:
            score += 15
        else:
            warnings.append("missing_company_name")

        if website:
            score += 18
        else:
            warnings.append("missing_company_website")

        if person_name:
            score += 18  # Increased from 16
        else:
            warnings.append("missing_contact_person")

        if person_title:
            score += 10  # Increased from 8
            if any(title in person_title.lower() for title in HIGH_PRIORITY_TITLES):
                score += 5
                notes.append("priority_title")

        email_domain = _domain_from_email(email)
        website_domain = _domain_from_url(website)

        if email:
            score += 16  # Increased from 14
            if not _is_generic_email(email):
                score += 6  # Bonus for non-generic email
                notes.append("direct_email")
            else:
                notes.append("generic_email_fallback")

            website_domain = website_domain.removeprefix("www.")
            if website_domain and email_domain and (email_domain == website_domain or email_domain.endswith("." + website_domain)):
                score += 4
                notes.append("email_matches_company_domain")
        else:
            warnings.append("missing_email")

        if valid_phone:
            score += 8
        if linkedin_url:
            score += 8
        if contact_page:
            score += 6
        if value_prop:
            score += 8 # Increased from 5
        else:
            score -= 4 # Penalty
            warnings.append("missing_value_proposition")
        if location:
            score += 4

        if verification:
            status = _clean(verification.get("status")).lower()
            if verified_email:
                score += 14
                notes.append("email_verified_valid")
            elif status == "risky":
                notes.append("email_verification_risky")
            elif status == "invalid":
                score -= 14
                warnings.append("email_invalid")

        fallback_paths = lead.get("fallback_contact_paths")
        if isinstance(fallback_paths, list) and fallback_paths:
            score += min(6, len(fallback_paths) * 2)

        usable_contact_paths = sum(bool(value) for value in (
            email if email_status != "invalid" else "", valid_phone,
            linkedin_url, lead.get("company_linkedin_url"), lead.get("contact_form_found") is True,
        ))
        if usable_contact_paths == 0:
            score -= 18
            warnings.append("no_contact_path")

        if not website and not linkedin_url and not contact_page:
            score -= 20
            warnings.append("weak_public_presence")

        if person_name and not email and not phone and not linkedin_url:
            score -= 6
            notes.append("person_without_contact_path")

        # A complete-looking row is not proof of a reachable decision maker.
        if not person_name or not (verified_email or valid_phone):
            score = min(score, 69)
        if email and not verified_email:
            score = min(score, 69)
        if "phone_not_validated" in warnings or "location_not_confirmed" in warnings:
            score = min(score, 49)
        score = max(0, min(score, 100))

        if score >= 80:  # Adjusted threshold
            confidence = "high"
        elif score >= 50:  # Adjusted threshold
            confidence = "medium"
        else:
            confidence = "low"

        rejected = (
            not company_name
            or not website
            or usable_contact_paths == 0
            or lead.get("industry_match") is False
            or lead.get("location_match") is False
            or lead.get("site_status") in {"dead", "blocked", "soft_404"}
        )
        usable = not rejected and score >= 40 # Adjusted threshold

        if rejected:
            quality_status = "Rejected"
        elif "email_not_verified" in warnings or "missing_contact_person" in warnings or "phone_not_validated" in warnings:
            quality_status = "Needs_Review"
        elif confidence == "high":
            quality_status = "Strong"
        elif confidence == "medium":
            quality_status = "Usable"
        else:
            quality_status = "Partial"
        acceptance_reason = _acceptance_explanation(
            lead=lead,
            score=score,
            quality_status=quality_status,
            rejected=rejected,
            notes=notes,
            warnings=warnings,
        )

        return {
            "quality_score": score,
            "confidence": confidence,
            "quality_status": quality_status,
            "usable": usable,
            "rejected": rejected,
            "acceptance_reason": acceptance_reason,
            "confidence_explanation": acceptance_reason,
            "quality_notes": notes,
            "quality_warnings": warnings,
            "field_sources": _field_source_map(lead),
        }
    except Exception as e:
        logger.error(f"Error scoring lead: {e}", exc_info=True)
        return {
            "quality_score": 0,
            "confidence": "low",
            "quality_status": "Error",
            "usable": False,
            "rejected": True,
            "acceptance_reason": "Rejected because the scoring step failed.",
            "confidence_explanation": "Rejected because the scoring step failed.",
            "quality_notes": [],
            "quality_warnings": ["scoring_error"],
            "field_sources": {},
        }


def rank_and_enrich_leads(leads: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    enriched: List[Dict[str, Any]] = []
    stats = {
        "input_count": len(leads),
        "rejected_count": 0,
        "usable_count": 0,
        "partial_count": 0,
        "error_count": 0,
    }

    for lead in leads:
        item = deepcopy(lead)
        quality = score_lead(item)
        item.update(quality)
        
        if item.get("quality_status") == "Error":
            stats["error_count"] += 1
            stats["rejected_count"] += 1
            continue
        
        if item["rejected"]:
            stats["rejected_count"] += 1
            continue
            
        if item["quality_status"] == "Partial":
            stats["partial_count"] += 1
        else:
            stats["usable_count"] += 1
        enriched.append(item)

    enriched.sort(
        key=lambda lead: (
            lead.get("quality_score", 0),
            1 if lead.get("confidence") == "high" else 0,
            1 if _clean(lead.get("contact_email")) else 0,
            1 if _clean(lead.get("contact_person_name") or lead.get("founder_name")) else 0,
        ),
        reverse=True,
    )
    return enriched, stats

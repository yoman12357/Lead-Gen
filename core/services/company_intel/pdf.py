from __future__ import annotations

import re
import textwrap
from datetime import datetime
from typing import Any, Dict, Iterable, List


def build_company_intel_pdf(run: Dict[str, Any]) -> bytes:
    """Build a simple text PDF for a saved company-intel run."""

    profile = run.get("company_profile") if isinstance(run.get("company_profile"), dict) else {}
    leads = run.get("leads") if isinstance(run.get("leads"), list) else []
    warnings = run.get("warnings") if isinstance(run.get("warnings"), list) else []
    errors = run.get("errors") if isinstance(run.get("errors"), list) else []

    lines: List[str] = []
    company = _clean(profile.get("company_name")) or "Company"
    lines.append(f"Company Intelligence Report: {company}")
    lines.append(f"Run ID: {_clean(run.get('run_id'))}")
    lines.append(f"Generated: {_clean(run.get('timestamp')) or datetime.utcnow().isoformat()}")
    lines.append(f"Prompt: {_clean(run.get('prompt'))}")
    lines.append("")

    lines.append("Company Overview")
    lines.append(_clean(profile.get("summary")) or "No company summary was available.")
    if _clean(profile.get("website")):
        lines.append(f"Website: {_clean(profile.get('website'))}")
    lines.append("")

    _append_section(lines, "Services", profile.get("services") or [])
    contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
    _append_section(lines, "Emails", contacts.get("emails") or [])
    _append_section(lines, "Phones", contacts.get("phones") or [])
    _append_social_links(lines, profile.get("social_links") or [])
    _append_leads(lines, leads)
    _append_section(lines, "Source URLs", profile.get("source_urls") or [])
    _append_section(lines, "Warnings", warnings)
    _append_section(lines, "Errors", errors)

    pages = _paginate(lines)
    return _render_pdf_pages(pages)


def company_intel_pdf_filename(run: Dict[str, Any]) -> str:
    profile = run.get("company_profile") if isinstance(run.get("company_profile"), dict) else {}
    company = _slug(_clean(profile.get("company_name")) or "company")
    date_text = _clean(run.get("timestamp"))[:10] or datetime.utcnow().strftime("%Y-%m-%d")
    return f"company_intel_{company}_{date_text}.pdf"


def _append_section(lines: List[str], title: str, values: Iterable[Any]) -> None:
    clean_values = [_clean(value) for value in values if _clean(value)]
    if not clean_values:
        return
    lines.append(title)
    for value in clean_values[:20]:
        lines.append(f"- {value}")
    lines.append("")


def _append_social_links(lines: List[str], links: Iterable[Any]) -> None:
    clean_links: List[str] = []
    for link in links:
        if isinstance(link, dict):
            label = _clean(link.get("label") or link.get("type") or "social")
            url = _clean(link.get("url"))
            if url:
                clean_links.append(f"{label}: {url}")
        elif _clean(link):
            clean_links.append(_clean(link))
    _append_section(lines, "Social Links", clean_links)


def _append_leads(lines: List[str], leads: List[Any]) -> None:
    lines.append("Lead Contacts")
    if not leads:
        lines.append("No Hunter leads were available for this run.")
        lines.append("")
        return
    for index, raw in enumerate(leads[:15], start=1):
        lead = raw if isinstance(raw, dict) else {}
        name = _clean(lead.get("contact_person_name") or lead.get("founder_name") or lead.get("name")) or "Unknown person"
        title = _clean(lead.get("contact_person_title") or lead.get("title") or lead.get("role"))
        email = _clean(lead.get("contact_email") or lead.get("email"))
        phone = _clean(lead.get("contact_phone") or lead.get("phone"))
        status = _clean(lead.get("verification_status") or lead.get("email_verification_status"))
        score = _clean(lead.get("quality_score"))
        parts = [name]
        if title:
            parts.append(title)
        if email:
            parts.append(email)
        if phone:
            parts.append(phone)
        if status:
            parts.append(f"status={status}")
        if score:
            parts.append(f"score={score}")
        lines.append(f"{index}. " + " | ".join(parts))
    lines.append("")


def _paginate(lines: List[str], *, max_lines_per_page: int = 44, width: int = 92) -> List[List[str]]:
    pages: List[List[str]] = [[]]
    for line in lines:
        wrapped = textwrap.wrap(line, width=width) or [""]
        for wrapped_line in wrapped:
            if len(pages[-1]) >= max_lines_per_page:
                pages.append([])
            pages[-1].append(wrapped_line)
    return pages


def _render_pdf_pages(pages: List[List[str]]) -> bytes:
    objects: List[bytes] = []
    page_ids: List[int] = []

    def add_object(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = 0
    for page_lines in pages or [[]]:
        content = _page_content_stream(page_lines)
        content_id = add_object(b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream")
        page_id = add_object(
            (
                f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    patched_objects = []
    for data in objects:
        patched_objects.append(data.replace(b"/Parent 0 0 R", f"/Parent {pages_id} 0 R".encode("ascii")))

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, data in enumerate(patched_objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(data)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(patched_objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(patched_objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _page_content_stream(lines: List[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _pdf_escape(value: Any) -> str:
    return _clean(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "company"


from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from core.services.company_intel.store import CompanyIntelRunStore
from core.tools.external.tavily_client import TavilyClient
from core.utils.phone_quality import phone_summary_from_text


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
SOCIAL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:linkedin\.com|instagram\.com|facebook\.com|x\.com|twitter\.com|youtube\.com)/[^\s\"'<>),]+",
    re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"(?is)<[^>]+>")
SCRIPT_STYLE_PATTERN = re.compile(r"(?is)<(?:script|style).*?>.*?</(?:script|style)>")


class CompanyIntelService:
    """Additive company intelligence chatbot service."""

    def __init__(
        self,
        *,
        store: Optional[CompanyIntelRunStore] = None,
        tavily_factory: Callable[[], Any] = TavilyClient,
        hunter_pipeline_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.store = store or CompanyIntelRunStore()
        self.tavily_factory = tavily_factory
        self.hunter_pipeline_factory = hunter_pipeline_factory

    async def chat(self, *, prompt: str, lead_count: int = 8, session_id: str = "") -> Dict[str, Any]:
        prompt = _clean(prompt)
        lead_count = max(1, min(int(lead_count or 8), 15))
        parsed = self.parse_prompt(prompt)
        if not parsed.get("company_name"):
            return {
                "success": False,
                "run_id": "",
                "assistant_message": "Which company should I research? Please send the company name.",
                "company_profile": {},
                "leads": [],
                "warnings": ["company_name_missing"],
                "errors": [],
                "steps": [{"name": "request_parsing", "status": "needs_clarification", "message": "Company name was not clear."}],
            }

        run_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []
        errors: List[str] = []
        steps: List[Dict[str, Any]] = [
            {
                "name": "request_parsing",
                "status": "completed",
                "message": f"Detected company: {parsed['company_name']}.",
            }
        ]

        company_profile = await self.collect_company_profile(
            company_name=parsed["company_name"],
            location_hint=parsed.get("location_hint", ""),
            industry_hint=parsed.get("industry_hint", ""),
            warnings=warnings,
            errors=errors,
            steps=steps,
        )
        leads = await self.fetch_hunter_leads(
            company_profile=company_profile,
            company_name=parsed["company_name"],
            location_hint=parsed.get("location_hint", ""),
            industry_hint=parsed.get("industry_hint", ""),
            lead_count=lead_count,
            warnings=warnings,
            errors=errors,
            steps=steps,
        )
        if len(leads) < lead_count:
            warnings.append(f"Hunter returned {len(leads)} lead(s), below requested {lead_count}.")

        assistant_message = self._assistant_message(company_profile=company_profile, leads=leads, warnings=warnings)
        payload = {
            "success": True,
            "run_id": run_id,
            "session_id": _clean(session_id),
            "prompt": prompt,
            "timestamp": timestamp,
            "assistant_message": assistant_message,
            "company_profile": company_profile,
            "leads": leads,
            "warnings": warnings,
            "errors": errors,
            "steps": steps,
            "metadata": {
                "company_name": company_profile.get("company_name") or parsed["company_name"],
                "lead_count_requested": lead_count,
                "lead_count_returned": len(leads),
                "provider": "company_intel",
            },
        }
        self.store.save_run(payload)
        return payload

    @staticmethod
    def parse_prompt(prompt: str) -> Dict[str, str]:
        text = _clean(prompt)
        if not text or len(text) < 2:
            return {}

        quoted = re.search(r"[\"']([^\"']{2,90})[\"']", text)
        if quoted:
            company = quoted.group(1)
        else:
            company = ""
            patterns = [
                r"(?:details|info|information|leads|research|report)\s+(?:about|for|on)\s+(.+)",
                r"(?:show|give|get|create|build|find)\s+(?:details\s+and\s+leads\s+for|details\s+for|leads\s+for|info\s+for)\s+(.+)",
                r"(?:company\s+(?:called|named))\s+(.+)",
                r"(?:about|for)\s+(.+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    company = match.group(1)
                    break
            if not company and len(text.split()) <= 4:
                company = text

        company = _trim_company_candidate(company)
        if not company or company.lower() in {"company", "a company", "the company", "details", "leads"}:
            return {}

        location_hint = ""
        location_match = re.search(r"\b(?:in|near|around|from)\s+([A-Z][A-Za-z .,-]{2,50})", text)
        if location_match:
            location_hint = _clean(location_match.group(1).split(" for ", 1)[0])

        industry_hint = ""
        industry_match = re.search(r"\b(?:industry|sector|space)\s*[:=]?\s*([A-Za-z /&-]{3,60})", text, flags=re.IGNORECASE)
        if industry_match:
            industry_hint = _clean(industry_match.group(1))

        return {
            "company_name": company,
            "location_hint": location_hint,
            "industry_hint": industry_hint,
        }

    async def collect_company_profile(
        self,
        *,
        company_name: str,
        location_hint: str,
        industry_hint: str,
        warnings: List[str],
        errors: List[str],
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_urls: List[str] = []
        search_results: List[Dict[str, Any]] = []
        website = ""
        resolved_homepage_text = ""
        resolved_homepage_html = ""
        search_text = ""

        try:
            resolved = await self._resolve_company_website(company_name)
            if resolved.get("website"):
                website = resolved["website"]
                resolved_homepage_text = resolved.get("text", "")
                resolved_homepage_html = resolved.get("html", "")
                source_urls.append(website)
                steps.append(
                    {
                        "name": "company_domain_resolution",
                        "status": "completed",
                        "message": f"Resolved likely official domain: {_domain_from_url(website)}.",
                    }
                )
        except Exception as exc:
            steps.append(
                {
                    "name": "company_domain_resolution",
                    "status": "partial",
                    "message": f"Direct company-domain resolution did not confirm a website: {exc}",
                }
            )

        try:
            tavily = self.tavily_factory()
            query = " ".join(
                value
                for value in [
                    f'"{company_name}"',
                    location_hint,
                    industry_hint,
                    "official website contact services LinkedIn",
                ]
                if value
            )
            data = await tavily.search({"query": query, "max_results": 5, "include_raw_content": False})
            search_results = [item for item in data.get("results") or [] if isinstance(item, dict)]
            steps.append(
                {
                    "name": "company_search",
                    "status": "completed" if search_results else "partial",
                    "message": f"Found {len(search_results)} search result(s) for company research.",
                    "count": len(search_results),
                }
            )
        except Exception as exc:
            message = f"Company search failed: {exc}"
            warnings.append(message)
            errors.append(message)
            steps.append({"name": "company_search", "status": "partial", "message": message})

        for result in search_results:
            url = _clean(result.get("url"))
            if url and url not in source_urls:
                source_urls.append(url)
            search_text += " " + _clean(result.get("title")) + " " + _clean(result.get("content"))
            if not website and _looks_like_official_website(url, company_name=company_name):
                website = url

        page_text = resolved_homepage_text
        page_html = resolved_homepage_html
        if website:
            if not page_text:
                try:
                    fetched = await self._fetch_page(website)
                    page_text = fetched.get("text", "")
                    page_html = fetched.get("html", "")
                    if fetched.get("url") and fetched["url"] not in source_urls:
                        source_urls.insert(0, fetched["url"])
                    steps.append({"name": "website_scrape", "status": "completed", "message": "Scraped official website text."})
                except Exception as exc:
                    message = f"Website scraping failed: {exc}"
                    warnings.append(message)
                    steps.append({"name": "website_scrape", "status": "partial", "message": message})
            else:
                steps.append({"name": "website_scrape", "status": "completed", "message": "Used confirmed official homepage text."})
        else:
            warnings.append("Official website was not confidently found.")
            steps.append({"name": "website_scrape", "status": "skipped", "message": "No official website found."})

        combined_text = f"{search_text}\n{page_text}"
        emails = _unique(EMAIL_PATTERN.findall(combined_text))
        phone_summary = phone_summary_from_text(page_html or combined_text, source_type="company_intel", source_url=website)
        phones = _unique(
            [
                phone_summary.get("contact_phone", ""),
                *(phone_summary.get("alternate_phones") or []),
            ]
        )
        social_links = self._social_links(combined_text)
        services = self._extract_services(combined_text, industry_hint=industry_hint)
        summary = self._summary(company_name=company_name, text=combined_text, services=services, website=website)

        profile = {
            "company_name": company_name,
            "website": website,
            "summary": summary,
            "services": services,
            "contacts": {"emails": emails[:5], "phones": phones[:5]},
            "social_links": social_links,
            "source_urls": source_urls[:12],
            "location_hint": location_hint,
            "industry_hint": industry_hint,
        }
        steps.append(
            {
                "name": "company_profile_normalization",
                "status": "completed",
                "message": "Normalized company profile fields.",
            }
        )
        return profile

    async def fetch_hunter_leads(
        self,
        *,
        company_profile: Dict[str, Any],
        company_name: str,
        location_hint: str,
        industry_hint: str,
        lead_count: int,
        warnings: List[str],
        errors: List[str],
        steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        try:
            from core.services._test_features.hunter.hunter_search_pipeline import HunterSearchPipeline
        except Exception as exc:
            message = f"Hunter pipeline unavailable: {exc}"
            warnings.append(message)
            errors.append(message)
            steps.append({"name": "hunter_leads", "status": "partial", "message": message})
            return []

        pipeline = self.hunter_pipeline_factory() if self.hunter_pipeline_factory else HunterSearchPipeline()
        if not getattr(pipeline, "api_key", None):
            message = "HUNTER_API_KEY is not configured; Hunter leads were skipped."
            warnings.append(message)
            steps.append({"name": "hunter_leads", "status": "skipped", "message": message})
            return []

        domain = _domain_from_url(company_profile.get("website", ""))
        leads: List[Dict[str, Any]] = []
        try:
            if domain and hasattr(pipeline, "_hunter_domain_search"):
                data = await pipeline._hunter_domain_search(domain)
                leads = pipeline._assemble_domain_search_leads(
                    domain_payloads=[{"domain": domain, "data": data}],
                    industry=industry_hint or company_name,
                    location=location_hint or _clean(company_profile.get("location_hint")) or "",
                    target_count=lead_count,
                )
                steps.append(
                    {
                        "name": "hunter_domain_search",
                        "status": "completed" if leads else "partial",
                        "message": f"Ran Hunter domain search for {domain}.",
                        "count": len(leads),
                    }
                )
            else:
                result = await pipeline.run(
                    industry=industry_hint or company_name,
                    location=location_hint or "global",
                    seed_query=f'"{company_name}" {domain} company contacts',
                    target_count=lead_count,
                )
                leads = result.get("leads") if isinstance(result.get("leads"), list) else []
                warnings.extend(str(item) for item in result.get("warnings") or [] if str(item).strip())
                errors.extend(str(item) for item in result.get("errors") or [] if str(item).strip())
                steps.extend(result.get("steps") or [])
        except Exception as exc:
            message = f"Hunter lead lookup failed: {exc}"
            warnings.append(message)
            errors.append(message)
            steps.append({"name": "hunter_leads", "status": "partial", "message": message})
            return []

        normalized_pool = [
            self._normalize_lead(lead, company_name=company_name)
            for lead in leads
            if self._lead_matches_company_domain(lead, domain=domain)
        ]
        normalized_pool.sort(key=self._person_lead_rank, reverse=True)
        person_leads = [lead for lead in normalized_pool if lead.get("contact_person_name")]
        generic_leads = [lead for lead in normalized_pool if not lead.get("contact_person_name")]
        normalized = (person_leads + generic_leads)[:lead_count]
        if generic_leads and len(person_leads) < lead_count:
            warnings.append(
                f"Hunter returned only {len(person_leads)} person-named lead(s) for {_domain_from_url(company_profile.get('website', '')) or company_name}; generic role emails were used only as fallback."
            )
        steps.append(
            {
                "name": "hunter_lead_normalization",
                "status": "completed" if normalized else "partial",
                "message": f"Prepared {len(normalized)} Hunter lead(s).",
                "count": len(normalized),
            }
        )
        return normalized

    async def _resolve_company_website(self, company_name: str) -> Dict[str, str]:
        for candidate in _candidate_company_urls(company_name):
            try:
                fetched = await self._fetch_page(candidate)
            except Exception:
                continue
            text = fetched.get("text", "")
            final_url = fetched.get("url") or candidate
            if _page_matches_company(text=text, url=final_url, company_name=company_name):
                return {
                    "website": _homepage_url(final_url),
                    "text": text,
                    "html": fetched.get("html", ""),
                }
        return {}

    async def _fetch_page(self, url: str) -> Dict[str, str]:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            response.raise_for_status()
            html = response.text or ""
            return {"url": str(response.url), "html": html, "text": _strip_html(html)[:12000]}

    @staticmethod
    def _social_links(text: str) -> List[Dict[str, str]]:
        links = []
        for url in _unique(SOCIAL_PATTERN.findall(text or "")):
            host = (urlparse(url).hostname or "").replace("www.", "")
            links.append({"label": host.split(".", 1)[0], "url": url.rstrip("/")})
        return links[:10]

    @staticmethod
    def _extract_services(text: str, *, industry_hint: str) -> List[str]:
        services: List[str] = []
        if industry_hint:
            services.append(industry_hint)
        lowered = (text or "").lower()
        service_terms = [
            "software",
            "consulting",
            "marketing",
            "sales",
            "analytics",
            "automation",
            "crm",
            "payment",
            "payments",
            "logistics",
            "manufacturing",
            "design",
            "development",
            "support",
            "training",
            "upfitting",
            "fleet",
            "commercial vehicle",
            "van shelving",
        ]
        for term in service_terms:
            if term in lowered:
                services.append(term.title())
        return _unique(services)[:8]

    @staticmethod
    def _summary(*, company_name: str, text: str, services: List[str], website: str) -> str:
        cleaned = _clean(text)
        if cleaned:
            sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
            if 40 <= len(sentence) <= 260:
                return sentence
        service_text = ", ".join(services[:3]) if services else "business services"
        website_text = f" Its likely website is {website}." if website else ""
        return f"{company_name} appears to provide {service_text}.{website_text}".strip()

    @staticmethod
    def _normalize_lead(lead: Dict[str, Any], *, company_name: str) -> Dict[str, Any]:
        email = _clean(lead.get("contact_email") or lead.get("email"))
        person_name = _clean(lead.get("contact_person_name") or lead.get("founder_name") or lead.get("person_name"))
        if not person_name and email:
            person_name = _person_name_from_email(email)
        return {
            "company_name": _clean(lead.get("company_name")) or company_name,
            "person_name": person_name,
            "contact_person_name": person_name,
            "title": _clean(lead.get("contact_person_title") or lead.get("title") or lead.get("role")),
            "contact_person_title": _clean(lead.get("contact_person_title") or lead.get("title") or lead.get("role")),
            "email": email,
            "contact_email": email,
            "phone": _clean(lead.get("contact_phone") or lead.get("phone")),
            "contact_phone": _clean(lead.get("contact_phone") or lead.get("phone")),
            "verification_status": _clean(lead.get("verification_status") or lead.get("email_verification_status")),
            "quality_score": lead.get("quality_score") or lead.get("email_confidence") or "",
            "source_url": _clean((lead.get("source_urls") or [""])[0] if isinstance(lead.get("source_urls"), list) else lead.get("source_url")),
            "linkedin_url": _clean(lead.get("linkedin_url")),
            "source": _clean(lead.get("source")),
        }

    @staticmethod
    def _lead_matches_company_domain(lead: Dict[str, Any], *, domain: str) -> bool:
        if not domain:
            return True
        email = _clean(lead.get("contact_email") or lead.get("email")).lower()
        lead_domain = _clean(lead.get("domain")).lower()
        website_domain = _domain_from_url(lead.get("company_website", "")).lower()
        return (
            lead_domain == domain
            or website_domain == domain
            or (email.endswith(f"@{domain}") if email else False)
        )

    @staticmethod
    def _person_lead_rank(lead: Dict[str, Any]) -> tuple[int, int, int, int]:
        email = _clean(lead.get("contact_email") or lead.get("email"))
        return (
            1 if lead.get("contact_person_name") else 0,
            0 if _is_role_email(email) else 1,
            1 if lead.get("linkedin_url") else 0,
            int(lead.get("quality_score") or 0),
        )

    @staticmethod
    def _assistant_message(*, company_profile: Dict[str, Any], leads: List[Dict[str, Any]], warnings: List[str]) -> str:
        company = company_profile.get("company_name") or "the company"
        lead_text = f"{len(leads)} lead(s)" if leads else "no Hunter leads"
        warning_text = f" Warnings: {len(warnings)}." if warnings else ""
        return f"I found company intelligence for {company} and prepared {lead_text} for this run.{warning_text}"


def _trim_company_candidate(value: str) -> str:
    text = _clean(value)
    text = re.split(r"\b(?:with|and|get|give|show|include|including|in|near|around|from|please)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"^(?:the\s+)?company\s+", "", text, flags=re.IGNORECASE)
    return text.strip(" .,:;!?\"'")


def _candidate_company_urls(company_name: str) -> List[str]:
    slug = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if not slug:
        return []
    return [
        f"https://www.{slug}.com",
        f"https://{slug}.com",
    ]


def _page_matches_company(*, text: str, url: str, company_name: str) -> bool:
    host = _domain_from_url(url)
    if not host:
        return False
    host_label = host.split(".", 1)[0]
    compact_company = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if compact_company and compact_company in re.sub(r"[^a-z0-9]+", "", host_label.lower()):
        return True
    tokens = _company_tokens(company_name)
    haystack = f"{host} {text}".lower()
    compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
    return bool(tokens and all(token in haystack or token in compact_haystack for token in tokens[:3]))


def _looks_like_official_website(url: str, *, company_name: str) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    blocked = (
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "youtube.com",
        "crunchbase.com",
        "wikipedia.org",
        "glassdoor.com",
        "indeed.com",
    )
    if any(host == item or host.endswith(f".{item}") for item in blocked):
        return False
    if not _host_matches_company(host, company_name):
        return False
    path = (urlparse(url).path or "").lower()
    third_party_markers = ("integration", "integrations", "partners", "marketplace", "apps", "blog")
    return not any(marker in path for marker in third_party_markers)


def _host_matches_company(host: str, company_name: str) -> bool:
    compact_host = re.sub(r"[^a-z0-9]+", "", host.split(".", 1)[0].lower())
    compact_company = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if compact_company and compact_company in compact_host:
        return True
    tokens = _company_tokens(company_name)
    return bool(tokens and all(token in compact_host for token in tokens[:2]))


def _company_tokens(company_name: str) -> List[str]:
    generic = {"the", "and", "company", "inc", "llc", "ltd", "corp", "corporation", "co", "group"}
    return [
        token
        for token in re.findall(r"[a-z0-9]+", company_name.lower())
        if len(token) >= 3 and token not in generic
    ]


def _strip_html(html: str) -> str:
    text = SCRIPT_STYLE_PATTERN.sub(" ", html or "")
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = re.sub(r"&(?:nbsp|amp|quot|apos);", " ", text)
    return _clean(text)


def _domain_from_url(url: Any) -> str:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _homepage_url(url: Any) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return _clean(url)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _person_name_from_email(email: str) -> str:
    cleaned = _clean(email).lower()
    if "@" not in cleaned:
        return ""
    local = re.sub(r"\+.*$", "", cleaned.split("@", 1)[0])
    if _is_role_email(cleaned):
        return ""
    parts = [part for part in re.split(r"[._-]+", local) if len(part) >= 2 and not part.isdigit()]
    if len(parts) < 2:
        return ""
    return " ".join(part.capitalize() for part in parts[:3])


def _is_role_email(email: str) -> bool:
    local = _clean(email).lower().split("@", 1)[0]
    role_locals = {
        "admin",
        "billing",
        "careers",
        "compliance",
        "contact",
        "dpo",
        "hello",
        "help",
        "hr",
        "info",
        "jobs",
        "legal",
        "marketing",
        "office",
        "partners",
        "press",
        "privacy",
        "sales",
        "security",
        "support",
        "team",
    }
    return local in role_locals or local.startswith(("info.", "support.", "sales.", "contact."))


def _unique(values: List[Any]) -> List[str]:
    seen = set()
    results = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(cleaned)
    return results


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

"""Bounded, incremental company discovery with independent provider fallbacks."""
from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import logging
import os
import re
import socket
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlparse

import httpx

from core.services.lead_search_policy import SearchIntent, domain_key, industry_evidence, location_evidence, is_listing_source, is_editorial_source, is_information_portal
from core.services.lead_quality_service import score_lead
from core.services.public_site_data import public_page, contact_links, contact_context, office_key, business_website_links, business_names_from_listing
from core.tools.external.html_search_fallback import HTMLSearchFallbackClient
from core.utils.phone_quality import build_phone_summary, extract_phone_candidates, phone_region_for_location, prefer_phone_region


def visible_text(markup: str) -> str:
    markup = re.sub(r"(?is)<!--.*?-->|<(script|style|noscript|svg)\b.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)</?(?:p|div|h[1-6]|li|section|footer|address|br|tr)\b[^>]*>", "\n", markup)
    markup = re.sub(r"(?s)<[^>]+>", " ", markup)
    return "\n".join(" ".join(line.split()) for line in html.unescape(markup).splitlines() if line.strip())


MARKDOWN_LINK = re.compile(r'!?\[([^\]]*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)')


def indexed_text(markdown: str) -> str:
    text = MARKDOWN_LINK.sub(r'\1', markdown)
    text = re.sub(r'https?://\S+|data:image/\S+', ' ', text)
    return visible_text(text)


def indexed_activity(markdown: str) -> str:
    # Indexed Markdown has no nav element. Bare link/menu lines still must not
    # establish that the company performs a service mentioned in its menu.
    body = '\n'.join(line for line in markdown.splitlines() if not re.fullmatch(r'\s*[-*+]?\s*(?:!?\[[^\]]*\]\([^\n]+\)\s*)+', line))
    return indexed_text(body)


def generic_company_identity(name):
    if re.fullmatch(r'(?:19|20)\d{2}', name.strip()):
        return True
    if re.fullmatch(r'(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+/?', name, re.I):
        return True
    if re.search(r'#site_title|#site_name|\{\{|\}\}|%site|your company|company name|just another', name, re.I):
        return True
    words = re.findall(r'[a-z0-9]+', name.casefold())
    generic = {'reliable', 'professional', 'chartered', 'certified', 'accountant', 'accountants',
               'accounting', 'services', 'service', 'digital', 'marketing', 'agency', 'company',
               'leading', 'best', 'top', 'home', 'welcome', 'contact', 'us', 'about'}
    return not words or all(word in generic for word in words)


def contact_material(page):
    """Read public text and explicit contact links, excluding executable data.

    Scanning raw scripts made analytics IDs look like phones and unrelated
    employee records look like the company's selected email address.
    """
    markup = re.sub(r'(?is)<svg\b[^>]*>.*?</svg>',
        lambda match: ' Fax: ' if re.search(r'(?:id|aria-label|title)=["\']fax["\']', match[0], re.I) else ' ', page['html'])
    markup = re.sub(r'(?is)<!--.*?-->|<(script|style|noscript)\b.*?</\1>', ' ', markup)
    def keep_contact_link(match):
        tag = match[0]
        link = re.search(r'href=["\']tel:([^"\']+)', tag, re.I) if re.match(r'<a\b', tag, re.I) else None
        return '\n tel: ' + unquote(link[1]).strip() + '\n' if link else ' '
    # Preserve explicit telephone values at their original positions, without
    # retaining attributes that can suppress a neighboring real number.
    phone_text = html.unescape(re.sub(r'(?s)<[^>]+>', keep_contact_link, markup))
    phone_text = MARKDOWN_LINK.sub(lambda match: match[1] + ('\n tel: ' + unquote(match[2][4:]) if match[2].lower().startswith('tel:') else ''), phone_text)
    links = re.findall(r'href=["\']((?:mailto|tel):[^"\']+)', markup, re.I)
    links += [match[2] for match in MARKDOWN_LINK.finditer(markup) if match[2].lower().startswith(('mailto:', 'tel:'))]
    decoded_links = [value.split(':', 1)[0] + ':' + unquote(value.split(':', 1)[1]).split('?', 1)[0].strip() for value in links]
    decoded = page['text'] + '\n' + '\n'.join(decoded_links)
    for value in re.findall(r'data-cfemail=["\']([a-f0-9]+)', markup, re.I):
        try:
            blob = bytes.fromhex(value)
            decoded += ' ' + ''.join(chr(char ^ blob[0]) for char in blob[1:])
        except (ValueError, IndexError):
            pass
    return decoded, phone_text


def company_identity(pages, domain, *, with_source=False, excluded_names=()):
    """Prefer the site's own organization metadata over an SEO page headline."""
    def result(name='', page=None, basis=''):
        return {'name': name, 'source_url': (page or {}).get('url', ''), 'basis': basis} if with_source else name
    excluded = {name.strip().casefold() for name in excluded_names}
    def generic(name):
        return name.strip().casefold() in excluded or generic_company_identity(name)
    # A location page can call itself "Toronto" in og:site_name. Prefer
    # company-wide homepage branding, then use other published brand evidence.
    pages = sorted(pages, key=lambda page: urlparse(page.get('url', '')).path.rstrip('/') != '')
    for page in pages:
        for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page['html'], re.I | re.S):
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            nodes = data if isinstance(data, list) else [data]
            for node in list(nodes):
                if isinstance(node, dict):
                    nodes.extend(node.get('@graph', []) if isinstance(node.get('@graph'), list) else [])
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                types = node.get('@type', [])
                types = types if isinstance(types, list) else [types]
                if not set(types) & {'Organization', 'LocalBusiness', 'ProfessionalService', 'AccountingService', 'Corporation', 'Dentist', 'MedicalBusiness', 'MedicalClinic', 'LegalService', 'Attorney', 'HomeAndConstructionBusiness', 'Electrician'}:
                    continue
                if node.get('url') and domain_key(str(node['url'])) != domain:
                    continue
                name = str(node.get('legalName') or node.get('name') or '').strip()
                if 1 < len(name) < 90 and not generic(name) and not re.search(r'best|leading|top \d|agency in|services in', name, re.I):
                    return result(name, page, 'organization_metadata')
        for tag in re.findall(r'<meta\b[^>]+>', page['html'], re.I):
            if re.search(r'(?:property|name)=["\']og:site_name["\']', tag, re.I):
                value = re.search(r'content=["\']([^"\']+)', tag, re.I)
                if value and 1 < len(value[1]) < 70 and not generic(value[1]):
                    return result(html.unescape(value[1]), page, 'site_name_metadata')
    for page in pages:
        for tag in re.findall(r'<img\b[^>]+>', page['html'], re.I):
            alt = re.search(r'alt=["\']([^"\']+)', tag, re.I)
            if alt and re.search(r'logo|brand', tag, re.I):
                name = re.sub(r'\blogo\b', '', html.unescape(alt[1]), flags=re.I).strip(' -|')
                compact = re.sub(r'[^a-z0-9]', '', name.casefold())
                if 3 < len(compact) < 65 and compact in re.sub(r'[^a-z0-9]', '', domain.casefold()) and not generic(name):
                    return result(name, page, 'logo_brand')
        text = visible_text(page['html'])
        for match in re.finditer(r'(?:©|copyright)\s*(?:©\s*)?(?:\d{4}(?:\s*[-–]\s*\d{4})?[,\s]*)?([^\n|©]{2,90})', text, re.I):
            name = re.split(r'\ball rights?\b|\bdesigned\b|\bpowered\b', match[1], flags=re.I)[0].strip(' .,-')
            name = re.sub(r'[®™©]', '', name).strip(' .,-–—')
            name = re.sub(r'\s+(?:19|20)\d{2}$', '', name).strip()
            if 2 < len(name) < 70 and not generic_company_identity(name) and not re.search(r'https?://|\.(?:com|co|uk|in|net)\b', name, re.I):
                return result(name, page, 'copyright_brand')
        for match in re.finditer(r'\b(?:Welcome to|About|At)\s+([A-Z][A-Za-z0-9&\'-]*(?:[ \t]+[A-Z][A-Za-z0-9&\'-]*){0,5})', text):
            name = match[1].strip()
            compact = re.sub(r'[^a-z0-9]', '', name.casefold())
            if len(compact) > 3 and compact in re.sub(r'[^a-z0-9]', '', domain.casefold()) and not generic_company_identity(name):
                return result(name, page, 'published_brand_statement')
    return result()


class LeadSearchEngine:
    def __init__(self, extractor, *, search_budget: int | None = None, max_seconds: float | None = None):
        self.extractor = extractor
        self.logger = logging.getLogger("agent.runtime")
        self.search_budget = search_budget or int(os.getenv("LEAD_SEARCH_QUERY_BUDGET", "18"))
        self.max_seconds = max_seconds or float(os.getenv("LEAD_SEARCH_MAX_SECONDS", "300"))
        self.html_fallback = HTMLSearchFallbackClient()
        self.accepted = {}
        self.checked = set()
        self.queries = []
        self.events = []
        self.rejections = Counter()
        self.warnings = []
        self.providers = set()
        self.page_cache = {}
        self.address_cache = {}
        self.dns_cache = {}
        self.http_slots = asyncio.Semaphore(10)
        self.company_slots = asyncio.Semaphore(6)
        self.search_slots = asyncio.Semaphore(3)
        self.tavily_disabled = False
        self.extract_calls = 0
        self.hunter_calls = 0
        self.hunter_email_sources = {}
        self.discovered = set()
        self.cancelled = False
        self.scrape_stats = Counter()
        self.resolution_queries = 0
        self.resolved_sources = set()
        self.rendered_domains = set()
        self.render_slots = asyncio.Semaphore(1)
        self.duplicate_keys = set()
        self.resolved_names = set()
        self.pending_business_names = []
        self.idle_seconds = max(0., float(os.getenv('LEAD_SEARCH_IDLE_SECONDS', '90')))
        self.last_accept_at = 0.
        self.run_timeout = None

    def snapshot(self, *, stage="searching", reason=""):
        leads = sorted(self.accepted.values(), key=lambda lead: (
            bool(lead.get("email_smtp_verified")), lead.get("quality_score", 0),
            bool(lead.get("contact_email") and lead.get("contact_phone")),
        ), reverse=True)[:self.intent.target_count]
        return {"leads": leads, "steps": list(self.events), "metadata": {
            "pipeline": "client_lead_search_v2", "stage": stage, "stop_reason": reason,
            "quality_policy_version": 3,
            "requested_count": self.intent.target_count, "returned_count": len(leads),
            "shortfall": max(0, self.intent.target_count - len(leads)),
            "discovered_targets": len(self.discovered), "checked_targets": len(self.checked),
            "queries_used": list(self.queries), "search_budget": self.search_budget,
            "providers_used": sorted(self.providers), "fallbacks_used": sorted({e['fallback'] for e in self.events if e.get('fallback')}),
            "rejection_reasons": dict(self.rejections), "warnings": list(dict.fromkeys(self.warnings)),
            "elapsed_seconds": round(time.monotonic() - self.started, 1),
            "provider_usage": {
                "tavily": self.extractor.tavily.usage_report() if callable(getattr(getattr(self.extractor, 'tavily', None), 'usage_report', None)) else None,
                "hunter_domain_search_attempts": self.hunter_calls,
                "gemini_calls": getattr(self.extractor, '_gemini_calls', 0),
            },
            "scraping": dict(self.scrape_stats),
            "completed": stage in {"completed", "partial", "cancelled", "failed"},
        }}

    async def publish(self, stage, message, **extra):
        self.events.append({"stage": stage, "message": message, **extra})
        if self.on_progress:
            await self.on_progress(self.snapshot(stage=stage))

    async def run(self, intent: SearchIntent, *, on_progress=None, is_cancelled=None):
        self.intent = intent
        self.started = time.monotonic()
        self.on_progress = on_progress
        self.is_cancelled = is_cancelled or (lambda: False)
        self.extractor._target_location = intent.location
        timeout = httpx.Timeout(8, connect=4)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CompanyResearch/1.0)", "Accept": "text/html,application/xhtml+xml"}
        reason = "search_exhausted"
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
            self.client = client
            try:
                async with asyncio.timeout(self.max_seconds) as run_timeout:
                    self.run_timeout = run_timeout
                    await self.publish("searching", f"Finding {intent.target_count} {intent.industry} companies in {intent.location}.")
                    for round_number in range(6):
                        if self.is_cancelled():
                            reason = "cancelled"
                            break
                        queries = [q for q in intent.queries(round_number) if q not in self.queries]
                        results = await asyncio.gather(*(self.search(q) for q in queries))
                        raw_results = [item for group in results for item in group]
                        candidates = self.candidates(raw_results)
                        # Separate business discovery from official-site enrichment.
                        # Resolve a few relevant listing/article results instead of
                        # either losing their businesses or exporting the publisher.
                        if round_number < 3 and len(self.accepted) < intent.target_count:
                            resolved = await self.resolve_business_sites(raw_results, resolve_names=round_number > 0 or intent.target_count > 8)
                            known = {domain_key(item['url']) for item in candidates}
                            candidates += [item for item in self.candidates(resolved) if domain_key(item['url']) not in known]
                        await self.publish("enriching", f"Checking {len(candidates)} new company websites; {len(self.accepted)} usable leads found.", round=round_number + 1)
                        for offset in range(0, len(candidates), 8):
                            if self.is_cancelled():
                                reason = "cancelled"
                                break
                            batch = candidates[offset:offset + 8]
                            await self.check_batch(batch)
                            await self.publish("enriching", f"{min(len(self.accepted), intent.target_count)} of {intent.target_count} usable leads found.")
                            if len(self.accepted) >= intent.target_count:
                                reason = "target_reached"
                                break
                        if reason in {"target_reached", "cancelled"}:
                            break
                        if len(self.queries) >= self.search_budget:
                            reason = "search_budget_reached"
                            break
                        await self.publish("expanding", "Trying additional search terms and contact fallbacks within the requested location.", fallback="query_expansion")
            except TimeoutError:
                reason = "no_recent_verified_businesses" if self.accepted and self.last_accept_at and self.idle_seconds and time.monotonic()-self.last_accept_at >= self.idle_seconds-.05 else "time_budget_reached"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning("lead_search_stage_failed error_type=%s", type(exc).__name__)
                self.warnings.append("A search stage failed. Results already checked have been preserved.")
                reason = "provider_error"
        stage = "cancelled" if reason == "cancelled" else "completed" if reason == "target_reached" else "partial"
        if stage == "partial" and not self.accepted and not self.providers and self.queries:
            # A provider outage is different from a successful empty search.
            stage, reason = "failed", "provider_error"
        if not self.accepted and reason == "provider_error":
            stage = "failed"
        result = self.snapshot(stage=stage, reason=reason)
        if self.on_progress:
            await self.on_progress(result)
        return result

    async def check_batch(self, batch):
        tasks = [asyncio.create_task(self.check_candidate(item)) for item in batch]
        try:
            for finished in asyncio.as_completed(tasks):
                await finished
                if len(self.accepted) >= self.intent.target_count:
                    break
        finally:
            # A reached target, deadline, or cancellation must not leave paid
            # enrichment tasks running after their search has finished.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def check_candidate(self, item):
        """Checkpoint each company before waiting for slower peers in the batch."""
        try:
            outcome = await self.enrich(item)
        except Exception as exc:
            self.checked.add(domain_key(item["url"]))
            self.rejections["website_unavailable"] += 1
            self.logger.warning("lead_search_company_failed domain=%s error_type=%s",
                                domain_key(item["url"]), type(exc).__name__)
            return
        self.checked.add(domain_key(item["url"]))
        if outcome and outcome.get("usable"):
            name_key = re.sub(r'[^a-z0-9]', '', outcome.get('company_name', '').casefold())
            phone = outcome.get('contact_phone', '')
            postcode = outcome.get('zip_code', '')
            identity_keys = {('name', name_key)} if name_key else set()
            if phone and postcode:
                identity_keys.add(('office', phone, postcode))
            if self.duplicate_keys & identity_keys:
                self.rejections['duplicate_business'] += 1
                return
            self.duplicate_keys.update(identity_keys)
            self.accepted[domain_key(outcome["company_website"])] = outcome
            self.last_accept_at = time.monotonic()
            if (len(self.accepted) < self.intent.target_count and self.run_timeout is not None
                    and self.idle_seconds and not self.run_timeout.expired()):
                # Stop an unproductive tail while preserving useful results.
                # New verified companies extend this window, never the total cap.
                # A completed target needs no idle timer: rescheduling to an
                # already elapsed total deadline can cancel its final checkpoint.
                self.run_timeout.reschedule(min(self.started+self.max_seconds, self.last_accept_at+self.idle_seconds))
            await self.publish("enriching", f"{min(len(self.accepted), self.intent.target_count)} of {self.intent.target_count} usable leads found.")

    @staticmethod
    def retryable(exc):
        if isinstance(exc, (httpx.TransportError, TimeoutError)):
            return True
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else getattr(exc, "details", {}).get("status_code")
        return status in {408, 429, 500, 502, 503, 504} or getattr(exc, "details", {}).get("retryable") is True

    async def provider_call(self, call, payload, timeout):
        for attempt in range(2):
            try:
                return await asyncio.wait_for(call(payload), timeout)
            except Exception as exc:
                if attempt or not self.retryable(exc):
                    raise
                self.logger.info("lead_search_provider_retry error_type=%s", type(exc).__name__)
                await asyncio.sleep(.25)

    async def search(self, query):
        if self.is_cancelled() or query in self.queries or len(self.queries) >= self.search_budget:
            return []
        self.queries.append(query)
        payload = {"query": query, "max_results": 12, "search_depth": "basic", "include_raw_content": False}
        if self.discovered:
            # Repeating close query variants otherwise keeps paying for the
            # same rejected directories and previously checked businesses.
            payload['exclude_domains'] = sorted(self.discovered)[:150]
        async with self.search_slots:
            if not self.tavily_disabled:
                try:
                    data = await self.provider_call(self.extractor.tavily.search, payload, 22)
                    self.providers.add("tavily")
                    results = data.get("results") or []
                    if results:
                        return [dict(item, discovery_query=query) for item in results if isinstance(item, dict)]
                except Exception as exc:
                    if getattr(exc, "code", "") in {"invalid_api_key", "tavily_quota_exceeded", "missing_api_key"}:
                        self.tavily_disabled = True
                    self.warnings.append("Primary search was unavailable for some queries; an alternate provider was tried.")
            try:
                data = await self.provider_call(self.html_fallback.search, payload, 22)
                self.providers.add("duckduckgo_html")
                self.events.append({"stage": "searching", "fallback": "alternate_search", "message": "Used alternate web search."})
                return [dict(item, discovery_query=query) for item in data.get("results", [])]
            except Exception:
                self.warnings.append("Some queries could not be completed by either search provider.")
                return []

    def candidates(self, results):
        by_domain = {}
        for item in results:
            url = str(item.get("url") or "")
            key = domain_key(url)
            if not key or not url.startswith(("https://", "http://")):
                continue
            self.discovered.add(key)
            if key in self.checked or key in self.accepted:
                continue
            if self.extractor._is_directory_or_noise_url(url) or is_listing_source(url, str(item.get('title', ''))) or is_editorial_source(url, str(item.get('title', '')) + ' ' + str(item.get('content', ''))) or is_information_portal(url, str(item.get('title', '')) + ' ' + str(item.get('content', ''))):
                self.rejections["directory_or_article"] += 1
                continue
            item = dict(item)
            text = str(item.get("title", "")) + " " + str(item.get("content", ""))
            item["priority"] = (3 if self.intent.location.casefold().split(",")[0] in text.casefold() else 0) + (2 if industry_evidence(text, self.intent.industry)["matched"] else 0)
            if key not in by_domain or item["priority"] > by_domain[key]["priority"]:
                by_domain[key] = item
        return sorted(by_domain.values(), key=lambda item: item["priority"], reverse=True)[:max(20, self.intent.target_count * 4)]

    async def resolve_business_sites(self, results, *, resolve_names=False):
        sources = []
        for item in results:
            url = str(item.get('url') or '')
            content = str(item.get('title', '')) + ' ' + str(item.get('content', ''))
            if url in self.resolved_sources or not url.startswith(('https://', 'http://')):
                continue
            if not industry_evidence(content, self.intent.industry)['matched']:
                continue
            if is_listing_source(url, content) or is_editorial_source(url, content):
                sources.append(item)
        sources = sources[:min(2, max(0, 6 - len(self.resolved_sources)))]
        self.resolved_sources.update(item['url'] for item in sources)
        pages = await asyncio.gather(*(self.fetch(item['url']) for item in sources))
        resolved, names = [], []
        for page in pages:
            if not page:
                continue
            for url in business_website_links(page, self.intent.location):
                if not self.extractor._is_directory_or_noise_url(url):
                    resolved.append({'url': url, 'title': '', 'content': '', 'discovery_source_url': page['url']})
            self.pending_business_names.extend(business_names_from_listing(page, self.intent.location))
        names = [name for name in dict.fromkeys(self.pending_business_names) if name.casefold() not in self.resolved_names] if resolve_names else []
        names = names[:min(3, 6-len(self.resolved_names))]
        if names:
            self.resolved_names.update(name.casefold() for name in names)
            queries = [f'"{name}" {self.intent.location} official website contact' for name in names]
            groups = await asyncio.gather(*(self.search(query) for query in queries))
            resolved.extend(item for group in groups for item in group)
            self.scrape_stats['business_names_resolved'] += len(names)
        if resolved:
            self.scrape_stats['official_sites_resolved'] += len(resolved)
            self.events.append({'stage': 'resolving', 'message': f'Resolved {len(resolved)} business websites from discovery sources; checking the businesses themselves.'})
        return resolved

    async def public_url(self, url):
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            allowed = parsed.scheme in {"http", "https"} and not parsed.username and not parsed.password and parsed.port in {None, 80, 443}
        except ValueError:
            return False
        if not host or not allowed:
            return False
        if host in self.address_cache:
            return self.address_cache[host]
        try:
            addresses = await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, host, None), 3)
            safe = bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
        except Exception:
            safe = False
        self.address_cache[host] = safe
        return safe

    async def fetch(self, url):
        if url in self.page_cache:
            self.scrape_stats['cache_hits'] += 1
            return self.page_cache[url]
        original = url
        for _ in range(4):
            if not await self.public_url(url):
                return None
            for attempt in range(2):
                try:
                    async with self.http_slots:
                        self.scrape_stats['http_requests'] += 1
                        async with self.client.stream("GET", url) as response:
                            if response.is_redirect:
                                url = urljoin(url, response.headers.get("location", ""))
                                break  # Validate the redirect before making another request.
                            response.raise_for_status()
                            if "html" not in response.headers.get("content-type", "text/html"):
                                return None
                            chunks = bytearray()
                            async for chunk in response.aiter_bytes():
                                chunks.extend(chunk)
                                if len(chunks) > 1_500_000:
                                    break
                            markup = chunks.decode(response.encoding or "utf-8", errors="replace")
                    if self.extractor._is_unusable_page(markup):
                        return None
                    result = {**public_page(markup, url), "retrieval_method": "direct"}
                    self.scrape_stats['pages_fetched'] += 1
                    self.page_cache[original] = result
                    return result
                except (httpx.HTTPError, ValueError) as exc:
                    if attempt or not self.retryable(exc):
                        self.scrape_stats['fetch_failures'] += 1
                        self.page_cache[original] = None
                        self.logger.info("lead_search_fetch_failed domain=%s error_type=%s", domain_key(url), type(exc).__name__)
                        return None
                    # Retry only safe reads, once, inside the overall run deadline.
                    delay = .25
                    if isinstance(exc, httpx.HTTPStatusError):
                        try:
                            delay = max(.25, min(2., float(exc.response.headers.get("Retry-After", ".25"))))
                        except ValueError:
                            pass
                    await asyncio.sleep(delay)
        return None

    async def site_pages(self, item):
        location = getattr(getattr(self, 'intent', None), 'location', '')
        target_role = getattr(getattr(self, 'intent', None), 'target_role', '')
        home = self.extractor._homepage_url(item["url"])
        first = await self.fetch(item["url"])
        if not first:
            first = await self.fetch(home)
        if not first:
            return []
        if len(first['text']) < 180 and re.search(r'<script\b', first['html'], re.I):
            first = await self.render_page(first['url']) or first
        home = self.extractor._homepage_url(first["url"])
        initial = [first]
        if home.rstrip('/') != first['url'].rstrip('/'):
            homepage = await self.fetch(home)
            if homepage and domain_key(homepage['url']) == domain_key(home):
                initial.append(homepage)
        # Avoid crawling entire unrelated businesses before rejecting them.
        # A short/JS-only page still gets extraction recovery in enrich().
        intent = getattr(self, 'intent', None)
        if intent and all(len(page['text']) > 350 for page in initial) and not any(industry_evidence(page['text'], intent.industry)['matched'] for page in initial):
            return initial
        urls = [url for source in initial for url in contact_links(source, location)]
        urls += [urljoin(home, path) for path in ('contact-us/', 'contact/', 'about/')]
        seen = {page['url'].rstrip('/') for page in initial}
        unique = []
        for url in urls:
            if url.rstrip('/') not in seen:
                seen.add(url.rstrip('/'))
                unique.append(url)
        # Follow real contact/location links first. Common paths are fallback
        # probes, rather than an obligation to request three extra 404 pages.
        limit = 8 if target_role else 6
        real_links = set(url for source in initial for url in contact_links(source, location))
        urls = unique[:min(3, limit - len(initial))] if real_links else unique[:2]
        pages = await asyncio.gather(*(self.fetch(url) for url in urls))
        collected = initial + [page for page in pages if page and domain_key(page['url']) == domain_key(home)]
        # A locations index often links to the actual office/contact page.
        deeper = [url for source in collected for url in contact_links(source, location)
                  if url.rstrip('/') not in seen and url.rstrip('/') != home.rstrip('/')]
        needs_more = intent and (not any(location_evidence(page['text'], location)['matched'] for page in collected) or target_role)
        if needs_more and len(collected) < limit and deeper:
            extra = await asyncio.gather(*(self.fetch(url) for url in list(dict.fromkeys(deeper))[:limit-len(collected)]))
            collected += [page for page in extra if page and domain_key(page['url']) == domain_key(home)]
        return list({page['url']: page for page in collected}.values())

    async def render_page(self, url):
        """Bounded public JS-shell fallback; never solve challenges or log in."""
        host = domain_key(url)
        if os.getenv('LEAD_RENDER_JS', 'true').casefold() not in {'1', 'true', 'yes'} or host in self.rendered_domains or len(self.rendered_domains) >= 3:
            return None
        self.rendered_domains.add(host)
        async with self.render_slots:
            try:
                from playwright.async_api import async_playwright
                async with asyncio.timeout(14):
                    async with async_playwright() as playwright:
                        options = {'headless': True}
                        channel = os.getenv('LEAD_BROWSER_CHANNEL', 'msedge' if os.name == 'nt' else '')
                        if channel:
                            options['channel'] = channel
                        browser = await playwright.chromium.launch(**options)
                        try:
                            context = await browser.new_context(service_workers='block')
                            async def route_request(route):
                                request = route.request
                                if request.method != 'GET' or request.resource_type in {'image', 'media', 'font'} or not await self.public_url(request.url):
                                    await route.abort()
                                else:
                                    await route.continue_()
                            await context.route('**/*', route_request)
                            page = await context.new_page()
                            await page.goto(url, wait_until='domcontentloaded', timeout=8000)
                            try:
                                await page.wait_for_function("document.body && document.body.innerText.length > 180", timeout=2500)
                            except Exception:
                                pass
                            markup = await page.content()
                            final_url = page.url
                            if not await self.public_url(final_url) or domain_key(final_url) != host or self.extractor._is_unusable_page(markup):
                                return None
                            result = {**public_page(markup[:1_500_000], final_url), 'retrieval_method': 'rendered'}
                            self.page_cache[url] = result
                            self.scrape_stats['rendered_pages'] += 1
                            return result
                        finally:
                            await browser.close()
            except Exception as exc:
                self.scrape_stats['render_failures'] += 1
                self.logger.info('lead_search_render_unavailable domain=%s error_type=%s', host, type(exc).__name__)
                return None

    async def extract_fallback(self, urls):
        if self.extract_calls >= 8 or self.tavily_disabled:
            return []
        self.extract_calls += 1
        try:
            data = await self.provider_call(self.extractor.tavily.extract, {"urls": urls[:2], "extract_depth": "basic"}, 18)
            allowed = {domain_key(url) for url in urls}
            pages = [{**public_page(row['raw_content'], row['url']), "text": indexed_text(row['raw_content']), "activity_text": indexed_activity(row['raw_content']), "retrieval_method": "indexed"} for row in data.get("results", []) if row.get("url") and row.get("raw_content") and domain_key(row['url']) in allowed]
            if pages:
                self.events.append({"stage": "enriching", "fallback": "indexed_site_extraction", "message": "Recovered official-site content through alternate extraction."})
            return pages
        except Exception:
            return []

    async def check_email(self, email):
        if not email:
            return {"status": "no_email_found", "mx_found": False, "smtp_verified": False, "confidence": 0}
        domain = email.split("@")[-1]
        if domain not in self.dns_cache:
            def resolve():
                import dns.resolver
                try:
                    records = dns.resolver.resolve(domain, "MX", lifetime=4)
                    return any(str(record.exchange).rstrip(".") for record in records)
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    return False
                except Exception:
                    return None
            self.dns_cache[domain] = await asyncio.to_thread(resolve)
        mx = self.dns_cache[domain]
        return {"status": "invalid" if mx is False else "unconfirmed", "normalized_email": email,
                "mx_found": mx is True, "smtp_verified": False, "confidence": 40 if mx else 0,
                "message": "Mail server found; mailbox delivery has not been confirmed." if mx else "No mail server found." if mx is False else "DNS check was inconclusive."}

    async def hunter_fallback(self, domain):
        key = os.getenv("HUNTER_API_KEY")
        if not key or self.hunter_calls >= 3:
            return ""
        self.hunter_calls += 1
        try:
            # Keys stay in the request and never enter job snapshots.
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://api.hunter.io/v2/domain-search", params={"domain": domain, "limit": 3, "api_key": key})
            if response.status_code != 200:
                return ""
            for item in response.json().get("data", {}).get("emails", []):
                email = str(item.get("value") or "")
                sources = [{'type': 'hunter_public_source', 'url': source['uri'], 'last_seen_on': source.get('last_seen_on', '')}
                           for source in item.get('sources', []) if isinstance(source, dict) and source.get('still_on_page') is not False
                           and str(source.get('uri', '')).startswith(('http://', 'https://'))]
                # Domain-wide person results do not establish relevance to the
                # requested local office. Keep this fallback company-level.
                generic_inbox = email.split('@')[0].casefold() in {'info', 'hello', 'contact', 'sales', 'enquiries', 'inquiries', 'business', 'office', 'reception', 'admin', 'general'}
                if email.endswith("@" + domain) and sources and generic_inbox:
                    self.hunter_email_sources[email] = sources
                    self.events.append({"stage": "enriching", "fallback": "hunter_domain_search", "message": "Found a sourced company email through domain enrichment."})
                    return email
        except Exception:
            pass
        return ""

    async def enrich(self, item):
        async with self.company_slots:
            if self.is_cancelled():
                return None
            pages = await self.site_pages(item)
            if not pages:
                pages = await self.extract_fallback([item["url"], self.extractor._homepage_url(item["url"])])
            if not pages:
                self.rejections["website_unavailable"] += 1
                return None
            pages = [{**public_page(page['html'], page['url']), **{k:v for k,v in page.items() if k not in {'html', 'text'}}} if 'addresses' not in page else page for page in pages]
            if any(is_information_portal(page['url'], page['text']) for page in pages):
                self.rejections['government_information_portal'] += 1
                return None
            pages = [page for page in pages if not is_editorial_source(page['url'], page['text']) and not is_listing_source(page['url'], page['text'])]
            if not pages:
                self.rejections['editorial_source_only'] += 1
                return None
            if is_listing_source(pages[0]['url'], pages[0]['text']):
                self.rejections['directory_or_article'] += 1
                return None
            # Only fetched official-site content establishes fit, never a search query.
            text = "\n".join(page["text"][:45000] for page in pages)
            if any(page['text'].casefold().count('lorem ipsum') >= 2 and re.search(r'blind texts|far World of Grammar|XpeedStudio', page['text'], re.I) for page in pages):
                self.rejections['unfinished_template_site'] += 1
                return None
            activity_text = '\n'.join(page.get('activity_text', page['text'])[:45000] for page in pages)
            fit = industry_evidence(activity_text, self.intent.industry)
            location_matches = [(location_evidence(page['text'], self.intent.location), page) for page in pages]
            location_matches = [(match, page) for match, page in location_matches if match['matched']]
            geo, geo_page = min(location_matches, key=lambda pair: (pair[0]['basis'] != 'address',
                not bool(re.search(r'contact|office|location', urlparse(pair[1]['url']).path, re.I)))) if location_matches else (location_evidence('', self.intent.location), {})
            fit_page = next((page for page in pages if industry_evidence(page.get('activity_text', page['text']), self.intent.industry)['matched']), {})
            if not fit["matched"] or not geo["matched"]:
                self.rejections["industry_mismatch" if not fit["matched"] else "location_unconfirmed"] += 1
                return None
            domain = domain_key(pages[0]["url"])
            region = phone_region_for_location(self.intent.location)
            emails, phones, email_sources, email_contexts, email_offices = [], [], {}, {}, {}
            # Sites that hide contact details behind scripts can still have indexed
            # official contact pages. This fallback never trusts third-party snippets.
            if not self.extractor._valid_email_matches(text) and not re.search(r'tel:|\+\d[\d\s()-]{8,}', text + ''.join(p['html'] for p in pages)):
                recovered = await self.extract_fallback([urljoin(self.extractor._homepage_url(pages[0]['url']), 'contact'), pages[0]['url']])
                pages.extend(page for page in recovered if page['url'] not in {p['url'] for p in pages})
            for page in pages:
                decoded, phone_text = contact_material(page)
                decoded = self.extractor._deobfuscate_contact_text(decoded)
                for email in self.extractor._valid_email_matches(decoded):
                    email_domain = email.split("@")[-1]
                    published_mailto = bool(re.search(r'mailto:' + re.escape(email), decoded, re.I))
                    public_business_inbox = email_domain in {'gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com'} and (published_mailto or ('contact' in page['url'] and email in page['text']))
                    same_brand_domain = (len(domain.split('.')[0]) >= 4 and email_domain.split('.')[0] == domain.split('.')[0]
                                         and (published_mailto or ('contact' in page['url'] and email in page['text'])))
                    if email_domain != domain and not public_business_inbox and not same_brand_domain:
                        continue
                    if re.match(r"^(?:hr|career|careers|jobs|privacy|security|abuse|noreply|no-reply|webmaster|dpo|press|media|accounting|accounts|billing|invoices)@", email):
                        continue
                    emails.append(email)
                    email_sources.setdefault(email, page["url"])
                    context = contact_context(page, email)
                    match = location_evidence(context, self.intent.location)['matched']
                    if email not in email_contexts or match:
                        email_contexts[email] = match
                        email_offices[email] = office_key(context)
                candidates = extract_phone_candidates(phone_text, source_type="contact_page" if "contact" in page["url"] else "homepage", source_url=page["url"], region=region)
                for candidate in candidates:
                    context = contact_context(page, candidate.get('raw', '') or candidate.get('e164', ''))
                    candidate['requested_office_match'] = location_evidence(context, self.intent.location)['matched']
                    candidate['office_key'] = office_key(context)
                    if candidate['requested_office_match']:
                        candidate['confidence'] = min(99, candidate['confidence'] + 15)
                phones.extend(candidates)
            ranked_emails = sorted(set(emails), key=lambda value: (not email_contexts.get(value, False), 0 if value.split("@")[0] in {"sales", "business", "hello", "contact", "info", "enquiries", "service"} else 1, value))
            email = next(iter(ranked_emails), "")
            preferred_office = email_offices.get(email)
            if preferred_office:
                for candidate in phones:
                    candidate['requested_office_match'] = candidate.get('office_key') == preferred_office
            summary = prefer_phone_region(build_phone_summary(phones), region)
            if not email and not summary["contact_phone"]:
                email = await self.hunter_fallback(domain)
                if email:
                    email_sources[email] = next((source['url'] for source in self.hunter_email_sources.get(email, [])), "Hunter: published domain sources")
            contact_page = next((page["url"] for page in pages if re.search(r"contact|enquir", urlparse(page["url"]).path, re.I)), "")
            contact_form = any(re.search(r"<form\b", page["html"], re.I) and re.search(r'<textarea\b|name=["\'][^"\']*(?:message|enquiry)', page['html'], re.I) and re.search(r"contact|enquir", urlparse(page["url"]).path, re.I) for page in pages)
            verification = await self.check_email(email)
            if verification["status"] == "invalid":
                email = ""
                for candidate in ranked_emails[1:]:
                    candidate_verification = await self.check_email(candidate)
                    if candidate_verification["status"] != "invalid":
                        email, verification = candidate, candidate_verification
                        break
            if not email and not summary["contact_phone"] and not contact_form:
                self.rejections["no_usable_contact"] += 1
                return None
            title = re.search(r"<title[^>]*>(.*?)</title>", pages[0]["html"], re.I | re.S)
            identity = company_identity(pages, domain, with_source=True, excluded_names=self.intent.location.split(','))
            name = identity['name'] or self.extractor._resolve_company_name("", title=visible_text(title.group(1)) if title else item.get("title", ""), url=pages[0]["url"], email=email)
            if name.casefold() in {part.strip().casefold() for part in self.intent.location.split(',')} or generic_company_identity(name) or len(name.split()) > 6 or re.search(r'for scalable|agency in|services in|leading|best |^(?:chartered )?accountants? (?:in |london)', name, re.I):
                name = domain.split('.')[0].replace('-', ' ').title()
            provider_industry = bool(re.search(r'dentist|dental|law firm|lawyer|architect|solar.*install|accountant|accounting', self.intent.industry, re.I))
            if provider_industry and re.search(r'^(?:(?:NSW|Australian|State|Federal)\s+)?Government\b|^City of\b|^State of\b', name, re.I):
                self.rejections['government_information_portal'] += 1
                return None
            if provider_industry and re.search(r'\b(?:Publishing|Publishers?|Society|Association)\b|\bCounty$', name, re.I):
                self.rejections['information_or_membership_organization'] += 1
                return None
            addresses = [address for page in pages for address in page.get('addresses', [])]
            address = next((a for a in addresses if location_evidence(', '.join(str(a.get(k) or '') for k in ('streetAddress','addressLocality','addressRegion','postalCode','addressCountry')), self.intent.location)['matched']), {})
            people = [person for page in pages for person in page.get('people', [])]
            role = self.intent.target_role.casefold()
            person = next((p for p in people if role and role in p['title'].casefold()), people[0] if people and not role else {})
            visible_address = self.extractor._extract_city_state(text=geo.get('evidence', ''), location=self.intent.location) if not address else {}
            lead = {"company_name": name, "company_website": self.extractor._homepage_url(pages[0]["url"]),
                    "industry": self.intent.industry, "industry_match": True, "industry_evidence": fit["evidence"],
                    "location": self.intent.location, "location_match": True, "location_evidence": geo["evidence"],
                    "location_basis": geo["basis"], "city": address.get('addressLocality', visible_address.get('city', '')), "state": address.get('addressRegion', visible_address.get('state', '')), "zip_code": address.get('postalCode', visible_address.get('zip_code', '')), "address": address.get('streetAddress', visible_address.get('address', '')),
                    "contact_person_name": person.get('name', ''), "contact_person_title": person.get('title', ''), "founder_name": next((p['name'] for p in people if 'founder' in p['title'].casefold()), ''), "target_role": self.intent.target_role,
                    "contact_email": email, "contact_page": contact_page, "contact_form_found": contact_form,
                    "email_verification": verification, "verification_status": verification["status"],
                    "verification_message": verification.get("message", ""), "email_mx_found": verification["mx_found"], "email_smtp_verified": False,
                    "source": "official_website", "site_status": "indexed" if pages[0].get('retrieval_method') == 'indexed' else "reachable", "verifying": False,
                    "company_name_basis": identity['basis'] or 'website_domain_or_title',
                    "email_source_type": "hunter_public_sources" if email in self.hunter_email_sources else "official_site",
                    "location_source_url": geo_page.get('url', ''), "industry_source_url": fit_page.get('url', ''),
                    "value_proposition": fit["evidence"], "checked_at": datetime.now(timezone.utc).isoformat(),
                    "source_details": [{"type": "official_site", "url": page["url"], "retrieval_method": page.get('retrieval_method', 'direct')} for page in pages] + self.hunter_email_sources.get(email, []),
                    "field_sources": {"contact_email": email_sources.get(email, ""), "location": geo_page.get('url', ''),
                                      "contact_person_name": person.get('source_url', ''), "address": address.get('source_url', '') or geo_page.get('url', ''),
                                      "industry": fit_page.get('url', ''), "company_name": identity['source_url'] or pages[0]['url']}, **summary}
            lead['published_contacts'] = [{'email': value, 'source_url': email_sources.get(value, ''), 'requested_office_match': email_contexts.get(value, False)} for value in ranked_emails[:12]]
            lead['whatsapp_urls'] = list(dict.fromkeys(url for page in pages for url in page.get('whatsapp_urls', [])))
            lead['social_urls'] = list(dict.fromkeys(url for page in pages for url in page.get('social_urls', [])))
            lead['company_linkedin_url'] = next((url for url in lead['social_urls'] if domain_key(url) in {'linkedin.com'} and '/company/' in urlparse(url).path), '')
            lead.update(score_lead(lead))
            # A verified contact form is a legitimate company contact route.
            if contact_form and not email and not summary["contact_phone"]:
                lead.update(usable=True, rejected=False, quality_status="Needs_Review", quality_score=45,
                            acceptance_reason="Official company and location matched; a contact form is available. No direct email or phone found.")
            lead["contact_level"] = "company" if email or summary["contact_phone"] else "contact_form"
            lead["pipeline_disposition"] = "Needs_Review"
            lead["lead_summary"] = f"{name} matches {self.intent.industry} in {self.intent.location}. " + ("Published company contact details found; email delivery remains unconfirmed." if email else "Company phone found." if summary["contact_phone"] else "Contact form available.")
            return lead

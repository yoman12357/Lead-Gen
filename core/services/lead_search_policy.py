"""Search planning and evidence rules shared by the client lead platform."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SearchIntent:
    industry: str
    location: str
    target_count: int = 15
    target_role: str = ""

    @property
    def terms(self) -> list[str]:
        text = self.industry.lower()
        if re.search(r"upfit|camper|rv builder|van conversion", text):
            return ["van upfitters", "camper van conversion", "custom campervan builders", "RV builders", "van conversion company"]
        if "saas" in text:
            return ["SaaS development", "SaaS application development", "software development company"] if re.search(r"develop|agency|service", text) else ["SaaS software company", "software subscription platform", "B2B SaaS product"]
        if re.search(r"accountant|accounting|accountancy", text):
            return ["accountants", "accountancy firm", "accounting services", "tax accountants", "bookkeeping services"]
        if "digital marketing" in text:
            return ["digital marketing agency", "digital marketing company", "SEO agency", "social media marketing agency", "performance marketing agency"]
        if re.search(r'dentist|dental', text):
            return ['dentist', 'dental clinic', 'dental practice', 'dental care']
        if re.search(r'law firm|lawyer|solicitor', text):
            return ['law firm', 'lawyers', 'legal services', 'solicitors']
        if re.search(r'architect', text):
            return ['architects', 'architecture firm', 'architectural services', 'architecture studio']
        if re.search(r'solar.*install', text):
            return ['solar installers', 'solar panel installation', 'solar installation company', 'solar energy contractor']
        if re.search(r'pet.*groom|dog.*groom', text):
            return ['pet grooming', 'dog groomers', 'pet salon', 'dog grooming services']
        if re.search(r'pet shop|pet store|pet suppl|online pet', text):
            return ['pet store', 'pet shop', 'pet supplies', 'pet accessories']
        return list(dict.fromkeys([self.industry] + [x.strip() for x in re.split(r"\s*/\s*|\s+or\s+", self.industry) if len(x.strip()) > 2]))

    @property
    def places(self) -> list[str]:
        # Subregions stay within the requested region. Never silently search a
        # different country to fill a sparse local market.
        value = self.location.casefold().strip()
        subregions = {
            "hawaii": ["Honolulu Hawaii", "Maui Hawaii", "Hilo Hawaii", "Kailua Kona Hawaii"],
            "california": ["Los Angeles California", "San Diego California", "San Francisco California"],
            "texas": ["Austin Texas", "Dallas Texas", "Houston Texas"],
            "india": ["Delhi India", "Mumbai India", "Bengaluru India", "Pune India"],
            "united kingdom": ["London UK", "Manchester UK", "Birmingham UK"],
            "usa": ["New York USA", "Austin Texas USA", "Los Angeles USA"],
        }
        return [self.location] + subregions.get(value, [])

    def queries(self, round_number: int) -> list[str]:
        term = self.terms[min(round_number, len(self.terms) - 1)]
        place = self.places[0]
        if round_number == 0:
            return [f'{term} "{place}" company contact', f'{term} "{place}" official website', f'"{place}" {term} services']
        if round_number == 1:
            return [f'{variant} "{place}" contact email phone' for variant in self.terms[1:4]] or [f'{term} "{place}" business contact us']
        if round_number == 2:
            return [f'{term} {subplace} official website' for subplace in self.places[1:4]] or [f'{variant} {place} "contact us" -directory -jobs' for variant in self.terms[:3]]
        if round_number >= 3:
            # Discovery can use a city's common spelling without requiring a
            # literal comma/state phrase. Qualification still checks full intent.
            city = self.location.split(',')[0].strip()
            suffix = {3: 'contact company official website', 4: 'services get a quote email', 5: 'local business telephone address'}.get(round_number, 'contact')
            return [f'{variant} "{city}" {suffix}' for variant in self.terms[-3:]]


def domain_key(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else "https://" + url).hostname or "").casefold().removeprefix("www.").rstrip(".")
    except ValueError:
        return ""


def is_listing_source(url: str, text: str = "") -> bool:
    """A directory's contact details must never become the listed company's lead."""
    host = domain_key(url)
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    if host.startswith(('directory.', 'directories.')):
        return True
    if re.search(r'/(?:[^/]*-)?members(?:/|$)|/find-(?:a-)?(?:dentist|lawyer|architect)(?:/|$)', path):
        return True
    if re.search(r'/installers/(?:[a-z]{2}|texas|australia|canada)(?:/|$)|businesslistings\.', path, re.I):
        return True
    if re.search(r'/(?:find-an-accountant|find-a-professional|member-directory|members-directory|useful-numbers|directory|listings?|participating-solar-contractors|solar-installers)(?:/|$)', path):
        return True
    if re.search(r'(?:^|[=&])(?:useful[-_.]numbers|member[-_.]directory)(?:&|$)', parsed_url.query, re.I):
        return True
    if re.search(r'regulated professions register|regulatory or professional bodies|regulatory authority', text[:4000], re.I):
        return True
    if re.search(r'^\s*(?:institute|association) of (?:financial|chartered|certified|public) accountants\b', text, re.I):
        return True
    if re.match(r'^\s*(?:#{1,6}\s*)?(?:useful numbers|business listings|member directory)\s*(?:\n|$)', text, re.I):
        return True
    website_fields = {domain_key(match[1]) for match in re.finditer(r'\b(?:website|web site)\s*:\s*((?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s]*)', text, re.I)}
    if len(website_fields - {host, ''}) >= 2:
        return True
    if re.search(r'\bemail formats?\b', text[:1600], re.I) and re.search(r'\b(?:company overview|all employees|NAICS|SIC|employee profiles)\b', text, re.I):
        return True
    if re.search(r'\b(?:contact number list|business contact database|businesses contact list)\b', text[:1800], re.I) and re.search(r'build your own list|bulk data|buy (?:data|list)|saved.*cart', text, re.I | re.S):
        return True
    domains = {"solarusa.org", "starleads.in", "prospeo.io", "leadiq.com", "designrush.com", "digitalagencynetwork.com", "themanifest.com",
               "sortlist.com", "sortlist.co.uk", "agencyspotter.com", "signalhire.com",
               "rocketreach.co", "lusha.com", "ensun.io", "yelp.com", "yell.com",
               "bark.com", "cylex-uk.co.uk", "f6s.com", "wellfound.com", "g2.com",
               "capterra.com", "softwareadvice.com", "sulekha.com", "threebestrated.in", "accountantsbook.co.uk"}
    if any(host == domain or host.endswith("." + domain) for domain in domains):
        return True
    # Unknown directories can copy a listed company's category and address
    # while exposing their own admin email. Detect the relationship rather
    # than relying exclusively on a growing hostname blacklist.
    for match in re.finditer(r"official\s+(?:company\s+)?(?:website|site)\s*[:–-]?\s*(https?://[^\s<>)]+)", text, re.I):
        if domain_key(match[1]) and domain_key(match[1]) != host:
            return True
    heading = text.strip().split('\n', 1)[0]
    if re.search(r'\b(?:installers? guide|company (?:reviews|profile))\b', heading, re.I):
        for match in re.finditer(r'\bwebsite\s*:?\s*(https?://[^\s<>)]+)', text, re.I):
            if domain_key(match[1]) not in {host, ''}:
                return True
    if re.search(r"(?:add|list) (?:your )?business|claim (?:this|your) (?:listing|business)", text, re.I):
        return True
    if all(re.search(pattern, text, re.I) for pattern in [r'view listing', r'send message', r'see phone number']):
        return True
    if re.search(r'no dentists work at|(?:is|are) a (?:very )?(?:comprehensive |online )?directory of (?:dentists|lawyers|architects|installers)', text, re.I):
        return True
    if re.search(r'builders you can reach out to|(?:companies|builders).{0,80}(?:grouped|organized) by state|here(?:\x27s| is) a list of (?:builders|companies)', text[:3000], re.I | re.S):
        return True
    opening = text[:1200]
    heading = text.strip().split('\n', 1)[0]
    if re.search(r'\bdirectory\b', heading, re.I):
        return True
    return bool(re.search(r"company overview.{0,60}(?:competitors|contact details)|"
                          r"(?:top|best)\s+(?:\d+\s+)?(?:digital marketing agencies|accounting firms|saas companies)|"
                          r"(?:browse|compare|find)\s+(?:the\s+)?(?:best\s+)?(?:agencies|companies|accountants)\s+(?:in|near)|"
                          r"add (?:your )?business|claim (?:this|your) (?:listing|business)", opening, re.I))


def is_editorial_source(url: str, text: str = '') -> bool:
    """A publisher's article can describe competitors, not its own offices."""
    path = urlparse(url).path
    host = domain_key(url)
    if host.startswith(('news.', 'newsroom.', 'pressrelease.', 'pressreleases.')):
        return True
    opening = text[:1800]
    if re.search(r'press release distribution|newswire (?:service|distribution)|submit (?:a |your )?press release', opening, re.I):
        return True
    if re.search(r'/(?:blogs?|news|articles?|insights)(?:/|$)|/(?:top|best)[-_]?\d+|/\d+[-_](?:best|top)', path, re.I):
        return True
    heading = text.strip().split('\n', 1)[0].lstrip('# ').strip()
    return bool(re.search(r'^(?:the\s+)?(?:top|best)\s+(?:\d+\s+)?.{0,70}\b(?:companies|agencies|firms|providers)\b', heading, re.I))


def is_information_portal(url: str, text: str = '') -> bool:
    """Licensing/registration mentions do not establish an operating provider."""
    host = domain_key(url)
    if re.search(r'(?:^|\.)(?:gov|gov\.[a-z]{2}|state\.[a-z]{2}\.us)$', host):
        return True
    return bool(re.search(r'department of motor vehicles|vehicle manufacturer licens|motor vehicle licens|regulated professions register|regulatory authority', text[:3000], re.I))


def industry_evidence(text: str, industry: str) -> dict:
    lowered = text.casefold()
    desired = industry.casefold()
    if re.search(r"upfit|camper|rv builder|van conversion", desired):
        patterns = [r"van (?:conversion|conversions|upfitting|upfitter|builds|builders|build.outs)", r"camper\s*vans? (?:builder|conversion|build)", r"custom (?:camper\s*)?van (?:build|design|interior)", r"(?:build|convert|upfit).{0,35}(?:camper|sprinter|custom) vans?", r"rv (?:builder|manufacturer|conversion)", r"motorhome (?:builder|manufacturer)"]
    elif "saas" in desired:
        patterns = [r"saas", r"software.as.a.service"]
        if re.search(r"develop|agency|service", desired) and not re.search(r"development|develop.{0,30}(?:software|saas)|build.{0,30}(?:software|saas)", lowered):
            return {"matched": False, "evidence": "No SaaS development-service evidence found."}
        if not re.search(r"develop|agency|service", desired):
            if not re.search(r"free trial|start.{0,12}trial|pricing|subscription|per month|per user", lowered):
                return {"matched": False, "evidence": "No subscription-product evidence found."}
    elif re.search(r"accountant|accounting|accountancy", desired):
        if re.search(r"professional body|membership body|institute of|association of accountants", lowered[:600]):
            return {"matched": False, "evidence": "Membership body rather than an accounting provider."}
        patterns = [r"accountan(?:t|cy)", r"accounting services", r"bookkeeping", r"tax (?:advice|returns|services)"]
    elif "digital marketing" in desired:
        patterns = [r"(?:digital|social media|performance) marketing", r"seo (?:agency|services|company)"]
    elif re.search(r'dentist|dental', desired):
        patterns = [r'\bdentists?\b', r'\bdental (?:clinic|practice|care|services|treatments)\b']
    elif re.search(r'law firm|lawyer|solicitor', desired):
        patterns = [r'\blaw firms?\b', r'\blawyers?\b', r'\bsolicitors?\b', r'\blegal services\b']
    elif re.search(r'architect', desired):
        patterns = [r'\barchitects?\b', r'\barchitectur(?:e|al) (?:firm|studio|services|design)\b']
    elif re.search(r'solar.*install', desired):
        if re.search(r'as a department of|solar (?:panel )?installation permits|register for solar credit|solar incentives.*enrollment', lowered[:1800]):
            return {"matched": False, "evidence": "Government, utility or incentive information rather than installation-service evidence."}
        if not re.search(r'\bsolar\b', lowered) or not re.search(r'install(?:ation|ations|er|ers|ing)?\b', lowered):
            return {"matched": False, "evidence": "No solar installation-service evidence found."}
        patterns = [r'\bsolar\b']
    elif re.search(r'pet.*groom|dog.*groom', desired):
        patterns = [r'\b(?:pet|dog|cat)\s+(?:grooming|groomers?|salon|spa)\b']
    elif re.search(r'pet shop|pet store|pet suppl|online pet', desired):
        patterns = [r'\bpet\s+(?:shop|store|supplies|products|accessories|food)\b', r'\bdog\s+(?:food|supplies|accessories)\b']
    else:
        words = [word for word in re.findall(r"[a-z]{3,}", desired) if word not in {"companies", "company", "services", "builders", "business"}]
        patterns = [r"\b" + re.escape(word) + r"\b" for word in words]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return {"matched": True, "evidence": text[max(0, match.start() - 70):match.end() + 140].strip()}
    return {"matched": False, "evidence": "Requested business activity was not evidenced on the official site."}


def location_evidence(text: str, location: str) -> dict:
    requested = location.strip()
    parts = [part.strip() for part in requested.split(",") if part.strip()]
    first = parts[0] if parts else ""
    qualifiers = {
        "uk": ["UK", "United Kingdom", "Great Britain"],
        "united kingdom": ["UK", "United Kingdom", "Great Britain"],
        "us": ["US", "USA", "United States", "United States of America"],
        "usa": ["US", "USA", "United States", "United States of America"],
        "united states": ["US", "USA", "United States", "United States of America"],
        "texas": ["Texas", "TX"], "tx": ["Texas", "TX"],
        "california": ["California", "CA"], "ca": ["California", "CA"],
        "hawaii": ["Hawaii", "HI"], "hi": ["Hawaii", "HI"],
    }
    aliases = {
        "hawaii": ["Hawaii", "Honolulu", "Maui", "Hilo", "Kailua-Kona", "Kailua Kona", r"HI\s+96\d{3}"],
        "delhi": ["New Delhi", "Delhi"], "new delhi": ["New Delhi", "Delhi"],
        "mumbai": ["Mumbai", "Navi Mumbai", "Bombay"],
        "bengaluru": ["Bengaluru", "Bangalore"], "bangalore": ["Bangalore", "Bengaluru"],
        "uk": ["United Kingdom", "London", "Manchester", "Birmingham"],
        "united kingdom": ["United Kingdom", "London", "Manchester", "Birmingham"],
        "usa": ["United States", "USA"], "us": ["United States", "USA"],
        "india": ["India", "Delhi", "Mumbai", "Bengaluru", "Pune", "Chennai", "Hyderabad"],
    }
    variants = aliases.get(first.casefold(), qualifiers.get(first.casefold(), [first]))
    matches = []
    for variant in variants:
        pattern = variant if "\\" in variant else re.escape(variant)
        for match in re.finditer(r"\b" + pattern + r"\b", text, re.I):
            # "London Road, Braintree" does not put a business in London.
            if re.match(r'\s+(?:[A-Z][a-z]+\s+)?(?:road|rd|street|st|lane|ln|avenue|ave|drive|dr|way|square|place|terrace|court|crescent)\b', text[match.end():], re.I):
                continue
            excerpt = text[max(0, match.start() - 140):match.end() + 160].strip()
            # Every explicitly requested qualifier must belong to this address /
            # presence statement, not another office elsewhere on the website.
            address_context = text[max(0, match.start() - 50):match.start()].rsplit("\n\n", 1)[-1] + text[match.start():match.end() + 110].split("\n\n", 1)[0]
            uk_postcode = bool(re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b', address_context, re.I))
            if any(not (part.casefold() in {'uk', 'united kingdom'} and uk_postcode) and not any(
                           re.search(r"\b" + re.escape(alias) + r"\b", address_context, 0 if alias == "US" else re.I)
                           for alias in qualifiers.get(part.casefold(), [part])) for part in parts[1:]):
                continue
            # A customer review, travel story or shipping destination is not an office.
            if re.search(r"testimonial|our client|our customer|ship(?:ping)? to|travel(?:led|ing)? to|vacation|not (?:in|from)|not only|canada if", excerpt, re.I):
                continue
            nearby = text[max(0, match.start() - 55):match.end() + 180]
            # Grouped international phones often contain five-digit chunks.
            # Remove those before looking for postal codes beside the place.
            address_text = re.sub(r"\+\d[\d \t().-]{6,}\d", " ", nearby)
            postal_pattern = r"(?<![\d+])\b\d{5,6}\b(?!\d)|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"
            if first.casefold() in {'mumbai', 'bombay', 'navi mumbai'}:
                postal_pattern = r'\b(?:400\d{3}|401\d{3}|4102\d{2})\b'
            elif first.casefold() in {'delhi', 'new delhi'}:
                postal_pattern = r'\b110\d{3}\b'
            elif first.casefold() == 'london':
                postal_pattern = r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b'
            elif first.casefold() == 'sydney':
                postal_pattern = r'\b(?:NSW\s*)?2\d{3}\b'
            elif first.casefold() == 'toronto':
                postal_pattern = r'\bM\d[A-Z]\s*\d[A-Z]\d\b'
            elif first.casefold() in {'bengaluru', 'bangalore'}:
                postal_pattern = r'\b560\d{3}\b'
            elif first.casefold() == 'austin':
                postal_pattern = r'\b78[67]\d{2}(?:-\d{4})?\b'
            postal = bool(re.search(postal_pattern, address_text, re.I))
            if first.casefold() in {'texas', 'tx', 'california', 'ca'}:
                # Another office's postcode after a full stop cannot establish
                # this state's address. TX/CA must accompany their own ZIP.
                postal = bool(re.match(r'^[,\s]*(?:(?:USA|US|United States)\b[,\s]*)?\d{5}(?:-\d{4})?\b', text[match.end():], re.I))
            if first.casefold() in {'sydney', 'toronto', 'bengaluru', 'bangalore', 'austin'}:
                # A different office's postcode in a shared footer must not turn
                # an unlabelled service-area city into an address.
                after_city = text[match.end():match.end() + 115]
                postal = bool(re.match(r'^[,\s]*(?:(?:NSW|ON|Ontario|TX|Texas|Karnataka|KA|India|Canada|Australia|USA|United States)\b[,\s]*){0,3}(?:' + postal_pattern + ')', after_city, re.I))
            before = text[max(0, match.start() - 90):match.start()]
            after = text[match.end():match.end() + 45]
            # Tie the location to the company's presence, not just an unrelated
            # "based on" or "contact" word elsewhere in a sales/travel page.
            business_context = bool(re.search(
                r"(?:offices?|our headquarters?|headquartered|(?:we are|we're|company is|business is|studio is|firm is|team is)\s+(?:located|based)|(?:^|[.!?\n])\s*(?:located|based))\s*(?:in|at|:)\s*(?:[\w-]+[,\s]+){0,4}$",
                before, re.I) or re.match(r"\s+(?:office|headquarters|branch)\b", after, re.I))
            if postal or business_context:
                matches.append({"matched": True, "evidence": excerpt[:320], "matched_place": match.group(0),
                                "basis": "address" if postal else "business_presence"})
    if matches:
        return next((item for item in matches if item['basis'] == 'address'), matches[0])
    return {"matched": False, "evidence": "No address or business-presence evidence for the requested location.", "matched_place": "", "basis": "unconfirmed"}

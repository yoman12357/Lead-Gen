# Four-market live audit — 23 October 2026 (Asia/Kolkata)

## Result and scope

**The selected final runs returned 10 leads in each of four markets. All 40 delivered businesses were reviewed for business activity, requested-market presence, identity and a supported published contact route.** No duplicate company domains, selected emails or selected phones occur in the reviewed export. These are company prospects; mailbox delivery, phone answering and individual buying intent are not established.

| Market | Requested / returned / qualified | Published emails independently supported | Published phones independently supported | Final run seconds | Final Tavily credits | Final Hunter credit delta |
|---|---:|---:|---:|---:|---:|---:|
| Dentists — Sydney | 10 / 10 / 10 | 5 | 10 | 95.0 | 12 | 0 |
| Law firms — Toronto | 10 / 10 / 10 | 4 of 5 selected emails | 10 | 14.6 | 6 | 0 |
| Architects — Bengaluru | 10 / 10 / 10 | 7 | 9 | 50.0 | 9 | 0 |
| Solar installers — Austin, Texas | 10 / 10 / 10 | 4 | 10 | 126.4 | 14 | 0 |

Sydney includes the explicitly reviewed metropolitan locations Bondi Junction, Paddington and the Inner West. Bengaluru accepts the Bangalore spelling. The Austin solar category includes commercial providers: RWE Americas is identified as a commercial/community solar design-build-install provider, not a residential rooftop contractor. Rows state these distinctions.

The workbook has four qualified market tabs, four review tabs, a quality summary, a field-correction ledger, source limitations, provider credits, the request ledger and total audit costs. The CSV files contain reviewed qualified prospects only. Review tabs retain each discovered business and its review decision; original field values appear in the correction ledger and original API responses remain preserved separately. XLSX stores phones as literal text; CSV escapes leading formula characters (including a phone's `+`) with an apostrophe for spreadsheet safety. The shareable report uses factual reviewer notes and official source links; full web-page capture files are not included in the download bundle.

## Completed checklist

- [x] Inspect the existing pipeline and prior audit assumptions before changes.
- [x] Add provider-reported usage tracking before the new live tests.
- [x] Test category variants and Australian, Canadian, Indian and US location evidence.
- [x] Request 10 leads for each market through the persisted HTTP job API.
- [x] Reject confirmed directory, publisher, government and membership-body false positives.
- [x] Improve bounded query expansion and exclusion of already discovered domains.
- [x] Repair office-page identity, fax selection, multi-country phone parsing and generic inbox fallback.
- [x] Independently fetch official sources and review every delivered company.
- [x] Preserve uncertainty and separately record source-supported contact corrections.
- [x] Export, reopen and validate the workbook and individual CSV files.
- [x] Retain every diagnostic run in the full audit cost ledger.
- [x] Run the full regression suite: **269 passed in 21.01 seconds**.
- [x] Reload the main local application with current sources; `/health` returned 200 and an existing persisted job was unchanged after restart.

## Architecture retained

The browser submits a persisted job through `POST /api/lead-searches`. `LeadSearchJobs` stores requests and progress in SQLite and invokes `ProductionLeadPipeline.run`, which constructs `SearchIntent` and `LeadSearchEngine`. The generic engine plans bounded queries, discovers company domains, fetches official pages, checks category/location evidence, extracts published contacts, checks mail-server DNS, ranks contacts and produces incremental snapshots. Tavily provides search and optional extraction; HTML search and Hunter are bounded fallbacks. The generic engine did not make Gemini calls in these runs.

The test runner uses the same HTTP API and saves terminal job responses. The independent evidence reader then refetches sources, and a complete review manifest gates the reviewed workbook. Discovery values and reviewer changes are separate. Specialized pipelines and existing UI flows were preserved. See `LEAD_PIPELINE_AUDIT.md` and `LEAD_15_QUALITY_AUDIT.md` for the earlier architecture and validation work.

## Confirmed issues and implemented fixes

| Priority | Confirmed root cause | Implemented change / verification |
|---|---|---|
| P1 | A directory can contain a target company's activity and address while publishing the directory owner's contacts. Government portals and membership bodies also mention services they do not supply. | Structural directory/profile/member rules, explicit directory self-description and marketplace labels, and provider-intent checks on publisher/government/membership identities. Regression cases cover the observed false positives. Earlier rejected examples remain in diagnostic responses and are absent from the final delivered sets. |
| P1 | Multi-office domestic numbers were parsed with the requested market's country, turning a New York number into an apparently valid Indian number. | Prefer the nearest preceding published country label for unprefixed numbers. A regression verifies New York `212 620 0996` becomes `+12126200996`, not `+912126200996`. The old discovery value was removed from the reviewed MBH row; its published company inbox remains the supported route. |
| P1 | Fax labels carried by SVG icons disappeared during text sanitization, and broad context could confuse a nearby phone/fax pair. | Preserve explicit Fax icon labels and reject the number immediately labelled Fax/F:. Tests cover neighbouring phone/fax numbers and SVG labels. Bennett Jones' final selected number is its phone, not its fax. |
| P1 | Office-page metadata such as `Toronto` could override the company brand. | Prefer homepage branding, exclude requested-place-only identity values and recognize additional business schema types. Year-only copyright values are rejected. |
| P1 | Domain-wide person enrichment did not establish that a person belongs to the requested office. Press inboxes were also selected as ordinary business routes. | Hunter's fallback selects sourced generic company inboxes; unrelated named people are not inferred to be local contacts. Press/media and other unsuitable role inboxes are excluded. |
| P2 | Plural profession keywords and a location checker designed around Indian/UK addresses missed real Australian and Canadian businesses. | Profession query variants and activity rules for dentistry, law, architecture and solar installation; local postcode rules and multi-country evidence capture. |
| P2 | A service-area city could borrow a nearby postcode from another office in a shared footer. | For the new markets, require the postcode beside the city/region address or an explicit business-presence statement. Regression cases reject unrelated Round Rock/Dripping Springs postcodes as Austin addresses. |
| P2 | Four rounds could stop before the configured 18-query budget; close query variants repeatedly returned previously checked sources. | Up to six bounded rounds, varied city phrasing and a maximum of 150 discovered-domain exclusions. All existing time/count/cancellation limits remain. Austin's diagnostic 7/10 shortfall was followed by a final 10/10 run; this does not guarantee that every future request reaches its target. |
| P2 | Query counts were not actual credit measurements. Failed or cancelled attempts could disappear from accounting. | Request `include_usage`, save one receipt per attempt, record HTTP outcome/request ID and preserve unreported billing as unknown. Job metadata includes Tavily receipts, Hunter attempt count and actual Gemini call count. |
| P2 | The earlier quality report hardcoded two markets, 15 rows each and Indian/UK phone regions. | Generalized evidence capture, dynamic workbook counts, explicit rejection support, review corrections, literal XLSX cells, formula-safe CSV output, and no-provider-call replay. |

## Credit accounting

**Selected final runs:** 41 Tavily credits reported by completed requests; 0 additional Hunter credits measured across those runs; 0 Gemini calls. Hunter attempts and Hunter credit debits are distinct: repeat/no-result lookups did not reduce the measured balance in these final runs.

**Entire audit, including debugging and superseded runs:**

| Market | Runs | Tavily credits reported | Attempts with unreported billing | Hunter unified credits measured |
|---|---:|---:|---:|---:|
| Sydney dentists | 5 | 50 | 0 | 1 |
| Toronto law firms | 3 | 20 | 0 | 1 |
| Bengaluru architects | 3 | 19 | 1 | 0 |
| Austin solar installers | 5 | 70 | 1 | 1 |
| **Total** | **16** | **159** | **2** | **3** |

There are 222 Tavily attempt records. Two earlier interrupted extraction requests have no returned usage receipt. Thus **159 is a measured lower bound for the full audit, not an exact final bill**. All attempts in the selected final runs have usage receipts. No dollar charge is inferred from plan credits.

Tavily's account usage endpoint returned unchanged snapshots and occasionally failed; one later snapshot included a large delayed update. Those account deltas cannot reliably attribute usage to individual jobs. The report retains these observations and uses returned per-request credit receipts for Tavily attribution. Hunter uses before/after unified-credit balance measurements; its searches/verifications fields are views of the same pool and are not added together. Concurrent activity on the provider account can affect account-level deltas.

Measurement references: [Tavily search usage](https://docs.tavily.com/documentation/api-reference/endpoint/search), [Tavily extraction usage](https://docs.tavily.com/documentation/api-reference/endpoint/extract), [Tavily account usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage), [Hunter usage](https://hunter.io/api-documentation/v2#usage).

## Review evidence and limits

- 40 company/category/location decisions and 40 supported published contact routes.
- 21 selected emails; 20 independently reproduced or supported by a second official reader. Fasken's email is masked in that reader and remains flagged; its current official managing-partner phone supports the row.
- 39 selected phones, all numbering-valid and independently publication-supported. No phone ownership or answer-rate claim.
- 34 direct HTTP source rechecks; six blocked source rechecks supplemented with official pages through a second public reader. Indexed or cached source content can be stale.
- Eight field changes across five companies are visible in `Review corrections`: stale/unconfirmed contacts removed or replaced, the misinterpreted foreign-office phone removed, the Toronto head-office number preferred, and published company names clarified.
- Mail-server DNS does not establish a deliverable mailbox. No SMTP probing or outreach occurred.
- Live Google Sheets writes were not exercised; this deliverable is an Excel workbook plus CSV files. The existing storage connector has controlled regression coverage.
- A single persistent application worker is the supported job deployment model. Multi-worker durability is outside this verification.

**Sign-off:** the four-market discovery-to-reviewed-export test is verified. This is not a blanket claim that all future markets, live external integrations, delivery/reachability, or deployment topologies have been verified. Source review remains necessary where the workbook flags uncertainty.

## Reproduction

Use the existing saved jobs to validate without consuming provider credits:

```powershell
python -X utf8 -m pytest -q --basetemp tmp_market10_done
python -X utf8 -m scripts.verify_pipeline_matrix --case dentists-sydney --case lawyers-toronto --case architects-bengaluru --case solar-austin --count 10 --output exports/market-10/deliverable --replay
python -X utf8 -m scripts.build_quality_review_report --input exports/market-10/deliverable --evidence exports/market-10/sources-deliverable --reviews exports/market-10/deliverable/manual-reviews.json --history exports/market-10 --history exports/market-10/final --history exports/market-10/verified --history exports/market-10/release
```

`scripts.verify_market_credits` performs new paid-provider requests and intentionally refuses to overwrite existing run files. A new output directory is required for another live audit.

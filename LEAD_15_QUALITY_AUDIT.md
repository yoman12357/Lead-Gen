# 15-lead quality audit — 22 October 2026

Goal: run two different business/location combinations with a target of 15 each, inspect lead quality from source evidence, fix demonstrated pipeline gaps, and rerun the affected searches.

Chosen cases: Digital Marketing in Mumbai; Accountants in London, UK. These are large markets with different contact formats and business categories. A lead must represent the actual operating company, fit the category and requested geography, have a sourced usable contact route, and be unique. Email MX does not establish mailbox delivery. Named decision makers are not invented.

- [x] Run the existing pipeline through the persisted API with target_count=15 for each case; preserve raw results and counts.
- [x] Independently inspect every result's company identity, official sources, category/location evidence, email, phone and duplicates; record defects and uncertain results.
- [x] Add focused regressions and fix demonstrated root causes without weakening acceptance criteria.
- [x] Rerun searches after changes with target_count=15; inspect all final records, run tests, and export the quality-reviewed results with explicit limitations.

Baseline evidence directory: `exports/quality-15/baseline/`.
Final evidence directory: `exports/quality-15/deliverable/`.
Fresh source snapshots/recheck records: `exports/quality-15/deliverable-sources/`.
The other audit folders are intermediate diagnostic runs, not the delivered dataset.

## Baseline findings

Both cases returned 15/15: Mumbai in 56.2 seconds (19 completed company checks, three queries), London in 93.7 seconds (44 checks, nine queries). The count/score contract passed but independent source review found quality defects; the baseline workbook is diagnostic evidence, not the final deliverable.

- **Confirmed wrong source types:** IFA's Find an Accountant membership directory and the UK's Regulated Professions Register entered the London results. Their member/regulator details must not become an operating-company lead.
- **Confirmed wrong location:** Web SEO India's Mumbai landing page passed despite its contact section publishing only a New Delhi office. An SEO heading is not office evidence.
- **Confirmed contact contamination:** a script's analytics-like number `1768642710` became `+911768642710`; an unrelated embedded Baker Tilly employee email could be selected from script data. Public visible text, explicit contact links and obfuscated published contacts must be separated from executable data.
- **Confirmed missed contact:** Beeing Social's `.com` website publishes `contact@beeingsocial.in`; exact hostname matching discarded it. Same-brand alternate domains require explicit official-source publication, not unrestricted cross-domain acceptance.
- **Confirmed weak identity:** "Chartered Accountants" and "Reliable Accounting Services" replaced the published ASK Accountants and London Accounting Firm brands.
- **Additional reliability gaps:** UK postcodes establish the country even when "UK" is omitted; a city's occurrence in a street name is not a locality; capped confidence values prevented a known target-office phone from outranking the general office; indexed recovery was incorrectly labelled as direct website reachability.

The new source-quality regressions initially produced **12 failures**. The first implementation passed all 63 focused quality/reliability/search tests. Two additional tests cover unrelated footer emails and office preference at capped confidence. The pre-existing working tree and specialized lead pipelines are preserved.

## Quality criteria

Review every returned company against its own pages, including those missed by automated flags. Separate company/category fit, requested location presence, published contacts, uniqueness, and email delivery certainty. Preserve fresh HTML/text snapshots with URL-specific names, and record source-access failures as unconfirmed rather than passing them. Direct HTTP and indexed recovery have separate provenance. Mumbai geography uses local postal evidence or an explicit base/office statement; city landing pages alone cannot fill the count. Multi-office providers remain eligible when their requested office is actually evidenced.

The final workbook will include per-record quality decisions and source links. No fabricated person, mailbox-delivery claim, or arbitrary score increase is permitted to meet the 15-lead target.

## Final verified result

| Business / location | Target / returned | Published emails | Mail servers found | Valid-format phones | Independently supported contact routes | Job seconds |
|---|---:|---:|---:|---:|---:|---:|
| Digital Marketing / Mumbai | 15 / 15 | 14 | 14 | 14 | 15 | 35.7 |
| Accountants / London, UK | 15 / 15 | 12 | 12 | 15 | 15 | 35.6 |

- **30 company records reviewed**, with category fit, source identity and own-office location evidence. Mumbai includes explicitly stated Thane/Navi Mumbai metropolitan offices; London includes Greater London. No directory, regulator or third-party competitor address remains in the reviewed set.
- **0 duplicate company hosts, 0 duplicate emails and 0 duplicate phone numbers** in the delivered set.
- All 26 selected emails were supported by official-source publication and had MX records at discovery. No SMTP deliverability or named decision-maker verification is claimed.
- All 29 phone numbers pass numbering validation; 28 were independently reproduced through official sources. Mindstorm's additional `+919619896439` was present in a contact link during discovery but was not independently reproduced by the second reader. The workbook flags that phone; its independently confirmed business email remains a usable route. No phone ownership or live reachability test was performed.
- Fresh independent HTTP checks reproduced official sources for **23 companies**. **7 companies** blocked the HTTP recheck and were supplemented with another public reader of their own official pages. Some of those reader results are indexed and may be stale; this distinction remains in the evidence manifest and workbook. Source blocking is not silently counted as an HTTP pass.
- **230 tests passed in 20.68 seconds**, clean test completion (`python -X utf8 -m pytest -q --basetemp tmp_quality15_final_gate`). This preserves the previous 202 cases and adds 28 source-quality cases.
- Browser checks passed for persisted jobs, refresh recovery, cancellation, click/Enter dispatch, specialized Velit routing, responsive widths, a reopened 15-row Excel download and zero page errors.
- The quality workbook was saved and reopened: **15 data rows in each market sheet**, plus summary and limitations/evidence sheets. Its builder refuses missing manual reviews, unsupported contact routes, bad phone formats, duplicate identities or a shortfall hidden by relabelling the target.

## Additional fixes confirmed by the 30-record review

1. Exclude professional/member directories, government professional registers, generic resource/telephone directories, and multi-company website-field listings by relationship/content/path instead of adding only hostname exceptions.
2. Separate a real operating firm's directory-membership badge from the identity of a directory. The saved-results verifier exposed this false positive for Xerxes; a regression now preserves the firm while still rejecting directory paths.
3. Read public visible contact text, explicit mailto/tel links and decoded published obfuscated emails; remove executable/script attributes from contact candidates. Preserve same-brand alternate-domain inboxes only when the official site actually publishes them.
4. Normalize balanced Markdown contact links, including UK `(0)` telephone prefixes, to avoid concatenating a link destination onto its visible number. Kreston Reeves now has its published London phone instead of an unreproduced broker employee email.
5. Qualify location from a matching postal address or explicit company base/office statement; reject city SEO headings alone and city words used as street names, such as London Road or London Square elsewhere. Use UK postcode evidence for the explicit UK qualifier.
6. Exclude editorial/listicle pages from category/location/contact qualification. An agency's own list of competitors must not establish its own address. Prefer own contact/office location pages over generic service pages.
7. Read navigation links from both the discovery page and homepage, prioritize contact/office routes over team pages, and deduplicate equivalent page URLs within the six-page limit. TechShu now yields its official Mumbai address, solutions inbox and business phone from its contact page, rather than relying on a broker email.
8. Use meaningful organization/site/logo/copyright/published-brand evidence for names; ignore template tokens, generic descriptors, domain-only metadata and copyright years. Preserve identity source URL and basis.
9. Reject sites dominated by unfinished template testimonials, retain explicit indexed/direct retrieval provenance, rank matched offices above equal-confidence general-office phones, and retain Hunter's actual public source URLs and last-seen dates while ignoring removed sources.

## Final artifacts and reproduction

- `exports/quality-15/deliverable/quality-reviewed-30-leads.xlsx` — user-facing workbook with review notes and field-level limitations.
- `exports/quality-15/deliverable/quality-review.json` — per-company reviewed facts and quantitative checks.
- `exports/quality-15/deliverable/manual-reviews.json` — 30 explicit company-fit decisions and seven supplemental official-source reviews.
- `exports/quality-15/deliverable/{marketing-mumbai,accountants-london}.json` — unmodified completed API job snapshots.
- `exports/quality-15/deliverable-sources/` — URL-specific fresh HTML/text evidence and independent contact-publication rechecks. Failed HTTP checks remain recorded.

New live test (uses configured search credits, no outreach):

```powershell
python -X utf8 -m scripts.verify_pipeline_matrix --case marketing-mumbai --case accountants-london --count 15 --output exports/quality-15/new-run
```

Revalidate the delivered terminal API snapshots and rebuild the raw workbook without new provider calls:

```powershell
python -X utf8 -m scripts.verify_pipeline_matrix --case marketing-mumbai --case accountants-london --count 15 --output exports/quality-15/deliverable --replay
python -X utf8 -m scripts.build_quality_review_report --input exports/quality-15/deliverable --evidence exports/quality-15/deliverable-sources --reviews exports/quality-15/deliverable/manual-reviews.json
```

The last live jobs completed successfully at 15/15. A verifier initially misclassified a directory badge in a short excerpt; after the classifier regression was fixed, those same saved jobs were revalidated with `--replay`. No replacement search or synthetic data was used to hide a failing lead-quality gate.

## Supplemental official-source checks

The seven HTTP-blocked companies were checked through the following first-party pages. Detailed field decisions and source-access limitations remain in the manual manifest.

- [Mindstorm contact](https://mindstorm.in/contact): business inbox and Worli/Mumbai location; independent phone publication remains inconclusive.
- [911 Marketing official homepage](https://911marketingagency.com/): digital agency, BKC Mumbai branch, company inbox and phone; indexed official search result.
- [Pixel Suba contact](https://pixelsuba.com/contact/): Dadar/Mumbai office, business inbox and phone; indexed official page.
- [Accotax contact](https://accotax.co.uk/contact/): Chelsea/London office by appointment, business inbox and central company phone.
- [The Accountancy Partnership London](https://www.theaccountancy.co.uk/london-accountants) and [contact](https://www.theaccountancy.co.uk/contact): Greenwich/London office, company inbox and phone.
- [Kreston Reeves London](https://www.krestonreeves.com/locations/london/): accountancy services, Shoreditch address and London office phone.
- [Menzies London](https://www.menzies.co.uk/office/london/): accountancy services, Gresham Street address and London office phone.

These are qualified company-level prospects with supported public contact routes. Mailbox delivery, phone answer rate, legal entity ownership and willingness to buy were not tested. Optional Google Sheets remains unconfigured and was not written to. This audit sends no email, LinkedIn message or contact form submission.

# Company briefs for supplier and project-partner review

## What a good summary is for this team, and why

A reviewer deciding which file to open first needs the company's line of business, who holds the largest stake, what its latest accounts show, and one concrete question to pursue. A short brief also needs to say when the evidence runs out. In this experiment, a good brief fits within 145 words, attributes financial figures to a year, preserves the company's role and the status of a court case, and recommends a source document to check. Supplier approval stays with the reviewer.

Cahaya Seri Catering illustrates the stakes. Its FY2024 accounts show an after-tax profit of RM 178,923. Its record also lists a pending winding-up petition in which the company is the defendant. The filing gives a claim amount of RM 355,900. A reviewer reading only the profit could easily prioritise a different document. The docket is the appropriate place to check what happened next.

The input is a synthetic snapshot dated 31 December 2025. Its latest financial year is FY2024 for every company with accounts. Among 50 companies there are 127 financial periods, 177 director entries, 134 shareholder entries, and 72 cases across 18 companies. Eight companies have corporate shareholders, and five companies appear on both sides of different cases. Cross-company joins on the anonymised names would be unreliable. [Dataset audit](evaluation/data-audit.json)

| Financial history | Companies | Consequence for the summary |
|---|---:|---|
| FY2022, FY2023 and FY2024 | 38 | Test comparability before calculating year-on-year growth. |
| FY2022 and FY2024 | 4 | Identify the missing FY2023 filing. |
| FY2024 only | 5 | Report the level and disclose the single period. |
| No supplied financials | 3 | Request accounts and leave performance unknown. |

Of the 47 companies with accounts, 11 report a latest-year loss and 11 report negative operating cash flow. The three audit observations that differ from a plain unqualified opinion all appear before FY2024. There are 101 null ratio cells, confined to tax efficiency, days inventory outstanding and inventory turnover. The unrounded share percentages sum to 100% for all 50 records at the supplied precision. The balance-sheet equation and the after-tax margin cross-check both pass for all 127 periods.

## What you built

The Python pipeline first produces sentences tied to JSON pointers in one company record. It formats RM amounts, computes financial features, and groups facts into company profile and ownership, finances, and litigation. Each optional fact has a specific follow-up. The original viewer reads the final Markdown by registration number. An evidence ledger for any company can be printed with the command in the README.

| Version | How content is chosen | Records |
|---|---|---:|
| Basic template | Fixed sections plus revenue trend or filing limitation, current ratio and a representative case where available | 50 |
| Pilot hybrid | A language model chooses a focus and a supporting detail from the evidence menu | 4 |
| Priority rules | Required disclosures plus deterministic priorities for the follow-up and supporting detail | 50 |
| Revised hybrid | The same required disclosures and the same word budget, with model-selected discretionary details and follow-up | 50 |

Growth is the change in revenue divided by positive prior revenue. It is shown only for adjacent fiscal years with comparable supplied year-end dates. The after-tax margin is profit after tax divided by positive revenue. The current ratio is current assets divided by positive current liabilities. Operating cash flow and borrowings come directly from the relevant statement. Losses keep their sign in calculations. RM amounts are displayed exactly at source precision, percentages to one decimal for calculated features, and the current ratio to two. Undefined ratios stay unavailable. For example, Unity Global Trading's revenue rose from RM 5,229,803 in FY2023 to RM 5,352,856 in FY2024, a 2.4% increase. Cahaya Seri Catering lacks the intermediate year, so its brief omits year-on-year growth.

The model is Qwen2.5-1.5B-Instruct (Q4_K_M), served through a free self-hosted llama.cpp chat-completions API. There was no configured Gemini key. The model's two output fields must refer to allowed fact keys. Python renders numbers, dates, legal wording and follow-ups from those keys. An invalid response triggers a limited retry and is recorded. Completed responses can be replayed offline. This arrangement gives the model a real editorial choice while keeping every displayed claim traceable. The cost is less natural variation and a hard limit on what the model can express. [Model and replay instructions](README.md)

Court-case selection first considers pending defendant winding-up petitions, then defendant petitions with judgment entered, then other pending defendant matters and defendant judgments. Remaining cases are ordered by procedural status, claim size and case ID. The amount is labelled as a claim. The documents do not establish who won, what sum was awarded, or what was paid.

**AI assistance.** ChatGPT and Codex assisted with experiment design, coding, testing, the version-masked assessment and drafting. Qwen performed the live evidence selection. The qualitative grades below come from one AI-assisted reading by the same implementation assistant. The supplementary source-to-summary check below was performed by the author with ChatGPT assistance using viewer screenshots; independent human review remains outstanding.

## How you know whether it's good

The evaluation protocol and 57 reference facts were recorded before generation. Four development records included an ordinary business, gapped filings with litigation, a company winding up, and a company without accounts. Fifteen different records were chosen for a locked comparison across routine and difficult cases. Each has three reference facts derived from its raw record. All 50 companies were processed to check operational coverage. The 15 were deliberately selected for variety, so the results are descriptive. [Protocol](evaluation/protocol.md) · [Company IDs, selection reasons and reference facts](evaluation/targets.json)

**The pilot changed the design.** The model-only selector included five of 12 target facts. On Cahaya Seri Catering it chose operating cash flow and omitted the filing gap and the petition. On Cahaya Golden Systems it preserved the winding-up status but omitted the FY2022 going-concern observation. The revised renderer reserves space for the trend or filing limitation, unusual audit opinions and a named case when proceedings exist. A narrow rule also prioritises the follow-up for winding-up status, absent accounts, audit exceptions or live defendant matters and defendant judgments. The revised hybrid covered all 12 pilot facts using the same four saved model responses. The subsequent comparison used the separate 15-company set.

| Method | Pilot facts | Held-out facts | Median words across generated records | Longest brief |
|---|---:|---:|---:|---:|
| Basic template | 11/12 | 37/45 (82.2%) | 71 | 101 |
| Pilot hybrid | 5/12 | — | 66 | 73 |
| Priority rules | 12/12 | **44/45 (97.8%)** | 77.5 | 114 |
| Revised hybrid | 12/12 | 42/45 (93.3%) | 75 | 113 |

The hybrid covered five more held-out facts than the basic template. The matched priority rules covered two more facts than the hybrid. Both were current ratios, one for a loss-making company and another for a company with an earlier audit disclaimer.

However, all three full-dataset methods omitted **CASE-2025-5402**, a settled debt-recovery case involving Pacific Pacific Education Sdn. Bhd. as the defendant, with a recorded claim of **RM7,427,000**. Instead, the summaries highlighted a smaller pending breach-of-contract claim of RM458,400 (CASE-2023-7966).

Although the settled case does not establish an outstanding liability or the amount ultimately paid, its substantial claim value may be relevant to supplier due diligence. This exposes a limitation of selecting only one representative court case using procedural priority rules.

A potential improvement would be to consider both case status and financial materiality, allowing a second significant case to be included where appropriate. This should be evaluated against summary completeness, factual accuracy, and readability before implementation.

**Accuracy and usefulness.** Structural and source checks found zero flagged discrepancies over the 50 final hybrid briefs (582 checks) and validated unique IDs and viewer format. The checks bind numbers to their field and year and named court claims to their case, role and status. They cannot establish business usefulness or exhaustively verify arbitrary prose. In a seeded, version-masked reading of 30 briefs against the same source records, the basic template averaged 86.50/100 and the hybrid 94.17/100. The hybrid scored higher on seven companies, tied on six and scored lower on two. Coverage uses the three reference facts. The other dimensions use the disclosed reviewer’s grades. The priority rules received the same automated checks and coverage measurement. The paired qualitative reading covered the basic template and revised hybrid only. [All results](evaluation/results.json) · [Thirty ratings and rationales](evaluation/assisted-review.csv)

| Dimension, scored 0–2 | Weight | Basic template | Revised hybrid |
|---|---:|---:|---:|
| Factual accuracy | 35% | 2.00 | 2.00 |
| Coverage | 30% | 1.47 | 1.80 |
| Decision usefulness | 20% | 1.60 | 1.87 |
| Clarity and concision | 15% | 1.80 | 1.80 |

The 50 responses used for the final run consumed 24,207 input and 1,069 output tokens. Requests took 120.88 seconds in total with a median of 2.42 seconds, excluding server startup. All 50 succeeded on the first attempt. One additional successful response was superseded after correcting an article in an evidence sentence. It used 560 input and 23 output tokens and is retained. Direct external API charges were zero. Local compute and electricity were not metered. The model chose cash flow as its focus for 32 of 50 companies. Required follow-ups applied to 12 records and changed the model’s choice in seven.

**Evaluation correction.** While checking the paired outputs, a transposed reference amount was found for Murni Bestari Tech. The FY2024 statement shows RM 1,497,176. The original reference said RM 1,491,176. Correcting this source transcription added one hit to each full method. No generator, selection rule or company changed in response. A new reference-amount check and regression test catch this error. [Correction record](evaluation/protocol.md#reference-correction)

### Supplementary source-to-summary spot check

After the main evaluation, an author-directed, AI-assisted spot check compared source records and generated summaries for seven companies across five scenarios. Both the priority-rule and revised-hybrid versions were examined (14 briefs in total). This was a targeted review of visible financial and litigation statements using the original viewer; it was not a blinded or independent human assessment.

- **Jaya Prima Travel (SYN-000067) — sustained losses:** Both versions correctly reported the FY2024 loss of RM 7,515,861 and negative operating cash flow of RM 5,939,447. Priority rules included the current ratio of 0.81; the hybrid omitted it. The source confirmed no recorded court cases.
- **Pacific Pacific Education (SYN-000397) — competing legal cases:** Both versions correctly reported FY2024 revenue of RM 6,863,227, profit of RM 371,117, missing FY2023 accounts, and the selected pending claim of RM 458,400. Both omitted the larger settled claim of RM 7,427,000. Priority rules included the current ratio of 2.55; the hybrid omitted it.
- **Cahaya Seri Catering (SYN-000286) — filing gap and winding-up petition:** Both versions disclosed missing FY2023 accounts and a pending defendant winding-up petition with a claim of RM 355,900, without stating that the company had already been wound up. Priority rules included the FY2024 current ratio of 1.90; the hybrid instead included operating cash flow of RM 220,184.
- **Global Pacific Perunding (SYN-000302), Gemilang Harmoni Enterprise (SYN-000333), and Pacific Seri Freight (SYN-001203) — no supplied accounts:** All six briefs acknowledged unavailable financial statements without inventing figures. The Pacific Seri Freight briefs also correctly reported a settled breach-of-contract case (CASE-2023-0273), the company's *plaintiff* role, and the RM 22,500 claim, checked against its litigation record.
- **Unity Global Trading (SYN-000029) — routine performance:** Both versions correctly reported FY2024 revenue of RM 5,352,856, after-tax profit of RM 96,805, and 2.4% growth from FY2023. The litigation tab confirmed no cases in the supplied record. Priority rules included the current ratio of 1.48; the hybrid omitted it.

No incorrect financial amounts or court-case descriptions were identified **among the specific claims checked**. The more important distinction was completeness: a brief can be factually correct but omit useful liquidity evidence or significant concluded litigation. This spot check did not verify every generated sentence, director count, ownership percentage, incorporation date or the litigation tabs of every company without accounts. It does not establish population-wide error rates, and it leaves the original evaluation scores unchanged. Independent reviewer testing remains future work.

## What you'd do next, and how you'd keep improving it

I would start the reviewer pilot with the priority-rule version. It covered 44 of the 45 prespecified facts, requires no inference service, and its choices are easy to inspect. The principal untested question is whether people reach the right source document more quickly with the hybrid's choice of follow-up. Two procurement reviewers could independently use each version in random order, record the first document they open, time to find the material issue, and any misleading claim. I would resolve disagreements against the source and reserve fresh cases for the next comparison.

For multi-case companies I would test including a second case when a large concluded claim and an open matter compete for space. The evaluation would measure both omissions and whether readers confuse the two statuses. I would also test short briefs with a missing ratio or altered fiscal year-end, then measure errors on a later snapshot and new sectors. In deployment I would log the record version, evidence references, selected facts, model version and corrections, and monitor omissions, failed requests and review time. Publishing an approval or predicting default would require a different task, outcome labels and validation.
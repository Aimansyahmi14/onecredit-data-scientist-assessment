# Evaluation protocol

Fixed before generation on the supplied snapshot (assessment 2026.11).

**Decision.** A procurement reviewer has time to open one or two source documents. The brief should convey what the company does, who holds the largest stake, its latest reported performance, any material gaps or proceedings, and a specific document to inspect. A claim amount describes a filing. A court status alone does not identify a winner. The benchmark has no supplier outcomes or expert-written summaries.

**Sample.** Four development companies (ordinary, gapped with litigation, winding up with a historical audit issue, and no accounts with a settled plaintiff case). Fifteen different companies form a locked, purposive challenge set. The 31 others can be processed to check scale. Only the pilot informs changes. All comparisons use identical company IDs; the 15 are not a random estimate of production quality. A row in `targets.json` records the selection reason and three source-derived facts per company. The order of records in the source has no statistical meaning.

**Measures, in order.**

1. Count failures separately: valid JSONL, unique known IDs, nonempty Markdown, correct company pairing, model responses saved, and company coverage. Never count a deterministic fallback as a successful model generation. Check the viewer's routes.
2. Count the prespecified facts present in the prose (45 on the locked set, 12 on the pilot). Search for independent terms/numbers from the raw records with case-insensitive matching. Related values in one check must match within the same paragraph. Inspect any ambiguous hits. This is a coverage measure; it cannot detect a mistaken assertion elsewhere.
3. Rate the final baseline and hybrid on the same 15 records using the following ordinal rubric. For each record, display the two texts in a seeded randomized order, with the source and three target facts beside them. Keep one rationale per version and disclose the reviewer. A stronger test would use two independent procurement reviewers. No LLM judge is treated as a human reviewer.
4. A wrong monetary sign, figure, period, case role or outcome, a claim represented as money owed, or an unsupported approval/rejection is a critical error. Record the error separately. A high weighted score cannot override it.
5. Compare the hybrid with a priority-rule control using the same evidence, required topics, and space. The additional value of the model is the comparison to this control. Report scores descriptively, ties and losses included.
6. Record word counts (space-delimited), cached provider responses, usage, failures and latency. Count direct external API charges separately from unmeasured computing costs. Take one improvement from observed pilot errors, then lock the design and run the 15-company comparison.

| Dimension | Weight | 2 | 1 | 0 |
|---|---:|---|---|---|
| Factual accuracy | 35% | All reviewed assertions supported and correctly qualified | A minor ambiguity with no change of meaning | Wrong fact, unsupported decision, or material ambiguity |
| Coverage | 30% | All three predefined facts | Two facts | Zero or one fact |
| Decision usefulness | 20% | The proposed next check targets a material issue, or an appropriate verification for a routine file | A relevant check but a higher-priority item is overlooked or the evidence needed is vague | No actionable or defensible next check |
| Clarity and concision | 15% | Easy to scan, at most 145 words, dates and roles clear | Understandable but repetitive, dense or longer than 145 words | Misleading structure or hard to follow |

A weighted score out of 100 is the sum of weight × rating / 2. The 145-word target is a design choice. The template supplies no weights, minimum sample size or cutoff for acceptance. Safeguards and ablation should be interpreted separately from model quality.

## Reference correction

During the source-by-source reading, Murni Bestari Tech’s FY2024 after-tax profit was found to be RM 1,497,176. The initial reference transposed a digit to RM 1,491,176. Both displayed briefs agreed with the statement. Correcting only this expected amount changed basic template coverage from 36 to 37, revised hybrid coverage from 41 to 42, and priority-rule coverage from 43 to 44, all out of 45. The three per-company targets, record selection, output texts, thresholds and relative ranking were otherwise identical. The evaluation now verifies comma-formatted reference amounts against the raw financial statements and claims before scoring. The unit suite includes the original erroneous amount as a regression.

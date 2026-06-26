# Phase 2 EvidenceResearchAgent Report

Status: needs_attention

Report path: `/home/vepfs/data/work1/muti-agent-work_test4/runs/subagent_reports/phase_2/evidence_research.md`

## Scope

Read-only audit of Phase 2 Evidence Registry + Research Indexing on:

- `stable_core/evidence`
- `research_tools`
- `evidence/*.jsonl`
- `docs/research/*.md` and `docs/research/*.tsv`
- `tests/test_evidence_registry.py`
- `tests/test_research_indexing.py`
- `stable_core/cli.py`

No `.env` file was read. No code or project files were modified except this report.

## Final Verdict

Phase 2 is now implemented at a basic, auditable manifest-indexing level, but it should remain `needs_attention` rather than `passed`.

The registry exists, parses cleanly, has unique IDs, exposes the required CLI commands, and avoids fabricated recent-paper/framework claims by marking unfinished research as `needs_attention`. The main remaining gaps are that stored `code:` evidence IDs are manifest-level IDs, not canonical line-range code evidence IDs, and the generated research outputs explicitly stop short of full code, framework, and recent-paper research.

## Findings

1. Phase 2 implementation surface now exists.

   Present files/directories include `stable_core/evidence`, `research_tools`, `evidence/registry.jsonl`, all required top-level research outputs, both Phase 2 test files, and updated CLI wiring in `stable_core/cli.py`.

2. Evidence schema and uniqueness are partially validated and persisted records are clean.

   `stable_core/evidence/registry.py` defines `EvidenceRecord`, validates non-empty `evidence_id`, allowed `source_type`, confidence range, and rejects duplicate IDs on append. `evidence/registry.jsonl` contains 17 parseable records, 17 unique IDs, no duplicate IDs, and no missing required top-level fields or locator keys in the stored data.

   Remaining gap: the implementation does not enforce canonical evidence ID patterns or `claim_scope` membership. All 17 stored `code:` IDs use manifest-level form such as `code:01_POPE:<commit>:MANIFEST.tsv` rather than the spec's line-range form `code:<baseline_id>:<commit>:<path>:L<start>-L<end>`, and their locator line fields are `null`.

3. CLI behavior is present for required Phase 2 commands.

   `stable_core/cli.py` registers `evidence init`, `evidence add`, `evidence list`, `index-baselines`, and `research-status`. Read-only CLI checks succeeded: `evidence list --registry evidence/registry.jsonl` returned status `passed` with count `17`, and `research-status` returned status `needs_attention` with baseline matrix and evidence registry marked `passed`.

4. Generated research reports avoid fabricated research.

   `docs/research/baseline_code_structure_matrix.tsv` indexes 17 baselines and marks code-path details as `needs_code_survey`. `reusable_patterns.md` states it is manifest-level only. `anti_patterns.md` says confirmed code anti-patterns are not claimed. `framework_reference_report.md` says external framework research is not complete and claims no findings. This is conservative and avoids fabricated research.

5. Recent paper research is correctly marked unfinished, but the phase is not complete.

   `docs/research/recent_paper_research.needs_attention.md` explicitly says no 2024-2026 recent-paper search was executed. This satisfies the “real or clearly marked needs_attention” safety requirement, but means Phase 2 should remain `needs_attention` until real paper research and code-span evidence are added.

## Test/Verification Notes

Read-only commands executed:

- file presence and safe-file listing under the allowed paths
- source inspection of `stable_core/evidence/registry.py`, `research_tools/baseline_indexer.py`, `stable_core/cli.py`, and the two Phase 2 test files
- structured JSONL validation of `evidence/registry.jsonl`
- `PYTHONDONTWRITEBYTECODE=1 python -m stable_core.cli evidence list --registry evidence/registry.jsonl`
- `PYTHONDONTWRITEBYTECODE=1 python -m stable_core.cli research-status`
- CLI help inspection for top-level and `evidence` subcommands

The pytest suite was not executed because this task was read-only and `tests/test_research_indexing.py` includes a CLI test that writes generated research artifacts and `evidence/registry.jsonl` in the repository default locations.

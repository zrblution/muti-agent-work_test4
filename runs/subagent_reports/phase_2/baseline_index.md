# BaselineIndexAgent Phase 2 Report

Status: NEEDS_ATTENTION - implementation now exists and passes manifest-level indexing checks, but it is not a full baseline code survey and its evidence IDs do not meet the code line-location form in the spec.

Report path: `/home/vepfs/data/work1/muti-agent-work_test4/runs/subagent_reports/phase_2/baseline_index.md`

## Scope

Read-only audit of the Phase 2 baseline indexing artifacts under:

`/home/vepfs/data/work1/muti-agent-work_test4`

Inspected only the allowed files:

- `docs/research/source_snapshots/baseline_MANIFEST.tsv`
- `docs/research/baseline_code_structure_matrix.tsv`
- `docs/research/reusable_patterns.md`
- `docs/research/anti_patterns.md`
- `evidence/registry.jsonl`
- `research_tools/__init__.py`
- `research_tools/baseline_indexer.py`
- `tests/test_research_indexing.py`

No large baseline code trees or PDFs were inspected.

## Validation Summary

### MANIFEST Snapshot

The server snapshot at `docs/research/source_snapshots/baseline_MANIFEST.tsv` exists and matches the local source manifest hash from the previous audit context.

- SHA-256: `c66541bec56f9fa80b4ae9aaed37450857d20868ab2df262e9f17f4cddc227d8`
- Lines: 18 total, including 1 header row and 17 data rows
- Parsed columns: 9 tab-separated fields
- Code snapshot rows: 10
- Paper-only rows: 7

### Baseline Matrix

`docs/research/baseline_code_structure_matrix.tsv` exists.

- Lines: 18 total, including 1 header row and 17 data rows
- Matrix baseline IDs exactly match the 17 MANIFEST baseline folders
- No extra matrix rows
- No missing matrix rows
- `has_code`, `repo_url`, and `clone_commit` values align with MANIFEST parsing
- All 10 code-available rows mark component path fields as `needs_code_survey`
- All 17 rows set `best_impl_base_for_new_ideas` to `unknown_until_code_survey`

The matrix clearly states that it is manifest-only and that full code structure survey is not completed.

### Reusable and Anti-Pattern Docs

`docs/research/reusable_patterns.md` exists and explicitly says it is generated from `MANIFEST.tsv` only, identifies candidate classes rather than audited implementation details, and requires code-path inspection before accepting patterns as reusable.

`docs/research/anti_patterns.md` exists and explicitly says Phase 2 does not claim confirmed anti-patterns from code inspection. It records a preliminary `metric_generation_coupling_risk` item with status `risk_to_check_in_code_survey`.

This is a clear representation of the lack of full code survey.

### Evidence Registry

`evidence/registry.jsonl` exists and is parseable JSONL.

- Records: 17
- Unique evidence IDs: 17
- Duplicate evidence IDs: 0
- Missing required top-level fields: 0
- Source type counts: `baseline_code=17`
- Claim scope counts: `implementation_pattern=17`

However, all evidence records are manifest-derived and use IDs like:

`code:01_POPE:08d957b917e5a378a2f99d35b6293c536a66298b:MANIFEST.tsv`

These IDs are unique but do not follow the spec's line-located code evidence form:

`code:<baseline_id>:<commit>:<path>:L<start>-L<end>`

All 17 `code:` evidence IDs lack `L<start>-L<end>` ranges. Seven paper-only rows are also represented as `source_type="baseline_code"` with no commit, which is acceptable only if interpreted as manifest availability evidence, not as surveyed baseline code evidence.

The registry contains no `external_framework` evidence. Therefore the broader evidence acceptance target of at least 5 framework evidence records is not met by this registry.

### Research Tools and Tests

`research_tools/baseline_indexer.py` exists and implements manifest parsing, matrix generation, preliminary research docs, evidence registry writing, and research status reporting.

`tests/test_research_indexing.py` exists and is no longer a placeholder. It tests:

- MANIFEST parsing
- generated matrix and evidence file creation
- CLI generation of required research artifacts
- research status reporting for unfinished paper research

The tests are meaningful for manifest-level indexing, but they do not assert line-located code evidence IDs, source-type separation for paper-only manifest evidence, or external framework evidence minimums.

## Findings

1. PASS: MANIFEST parsing and row counts are correct. The snapshot has 17 data rows, with 10 code snapshot rows and 7 paper-only rows, and the matrix has exactly the same 17 baseline IDs with no drift.
2. PASS: The generated matrix and markdown docs clearly disclose that the output is manifest-level only and that full baseline code survey has not been completed.
3. PARTIAL: The registry is valid JSONL with 17 unique evidence IDs and all required top-level fields, but every `code:` ID points to `MANIFEST.tsv` and lacks the spec's `:L<start>-L<end>` locator suffix.
4. PARTIAL: Seven paper-only baselines are stored as `source_type="baseline_code"` with no commit; this should not be treated as surveyed code evidence.
5. GAP: No `external_framework` evidence records are present, so the spec's broader evidence-registry acceptance target for framework evidence is still unmet.

## Final Verdict

The implementation is acceptable as a manifest-level baseline availability index and clearly prevents downstream agents from mistaking it for a full code survey. It should remain `NEEDS_ATTENTION` rather than `PASS` for the full research/evidence registry spec because code evidence is not line-located, paper-only entries are typed as `baseline_code`, and framework evidence is absent.

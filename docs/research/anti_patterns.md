# Anti-Patterns (Preliminary)

Phase 2 does not claim confirmed anti-patterns from code inspection.

## Anti-pattern: metric-generation coupling risk

- anti_pattern_id: anti_metric_generation_coupling_risk_001
- evidence_id: manifest-level entries in `evidence/registry.jsonl`
- why_bad: benchmark metric logic must remain inside BenchmarkAdapter and must not be mixed into model generation or idea plugins.
- status: risk_to_check_in_code_survey

#!/usr/bin/env python3
"""Compare multiple eval-run JSON result files and print a compact diff table.

Usage:
    python3 compare-eval-runs.py baseline.json hierarchy.json coarse2fine.json combined.json

Each file is expected to contain an object with a "results" key whose value is
a list of per-case result dicts (same format as produced by
tests/eval/test_retrieval.py with --eval-output).
"""

# Compare multiple eval-run JSON result files and print a compact diff table.
# Usage: uv run python3 scripts/compare-eval-runs.py baseline.json hierarchy.json ...

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


def load_results(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unexpected result format in {path}")


@dataclass
class _SimpleMetrics:
    total_cases: int = 0
    passed_cases: int = 0
    pass_rate: float = 0.0
    recall_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    citation_accuracy: float = 0.0
    no_answer_accuracy: float = 0.0
    unauthorized_leakage_count: int = 0
    anchor_accuracy: float = 1.0
    expansion_coverage: float = 0.0
    expansion_cases_total: int = 0
    expansion_cases_passed: int = 0
    latency_ms_by_stage: dict[str, list[float]] = field(default_factory=dict)


def compute_metrics(results: list[dict]) -> _SimpleMetrics:
    ks = [1, 3, 5, 10]
    recall_sums = dict.fromkeys(ks, 0.0)
    mrr_sum = 0.0
    citation_acc_sum = 0.0
    citation_cases = 0
    no_answer_correct = 0
    no_answer_cases = 0
    leakage = 0
    anchor_total = 0
    anchor_passed = 0
    expansion_total = 0
    expansion_passed = 0
    latency: dict[str, list[float]] = {}

    for r in results:
        retrieved = r.get("retrieved_ids", [])
        gold = set(r.get("gold_ids", []))
        cited = r.get("cited_ids", [])

        if gold:
            for k in ks:
                top_k = set(retrieved[:k])
                recall_sums[k] += len(top_k & gold) / len(gold)
            for rank, doc_id in enumerate(retrieved, 1):
                if doc_id in gold:
                    mrr_sum += 1.0 / rank
                    break
            cited_set = set(cited)
            citation_acc_sum += 1.0 if (cited_set & gold) else 0.0
            citation_cases += 1

        if r.get("expected_no_answer"):
            no_answer_cases += 1
            if not r.get("has_answer"):
                no_answer_correct += 1

        leakage += len(r.get("unauthorized_docs_cited", []))

        am = r.get("anchor_matched")
        if am is not None:
            anchor_total += 1
            if am:
                anchor_passed += 1

        if r.get("expansion_eligible"):
            expansion_total += 1
            if r.get("expansion_applied"):
                expansion_passed += 1

        for stage, ms in r.get("latency_by_stage", {}).items():
            latency.setdefault(stage, []).append(ms)

    n = len(results) or 1
    m = _SimpleMetrics(total_cases=len(results))
    m.passed_cases = sum(1 for r in results if r.get("passed"))
    m.pass_rate = m.passed_cases / n
    m.recall_at_k = {k: recall_sums[k] / n for k in ks}
    m.mrr = mrr_sum / n
    m.citation_accuracy = citation_acc_sum / (citation_cases or 1)
    m.no_answer_accuracy = no_answer_correct / (no_answer_cases or 1)
    m.unauthorized_leakage_count = leakage
    m.anchor_accuracy = anchor_passed / anchor_total if anchor_total else 1.0
    m.expansion_coverage = expansion_passed / expansion_total if expansion_total else 0.0
    m.expansion_cases_total = expansion_total
    m.expansion_cases_passed = expansion_passed
    m.latency_ms_by_stage = latency
    return m


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <baseline.json> <run2.json> [run3.json ...]")
        sys.exit(1)

    paths = sys.argv[1:]
    names = [Path(p).stem.replace("results-", "") for p in paths]

    all_results = [load_results(p) for p in paths]
    case_ids: list[str] = []
    seen: set[str] = set()
    for results in all_results:
        for r in results:
            cid = str(r["id"])
            if cid not in seen:
                case_ids.append(cid)
                seen.add(cid)

    # Per-case pass/fail comparison
    print("=== Per-case pass/fail comparison ===\n")
    print(f"Configurations: {', '.join(names)}")
    print(f"Unique case IDs: {len(case_ids)}")
    print(f"Cases per run: {[len(r) for r in all_results]}\n")

    if case_ids:
        col_width = max(14, max(len(n) for n in names) + 2)
        header = f"{'Case':<14} | " + " | ".join(f"{n:<{col_width}}" for n in names)
        print(header)
        print("-" * len(header))
        for cid in case_ids:
            row = [f"{cid:<14}"]
            for results in all_results:
                by_id = {str(r["id"]): r for r in results}
                case = by_id.get(cid, {})
                if not case:
                    row.append(f"{'MISSING':<{col_width}}")
                elif case.get("passed"):
                    row.append(f"{'PASS':<{col_width}}")
                else:
                    en = case.get("expected_no_answer", False)
                    ha = case.get("has_answer", False)
                    if en and ha:
                        reason = "no-answer-fail"
                    elif not en and not ha:
                        reason = "has-answer-fail"
                    else:
                        reason = "retrieval-fail"
                    row.append(f"{'FAIL:' + reason:<{col_width}}")
            print(" | ".join(row))
    else:
        print("No case IDs found in results.")

    # Aggregate metrics
    print("\n\n=== Aggregate metrics ===\n")
    metrics_list = [compute_metrics(results) for results in all_results]

    metric_defs = [
        ("total_cases", "Total cases", False),
        ("passed_cases", "Passed", False),
        ("pass_rate", "Pass rate", True),
        ("mrr", "MRR", True),
        ("citation_accuracy", "Citation acc", True),
        ("no_answer_accuracy", "No-answer acc", True),
        ("unauthorized_leakage_count", "Leakage count", False),
        ("anchor_accuracy", "Anchor acc", True),
        ("expansion_coverage", "Expansion cov", True),
    ]

    for attr, label, is_float in metric_defs:
        vals = []
        for m in metrics_list:
            v = getattr(m, attr)
            if is_float:
                vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        print(f"  {label:<20} | " + " | ".join(f"{v:<20}" for v in vals))

    if any(m.expansion_cases_total for m in metrics_list):
        print(
            f"\n  {'Expansion total':<20} | "
            + " | ".join(f"{m.expansion_cases_total:<20}" for m in metrics_list)
        )
        print(
            f"  {'Expansion passed':<20} | "
            + " | ".join(f"{m.expansion_cases_passed:<20}" for m in metrics_list)
        )

    # Latency
    print("\n=== Latency (ms) by stage ===\n")
    all_stages: set[str] = set()
    for m in metrics_list:
        all_stages.update(m.latency_ms_by_stage.keys())
    for stage in sorted(all_stages):
        line = f"  {stage:<25} | "
        for m in metrics_list:
            vals = m.latency_ms_by_stage.get(stage, [])
            if vals:
                avg = sum(vals) / len(vals)
                line += f"{avg:<10.1f}         "
            else:
                line += f"{'N/A':<20}"
            if m != metrics_list[-1]:
                line += " | "
        print(line)

    print("\n=== Legend ===")
    for name, path in zip(names, paths, strict=True):
        print(f"  {name:<20} {path}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()

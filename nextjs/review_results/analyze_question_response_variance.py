#!/usr/bin/env python3
"""Compute per-user question response-ratio mean and variance.

The workbook is produced from review_annotations.csv by build_user_review_workbook.py.
This script reads the workbook's main_node_summary sheet so Q6/Q7/Q8 applicability
matches the existing analysis logic.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from analyze_user_review_workbook import (  # noqa: E402
    QUESTION_COLUMNS,
    QUESTION_NAMES,
    YES,
    read_workbook,
    severity,
    severity_label,
    user_sort_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workbook",
        nargs="?",
        default="review_annotations_user_review_workbook_latest.xlsx",
        help="Workbook generated from review_annotations.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default="question_response_variance",
        help="Directory for CSV outputs.",
    )
    return parser.parse_args()


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return SCRIPT_DIR / path


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def variance_population(values: list[float]) -> float:
    if not values:
        return 0.0
    m = mean(values)
    return sum((value - m) ** 2 for value in values) / len(values)


def variance_sample(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sum((value - m) ** 2 for value in values) / (len(values) - 1)


def round_float(value: float, digits: int = 8) -> float:
    return round(float(value), digits)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def collect_counts(main_rows: list[dict[str, str]]) -> tuple[dict, dict]:
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    totals = defaultdict(lambda: defaultdict(Counter))

    for row in main_rows:
        reviewer = row.get("id", "")
        if not reviewer:
            continue

        for slot, column in QUESTION_COLUMNS.items():
            answer = row.get(column, "")
            if answer:
                counts["all_answers"][reviewer][slot][answer] += 1
                totals["all_answers"][reviewer][slot] += 1

        if row.get("answer_q1_label") == YES:
            for slot, column in QUESTION_COLUMNS.items():
                if slot == "Q1":
                    continue
                answer = row.get(column, "")
                if answer:
                    counts["q1_yes_only"][reviewer][slot][answer] += 1
                    totals["q1_yes_only"][reviewer][slot] += 1

    return counts, totals


def answer_sets_for_scope(counts: dict, scope: str) -> dict[str, list[str]]:
    answer_sets = defaultdict(set)
    for reviewer_slots in counts.get(scope, {}).values():
        for slot, counter in reviewer_slots.items():
            answer_sets[slot].update(counter)
    return {slot: sorted(answers, key=lambda answer: (severity(slot, answer), answer)) for slot, answers in answer_sets.items()}


def build_user_answer_ratio_rows(counts: dict, totals: dict, users: list[str]) -> list[dict[str, Any]]:
    rows = []
    for scope in ["all_answers", "q1_yes_only"]:
        answer_sets = answer_sets_for_scope(counts, scope)
        for slot in sorted(answer_sets):
            for reviewer in users:
                total = totals[scope][reviewer][slot]
                if total <= 0:
                    continue
                for answer in answer_sets[slot]:
                    count = counts[scope][reviewer][slot][answer]
                    ratio = count / total
                    rows.append({
                        "scope": scope,
                        "reviewer_id": reviewer,
                        "question": slot,
                        "question_name": QUESTION_NAMES[slot],
                        "answer": answer,
                        "severity": severity_label(severity(slot, answer)),
                        "response_count": count,
                        "question_total": total,
                        "ratio": round_float(ratio),
                        "pct": round_float(ratio * 100, 4),
                    })
    return rows


def build_answer_stat_rows(counts: dict, totals: dict, users: list[str]) -> list[dict[str, Any]]:
    rows = []
    for scope in ["all_answers", "q1_yes_only"]:
        answer_sets = answer_sets_for_scope(counts, scope)
        for slot in sorted(answer_sets):
            active_users = [user for user in users if totals[scope][user][slot] > 0]
            for answer in answer_sets[slot]:
                ratios = [
                    counts[scope][user][slot][answer] / totals[scope][user][slot]
                    for user in active_users
                ]
                total_count = sum(counts[scope][user][slot][answer] for user in active_users)
                total_denominator = sum(totals[scope][user][slot] for user in active_users)
                pop_var = variance_population(ratios)
                sample_var = variance_sample(ratios)
                rows.append({
                    "scope": scope,
                    "question": slot,
                    "question_name": QUESTION_NAMES[slot],
                    "answer": answer,
                    "severity": severity_label(severity(slot, answer)),
                    "users": len(active_users),
                    "total_count": total_count,
                    "total_responses": total_denominator,
                    "pooled_ratio": round_float(total_count / total_denominator if total_denominator else 0.0),
                    "mean_ratio": round_float(mean(ratios)),
                    "variance_ratio_population": round_float(pop_var),
                    "variance_ratio_sample": round_float(sample_var),
                    "stddev_ratio_population": round_float(math.sqrt(pop_var)),
                    "mean_pct": round_float(mean(ratios) * 100, 4),
                    "variance_pct_population": round_float(pop_var * 10000, 6),
                    "stddev_pct_population": round_float(math.sqrt(pop_var) * 100, 4),
                    "min_pct": round_float(min(ratios) * 100 if ratios else 0.0, 4),
                    "max_pct": round_float(max(ratios) * 100 if ratios else 0.0, 4),
                })
    return rows


def build_severity_stat_rows(counts: dict, totals: dict, users: list[str]) -> list[dict[str, Any]]:
    rows = []
    for scope in ["all_answers", "q1_yes_only"]:
        slots = sorted({slot for reviewer_slots in counts.get(scope, {}).values() for slot in reviewer_slots})
        for slot in slots:
            active_users = [user for user in users if totals[scope][user][slot] > 0]
            for level in [-1, 0, 1, 2]:
                ratios = []
                total_count = 0
                total_denominator = 0
                for user in active_users:
                    denominator = totals[scope][user][slot]
                    level_count = sum(
                        count
                        for answer, count in counts[scope][user][slot].items()
                        if severity(slot, answer) == level
                    )
                    ratios.append(level_count / denominator)
                    total_count += level_count
                    total_denominator += denominator
                pop_var = variance_population(ratios)
                rows.append({
                    "scope": scope,
                    "question": slot,
                    "question_name": QUESTION_NAMES[slot],
                    "severity": severity_label(level),
                    "severity_level": level,
                    "users": len(active_users),
                    "total_count": total_count,
                    "total_responses": total_denominator,
                    "pooled_ratio": round_float(total_count / total_denominator if total_denominator else 0.0),
                    "mean_ratio": round_float(mean(ratios)),
                    "variance_ratio_population": round_float(pop_var),
                    "variance_ratio_sample": round_float(variance_sample(ratios)),
                    "stddev_ratio_population": round_float(math.sqrt(pop_var)),
                    "mean_pct": round_float(mean(ratios) * 100, 4),
                    "variance_pct_population": round_float(pop_var * 10000, 6),
                    "stddev_pct_population": round_float(math.sqrt(pop_var) * 100, 4),
                    "min_pct": round_float(min(ratios) * 100 if ratios else 0.0, 4),
                    "max_pct": round_float(max(ratios) * 100 if ratios else 0.0, 4),
                })
    return rows


def main() -> None:
    args = parse_args()
    workbook = resolve_path(args.workbook)
    output_dir = resolve_path(args.output_dir)

    sheets = read_workbook(workbook)
    main_rows = sheets.get("main_node_summary") or sheets.get("main_node_rows") or []
    if not main_rows:
        raise SystemExit(f"No main_node_summary rows found in {workbook}")

    users = sorted({row.get("id", "") for row in main_rows if row.get("id", "")}, key=user_sort_key)
    counts, totals = collect_counts(main_rows)

    user_ratio_rows = build_user_answer_ratio_rows(counts, totals, users)
    answer_stat_rows = build_answer_stat_rows(counts, totals, users)
    severity_stat_rows = build_severity_stat_rows(counts, totals, users)

    write_csv(output_dir / "user_question_answer_ratios.csv", user_ratio_rows)
    write_csv(output_dir / "question_answer_ratio_stats.csv", answer_stat_rows)
    write_csv(output_dir / "question_severity_ratio_stats.csv", severity_stat_rows)

    print(f"Workbook: {workbook}")
    print(f"Users: {len(users)}")
    print(f"Node rows: {len(main_rows)}")
    print(f"Wrote: {output_dir / 'user_question_answer_ratios.csv'}")
    print(f"Wrote: {output_dir / 'question_answer_ratio_stats.csv'}")
    print(f"Wrote: {output_dir / 'question_severity_ratio_stats.csv'}")


if __name__ == "__main__":
    main()

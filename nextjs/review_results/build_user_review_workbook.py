#!/usr/bin/env python3
"""Rebuild the user review workbook from review_annotations_v*.csv exports.

This script was reconstructed from review_annotations_v12_user_review_workbook.xlsx.
It uses only the Python standard library so it can run on future v13/v14 exports
without installing Excel packages.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
USER_RE = re.compile(r"^user\d+$")

QUESTION_SLOTS = [
    ("Q1", "label"),
    ("Q2", "mask_missing"),
    ("Q3", "mask_extra"),
    ("Q4", "instance"),
    ("Q5", "mask_quality"),
    ("Q6", "decomposition"),
    ("Q7", "missing_child"),
    ("Q8", "leaf_stop"),
]

GOOD = {
    "Q1": {"\uc608"},  # 예, 맞음
    "Q2": {"\ubaa8\ub450 \ud3ec\ud568\ud568"},  # 모두 포함함
    "Q3": {"\ud3ec\ud568\ud558\uc9c0 \uc54a\uc74c"},  # 포함하지 않음
    "Q4": {"\uc815\ud655"},  # 정확
    "Q5": {"\uc815\ud655"},  # 정확
    "Q6": {"\uc5c6\uc74c"},  # 없음
    "Q7": {"\uc5c6\uc74c"},  # 없음
    "Q8": {"\uc608"},  # 예
}

SOFT = {
    "Q1": {"\ud310\ub2e8\ubd88\uac00"},  # 판단불가
    "Q2": {"\uc57d\uac04 \ub193\uce68", "\ud310\ub2e8\ubd88\uac00"},  # 약간 놓침, 판단불가
    "Q3": {"\uc57d\uac04 \ud3ec\ud568", "\ud310\ub2e8\ubd88\uac00"},  # 약간 포함, 판단불가
    "Q4": {"\uc218\uc6a9 \uac00\ub2a5", "\ud310\ub2e8\ubd88\uac00"},  # 수용 가능, 판단불가
    "Q5": {"\uc218\uc6a9 \uac00\ub2a5", "\ud310\ub2e8\ubd88\uac00"},  # 수용 가능, 판단불가
    "Q6": {"\uc870\uae08 \uc788\uc74c", "\ud310\ub2e8\ubd88\uac00"},  # 조금 있음, 판단불가
    "Q7": {"\uc870\uae08 \uc788\uc74c", "\ud310\ub2e8\ubd88\uac00"},  # 조금 있음, 판단불가
    "Q8": {"\ud310\ub2e8\ubd88\uac00"},  # 판단불가
}

CRITICAL = {
    "Q1": {"\uc544\ub2c8\uc624"},  # 아니오, 아님
    "Q2": {"\ub9ce\uc774 \ub193\uce68"},  # 많이 놓침
    "Q3": {"\ub9ce\uc774 \ud3ec\ud568"},  # 많이 포함
    "Q4": {"\ubd80\uc815\ud655", "\uc2e4\ud328"},  # 부정확, 실패
    "Q5": {"\ubd80\uc815\ud655", "\uc2e4\ud328"},  # 부정확, 실패
    "Q6": {"\ub9ce\uc774 \uc788\uc74c"},  # 많이 있음
    "Q7": {"\ub9ce\uc774 \uc788\uc74c"},  # 많이 있음
    "Q8": {"\uc544\ub2c8\uc624"},  # 아니오
}

MAIN_NODE_COLUMNS = [
    "id",
    "image_id",
    "path_label",
    "label",
    "depth",
    "is_leaf",
    "child_count",
    "bbox_pct",
    "bbox_size",
    "instance_count",
    "answer_q1_label",
    "answer_q2_mask_missing",
    "answer_q3_mask_extra",
    "answer_q4_instance",
    "answer_q5_mask_quality",
    "answer_q6_decomposition_nonleaf",
    "answer_q7_missing_child_nonleaf",
    "answer_q8_leaf_stop",
]


def raise_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", nargs="?", help="review_annotations_v*.csv")
    parser.add_argument("--manifest", default="image_manifest.csv")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def version_number(path: Path) -> int:
    match = re.search(r"review_annotations_v(\d+)\.csv$", path.name)
    return int(match.group(1)) if match else -1


def latest_input() -> Path:
    final_csv = Path("review_annotations.csv")
    if final_csv.exists():
        return final_csv
    candidates = sorted(Path(".").glob("review_annotations_v*.csv"), key=lambda p: (version_number(p), p.stat().st_mtime), reverse=True)
    if not candidates:
        raise FileNotFoundError("No review_annotations.csv or review_annotations_v*.csv found.")
    return candidates[0]


def safe_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_kst(value: str | None) -> str:
    dt = parse_dt(value)
    return dt.astimezone(KST).isoformat() if dt else ""


def date_kst(value: str | None) -> str:
    dt = parse_dt(value)
    return dt.astimezone(KST).date().isoformat() if dt else ""


def answer_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(map(str, value))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def has_answer(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def label_from_node(node_id: str) -> str:
    return str(node_id or "").split("__")[-1]


def path_label(node_id: str) -> str:
    parts = str(node_id or "").split("__")
    if parts and parts[0] == "root":
        parts = parts[1:]
    return "/".join(parts)


def depth(node_id: str) -> int:
    parts = [p for p in str(node_id or "").split("__") if p]
    return max(len(parts) - 1, 0)


def top_label(node_id: str) -> str:
    parts = str(node_id or "").split("__")
    return parts[1] if len(parts) > 1 and parts[0] == "root" else label_from_node(node_id)


def parent_from_path(node_id: str) -> str:
    parts = str(node_id or "").split("__")
    if len(parts) <= 2:
        return "root"
    return "__".join(parts[:-1])


def pct(n: float, d: float) -> float | str:
    return round((n / d) * 100, 2) if d else ""


def mean(values: list[float]) -> float | str:
    return round(sum(values) / len(values), 6) if values else ""


def bbox_metrics(node: dict[str, Any], image_area: float | None) -> tuple[Any, Any, Any, Any, str]:
    bbox = node.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return "", "", "", "", "missing"
    try:
        x1, y1, x2, y2 = [float(x) for x in bbox]
    except (TypeError, ValueError):
        return "", "", "", "", "missing"
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)
    area = w * h
    area_pct = round((area / image_area) * 100, 2) if image_area else ""
    if area_pct == "":
        bucket = "missing"
    elif area_pct < 0.1:
        bucket = "small"
    elif area_pct < 1:
        bucket = "small"
    elif area_pct < 5:
        bucket = "medium"
    else:
        bucket = "large"
    return int(w), int(h), int(area), area_pct, bucket


def severity(slot: str, value: str) -> int:
    if not value:
        return 0
    if value in CRITICAL.get(slot, set()):
        return 2
    if value in SOFT.get(slot, set()):
        return 1
    if slot in GOOD and value not in GOOD[slot]:
        return 1
    return 0


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            nodes = safe_json(row.get("nodes"), {})
            actual_nodes = safe_json(row.get("actual_nodes"), [])
            full_size = safe_json(row.get("full_size"), [])
            image_area = None
            if isinstance(full_size, list) and len(full_size) == 2:
                try:
                    image_area = float(full_size[0]) * float(full_size[1])
                except (TypeError, ValueError):
                    image_area = None
            out[str(row.get("image_id", ""))] = {
                "nodes": nodes if isinstance(nodes, dict) else {},
                "actual_nodes": actual_nodes if isinstance(actual_nodes, list) else [],
                "image_area": image_area,
            }
    return out


def load_annotations(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows = []
    reviewers = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            reviewer = str(row.get("reviewer_id", ""))
            reviewers.append(reviewer)
            if not USER_RE.match(reviewer):
                continue
            payload = safe_json(row.get("payload"), {})
            if isinstance(payload, dict):
                rows.append({"reviewer_id": reviewer, "payload": payload, "updated_at": row.get("updated_at", "")})
    return rows, reviewers


def applicable_answers(answers: dict[str, str], is_leaf: bool) -> tuple[list[tuple[str, str, str]], str]:
    slots = [
        ("Q1", "label", answers.get("label", "")),
        ("Q2", "mask_missing", answers.get("mask_missing", "")),
        ("Q3", "mask_extra", answers.get("mask_extra", "")),
        ("Q4", "instance", answers.get("instance", "")),
        ("Q5", "mask_quality", answers.get("mask_quality", "")),
    ]
    leaf_source = ""
    if is_leaf:
        value = answers.get("decomposition", "") or answers.get("missing_child", "")
        if answers.get("decomposition", ""):
            leaf_source = "decomposition"
        elif answers.get("missing_child", ""):
            leaf_source = "missing_child"
        slots.append(("Q8", "leaf_stop", value))
    else:
        slots.extend([
            ("Q6", "decomposition", answers.get("decomposition", "")),
            ("Q7", "missing_child", answers.get("missing_child", "")),
        ])
    return slots, leaf_source


def build_rows(input_csv: Path, manifest: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    annotation_rows, source_reviewers = load_annotations(input_csv)
    main_rows = []
    tree_rows = []

    for reviewer_row in annotation_rows:
        reviewer = reviewer_row["reviewer_id"]
        for image_id, image_payload in (reviewer_row["payload"] or {}).items():
            image_id = str(image_id)
            image_meta = manifest.get(image_id, {})
            manifest_nodes = image_meta.get("nodes", {})
            image_area = image_meta.get("image_area")
            nodes_payload = (image_payload or {}).get("nodes") or {}
            if isinstance(nodes_payload, dict):
                for node_id, node_payload in nodes_payload.items():
                    node_id = str(node_id)
                    raw_answers = (node_payload or {}).get("answers") or {}
                    answers = {k: answer_value(v) for k, v in raw_answers.items() if has_answer(v)}
                    if not any(k in answers for k in ["label", "mask_missing", "mask_extra", "instance", "mask_quality", "decomposition", "missing_child"]):
                        continue

                    node_meta = manifest_nodes.get(node_id, {}) if isinstance(manifest_nodes, dict) else {}
                    children = node_meta.get("children") if isinstance(node_meta, dict) else []
                    if not isinstance(children, list):
                        children = []
                    is_leaf = len(children) == 0
                    parent_id = node_meta.get("parent") or parent_from_path(node_id)
                    label = node_meta.get("label") or label_from_node(node_id)
                    w, h, area, area_pct, area_bucket = bbox_metrics(node_meta if isinstance(node_meta, dict) else {}, image_area)
                    slots, leaf_source = applicable_answers(answers, is_leaf)
                    answered = [(slot, qid, val) for slot, qid, val in slots if val]
                    critical_questions = []
                    soft_questions = []
                    issue_score = 0
                    for slot, qid, val in answered:
                        sev = severity(slot, val)
                        issue_score += sev
                        if sev >= 2:
                            critical_questions.append(f"{slot}_{qid}")
                        elif sev == 1:
                            soft_questions.append(f"{slot}_{qid}")

                    row = {
                        "reviewer_id": reviewer,
                        "id": reviewer,
                        "image_id": image_id,
                        "node_id": node_id,
                        "path_label": path_label(node_id),
                        "label": label,
                        "top_level_label": top_label(node_id),
                        "depth": depth(node_id),
                        "is_leaf": str(is_leaf),
                        "child_count": len(children),
                        "bbox_pct": area_pct,
                        "bbox_size": area_bucket,
                        "instance_count": len(node_meta.get("instance_paths") or []) if isinstance(node_meta, dict) else "",
                        "applicable_question_count": len(slots),
                        "answered_question_count": len(answered),
                        "question_completion_pct": pct(len(answered), len(slots)),
                        "answered_question_slots": "|".join(slot for slot, _, _ in answered),
                        "critical_issue_question_count": len(critical_questions),
                        "soft_issue_question_count": len(soft_questions),
                        "critical": len(critical_questions),
                        "soft": len(soft_questions),
                        "issue_score": issue_score,
                        "has_critical_issue": str(bool(critical_questions)),
                        "has_any_issue": str(bool(critical_questions or soft_questions)),
                        "critical_issue_questions": "|".join(critical_questions),
                        "soft_issue_questions": "|".join(soft_questions),
                        "answer_q1_label": answers.get("label", ""),
                        "answer_q2_mask_missing": answers.get("mask_missing", ""),
                        "answer_q3_mask_extra": answers.get("mask_extra", ""),
                        "answer_q4_instance": answers.get("instance", ""),
                        "answer_q5_mask_quality": answers.get("mask_quality", ""),
                        "answer_q6_decomposition_nonleaf": "" if is_leaf else answers.get("decomposition", ""),
                        "answer_q7_missing_child_nonleaf": "" if is_leaf else answers.get("missing_child", ""),
                        "answer_q8_leaf_stop": (answers.get("decomposition", "") or answers.get("missing_child", "")) if is_leaf else "",
                        "leaf_q8_source": leaf_source,
                    }
                    main_rows.append(row)

            tree_summary = (image_payload or {}).get("tree_summary") or {}
            tree_answers = tree_summary.get("answers") or {}
            tree_answers = {k: answer_value(v) for k, v in tree_answers.items() if has_answer(v)}
            if tree_answers:
                tree_rows.append({
                    "id": reviewer,
                    "reviewer_id": reviewer,
                    "image_id": image_id,
                    "answer_overall_consistency": tree_answers.get("overall_consistency", ""),
                    "answer_missing_critical_nodes": tree_answers.get("missing_critical_nodes", ""),
                    "answer_summary_comment": tree_answers.get("summary_comment", ""),
                })

    main_rows.sort(key=lambda r: (r["reviewer_id"], r["image_id"], r["node_id"]))
    tree_rows.sort(key=lambda r: (r["reviewer_id"], r["image_id"]))
    return summarize(main_rows, tree_rows, input_csv, source_reviewers)


def summarize(main_rows: list[dict[str, Any]], tree_rows: list[dict[str, Any]], input_csv: Path, source_reviewers: list[str]) -> dict[str, list[dict[str, Any]]]:
    by_user = defaultdict(list)
    by_user_image = defaultdict(list)
    by_question_user = defaultdict(Counter)
    by_question = defaultdict(Counter)
    by_question_user_q1_yes = defaultdict(Counter)
    by_question_q1_yes = defaultdict(Counter)
    by_label = defaultdict(list)
    by_node = defaultdict(list)
    chart_data = []
    for row in main_rows:
        by_user[row["reviewer_id"]].append(row)
        by_user_image[(row["reviewer_id"], row["image_id"])].append(row)
        by_label[row["label"]].append(row)
        by_node[(row["image_id"], row["node_id"])].append(row)
        values = {
            "Q1": row["answer_q1_label"],
            "Q2": row["answer_q2_mask_missing"],
            "Q3": row["answer_q3_mask_extra"],
            "Q4": row["answer_q4_instance"],
            "Q5": row["answer_q5_mask_quality"],
            "Q6": row["answer_q6_decomposition_nonleaf"],
            "Q7": row["answer_q7_missing_child_nonleaf"],
            "Q8": row["answer_q8_leaf_stop"],
        }
        for slot, value in values.items():
            if value:
                by_question_user[(row["reviewer_id"], slot)][value] += 1
                by_question[slot][value] += 1
        if row["answer_q1_label"] == "\uc608":
            for slot, value in values.items():
                if slot == "Q1" or not value:
                    continue
                by_question_user_q1_yes[(row["reviewer_id"], slot)][value] += 1
                by_question_q1_yes[slot][value] += 1

    tree_by_user = Counter(row["reviewer_id"] for row in tree_rows)
    tree_keys = {(row["reviewer_id"], row["image_id"]) for row in tree_rows}
    tree_images_by_user = defaultdict(set)
    for row in tree_rows:
        tree_images_by_user[row["reviewer_id"]].add(row["image_id"])
    user_progress = []
    for reviewer, rows in sorted(by_user.items(), key=lambda item: user_sort_key(item[0])):
        applicable = sum(int(row["applicable_question_count"]) for row in rows)
        answered = sum(int(row["answered_question_count"]) for row in rows)
        critical = sum(row["has_critical_issue"] == "True" for row in rows)
        any_issue = sum(row["has_any_issue"] == "True" for row in rows)
        image_ids = {row["image_id"] for row in rows} | tree_images_by_user[reviewer]
        user_progress.append({
            "id": reviewer,
            "images_answered": len(image_ids),
            "nodes_answered": len(rows),
            "applicable_question_total": applicable,
            "answered_question_total": answered,
            "question_completion_pct": pct(answered, applicable),
            "tree_summaries_answered": tree_by_user[reviewer],
            "critical_issue_nodes": critical,
            "critical_issue_node_rate_pct": pct(critical, len(rows)),
            "any_issue_nodes": any_issue,
            "any_issue_node_rate_pct": pct(any_issue, len(rows)),
            "avg_issue_score": mean([float(row["issue_score"]) for row in rows]),
            "avg_depth": mean([float(row["depth"]) for row in rows]),
        })
        chart_data.append({"chart": "user_nodes", "reviewer_id": reviewer, "nodes_answered": len(rows)})

    user_image_summary = []
    image_keys = set(by_user_image) | tree_keys
    for reviewer, image_id in sorted(image_keys, key=lambda item: (user_sort_key(item[0]), item[1])):
        rows = by_user_image.get((reviewer, image_id), [])
        applicable = sum(int(row["applicable_question_count"]) for row in rows)
        answered = sum(int(row["answered_question_count"]) for row in rows)
        critical = sum(row["has_critical_issue"] == "True" for row in rows)
        any_issue = sum(row["has_any_issue"] == "True" for row in rows)
        user_image_summary.append({
            "reviewer_id": reviewer,
            "image_id": image_id,
            "nodes_answered": len(rows),
            "applicable_question_total": applicable,
            "answered_question_total": answered,
            "question_completion_pct": pct(answered, applicable),
            "critical_issue_nodes": critical,
            "critical_issue_node_rate_pct": pct(critical, len(rows)),
            "any_issue_nodes": any_issue,
            "any_issue_node_rate_pct": pct(any_issue, len(rows)),
            "avg_issue_score": mean([float(row["issue_score"]) for row in rows]),
            "avg_depth": mean([float(row["depth"]) for row in rows]),
            "has_tree_summary": str((reviewer, image_id) in tree_keys),
        })

    user_question_summary = []
    for (reviewer, slot), counter in sorted(by_question_user.items(), key=lambda item: (user_sort_key(item[0][0]), item[0][1])):
        total = sum(counter.values())
        most_answer, most_count = counter.most_common(1)[0]
        critical = sum(count for answer, count in counter.items() if severity(slot, answer) >= 2)
        soft = sum(count for answer, count in counter.items() if severity(slot, answer) == 1)
        user_question_summary.append({
            "reviewer_id": reviewer,
            "question_slot": slot,
            "response_count": total,
            "unique_answers": len(counter),
            "most_common_answer": most_answer,
            "most_common_answer_count": most_count,
            "critical_issue_responses": critical,
            "critical_issue_response_rate_pct": pct(critical, total),
            "soft_issue_responses": soft,
            "soft_issue_response_rate_pct": pct(soft, total),
        })

    user_question_q1_yes = []
    for (reviewer, slot), counter in sorted(by_question_user_q1_yes.items(), key=lambda item: (user_sort_key(item[0][0]), item[0][1])):
        total = sum(counter.values())
        most_answer, most_count = counter.most_common(1)[0]
        critical = sum(count for answer, count in counter.items() if severity(slot, answer) >= 2)
        soft = sum(count for answer, count in counter.items() if severity(slot, answer) == 1)
        user_question_q1_yes.append({
            "reviewer_id": reviewer,
            "question_slot": slot,
            "scope": "Q1_yes_only",
            "response_count": total,
            "unique_answers": len(counter),
            "most_common_answer": most_answer,
            "most_common_answer_count": most_count,
            "critical_issue_responses": critical,
            "critical_issue_response_rate_pct": pct(critical, total),
            "soft_issue_responses": soft,
            "soft_issue_response_rate_pct": pct(soft, total),
        })

    question_distribution = []
    for slot, counter in sorted(by_question.items()):
        total = sum(counter.values())
        for answer, count in sorted(counter.items(), key=lambda item: (severity(slot, item[0]), item[0])):
            question_distribution.append({
                "question_slot": slot,
                "answer_value": answer,
                "response_count": count,
                "question_total": total,
                "response_pct": pct(count, total),
                "severity_level": severity(slot, answer),
            })

    question_dist_q1_yes = []
    for slot, counter in sorted(by_question_q1_yes.items()):
        total = sum(counter.values())
        for answer, count in sorted(counter.items(), key=lambda item: (severity(slot, item[0]), item[0])):
            question_dist_q1_yes.append({
                "question_slot": slot,
                "scope": "Q1_yes_only",
                "answer_value": answer,
                "response_count": count,
                "question_total": total,
                "response_pct": pct(count, total),
                "severity_level": severity(slot, answer),
            })

    q1_filter_summary = []
    for reviewer, rows in sorted(by_user.items(), key=lambda item: user_sort_key(item[0])):
        q1_counts = Counter(row["answer_q1_label"] for row in rows)
        q1_yes_rows = [row for row in rows if row["answer_q1_label"] == "\uc608"]
        all_q2_q8 = 0
        q1_yes_q2_q8 = 0
        for row in rows:
            values = [
                row["answer_q2_mask_missing"],
                row["answer_q3_mask_extra"],
                row["answer_q4_instance"],
                row["answer_q5_mask_quality"],
                row["answer_q6_decomposition_nonleaf"],
                row["answer_q7_missing_child_nonleaf"],
                row["answer_q8_leaf_stop"],
            ]
            answered = sum(1 for value in values if value)
            all_q2_q8 += answered
            if row["answer_q1_label"] == "\uc608":
                q1_yes_q2_q8 += answered
        q1_filter_summary.append({
            "reviewer_id": reviewer,
            "total_nodes": len(rows),
            "q1_yes_nodes": len(q1_yes_rows),
            "q1_yes_node_pct": pct(len(q1_yes_rows), len(rows)),
            "q1_no_nodes": q1_counts["\uc544\ub2c8\uc624"],
            "q1_uncertain_nodes": q1_counts["\ud310\ub2e8\ubd88\uac00"],
            "q1_other_nodes": sum(count for answer, count in q1_counts.items() if answer not in {"\uc608", "\uc544\ub2c8\uc624", "\ud310\ub2e8\ubd88\uac00"}),
            "q2_to_q8_responses_all": all_q2_q8,
            "q2_to_q8_responses_q1_yes_only": q1_yes_q2_q8,
            "q2_to_q8_responses_excluded_by_q1": all_q2_q8 - q1_yes_q2_q8,
        })

    problem_labels = []
    for label, rows in by_label.items():
        critical = sum(row["has_critical_issue"] == "True" for row in rows)
        any_issue = sum(row["has_any_issue"] == "True" for row in rows)
        top = Counter(row["top_level_label"] for row in rows).most_common(1)[0][0]
        q_counter = Counter()
        for row in rows:
            for q in str(row["critical_issue_questions"]).split("|"):
                if q:
                    q_counter[q] += 1
        problem_labels.append({
            "label": label,
            "top_level_label": top,
            "node_rows": len(rows),
            "reviewer_count": len({row["reviewer_id"] for row in rows}),
            "image_count": len({row["image_id"] for row in rows}),
            "critical_issue_nodes": critical,
            "critical_issue_node_rate_pct": pct(critical, len(rows)),
            "any_issue_nodes": any_issue,
            "any_issue_node_rate_pct": pct(any_issue, len(rows)),
            "avg_issue_score": mean([float(row["issue_score"]) for row in rows]),
            "avg_depth": mean([float(row["depth"]) for row in rows]),
            "top_critical_issue_questions": "|".join(f"{k}:{v}" for k, v in q_counter.most_common(8)),
        })
    problem_labels.sort(key=lambda row: (float(row["critical_issue_node_rate_pct"] or 0), int(row["node_rows"])), reverse=True)
    for index, row in enumerate(problem_labels, start=1):
        row["rank_critical_issue_rate"] = index

    problem_nodes = []
    for (image_id, node_id), rows in by_node.items():
        first = rows[0]
        critical = sum(row["has_critical_issue"] == "True" for row in rows)
        any_issue = sum(row["has_any_issue"] == "True" for row in rows)
        problem_nodes.append({
            "image_id": image_id,
            "node_id": node_id,
            "path_label": first["path_label"],
            "label": first["label"],
            "top_level_label": first["top_level_label"],
            "depth": first["depth"],
            "is_leaf": first["is_leaf"],
            "node_rows": len(rows),
            "reviewer_count": len({row["reviewer_id"] for row in rows}),
            "critical_issue_nodes": critical,
            "critical_issue_node_rate_pct": pct(critical, len(rows)),
            "any_issue_nodes": any_issue,
            "any_issue_node_rate_pct": pct(any_issue, len(rows)),
            "avg_issue_score": mean([float(row["issue_score"]) for row in rows]),
        })
    problem_nodes.sort(key=lambda row: (float(row["critical_issue_node_rate_pct"] or 0), int(row["node_rows"])), reverse=True)
    for index, row in enumerate(problem_nodes, start=1):
        row["rank_critical_issue_rate"] = index

    column_guide = [{"field_name": col, "meaning": col.replace("_", " ")} for col in MAIN_NODE_COLUMNS]
    metadata = [
        {"metric": "generated_at_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"metric": "source_file", "value": str(input_csv.resolve())},
        {"metric": "main_node_summary_rows", "value": len(main_rows)},
        {"metric": "tree_summary_rows", "value": len(tree_rows)},
        {"metric": "included_reviewers", "value": "|".join(sorted(by_user, key=user_sort_key))},
        {"metric": "source_reviewers", "value": "|".join(source_reviewers)},
    ]
    graphs = [{"Review Graph Overview": "All chart source data is in chart_data."}]
    return {
        "main_node_summary": main_rows,
        "tree_summary": tree_rows,
        "user_progress": user_progress,
        "user_image_summary": user_image_summary,
        "user_question_summary": user_question_summary,
        "question_distribution": question_distribution,
        "q1_filter_summary": q1_filter_summary,
        "user_question_q1_yes": user_question_q1_yes,
        "question_dist_q1_yes": question_dist_q1_yes,
        "problem_labels": problem_labels,
        "problem_nodes": problem_nodes,
        "column_guide": column_guide,
        "metadata": metadata,
        "chart_data": chart_data,
        "graphs": graphs,
    }


def user_sort_key(user: str) -> tuple[int, str]:
    if user.startswith("user") and user[4:].isdigit():
        return int(user[4:]), user
    return 10**9, user


def xlsx_escape(value: Any) -> str:
    return str("" if value is None else value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def col_name(index: int) -> str:
    out = ""
    while index:
        index, r = divmod(index - 1, 26)
        out = chr(65 + r) + out
    return out


def is_number(value: Any, column: str) -> bool:
    if value in ("", None):
        return False
    if column.endswith("_id") or column in {"node_id", "image_id", "reviewer_id"}:
        return False
    if isinstance(value, (int, float)):
        return True
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", str(value)))


def cell(row: int, col: int, column: str, value: Any, header: bool = False) -> str:
    if value in ("", None):
        return ""
    ref = f"{col_name(col)}{row}"
    style = ' s="1"' if header else ""
    if not header and is_number(value, column):
        return f'<c r="{ref}"{style}><v>{xlsx_escape(value)}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{xlsx_escape(value)}</t></is></c>'


def columns_for(name: str, rows: list[dict[str, Any]]) -> list[str]:
    preferred = {
        "main_node_summary": MAIN_NODE_COLUMNS,
        "tree_summary": ["id", "image_id", "answer_overall_consistency", "answer_missing_critical_nodes", "answer_summary_comment"],
        "user_progress": ["id", "nodes_answered", "critical_issue_nodes", "critical_issue_node_rate_pct", "any_issue_nodes", "any_issue_node_rate_pct", "avg_issue_score", "avg_depth"],
        "user_image_summary": ["reviewer_id", "image_id", "nodes_answered", "applicable_question_total", "answered_question_total", "question_completion_pct", "critical_issue_nodes", "critical_issue_node_rate_pct", "any_issue_nodes", "any_issue_node_rate_pct", "avg_issue_score", "avg_depth", "has_tree_summary"],
        "user_question_summary": ["reviewer_id", "question_slot", "response_count", "unique_answers", "most_common_answer", "most_common_answer_count", "critical_issue_responses", "critical_issue_response_rate_pct", "soft_issue_responses", "soft_issue_response_rate_pct"],
        "question_distribution": ["question_slot", "answer_value", "response_count", "question_total", "response_pct", "severity_level"],
        "q1_filter_summary": ["reviewer_id", "total_nodes", "q1_yes_nodes", "q1_yes_node_pct", "q1_no_nodes", "q1_uncertain_nodes", "q1_other_nodes", "q2_to_q8_responses_all", "q2_to_q8_responses_q1_yes_only", "q2_to_q8_responses_excluded_by_q1"],
        "user_question_q1_yes": ["reviewer_id", "question_slot", "scope", "response_count", "unique_answers", "most_common_answer", "most_common_answer_count", "critical_issue_responses", "critical_issue_response_rate_pct", "soft_issue_responses", "soft_issue_response_rate_pct"],
        "question_dist_q1_yes": ["question_slot", "scope", "answer_value", "response_count", "question_total", "response_pct", "severity_level"],
        "problem_labels": ["rank_critical_issue_rate", "label", "top_level_label", "node_rows", "reviewer_count", "image_count", "critical_issue_nodes", "critical_issue_node_rate_pct", "any_issue_nodes", "any_issue_node_rate_pct", "avg_issue_score", "avg_depth", "top_critical_issue_questions"],
        "problem_nodes": ["rank_critical_issue_rate", "image_id", "node_id", "path_label", "label", "top_level_label", "depth", "is_leaf", "node_rows", "reviewer_count", "critical_issue_nodes", "critical_issue_node_rate_pct", "any_issue_nodes", "any_issue_node_rate_pct", "avg_issue_score"],
        "column_guide": ["field_name", "meaning"],
        "metadata": ["metric", "value"],
    }.get(name, [])
    cols = list(preferred)
    if name in {"main_node_summary", "tree_summary", "user_progress"}:
        return cols
    for row in rows:
        for key in row:
            if key not in cols:
                cols.append(key)
    return cols


def sheet_xml(rows: list[dict[str, Any]], cols: list[str]) -> str:
    last = f"{col_name(max(len(cols), 1))}{max(len(rows) + 1, 1)}"
    col_xml = "".join(f'<col min="{i}" max="{i}" width="{min(max(len(c) + 2, 10), 42)}" customWidth="1"/>' for i, c in enumerate(cols, 1))
    row_xml = ['<row r="1">' + "".join(cell(1, i, c, c, True) for i, c in enumerate(cols, 1)) + "</row>"]
    for r_i, row in enumerate(rows, 2):
        row_xml.append(f'<row r="{r_i}">' + "".join(cell(r_i, c_i, col, row.get(col, "")) for c_i, col in enumerate(cols, 1)) + "</row>")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:{last}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{col_xml}</cols><sheetData>{''.join(row_xml)}</sheetData><autoFilter ref="A1:{last}"/></worksheet>'''


def write_xlsx(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    order = ["main_node_summary", "tree_summary", "user_progress", "user_image_summary", "user_question_summary", "question_distribution", "q1_filter_summary", "user_question_q1_yes", "question_dist_q1_yes", "problem_labels", "problem_nodes", "column_guide", "metadata", "chart_data", "graphs"]
    names = [name for name in order if name in sheets]
    workbook_sheets = "".join(f'<sheet name="{xlsx_escape(name[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1))
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets></workbook>'''
    wb_rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1))
    wb_rels += f'<Relationship Id="rId{len(names)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    content_sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(names) + 1))
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2F5D7C"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{content_sheets}</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{wb_rels}</Relationships>''')
        z.writestr("xl/styles.xml", styles)
        for index, name in enumerate(names, 1):
            cols = columns_for(name, sheets[name])
            z.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml(sheets[name], cols))


def main() -> None:
    raise_field_limit()
    args = parse_args()
    input_csv = Path(args.input_csv) if args.input_csv else latest_input()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = input_csv.parent / manifest_path
    output = Path(args.output) if args.output else input_csv.with_name(f"{input_csv.stem}_user_review_workbook.xlsx")
    manifest = load_manifest(manifest_path)
    sheets = build_rows(input_csv, manifest)
    write_xlsx(output, sheets)
    print(f"Wrote {output}")
    for name, rows in sheets.items():
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main()

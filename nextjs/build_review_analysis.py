#!/usr/bin/env python3
"""Build reviewer-level analysis CSVs from review_annotations exports.

The script is intentionally stdlib-only so v10/v11 exports can be analyzed
without adding project dependencies.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))
USER_RE = re.compile(r"^user(\d+)$")

ANSWER_COLUMNS = [
    "label",
    "instance",
    "mask_extra",
    "mask_missing",
    "mask_quality",
    "decomposition",
    "missing_child",
    "mask",
    "adopt",
    "parent_child",
]

GOOD_ANSWERS = {
    "label": {"예", "맞음"},
    "instance": {"정확"},
    "mask_extra": {"포함하지 않음"},
    "mask_missing": {"모두 포함함"},
    "mask_quality": {"정확"},
    "decomposition": {"예", "맞음", "없음"},
    "missing_child": {"예", "없음"},
    "mask": {"정확"},
    "adopt": {"채택"},
    "parent_child": {"맞음"},
}

WARNING_ANSWERS = {
    "label": {"판단불가", "부분적으로 맞음"},
    "instance": {"판단불가", "수용 가능"},
    "mask_extra": {"약간 포함", "판단불가"},
    "mask_missing": {"약간 놓침", "판단불가"},
    "mask_quality": {"수용 가능", "판단불가"},
    "decomposition": {"조금 있음", "판단불가"},
    "missing_child": {"조금 있음", "판단불가"},
    "mask": {"수용 가능", "판단불가"},
    "adopt": {"보류"},
    "parent_child": {"판단불가"},
}

BAD_ANSWERS = {
    "label": {"아니오", "아님"},
    "instance": {"부정확", "실패"},
    "mask_extra": {"많이 포함"},
    "mask_missing": {"많이 놓침"},
    "mask_quality": {"부정확", "실패"},
    "decomposition": {"아니오", "아님", "많이 있음"},
    "missing_child": {"아니오", "많이 있음"},
    "mask": {"부정확", "실패"},
    "adopt": {"기각"},
    "parent_child": {"아님"},
}


def raise_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create user1-user20 review analysis CSVs. "
            "If no input CSV is given, the newest review_annotations_v*.csv is used."
        )
    )
    parser.add_argument(
        "input_csv",
        nargs="?",
        default=None,
        help=(
            "review_annotations export CSV, e.g. review_annotations_v10.csv. "
            "Default: auto-detect newest review_annotations_v*.csv"
        ),
    )
    parser.add_argument(
        "--manifest",
        default="image_manifest.csv",
        help="image_manifest.csv with node metadata",
    )
    parser.add_argument(
        "--output-dir",
        default="review_analysis_readable",
        help="directory for generated CSV files",
    )
    parser.add_argument(
        "--min-user",
        type=int,
        default=1,
        help="first reviewer number to include",
    )
    parser.add_argument(
        "--max-user",
        type=int,
        default=20,
        help="last reviewer number to include",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="also write legacy separate CSV files",
    )
    parser.add_argument(
        "--write-html",
        action="store_true",
        help="also write the HTML preview report and per-table CSV folder",
    )
    return parser.parse_args()


def version_number(path: Path) -> int:
    match = re.search(r"review_annotations_v(\d+)\.csv$", path.name)
    return int(match.group(1)) if match else -1


def find_latest_input_csv() -> Path:
    candidates = sorted(
        Path(".").glob("review_annotations_v*.csv"),
        key=lambda path: (version_number(path), path.stat().st_mtime),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "No review_annotations_v*.csv file found. "
            "Place review_annotations_v9.csv/v10.csv/etc. in this folder, "
            "or pass the CSV path explicitly."
        )
    return candidates[0]


def user_number(reviewer_id: str) -> int | None:
    match = USER_RE.match(reviewer_id or "")
    return int(match.group(1)) if match else None


def included_user(reviewer_id: str, min_user: int, max_user: int) -> bool:
    number = user_number(reviewer_id)
    return number is not None and min_user <= number <= max_user


def safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
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


def iso(dt: datetime | None) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt else ""


def kst_iso(dt: datetime | None) -> str:
    return dt.astimezone(KST).isoformat() if dt else ""


def kst_date(dt: datetime | None) -> str:
    return dt.astimezone(KST).date().isoformat() if dt else ""


def kst_hour(dt: datetime | None) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:00") if dt else ""


def normalize_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def has_answer_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def node_depth(node_id: str) -> int:
    if not node_id or node_id == "root":
        return 0
    parts = node_id.split("__")
    return max(len(parts) - 1, 0)


def path_label(node_id: str) -> str:
    if not node_id:
        return ""
    parts = node_id.split("__")
    return "/".join(parts[1:] if parts and parts[0] == "root" else parts)


def top_label(node_id: str) -> str:
    parts = node_id.split("__")
    return parts[1] if len(parts) > 1 and parts[0] == "root" else ""


def parent_from_path(node_id: str) -> str:
    parts = node_id.split("__")
    if len(parts) <= 2:
        return "root"
    return "__".join(parts[:-1])


def label_from_node(node_id: str) -> str:
    return node_id.split("__")[-1] if node_id else ""


def bbox_area(bbox: Any) -> float | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def area_bin(area_ratio: float | None) -> str:
    if area_ratio is None:
        return "missing"
    if area_ratio < 0.001:
        return "tiny_<0.1%"
    if area_ratio < 0.01:
        return "small_0.1-1%"
    if area_ratio < 0.05:
        return "medium_1-5%"
    if area_ratio < 0.2:
        return "large_5-20%"
    return "huge_>=20%"


def count_bin(value: int | None) -> str:
    if value is None:
        return "missing"
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 3:
        return "2-3"
    if value <= 9:
        return "4-9"
    return "10+"


def severity(question: str, answer: str) -> int:
    if not answer:
        return 0
    if answer in BAD_ANSWERS.get(question, set()):
        return 2
    if answer in WARNING_ANSWERS.get(question, set()):
        return 1
    if question in GOOD_ANSWERS and answer not in GOOD_ANSWERS[question]:
        return 1
    return 0


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    manifest: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            image_id = row.get("image_id", "")
            nodes = safe_json_loads(row.get("nodes"), {})
            actual_nodes = safe_json_loads(row.get("actual_nodes"), [])
            full_size = safe_json_loads(row.get("full_size"), [])
            full_area = None
            if isinstance(full_size, list) and len(full_size) == 2:
                try:
                    full_area = float(full_size[0]) * float(full_size[1])
                except (TypeError, ValueError):
                    full_area = None
            manifest[image_id] = {
                "nodes": nodes if isinstance(nodes, dict) else {},
                "actual_nodes": set(actual_nodes if isinstance(actual_nodes, list) else []),
                "full_area": full_area,
                "dataset_prefix": row.get("dataset_prefix", ""),
            }
    return manifest


def manifest_node_meta(
    manifest: dict[str, dict[str, Any]],
    image_id: str,
    node_id: str,
    fallback_node_ids: set[str],
) -> dict[str, Any]:
    image_meta = manifest.get(image_id, {})
    nodes = image_meta.get("nodes", {})
    node = nodes.get(node_id, {}) if isinstance(nodes, dict) else {}
    children = node.get("children") if isinstance(node, dict) else None
    if not isinstance(children, list):
        children = [nid for nid in fallback_node_ids if nid.startswith(f"{node_id}__")]
    parent = node.get("parent") if isinstance(node, dict) else None
    bbox = node.get("bbox") if isinstance(node, dict) else None
    area = bbox_area(bbox)
    full_area = image_meta.get("full_area")
    instance_paths = node.get("instance_paths") if isinstance(node, dict) else None
    instance_count = len(instance_paths) if isinstance(instance_paths, list) else None
    label = node.get("label") if isinstance(node, dict) else None
    actual_nodes = image_meta.get("actual_nodes", set())
    area_ratio = area / full_area if area is not None and full_area else None
    return {
        "label": label or label_from_node(node_id),
        "parent_id": parent or parent_from_path(node_id),
        "depth": node_depth(node_id),
        "is_leaf": len(children) == 0,
        "child_count": len(children),
        "actual": node.get("actual", node_id in actual_nodes) if isinstance(node, dict) else node_id in actual_nodes,
        "bbox_area": area,
        "bbox_area_ratio": area_ratio,
        "bbox_area_bin": area_bin(area_ratio),
        "instance_count": instance_count,
        "instance_count_bin": count_bin(instance_count),
        "dataset_prefix": image_meta.get("dataset_prefix", ""),
    }


def add_ratio(row: dict[str, Any], numerator: int | float, denominator: int | float, key: str = "ratio") -> None:
    row[key] = round(float(numerator) / float(denominator), 6) if denominator else ""


def mean(values: list[float]) -> str | float:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    return round(sum(clean) / len(clean), 6) if clean else ""


def pct(value: int, total: int) -> str | float:
    return round(value / total, 6) if total else ""


def update_min_max(
    bucket: dict[str, Any],
    dt: datetime | None,
    first_key: str = "first_updated_at_utc",
    last_key: str = "last_updated_at_utc",
) -> None:
    if not dt:
        return
    first = parse_timestamp(bucket.get(first_key))
    last = parse_timestamp(bucket.get(last_key))
    if first is None or dt < first:
        bucket[first_key] = iso(dt)
        bucket[first_key.replace("_utc", "_kst")] = kst_iso(dt)
    if last is None or dt > last:
        bucket[last_key] = iso(dt)
        bucket[last_key.replace("_utc", "_kst")] = kst_iso(dt)


def collect_rows(
    input_csv: Path,
    manifest: dict[str, dict[str, Any]],
    min_user: int,
    max_user: int,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], set[str]], set[str], dict[str, str]]:
    details: list[dict[str, Any]] = []
    targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    source_users: set[str] = set()
    reviewer_row_updated_at: dict[str, str] = {}
    all_answer_keys: set[str] = set()

    with input_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            reviewer_id = row.get("reviewer_id", "")
            source_users.add(reviewer_id)
            if not included_user(reviewer_id, min_user, max_user):
                continue

            reviewer_row_updated_at[reviewer_id] = row.get("updated_at", "")
            payload = safe_json_loads(row.get("payload"), {})
            if not isinstance(payload, dict):
                continue

            for image_id, image_payload in payload.items():
                nodes = (image_payload or {}).get("nodes", {})
                if not isinstance(nodes, dict):
                    continue
                node_ids = set(nodes.keys())
                targets[(reviewer_id, image_id)].update(node_ids)

                for node_id, node_payload in nodes.items():
                    answers = (node_payload or {}).get("answers", {})
                    if not isinstance(answers, dict):
                        continue
                    answers = {k: normalize_answer(v) for k, v in answers.items() if has_answer_value(v)}
                    if not answers:
                        continue

                    all_answer_keys.update(answers)
                    meta = manifest_node_meta(manifest, image_id, node_id, node_ids)
                    updated_at = parse_timestamp((node_payload or {}).get("updated_at"))
                    answer_severities = {
                        key: severity(key, value)
                        for key, value in answers.items()
                    }
                    bad_questions = [k for k, score in answer_severities.items() if score >= 2]
                    warning_questions = [k for k, score in answer_severities.items() if score == 1]
                    issue_score = sum(answer_severities.values())
                    depth = meta["depth"]
                    label = meta["label"]
                    label_tokens = [part for part in re.split(r"[_\s]+", label) if part]
                    ancestor_labels = path_label(node_id).split("/")[:-1]

                    detail = {
                        "reviewer_id": reviewer_id,
                        "user_number": user_number(reviewer_id),
                        "image_id": image_id,
                        "node_id": node_id,
                        "label": label,
                        "path_label": path_label(node_id),
                        "top_level_label": top_label(node_id),
                        "parent_id": meta["parent_id"],
                        "parent_label": label_from_node(meta["parent_id"]),
                        "ancestor_labels": "/".join(ancestor_labels),
                        "depth": depth,
                        "is_leaf": str(bool(meta["is_leaf"])),
                        "child_count": meta["child_count"],
                        "actual": str(bool(meta["actual"])),
                        "bbox_area": "" if meta["bbox_area"] is None else round(meta["bbox_area"], 6),
                        "bbox_area_ratio": "" if meta["bbox_area_ratio"] is None else round(meta["bbox_area_ratio"], 8),
                        "bbox_area_bin": meta["bbox_area_bin"],
                        "instance_count": "" if meta["instance_count"] is None else meta["instance_count"],
                        "instance_count_bin": meta["instance_count_bin"],
                        "has_others_ancestor": str("others" in node_id.split("__")),
                        "label_char_count": len(label),
                        "label_token_count": len(label_tokens),
                        "dataset_prefix": meta["dataset_prefix"],
                        "node_updated_at_utc": iso(updated_at),
                        "node_updated_at_kst": kst_iso(updated_at),
                        "node_updated_date_kst": kst_date(updated_at),
                        "node_updated_hour_kst": kst_hour(updated_at),
                        "reviewer_row_updated_at": reviewer_row_updated_at.get(reviewer_id, ""),
                        "answer_count": len(answers),
                        "answered_questions": "|".join(sorted(answers)),
                        "bad_flag": str(bool(bad_questions)),
                        "nonideal_flag": str(bool(bad_questions or warning_questions)),
                        "bad_question_count": len(bad_questions),
                        "warning_question_count": len(warning_questions),
                        "issue_score": issue_score,
                        "bad_questions": "|".join(sorted(bad_questions)),
                        "warning_questions": "|".join(sorted(warning_questions)),
                    }
                    detail.update({f"answer_{key}": answers.get(key, "") for key in sorted(all_answer_keys | set(ANSWER_COLUMNS))})
                    details.append(detail)

    final_answer_keys = sorted(all_answer_keys | set(ANSWER_COLUMNS))
    for detail in details:
        for key in final_answer_keys:
            detail.setdefault(f"answer_{key}", "")

    return details, targets, source_users, reviewer_row_updated_at


def write_csv(path: Path, rows: list[dict[str, Any]], preferred: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    if preferred:
        keys.extend([key for key in preferred if key not in keys])
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_selected_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


TABLE_ORDER = [
    "user_progress",
    "question_response_distribution",
    "question_by_leaf",
    "question_by_depth",
    "question_by_depth_leaf",
    "leaf_special_response_distribution",
    "label_problem_rank",
    "label_feature_bins",
    "image_quality_summary",
    "user_image_summary",
    "timestamp_flow",
    "node_problem_rank",
    "agreement_by_question",
    "agreement_by_depth_leaf",
    "agreement_by_label",
    "metadata",
    "table_catalog",
]


PRETTY_TABLES = {
    "table_catalog": {
        "file": "00_table_index.csv",
        "columns": ["metric", "value"],
        "title": "Table Index",
    },
    "user_progress": {
        "file": "01_user_progress.csv",
        "columns": [
            "reviewer_id",
            "present_in_source",
            "target_images",
            "target_nodes",
            "nodes_answered",
            "completion_rate",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_depth",
            "avg_issue_score",
            "active_days_kst",
            "first_updated_at_kst",
            "last_updated_at_kst",
        ],
        "title": "User Progress",
    },
    "question_response_distribution": {
        "file": "02_question_response_distribution.csv",
        "columns": ["question", "answer_value", "response_count", "group_total", "ratio"],
        "title": "Question Response Distribution",
    },
    "question_by_leaf": {
        "file": "03_question_by_leaf.csv",
        "columns": ["question", "is_leaf", "answer_value", "response_count", "group_total", "ratio"],
        "title": "Question By Leaf",
    },
    "question_by_depth_leaf": {
        "file": "04_question_by_depth_leaf.csv",
        "columns": ["question", "depth", "is_leaf", "answer_value", "response_count", "group_total", "ratio"],
        "title": "Question By Depth And Leaf",
    },
    "leaf_special_response_distribution": {
        "file": "05_leaf_special_responses.csv",
        "columns": ["question", "is_leaf", "answer_value", "response_count", "group_total", "ratio"],
        "title": "Leaf Special Responses",
    },
    "label_problem_rank": {
        "file": "06_label_problem_rank.csv",
        "columns": [
            "rank_bad_rate",
            "label",
            "response_count",
            "unique_node_count",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_depth",
            "leaf_ratio",
            "others_path_ratio",
            "avg_issue_score",
            "top_bad_questions",
            "example_bad_nodes",
        ],
        "title": "Label Problem Rank",
    },
    "label_feature_bins": {
        "file": "07_label_feature_bins.csv",
        "columns": [
            "rank_bad_rate",
            "feature",
            "feature_value",
            "response_count",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_issue_score",
        ],
        "title": "Label Feature Bins",
    },
    "image_quality_summary": {
        "file": "08_image_quality_summary.csv",
        "columns": [
            "rank_bad_rate",
            "image_id",
            "reviewer_count",
            "nodes_answered",
            "unique_nodes_answered",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_depth",
            "avg_issue_score",
        ],
        "title": "Image Quality Summary",
    },
    "user_image_summary": {
        "file": "09_user_image_summary.csv",
        "columns": [
            "reviewer_id",
            "image_id",
            "target_nodes_in_payload",
            "manifest_actual_nodes",
            "nodes_answered",
            "completion_rate",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_depth",
            "avg_issue_score",
            "first_updated_at_kst",
            "last_updated_at_kst",
        ],
        "title": "User Image Summary",
    },
    "timestamp_flow": {
        "file": "10_timestamp_flow.csv",
        "columns": [
            "reviewer_id",
            "date_kst",
            "hour_kst",
            "response_count",
            "cumulative_response_count",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
        ],
        "title": "Timestamp Flow",
    },
    "node_problem_rank": {
        "file": "11_node_problem_rank.csv",
        "columns": [
            "rank_bad_rate",
            "image_id",
            "node_id",
            "label",
            "path_label",
            "depth",
            "is_leaf",
            "reviewer_count",
            "response_count",
            "bad_nodes",
            "bad_node_rate",
            "nonideal_nodes",
            "nonideal_node_rate",
            "avg_issue_score",
            "bbox_area_bin",
            "instance_count_bin",
        ],
        "title": "Node Problem Rank",
    },
    "agreement_by_question": {
        "file": "12_agreement_by_question.csv",
        "columns": [
            "question",
            "overlap_item_count",
            "avg_majority_share",
            "avg_pairwise_agreement",
            "avg_reviewers_per_item",
        ],
        "title": "Agreement By Question",
    },
    "agreement_by_depth_leaf": {
        "file": "13_agreement_by_depth_leaf.csv",
        "columns": [
            "question",
            "depth",
            "is_leaf",
            "overlap_item_count",
            "avg_majority_share",
            "avg_pairwise_agreement",
            "avg_reviewers_per_item",
        ],
        "title": "Agreement By Depth And Leaf",
    },
    "agreement_by_label": {
        "file": "14_agreement_by_label.csv",
        "columns": [
            "question",
            "label",
            "overlap_item_count",
            "avg_majority_share",
            "avg_pairwise_agreement",
            "avg_reviewers_per_item",
        ],
        "title": "Agreement By Label",
    },
    "metadata": {
        "file": "99_metadata.csv",
        "columns": ["metric", "value", "source_file", "manifest_file"],
        "title": "Metadata",
    },
}


def analysis_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    table = row.get("table_name", "")
    table_index = TABLE_ORDER.index(table) if table in TABLE_ORDER else len(TABLE_ORDER)
    rank = row.get("rank_bad_rate")
    rank_value = int(rank) if str(rank).isdigit() else 999999
    return (
        table_index,
        row.get("reviewer_id", ""),
        row.get("question", ""),
        row.get("depth", ""),
        row.get("is_leaf", ""),
        rank_value,
        row.get("image_id", ""),
        row.get("label", ""),
        row.get("answer_value", ""),
    )


def filtered_pretty_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [row for row in rows if row.get("table_name") == table_name]
    if table_name in {"label_problem_rank", "image_quality_summary", "node_problem_rank"}:
        out.sort(key=lambda row: int(row.get("rank_bad_rate") or 999999))
    elif table_name == "label_feature_bins":
        out.sort(
            key=lambda row: (
                row.get("feature", ""),
                int(row.get("rank_bad_rate") or 999999),
                row.get("feature_value", ""),
            )
        )
    elif table_name == "timestamp_flow":
        out.sort(key=lambda row: (row.get("reviewer_id", ""), row.get("hour_kst", "")))
    else:
        out.sort(key=analysis_sort_key)
    return out


def write_pretty_table_csvs(output_dir: Path, prefix: str, analysis_rows: list[dict[str, Any]]) -> Path:
    pretty_dir = output_dir / f"{prefix}_pretty_tables"
    for table_name, config in PRETTY_TABLES.items():
        rows = filtered_pretty_rows(table_name, analysis_rows)
        if not rows and table_name.startswith("agreement_"):
            continue
        write_selected_csv(pretty_dir / config["file"], rows, config["columns"])
    return pretty_dir


def html_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int = 30) -> str:
    clipped = rows[:max_rows]
    head = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    body_parts = []
    for row in clipped:
        cells = "".join(html_cell(row.get(col, "")) for col in columns)
        body_parts.append(f"<tr>{cells}</tr>")
    more = ""
    if len(rows) > max_rows:
        more = f"<p class=\"more\">Showing {max_rows:,} of {len(rows):,} rows. Open the CSV for the full table.</p>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>{more}"


def html_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    classes = []
    try:
        numeric = float(text)
        if "rate" in text:
            pass
        if numeric >= 0.5:
            classes.append("strong")
    except ValueError:
        pass
    return f"<td>{html.escape(text)}</td>"


def write_html_report(
    path: Path,
    prefix: str,
    pretty_dir: Path,
    analysis_rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    user_progress = filtered_pretty_rows("user_progress", analysis_rows)
    question_dist = filtered_pretty_rows("question_response_distribution", analysis_rows)
    leaf_special = filtered_pretty_rows("leaf_special_response_distribution", analysis_rows)
    label_rank = [
        row
        for row in filtered_pretty_rows("label_problem_rank", analysis_rows)
        if int(row.get("response_count") or 0) >= 20
    ]
    image_rank = filtered_pretty_rows("image_quality_summary", analysis_rows)
    feature_bins = filtered_pretty_rows("label_feature_bins", analysis_rows)

    links = []
    for table_name, config in PRETTY_TABLES.items():
        rows = filtered_pretty_rows(table_name, analysis_rows)
        csv_path = pretty_dir / config["file"]
        if rows or csv_path.exists():
            links.append(
                f"<li><a href=\"{html.escape(str(csv_path.name))}\">{html.escape(config['title'])}</a>"
                f" <span>{len(rows):,} rows</span></li>"
            )

    sections = [
        (
            "User Progress",
            user_progress,
            PRETTY_TABLES["user_progress"]["columns"],
            25,
        ),
        (
            "Overall Question Distribution",
            question_dist,
            PRETTY_TABLES["question_response_distribution"]["columns"],
            80,
        ),
        (
            "Leaf Node Special Questions",
            leaf_special,
            PRETTY_TABLES["leaf_special_response_distribution"]["columns"],
            40,
        ),
        (
            "Worst Labels, Min 20 Responses",
            label_rank,
            PRETTY_TABLES["label_problem_rank"]["columns"],
            30,
        ),
        (
            "Worst Images",
            image_rank,
            PRETTY_TABLES["image_quality_summary"]["columns"],
            30,
        ),
        (
            "Feature Bins",
            feature_bins,
            PRETTY_TABLES["label_feature_bins"]["columns"],
            80,
        ),
    ]

    section_html = []
    for title, rows, columns, max_rows in sections:
        section_html.append(
            f"<section><h2>{html.escape(title)}</h2>{html_table(rows, columns, max_rows)}</section>"
        )

    doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{html.escape(prefix)} Review Analysis</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      color: #182026;
      background: #f6f7f9;
    }}
    header {{
      padding: 28px 32px 16px;
      background: #ffffff;
      border-bottom: 1px solid #d9dee5;
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    p {{ margin: 0; color: #56616f; }}
    main {{ padding: 24px 32px 40px; }}
    section {{
      margin-bottom: 24px;
      padding: 18px;
      background: #ffffff;
      border: 1px solid #d9dee5;
      border-radius: 6px;
      overflow-x: auto;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
      line-height: 1.35;
    }}
    th, td {{
      border-bottom: 1px solid #e5e9ef;
      padding: 7px 9px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #eef2f6;
      font-weight: 700;
    }}
    tbody tr:nth-child(even) {{ background: #fafbfc; }}
    .links {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 8px 18px;
      margin: 16px 0 0;
      padding-left: 18px;
    }}
    .links span {{ color: #6b7480; }}
    .more {{ margin-top: 10px; font-size: 12px; }}
    a {{ color: #075f8f; text-decoration: none; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(prefix)} Review Analysis</h1>
    <p>Clean summary report. Full table CSVs are linked below and stored in the same folder as this report.</p>
    <ul class="links">{''.join(links)}</ul>
  </header>
  <main>{''.join(section_html)}</main>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


XLSX_SHEETS = [
    ("node_response", "node_response", None),
    ("user_progress", "user_progress", "user_progress"),
    ("user_image_summary", "user_image", "user_image_summary"),
    ("question_response_distribution", "question_overall", "question_response_distribution"),
    ("question_by_user", "question_by_user", None),
    ("question_by_depth", "question_by_depth", None),
    ("question_by_leaf", "question_by_leaf", "question_by_leaf"),
    ("question_by_depth_leaf", "question_depth_leaf", "question_by_depth_leaf"),
    ("leaf_special_response_distribution", "leaf_special", "leaf_special_response_distribution"),
    ("label_problem_rank", "label_problem_rank", "label_problem_rank"),
    ("label_feature_bins", "label_features", "label_feature_bins"),
    ("image_quality_summary", "image_quality", "image_quality_summary"),
    ("node_problem_rank", "node_problem_rank", "node_problem_rank"),
    ("timestamp_flow", "timestamp_flow", "timestamp_flow"),
    ("agreement_by_question", "agreement_question", "agreement_by_question"),
    ("agreement_by_depth_leaf", "agreement_depth_leaf", "agreement_by_depth_leaf"),
    ("agreement_by_label", "agreement_label", "agreement_by_label"),
    ("metadata", "metadata", "metadata"),
    ("table_catalog", "table_index", "table_catalog"),
]

TEXT_COLUMNS = {
    "reviewer_id",
    "image_id",
    "node_id",
    "label",
    "path_label",
    "top_level_label",
    "parent_id",
    "parent_label",
    "ancestor_labels",
    "dataset_prefix",
    "node_updated_at_utc",
    "node_updated_at_kst",
    "node_updated_date_kst",
    "node_updated_hour_kst",
    "reviewer_row_updated_at",
    "answered_questions",
    "bad_questions",
    "warning_questions",
    "question",
    "answer_value",
    "metric",
    "value",
    "date_kst",
    "hour_kst",
    "feature",
    "feature_value",
    "example_bad_nodes",
    "top_bad_questions",
    "source_file",
    "manifest_file",
}


def xlsx_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def xlsx_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or "sheet"
    base = cleaned
    index = 2
    while cleaned in used:
        suffix = f"_{index}"
        cleaned = f"{base[:31 - len(suffix)]}{suffix}"
        index += 1
    used.add(cleaned)
    return cleaned


def excel_column(index: int) -> str:
    letters = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def excel_cell(row_index: int, column_index: int) -> str:
    return f"{excel_column(column_index)}{row_index}"


def is_number_for_xlsx(column: str, value: Any) -> bool:
    if value in ("", None) or column in TEXT_COLUMNS or column.startswith("answer_"):
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value)
    if text in {"True", "False"}:
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return not (len(text) > 1 and text.startswith("0") and "." not in text)
    return False


def xlsx_cell(row_index: int, column_index: int, column: str, value: Any, style: int = 0) -> str:
    if value in ("", None):
        return ""
    ref = excel_cell(row_index, column_index)
    style_attr = f' s="{style}"' if style else ""
    if is_number_for_xlsx(column, value):
        return f'<c r="{ref}"{style_attr}><v>{xlsx_escape(value)}</v></c>'
    preserve = ' xml:space="preserve"' if str(value).strip() != str(value) else ""
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t{preserve}>{xlsx_escape(value)}</t></is></c>'


def xlsx_columns(rows: list[dict[str, Any]], preferred: list[str] | None = None) -> list[str]:
    columns: list[str] = []
    if preferred:
        columns.extend([column for column in preferred if column not in columns])
    for row in rows:
        for column in row:
            if column != "table_name" and column not in columns:
                columns.append(column)
    return columns


def xlsx_column_widths(rows: list[dict[str, Any]], columns: list[str]) -> list[float]:
    widths = []
    sample_rows = rows[:200]
    for column in columns:
        max_len = len(column)
        for row in sample_rows:
            value = row.get(column, "")
            if value not in ("", None):
                max_len = max(max_len, len(str(value)))
        widths.append(float(min(max(max_len + 2, 8), 48)))
    return widths


def xlsx_sheet_xml(rows: list[dict[str, Any]], columns: list[str]) -> str:
    last_column = excel_column(max(len(columns), 1))
    last_row = max(len(rows) + 1, 1)
    dimension = f"A1:{last_column}{last_row}"
    widths = xlsx_column_widths(rows, columns)
    col_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width:.1f}" customWidth="1"/>'
        for idx, width in enumerate(widths, start=1)
    )
    header_cells = "".join(
        xlsx_cell(1, idx, column, column, 1)
        for idx, column in enumerate(columns, start=1)
    )
    row_parts = [f'<row r="1">{header_cells}</row>']
    for row_index, row in enumerate(rows, start=2):
        cells = "".join(
            xlsx_cell(row_index, col_index, column, row.get(column, ""))
            for col_index, column in enumerate(columns, start=1)
        )
        row_parts.append(f'<row r="{row_index}">{cells}</row>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="{dimension}"/>
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
      <selection pane="bottomLeft"/>
    </sheetView>
  </sheetViews>
  <cols>{col_xml}</cols>
  <sheetData>{''.join(row_parts)}</sheetData>
  <autoFilter ref="{dimension}"/>
</worksheet>'''


def xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  {sheet_overrides}
</Types>'''


def xlsx_styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><name val="Arial"/><color rgb="FFFFFFFF"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF2F5D7C"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def write_xlsx_workbook(
    path: Path,
    sheets: list[tuple[str, list[dict[str, Any]], list[str]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    sheet_names = [xlsx_sheet_name(name, used_names) for name, _, _ in sheets]
    workbook_sheets = "".join(
        f'<sheet name="{xlsx_escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, name in enumerate(sheet_names, start=1)
    )
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews><workbookView activeTab="0"/></bookViews>
  <sheets>{workbook_sheets}</sheets>
</workbook>'''
    workbook_rels = "".join(
        f'<Relationship Id="rId{idx}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{idx}.xml"/>'
        for idx in range(1, len(sheets) + 1)
    )
    workbook_rels += (
        f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>build_review_analysis.py</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{iso(datetime.now(timezone.utc))}</dcterms:created>
</cp:coreProperties>'''
    app = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>build_review_analysis.py</Application>
  <TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">'''
    app += "".join(f"<vt:lpstr>{xlsx_escape(name)}</vt:lpstr>" for name in sheet_names)
    app += "</vt:vector></TitlesOfParts></Properties>"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", xlsx_content_types(len(sheets)))
        archive.writestr("_rels/.rels", rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{workbook_rels}</Relationships>''',
        )
        archive.writestr("xl/styles.xml", xlsx_styles())
        for idx, (_, rows, columns) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", xlsx_sheet_xml(rows, columns))


def build_workbook_sheets(
    details: list[dict[str, Any]],
    analysis_rows: list[dict[str, Any]],
    detail_columns: list[str],
) -> list[tuple[str, list[dict[str, Any]], list[str]]]:
    sheets: list[tuple[str, list[dict[str, Any]], list[str]]] = [
        ("node_response", details, detail_columns)
    ]
    for table_name, sheet_name, pretty_key in XLSX_SHEETS[1:]:
        rows = filtered_pretty_rows(table_name, analysis_rows)
        if not rows and table_name.startswith("agreement_"):
            continue
        if pretty_key and pretty_key in PRETTY_TABLES:
            columns = PRETTY_TABLES[pretty_key]["columns"]
        else:
            columns = xlsx_columns(rows)
        sheets.append((sheet_name, rows, columns))
    return sheets


def distribution_rows(
    table_name: str,
    grouped_counts: dict[tuple[Any, ...], Counter],
    group_fields: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_key, counter in sorted(grouped_counts.items(), key=lambda item: tuple(str(v) for v in item[0])):
        total = sum(counter.values())
        for answer_value, count in counter.most_common():
            row = {"table_name": table_name}
            row.update(dict(zip(group_fields, group_key)))
            row.update({"answer_value": answer_value, "response_count": count, "group_total": total})
            add_ratio(row, count, total)
            rows.append(row)
    return rows


def add_distribution(
    buckets: dict[tuple[Any, ...], Counter],
    group_key: tuple[Any, ...],
    answer: str,
) -> None:
    if answer:
        buckets[group_key][answer] += 1


def build_analysis_tables(
    details: list[dict[str, Any]],
    targets: dict[tuple[str, str], set[str]],
    source_users: set[str],
    reviewer_row_updated_at: dict[str, str],
    manifest: dict[str, dict[str, Any]],
    input_csv: Path,
    manifest_path: Path,
    min_user: int,
    max_user: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_users = [f"user{i}" for i in range(min_user, max_user + 1)]
    details_by_user = defaultdict(list)
    details_by_user_image = defaultdict(list)
    details_by_image = defaultdict(list)
    details_by_node = defaultdict(list)
    details_by_label = defaultdict(list)

    answer_keys = sorted(
        key.replace("answer_", "")
        for key in {k for row in details for k in row if k.startswith("answer_")}
        if key != "answer_count"
    )

    table_catalog = {
        "node_response": "One row per answered reviewer-image-node, with node metadata and answer columns.",
        "user_progress": "Reviewer-level progress, completion, issue rates, and first/last timestamps.",
        "user_image_summary": "Reviewer-by-image completion and quality summary.",
        "question_response_distribution": "Overall count and ratio for each question-answer pair.",
        "question_by_user": "Question-answer distribution split by reviewer.",
        "question_by_depth": "Question-answer distribution split by node depth.",
        "question_by_leaf": "Question-answer distribution split by leaf/non-leaf node.",
        "question_by_depth_leaf": "Question-answer distribution split by depth and leaf status together.",
        "leaf_special_response_distribution": "Leaf/non-leaf distribution for decomposition and missing_child answers.",
        "timestamp_flow": "KST hourly response flow with cumulative counts.",
        "image_quality_summary": "Image-level quality and issue summary across reviewers.",
        "node_problem_rank": "Image-node-level issue rates for finding bad targets.",
        "label_problem_rank": "Label-level issue rates and examples for paper analysis.",
        "label_feature_bins": "Issue rates by interpretable label/node features such as depth, area, and leaf status.",
        "agreement_by_question": "Inter-reviewer agreement summary by question for overlapped reviewed nodes.",
        "agreement_by_depth_leaf": "Inter-reviewer agreement by question, depth, and leaf status.",
        "agreement_by_label": "Inter-reviewer agreement by question and label.",
        "metadata": "Run metadata and included/excluded reviewer scope.",
    }

    for table, description in table_catalog.items():
        rows.append(
            {
                "table_name": "table_catalog",
                "metric": table,
                "value": description,
            }
        )

    for row in details:
        details_by_user[row["reviewer_id"]].append(row)
        details_by_user_image[(row["reviewer_id"], row["image_id"])].append(row)
        details_by_image[row["image_id"]].append(row)
        details_by_node[(row["image_id"], row["node_id"])].append(row)
        details_by_label[row["label"]].append(row)

    rows.append(
        {
            "table_name": "metadata",
            "metric": "source_file",
            "value": str(input_csv),
            "source_file": str(input_csv),
            "manifest_file": str(manifest_path),
        }
    )
    metadata = {
        "generated_at_utc": iso(datetime.now(timezone.utc)),
        "reviewer_scope": f"user{min_user}-user{max_user}",
        "present_in_scope": "|".join(sorted(u for u in expected_users if u in source_users)),
        "missing_in_scope": "|".join(sorted(u for u in expected_users if u not in source_users)),
        "excluded_reviewers": "|".join(sorted(u for u in source_users if not included_user(u, min_user, max_user))),
        "node_response_rows": len(details),
        "target_user_image_rows": len(targets),
        "images_with_any_answer": len({row["image_id"] for row in details}),
        "answer_keys": "|".join(answer_keys),
    }
    for metric, value in metadata.items():
        rows.append({"table_name": "metadata", "metric": metric, "value": value})

    for reviewer_id in expected_users:
        user_rows = details_by_user.get(reviewer_id, [])
        target_pairs = [pair for pair in targets if pair[0] == reviewer_id]
        target_node_count = sum(len(targets[pair]) for pair in target_pairs)
        timestamps = [parse_timestamp(row["node_updated_at_utc"]) for row in user_rows if row.get("node_updated_at_utc")]
        active_days = {kst_date(dt) for dt in timestamps if dt}
        bad_count = sum(row["bad_flag"] == "True" for row in user_rows)
        nonideal_count = sum(row["nonideal_flag"] == "True" for row in user_rows)
        answer_cell_count = sum(
            1
            for row in user_rows
            for key in answer_keys
            if row.get(f"answer_{key}", "")
        )
        progress = {
            "table_name": "user_progress",
            "reviewer_id": reviewer_id,
            "user_number": user_number(reviewer_id),
            "present_in_source": str(reviewer_id in source_users),
            "row_updated_at": reviewer_row_updated_at.get(reviewer_id, ""),
            "target_images": len(target_pairs),
            "target_nodes": target_node_count,
            "nodes_answered": len(user_rows),
            "answer_cells": answer_cell_count,
            "images_touched": len({row["image_id"] for row in user_rows}),
            "leaf_nodes_answered": sum(row["is_leaf"] == "True" for row in user_rows),
            "nonleaf_nodes_answered": sum(row["is_leaf"] == "False" for row in user_rows),
            "bad_nodes": bad_count,
            "nonideal_nodes": nonideal_count,
            "active_days_kst": len(active_days),
            "avg_depth": mean([float(row["depth"]) for row in user_rows]),
            "avg_issue_score": mean([float(row["issue_score"]) for row in user_rows]),
        }
        add_ratio(progress, progress["nodes_answered"], target_node_count, "completion_rate")
        add_ratio(progress, bad_count, len(user_rows), "bad_node_rate")
        add_ratio(progress, nonideal_count, len(user_rows), "nonideal_node_rate")
        if timestamps:
            progress["first_updated_at_utc"] = iso(min(timestamps))
            progress["first_updated_at_kst"] = kst_iso(min(timestamps))
            progress["last_updated_at_utc"] = iso(max(timestamps))
            progress["last_updated_at_kst"] = kst_iso(max(timestamps))
        rows.append(progress)

    for reviewer_id, image_id in sorted(targets):
        image_rows = details_by_user_image.get((reviewer_id, image_id), [])
        target_count = len(targets[(reviewer_id, image_id)])
        manifest_actual = len(manifest.get(image_id, {}).get("actual_nodes", set()))
        bad_count = sum(row["bad_flag"] == "True" for row in image_rows)
        nonideal_count = sum(row["nonideal_flag"] == "True" for row in image_rows)
        timestamps = [parse_timestamp(row["node_updated_at_utc"]) for row in image_rows if row.get("node_updated_at_utc")]
        row = {
            "table_name": "user_image_summary",
            "reviewer_id": reviewer_id,
            "user_number": user_number(reviewer_id),
            "image_id": image_id,
            "target_nodes_in_payload": target_count,
            "manifest_actual_nodes": manifest_actual,
            "nodes_answered": len(image_rows),
            "leaf_nodes_answered": sum(item["is_leaf"] == "True" for item in image_rows),
            "nonleaf_nodes_answered": sum(item["is_leaf"] == "False" for item in image_rows),
            "bad_nodes": bad_count,
            "nonideal_nodes": nonideal_count,
            "avg_depth": mean([float(item["depth"]) for item in image_rows]),
            "avg_issue_score": mean([float(item["issue_score"]) for item in image_rows]),
        }
        add_ratio(row, len(image_rows), target_count, "completion_rate")
        add_ratio(row, bad_count, len(image_rows), "bad_node_rate")
        add_ratio(row, nonideal_count, len(image_rows), "nonideal_node_rate")
        if timestamps:
            row["first_updated_at_utc"] = iso(min(timestamps))
            row["first_updated_at_kst"] = kst_iso(min(timestamps))
            row["last_updated_at_utc"] = iso(max(timestamps))
            row["last_updated_at_kst"] = kst_iso(max(timestamps))
        rows.append(row)

    dist_overall: dict[tuple[Any, ...], Counter] = defaultdict(Counter)
    dist_user: dict[tuple[Any, ...], Counter] = defaultdict(Counter)
    dist_depth: dict[tuple[Any, ...], Counter] = defaultdict(Counter)
    dist_leaf: dict[tuple[Any, ...], Counter] = defaultdict(Counter)
    dist_depth_leaf: dict[tuple[Any, ...], Counter] = defaultdict(Counter)
    dist_leaf_focus: dict[tuple[Any, ...], Counter] = defaultdict(Counter)

    for row in details:
        for key in answer_keys:
            answer = row.get(f"answer_{key}", "")
            if not answer:
                continue
            add_distribution(dist_overall, (key,), answer)
            add_distribution(dist_user, (row["reviewer_id"], key), answer)
            add_distribution(dist_depth, (key, row["depth"]), answer)
            add_distribution(dist_leaf, (key, row["is_leaf"]), answer)
            add_distribution(dist_depth_leaf, (key, row["depth"], row["is_leaf"]), answer)
            if key in {"decomposition", "missing_child"}:
                add_distribution(dist_leaf_focus, (key, row["is_leaf"]), answer)

    rows.extend(distribution_rows("question_response_distribution", dist_overall, ["question"]))
    rows.extend(distribution_rows("question_by_user", dist_user, ["reviewer_id", "question"]))
    rows.extend(distribution_rows("question_by_depth", dist_depth, ["question", "depth"]))
    rows.extend(distribution_rows("question_by_leaf", dist_leaf, ["question", "is_leaf"]))
    rows.extend(distribution_rows("question_by_depth_leaf", dist_depth_leaf, ["question", "depth", "is_leaf"]))
    rows.extend(distribution_rows("leaf_special_response_distribution", dist_leaf_focus, ["question", "is_leaf"]))

    cumulative_by_user = Counter()
    time_buckets = defaultdict(lambda: {"response_count": 0, "bad_nodes": 0, "nonideal_nodes": 0})
    for row in details:
        hour = row.get("node_updated_hour_kst", "")
        date = row.get("node_updated_date_kst", "")
        if not hour:
            continue
        for reviewer_key in (row["reviewer_id"], "ALL"):
            bucket = time_buckets[(reviewer_key, date, hour)]
            bucket["response_count"] += 1
            bucket["bad_nodes"] += int(row["bad_flag"] == "True")
            bucket["nonideal_nodes"] += int(row["nonideal_flag"] == "True")

    for reviewer_id, date, hour in sorted(time_buckets):
        bucket = time_buckets[(reviewer_id, date, hour)]
        cumulative_by_user[reviewer_id] += bucket["response_count"]
        row = {
            "table_name": "timestamp_flow",
            "reviewer_id": reviewer_id,
            "date_kst": date,
            "hour_kst": hour,
            "response_count": bucket["response_count"],
            "bad_nodes": bucket["bad_nodes"],
            "nonideal_nodes": bucket["nonideal_nodes"],
            "cumulative_response_count": cumulative_by_user[reviewer_id],
        }
        add_ratio(row, bucket["bad_nodes"], bucket["response_count"], "bad_node_rate")
        add_ratio(row, bucket["nonideal_nodes"], bucket["response_count"], "nonideal_node_rate")
        rows.append(row)

    for image_id, image_rows in sorted(details_by_image.items()):
        reviewers = {row["reviewer_id"] for row in image_rows}
        bad_count = sum(row["bad_flag"] == "True" for row in image_rows)
        nonideal_count = sum(row["nonideal_flag"] == "True" for row in image_rows)
        row = {
            "table_name": "image_quality_summary",
            "image_id": image_id,
            "reviewer_count": len(reviewers),
            "nodes_answered": len(image_rows),
            "unique_nodes_answered": len({row["node_id"] for row in image_rows}),
            "bad_nodes": bad_count,
            "nonideal_nodes": nonideal_count,
            "avg_depth": mean([float(row["depth"]) for row in image_rows]),
            "avg_issue_score": mean([float(row["issue_score"]) for row in image_rows]),
        }
        add_ratio(row, bad_count, len(image_rows), "bad_node_rate")
        add_ratio(row, nonideal_count, len(image_rows), "nonideal_node_rate")
        rows.append(row)

    for (image_id, node_id), node_rows in sorted(details_by_node.items()):
        bad_count = sum(row["bad_flag"] == "True" for row in node_rows)
        nonideal_count = sum(row["nonideal_flag"] == "True" for row in node_rows)
        first = node_rows[0]
        row = {
            "table_name": "node_problem_rank",
            "image_id": image_id,
            "node_id": node_id,
            "label": first["label"],
            "path_label": first["path_label"],
            "depth": first["depth"],
            "is_leaf": first["is_leaf"],
            "bbox_area_bin": first["bbox_area_bin"],
            "instance_count_bin": first["instance_count_bin"],
            "reviewer_count": len({item["reviewer_id"] for item in node_rows}),
            "response_count": len(node_rows),
            "bad_nodes": bad_count,
            "nonideal_nodes": nonideal_count,
            "avg_issue_score": mean([float(item["issue_score"]) for item in node_rows]),
        }
        add_ratio(row, bad_count, len(node_rows), "bad_node_rate")
        add_ratio(row, nonideal_count, len(node_rows), "nonideal_node_rate")
        rows.append(row)

    for label, label_rows in sorted(details_by_label.items()):
        bad_count = sum(row["bad_flag"] == "True" for row in label_rows)
        nonideal_count = sum(row["nonideal_flag"] == "True" for row in label_rows)
        top_bad_questions = Counter()
        example_nodes = []
        for item in label_rows:
            for question in item.get("bad_questions", "").split("|"):
                if question:
                    top_bad_questions[question] += 1
            if item["bad_flag"] == "True" and len(example_nodes) < 5:
                example_nodes.append(f"{item['image_id']}:{item['node_id']}")
        row = {
            "table_name": "label_problem_rank",
            "label": label,
            "response_count": len(label_rows),
            "unique_node_count": len({(item["image_id"], item["node_id"]) for item in label_rows}),
            "bad_nodes": bad_count,
            "nonideal_nodes": nonideal_count,
            "avg_depth": mean([float(item["depth"]) for item in label_rows]),
            "leaf_ratio": pct(sum(item["is_leaf"] == "True" for item in label_rows), len(label_rows)),
            "others_path_ratio": pct(sum(item["has_others_ancestor"] == "True" for item in label_rows), len(label_rows)),
            "avg_label_char_count": mean([float(item["label_char_count"]) for item in label_rows]),
            "avg_label_token_count": mean([float(item["label_token_count"]) for item in label_rows]),
            "avg_issue_score": mean([float(item["issue_score"]) for item in label_rows]),
            "top_bad_questions": "|".join(f"{k}:{v}" for k, v in top_bad_questions.most_common(5)),
            "example_bad_nodes": "|".join(example_nodes),
        }
        add_ratio(row, bad_count, len(label_rows), "bad_node_rate")
        add_ratio(row, nonideal_count, len(label_rows), "nonideal_node_rate")
        rows.append(row)

    feature_specs = [
        ("depth", lambda row: row["depth"]),
        ("is_leaf", lambda row: row["is_leaf"]),
        ("label_token_count", lambda row: row["label_token_count"]),
        ("bbox_area_bin", lambda row: row["bbox_area_bin"]),
        ("instance_count_bin", lambda row: row["instance_count_bin"]),
        ("has_others_ancestor", lambda row: row["has_others_ancestor"]),
        ("top_level_label", lambda row: row["top_level_label"]),
    ]
    for feature_name, getter in feature_specs:
        buckets = defaultdict(list)
        for row in details:
            buckets[str(getter(row))].append(row)
        for feature_value, bucket_rows in sorted(buckets.items()):
            bad_count = sum(row["bad_flag"] == "True" for row in bucket_rows)
            nonideal_count = sum(row["nonideal_flag"] == "True" for row in bucket_rows)
            out = {
                "table_name": "label_feature_bins",
                "feature": feature_name,
                "feature_value": feature_value,
                "response_count": len(bucket_rows),
                "bad_nodes": bad_count,
                "nonideal_nodes": nonideal_count,
                "avg_issue_score": mean([float(row["issue_score"]) for row in bucket_rows]),
            }
            add_ratio(out, bad_count, len(bucket_rows), "bad_node_rate")
            add_ratio(out, nonideal_count, len(bucket_rows), "nonideal_node_rate")
            rows.append(out)

    agreement_groups = defaultdict(Counter)
    agreement_meta = {}
    for row in details:
        for key in answer_keys:
            answer = row.get(f"answer_{key}", "")
            if not answer:
                continue
            group_key = (row["image_id"], row["node_id"], key)
            agreement_groups[group_key][answer] += 1
            agreement_meta[group_key] = {
                "question": key,
                "depth": row["depth"],
                "is_leaf": row["is_leaf"],
                "label": row["label"],
            }

    agreement_by_question = defaultdict(list)
    agreement_by_depth_leaf = defaultdict(list)
    agreement_by_label = defaultdict(list)
    for group_key, counter in agreement_groups.items():
        total = sum(counter.values())
        if total < 2:
            continue
        majority = max(counter.values())
        pair_total = total * (total - 1)
        pair_agree = sum(count * (count - 1) for count in counter.values())
        majority_share = majority / total
        pairwise_agreement = pair_agree / pair_total if pair_total else 1.0
        meta = agreement_meta[group_key]
        item = {
            "majority_share": majority_share,
            "pairwise_agreement": pairwise_agreement,
            "reviewer_count": total,
        }
        agreement_by_question[meta["question"]].append(item)
        agreement_by_depth_leaf[(meta["question"], meta["depth"], meta["is_leaf"])].append(item)
        agreement_by_label[(meta["question"], meta["label"])].append(item)

    def agreement_summary(table_name: str, grouped: dict[Any, list[dict[str, float]]], fields: list[str]) -> None:
        for key, items in sorted(grouped.items(), key=lambda item: str(item[0])):
            key_tuple = key if isinstance(key, tuple) else (key,)
            out = {"table_name": table_name}
            out.update(dict(zip(fields, key_tuple)))
            out["overlap_item_count"] = len(items)
            out["avg_majority_share"] = mean([item["majority_share"] for item in items])
            out["avg_pairwise_agreement"] = mean([item["pairwise_agreement"] for item in items])
            out["avg_reviewers_per_item"] = mean([item["reviewer_count"] for item in items])
            rows.append(out)

    agreement_summary("agreement_by_question", agreement_by_question, ["question"])
    agreement_summary("agreement_by_depth_leaf", agreement_by_depth_leaf, ["question", "depth", "is_leaf"])
    agreement_summary("agreement_by_label", agreement_by_label, ["question", "label"])

    for rank_table in {
        "image_quality_summary",
        "node_problem_rank",
        "label_problem_rank",
        "label_feature_bins",
    }:
        rankable = [row for row in rows if row.get("table_name") == rank_table]
        rankable.sort(
            key=lambda row: (
                float(row.get("bad_node_rate") or 0),
                float(row.get("nonideal_node_rate") or 0),
                int(row.get("response_count") or row.get("nodes_answered") or 0),
            ),
            reverse=True,
        )
        for index, row in enumerate(rankable, start=1):
            row["rank_bad_rate"] = index

    return rows


def main() -> None:
    raise_field_limit()
    args = parse_args()
    input_csv = Path(args.input_csv) if args.input_csv else find_latest_input_csv()
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    print(f"Using input CSV: {input_csv}")

    manifest = load_manifest(manifest_path)
    details, targets, source_users, reviewer_row_updated_at = collect_rows(
        input_csv=input_csv,
        manifest=manifest,
        min_user=args.min_user,
        max_user=args.max_user,
    )

    user_suffix = f"user{args.min_user}_{args.max_user}"
    prefix = f"{input_csv.stem}_{user_suffix}"
    workbook_path = output_dir / f"{prefix}_analysis_workbook.xlsx"

    detail_preferred = [
        "reviewer_id",
        "user_number",
        "image_id",
        "node_id",
        "label",
        "path_label",
        "top_level_label",
        "parent_id",
        "parent_label",
        "depth",
        "is_leaf",
        "child_count",
        "actual",
        "bbox_area",
        "bbox_area_ratio",
        "bbox_area_bin",
        "instance_count",
        "instance_count_bin",
        "has_others_ancestor",
        "node_updated_at_utc",
        "node_updated_at_kst",
        "node_updated_date_kst",
        "node_updated_hour_kst",
        "answer_count",
        "answered_questions",
        "bad_flag",
        "nonideal_flag",
        "bad_question_count",
        "warning_question_count",
        "issue_score",
        "bad_questions",
        "warning_questions",
    ] + [f"answer_{key}" for key in ANSWER_COLUMNS]

    analysis_rows = build_analysis_tables(
        details=details,
        targets=targets,
        source_users=source_users,
        reviewer_row_updated_at=reviewer_row_updated_at,
        manifest=manifest,
        input_csv=input_csv,
        manifest_path=manifest_path,
        min_user=args.min_user,
        max_user=args.max_user,
    )
    analysis_preferred = [
        "table_name",
        "metric",
        "value",
        "reviewer_id",
        "user_number",
        "image_id",
        "node_id",
        "label",
        "question",
        "answer_value",
        "depth",
        "is_leaf",
        "date_kst",
        "hour_kst",
        "feature",
        "feature_value",
        "response_count",
        "group_total",
        "ratio",
        "nodes_answered",
        "target_nodes",
        "target_nodes_in_payload",
        "completion_rate",
        "bad_nodes",
        "bad_node_rate",
        "nonideal_nodes",
        "nonideal_node_rate",
        "avg_issue_score",
        "avg_depth",
        "rank_bad_rate",
        "first_updated_at_kst",
        "last_updated_at_kst",
    ]
    analysis_rows = sorted(analysis_rows, key=analysis_sort_key)

    workbook_sheets = build_workbook_sheets(details, analysis_rows, detail_preferred)
    write_xlsx_workbook(workbook_path, workbook_sheets)
    print(f"Wrote {workbook_path} ({len(workbook_sheets)} sheets; first sheet: node_response)")

    if args.write_csv:
        detail_path = output_dir / f"{prefix}_node_responses.csv"
        analysis_path = output_dir / f"{prefix}_analysis_tables.csv"
        combined_path = output_dir / f"{prefix}_combined_tables.csv"
        write_csv(detail_path, details, detail_preferred)
        write_csv(analysis_path, analysis_rows, analysis_preferred)
        combined_rows = [{"table_name": "node_response", **row} for row in details] + analysis_rows
        combined_preferred = ["table_name"] + detail_preferred + analysis_preferred
        write_csv(combined_path, combined_rows, combined_preferred)
        print(f"Wrote {detail_path} ({len(details)} node-response rows)")
        print(f"Wrote {analysis_path} ({len(analysis_rows)} table rows)")
        print(f"Wrote {combined_path} ({len(combined_rows)} combined rows)")

    if args.write_html:
        pretty_dir = write_pretty_table_csvs(output_dir, prefix, analysis_rows)
        report_path = pretty_dir / "index.html"
        write_html_report(report_path, prefix, pretty_dir, analysis_rows)
        print(f"Wrote {pretty_dir} (clean per-table CSVs)")
        print(f"Wrote {report_path} (HTML summary report)")


if __name__ == "__main__":
    main()

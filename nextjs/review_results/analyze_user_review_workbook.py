#!/usr/bin/env python3
"""Analyze an existing review workbook without rebuilding it.

Input:
    review_annotations_user_review_workbook.xlsx

Output:
    A folder with CSV tables, SVG charts, an HTML report, and an analysis xlsx.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
USER_RE = re.compile(r"^user(\d+)$")

YES = "\uc608"
NO = "\uc544\ub2c8\uc624"
UNCERTAIN = "\ud310\ub2e8\ubd88\uac00"
ALL_INCLUDED = "\ubaa8\ub450 \ud3ec\ud568\ud568"
SLIGHT_MISSING = "\uc57d\uac04 \ub193\uce68"
MANY_MISSING = "\ub9ce\uc774 \ub193\uce68"
NO_EXTRA = "\ud3ec\ud568\ud558\uc9c0 \uc54a\uc74c"
SLIGHT_EXTRA = "\uc57d\uac04 \ud3ec\ud568"
MANY_EXTRA = "\ub9ce\uc774 \ud3ec\ud568"
ACCURATE = "\uc815\ud655"
ACCEPTABLE = "\uc218\uc6a9 \uac00\ub2a5"
INACCURATE = "\ubd80\uc815\ud655"
FAIL = "\uc2e4\ud328"
NONE = "\uc5c6\uc74c"
SOME = "\uc870\uae08 \uc788\uc74c"
MANY = "\ub9ce\uc774 \uc788\uc74c"
MATCH = "\ub9de\uc74c"
MOSTLY_MATCH = "\ub300\uccb4\ub85c \ub9de\uc74c"
PARTIAL_MATCH = "\ubd80\ubd84\uc801\uc73c\ub85c \ub9de\uc74c"
NOT_MATCH = "\uc544\ub2d8"

QUESTION_COLUMNS = {
    "Q1": "answer_q1_label",
    "Q2": "answer_q2_mask_missing",
    "Q3": "answer_q3_mask_extra",
    "Q4": "answer_q4_instance",
    "Q5": "answer_q5_mask_quality",
    "Q6": "answer_q6_decomposition_nonleaf",
    "Q7": "answer_q7_missing_child_nonleaf",
    "Q8": "answer_q8_leaf_stop",
}

QUESTION_NAMES = {
    "Q1": "label_exists",
    "Q2": "mask_missing",
    "Q3": "mask_extra",
    "Q4": "instance_separation",
    "Q5": "mask_quality",
    "Q6": "decomposition_nonleaf",
    "Q7": "missing_child_nonleaf",
    "Q8": "leaf_stop",
}

GOOD = {
    "Q1": {YES},
    "Q2": {ALL_INCLUDED},
    "Q3": {NO_EXTRA},
    "Q4": {ACCURATE},
    "Q5": {ACCURATE},
    "Q6": {NONE},
    "Q7": {NONE},
    "Q8": {YES},
}

SOFT = {
    "Q1": {UNCERTAIN},
    "Q2": {SLIGHT_MISSING, UNCERTAIN},
    "Q3": {SLIGHT_EXTRA, UNCERTAIN},
    "Q4": {ACCEPTABLE, UNCERTAIN},
    "Q5": {ACCEPTABLE, UNCERTAIN},
    "Q6": {SOME, UNCERTAIN},
    "Q7": {SOME, UNCERTAIN},
    "Q8": {UNCERTAIN},
}

CRITICAL = {
    "Q1": {NO},
    "Q2": {MANY_MISSING},
    "Q3": {MANY_EXTRA},
    "Q4": {INACCURATE, FAIL},
    "Q5": {INACCURATE, FAIL},
    "Q6": {MANY},
    "Q7": {MANY},
    "Q8": {NO},
}

TREE_QUESTION_COLUMNS = {
    "T1": "answer_overall_consistency",
    "T2": "answer_missing_critical_nodes",
}

TREE_QUESTION_NAMES = {
    "T1": "overall_consistency",
    "T2": "missing_critical_nodes",
}

TREE_GOOD = {
    "T1": {MATCH},
    "T2": {NONE},
}

TREE_SOFT = {
    "T1": {MOSTLY_MATCH, PARTIAL_MATCH, UNCERTAIN},
    "T2": {SOME, UNCERTAIN},
}

TREE_CRITICAL = {
    "T1": {NOT_MATCH},
    "T2": {MANY},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", nargs="?", default="review_annotations_user_review_workbook.xlsx")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--min-label-rows", type=int, default=10)
    parser.add_argument("--min-image-rows", type=int, default=5)
    return parser.parse_args()


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    script_path = Path(__file__).resolve().parent / path
    return script_path


def user_sort_key(user: str) -> tuple[int, str]:
    match = USER_RE.match(str(user))
    return (int(match.group(1)), user) if match else (10**9, str(user))


def html_escape(value: Any) -> str:
    return str("" if value is None else value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def xlsx_escape(value: Any) -> str:
    return html_escape(value)


def cell_ref_to_col(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch.upper()) - ord("A") + 1)
    return value


def read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        xml = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings = []
    for item in xml.findall(f"{NS_MAIN}si"):
        strings.append("".join(text.text or "" for text in item.iter(f"{NS_MAIN}t")))
    return strings


def cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(f"{NS_MAIN}t"))
    value = cell.find(f"{NS_MAIN}v")
    raw = value.text if value is not None and value.text is not None else ""
    if cell_type == "s" and raw:
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def normalize_target(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def read_sheet(z: zipfile.ZipFile, target: str, shared_strings: list[str]) -> list[dict[str, str]]:
    xml = ET.fromstring(z.read(normalize_target(target)))
    raw_rows = []
    for row_el in xml.findall(f".//{NS_MAIN}sheetData/{NS_MAIN}row"):
        values: dict[int, str] = {}
        for cell in row_el.findall(f"{NS_MAIN}c"):
            ref = cell.get("r", "")
            if ref:
                values[cell_ref_to_col(ref)] = cell_text(cell, shared_strings)
        if values:
            raw_rows.append(values)
    if not raw_rows:
        return []
    headers = [raw_rows[0].get(i, "") for i in range(1, max(raw_rows[0]) + 1)]
    rows = []
    for raw in raw_rows[1:]:
        rows.append({header: raw.get(i, "") for i, header in enumerate(headers, 1) if header})
    return rows


def read_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(path) as z:
        shared_strings = read_shared_strings(z)
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{NS_REL}Relationship")}
        sheets = {}
        for sheet in workbook.findall(f".//{NS_MAIN}sheet"):
            name = sheet.get("name", "")
            rel_id = sheet.get(f"{NS_DOC_REL}id")
            target = rel_targets.get(rel_id, "")
            if name and target:
                sheets[name] = read_sheet(z, target, shared_strings)
        return sheets


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def pct(n: float, d: float) -> float:
    return round((n / d) * 100, 2) if d else 0.0


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def severity(slot: str, answer: str) -> int:
    if not answer:
        return -1
    if answer in CRITICAL.get(slot, set()):
        return 2
    if answer in SOFT.get(slot, set()):
        return 1
    if answer in GOOD.get(slot, set()):
        return 0
    return 1


def tree_severity(slot: str, answer: str) -> int:
    if not answer:
        return -1
    if answer in TREE_CRITICAL.get(slot, set()):
        return 2
    if answer in TREE_SOFT.get(slot, set()):
        return 1
    if answer in TREE_GOOD.get(slot, set()):
        return 0
    return 1


def severity_label(level: int) -> str:
    if level >= 2:
        return "critical"
    if level == 1:
        return "soft"
    if level == 0:
        return "good"
    return "blank"


def question_values(row: dict[str, str], q1_yes_only: bool = False) -> dict[str, str]:
    if q1_yes_only and row.get("answer_q1_label") != YES:
        return {}
    values = {}
    for slot, column in QUESTION_COLUMNS.items():
        if q1_yes_only and slot == "Q1":
            continue
        value = row.get(column, "")
        if value:
            values[slot] = value
    return values


def has_critical(row: dict[str, str], q1_yes_only: bool = False) -> bool:
    return any(severity(slot, answer) >= 2 for slot, answer in question_values(row, q1_yes_only).items())


def has_any_issue(row: dict[str, str], q1_yes_only: bool = False) -> bool:
    return any(severity(slot, answer) >= 1 for slot, answer in question_values(row, q1_yes_only).items())


def critical_question_counter(rows: list[dict[str, str]], q1_yes_only: bool = False) -> Counter:
    counter = Counter()
    for row in rows:
        for slot, answer in question_values(row, q1_yes_only).items():
            if severity(slot, answer) >= 2:
                counter[slot] += 1
    return counter


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


def group_rows(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, ""))].append(row)
    return groups


def summarize_group(items: list[dict[str, str]], q1_yes_only: bool = False) -> dict[str, Any]:
    q1 = Counter(row.get("answer_q1_label", "") for row in items)
    active_items = [row for row in items if (not q1_yes_only or row.get("answer_q1_label") == YES)]
    critical_nodes = sum(has_critical(row, q1_yes_only) for row in items)
    any_nodes = sum(has_any_issue(row, q1_yes_only) for row in items)
    q1_yes_count = q1[YES]
    return {
        "nodes": len(items),
        "active_nodes": len(active_items),
        "q1_yes": q1_yes_count,
        "q1_no": q1[NO],
        "q1_uncertain": q1[UNCERTAIN],
        "q1_yes_pct": pct(q1_yes_count, len(items)),
        "q1_no_pct": pct(q1[NO], len(items)),
        "q1_uncertain_pct": pct(q1[UNCERTAIN], len(items)),
        "critical_nodes": critical_nodes,
        "critical_node_rate_pct": pct(critical_nodes, len(active_items) if q1_yes_only else len(items)),
        "any_issue_nodes": any_nodes,
        "any_issue_node_rate_pct": pct(any_nodes, len(active_items) if q1_yes_only else len(items)),
        "leaf_nodes": sum(row.get("is_leaf") == "True" for row in items),
        "nonleaf_nodes": sum(row.get("is_leaf") == "False" for row in items),
        "avg_depth": mean([to_float(row.get("depth")) for row in items]),
        "avg_bbox_pct": mean([to_float(row.get("bbox_pct")) for row in items]),
        "avg_child_count": mean([to_float(row.get("child_count")) for row in items]),
        "avg_instance_count": mean([to_float(row.get("instance_count")) for row in items]),
    }


def overview_metrics(main_rows: list[dict[str, str]], tree_rows: list[dict[str, str]], user_image_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    users = sorted({row.get("id", "") for row in main_rows if row.get("id", "")}, key=user_sort_key)
    images = {row.get("image_id", "") for row in user_image_rows if row.get("image_id", "")}
    if not images:
        images = {row.get("image_id", "") for row in main_rows if row.get("image_id", "")}
    base = summarize_group(main_rows)
    q1_yes_base = summarize_group(main_rows, q1_yes_only=True)
    leaf_nodes = sum(row.get("is_leaf") == "True" for row in main_rows)
    return [
        {"metric": "users", "value": len(users), "note": "Expected user1-user20."},
        {"metric": "user_image_pairs", "value": len(user_image_rows) or "", "note": "Includes zero-reviewable-node images if present."},
        {"metric": "unique_images", "value": len(images), "note": "Unique image IDs present in workbook."},
        {"metric": "node_rows", "value": len(main_rows), "note": "Rows in main_node_summary."},
        {"metric": "tree_summary_rows", "value": len(tree_rows), "note": "Rows in tree_summary."},
        {"metric": "leaf_nodes", "value": leaf_nodes, "note": f"{pct(leaf_nodes, len(main_rows))}% of node rows."},
        {"metric": "nonleaf_nodes", "value": len(main_rows) - leaf_nodes, "note": ""},
        {"metric": "q1_yes_nodes", "value": base["q1_yes"], "note": f"{base['q1_yes_pct']}% of node rows."},
        {"metric": "q1_no_nodes", "value": base["q1_no"], "note": f"{base['q1_no_pct']}% of node rows."},
        {"metric": "q1_uncertain_nodes", "value": base["q1_uncertain"], "note": f"{base['q1_uncertain_pct']}% of node rows."},
        {"metric": "critical_issue_nodes_all", "value": base["critical_nodes"], "note": f"{base['critical_node_rate_pct']}% of all nodes."},
        {"metric": "any_issue_nodes_all", "value": base["any_issue_nodes"], "note": f"{base['any_issue_node_rate_pct']}% of all nodes."},
        {"metric": "critical_issue_nodes_q1_yes_only", "value": q1_yes_base["critical_nodes"], "note": f"{q1_yes_base['critical_node_rate_pct']}% among Q1=yes nodes, Q2-Q8 only."},
        {"metric": "any_issue_nodes_q1_yes_only", "value": q1_yes_base["any_issue_nodes"], "note": f"{q1_yes_base['any_issue_node_rate_pct']}% among Q1=yes nodes, Q2-Q8 only."},
        {"metric": "avg_depth", "value": base["avg_depth"], "note": ""},
        {"metric": "avg_bbox_pct", "value": base["avg_bbox_pct"], "note": "bbox area percentage of image, averaged over node rows."},
    ]


def user_quality(main_rows: list[dict[str, str]], user_image_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    image_counts = Counter()
    for row in user_image_rows:
        reviewer = row.get("reviewer_id", "") or row.get("id", "")
        if reviewer:
            image_counts[reviewer] += 1
    out = []
    for user, items in sorted(group_rows(main_rows, "id").items(), key=lambda item: user_sort_key(item[0])):
        base = summarize_group(items)
        q1_yes_base = summarize_group(items, q1_yes_only=True)
        out.append({
            "id": user,
            "nodes": base["nodes"],
            "images": image_counts[user] or len({row.get("image_id", "") for row in items}),
            "q1_yes_pct": base["q1_yes_pct"],
            "q1_no": base["q1_no"],
            "q1_uncertain": base["q1_uncertain"],
            "critical_nodes_all": base["critical_nodes"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "any_issue_nodes_all": base["any_issue_nodes"],
            "any_issue_rate_all_pct": base["any_issue_node_rate_pct"],
            "critical_nodes_q1_yes": q1_yes_base["critical_nodes"],
            "critical_rate_q1_yes_pct": q1_yes_base["critical_node_rate_pct"],
            "any_issue_nodes_q1_yes": q1_yes_base["any_issue_nodes"],
            "any_issue_rate_q1_yes_pct": q1_yes_base["any_issue_node_rate_pct"],
            "leaf_pct": pct(base["leaf_nodes"], base["nodes"]),
            "avg_depth": base["avg_depth"],
            "avg_bbox_pct": base["avg_bbox_pct"],
        })
    return out


def question_distribution(main_rows: list[dict[str, str]], q1_yes_only: bool = False) -> list[dict[str, Any]]:
    counters = {slot: Counter() for slot in QUESTION_COLUMNS}
    totals = Counter()
    for row in main_rows:
        if q1_yes_only and row.get("answer_q1_label") != YES:
            continue
        for slot, column in QUESTION_COLUMNS.items():
            if q1_yes_only and slot == "Q1":
                continue
            answer = row.get(column, "")
            if answer:
                counters[slot][answer] += 1
                totals[slot] += 1
    out = []
    for slot in sorted(counters):
        for answer, count in sorted(counters[slot].items(), key=lambda item: (severity(slot, item[0]), item[0])):
            total = totals[slot]
            level = severity(slot, answer)
            out.append({
                "scope": "q1_yes_only_q2_q8" if q1_yes_only else "all_answers",
                "question": slot,
                "question_name": QUESTION_NAMES[slot],
                "answer": answer,
                "severity": severity_label(level),
                "count": count,
                "total": total,
                "pct": pct(count, total),
            })
    return out


def depth_summary(main_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for depth_value, items in sorted(group_rows(main_rows, "depth").items(), key=lambda item: to_float(item[0])):
        base = summarize_group(items)
        q1_yes = summarize_group(items, q1_yes_only=True)
        out.append({
            "depth": depth_value,
            "nodes": base["nodes"],
            "leaf_pct": pct(base["leaf_nodes"], base["nodes"]),
            "q1_no_pct": base["q1_no_pct"],
            "q1_uncertain_pct": base["q1_uncertain_pct"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "any_issue_rate_all_pct": base["any_issue_node_rate_pct"],
            "critical_rate_q1_yes_pct": q1_yes["critical_node_rate_pct"],
            "any_issue_rate_q1_yes_pct": q1_yes["any_issue_node_rate_pct"],
            "avg_bbox_pct": base["avg_bbox_pct"],
            "avg_child_count": base["avg_child_count"],
        })
    return out


def depth_question_distribution(main_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counter: dict[tuple[str, str, str], int] = Counter()
    totals: dict[tuple[str, str], int] = Counter()
    for row in main_rows:
        if row.get("answer_q1_label") != YES:
            continue
        depth_value = row.get("depth", "")
        for slot, answer in question_values(row, q1_yes_only=True).items():
            counter[(depth_value, slot, answer)] += 1
            totals[(depth_value, slot)] += 1
    out = []
    for (depth_value, slot, answer), count in sorted(counter.items(), key=lambda item: (to_float(item[0][0]), item[0][1], severity(item[0][1], item[0][2]), item[0][2])):
        total = totals[(depth_value, slot)]
        out.append({
            "scope": "q1_yes_only_q2_q8",
            "depth": depth_value,
            "question": slot,
            "question_name": QUESTION_NAMES[slot],
            "answer": answer,
            "severity": severity_label(severity(slot, answer)),
            "count": count,
            "total": total,
            "pct": pct(count, total),
        })
    return out


def leaf_nonleaf_summary(main_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for value, group_name in [("True", "leaf"), ("False", "nonleaf")]:
        items = [row for row in main_rows if row.get("is_leaf") == value]
        base = summarize_group(items)
        q1_yes = summarize_group(items, q1_yes_only=True)
        q8_counter = Counter(row.get("answer_q8_leaf_stop", "") for row in items if row.get("answer_q8_leaf_stop", ""))
        out.append({
            "group": group_name,
            "nodes": base["nodes"],
            "q1_no_pct": base["q1_no_pct"],
            "q1_uncertain_pct": base["q1_uncertain_pct"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "any_issue_rate_all_pct": base["any_issue_node_rate_pct"],
            "critical_rate_q1_yes_pct": q1_yes["critical_node_rate_pct"],
            "any_issue_rate_q1_yes_pct": q1_yes["any_issue_node_rate_pct"],
            "q8_yes": q8_counter[YES],
            "q8_no": q8_counter[NO],
            "q8_uncertain": q8_counter[UNCERTAIN],
            "avg_depth": base["avg_depth"],
            "avg_bbox_pct": base["avg_bbox_pct"],
        })
    return out


def label_risk(main_rows: list[dict[str, str]], min_rows: int) -> list[dict[str, Any]]:
    out = []
    total_critical = sum(has_critical(row) for row in main_rows)
    for label, items in group_rows(main_rows, "label").items():
        if len(items) < min_rows:
            continue
        base = summarize_group(items)
        q1_yes = summarize_group(items, q1_yes_only=True)
        q_counter = critical_question_counter(items)
        top_questions = "|".join(f"{question}:{count}" for question, count in q_counter.most_common(5))
        out.append({
            "label": label,
            "node_rows": base["nodes"],
            "image_count": len({row.get("image_id", "") for row in items}),
            "reviewer_count": len({row.get("id", "") for row in items}),
            "q1_no_pct": base["q1_no_pct"],
            "q1_uncertain_pct": base["q1_uncertain_pct"],
            "critical_nodes_all": base["critical_nodes"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "critical_share_of_dataset_pct": pct(base["critical_nodes"], total_critical),
            "any_issue_rate_all_pct": base["any_issue_node_rate_pct"],
            "critical_rate_q1_yes_pct": q1_yes["critical_node_rate_pct"],
            "any_issue_rate_q1_yes_pct": q1_yes["any_issue_node_rate_pct"],
            "avg_depth": base["avg_depth"],
            "avg_bbox_pct": base["avg_bbox_pct"],
            "top_critical_questions": top_questions,
        })
    out.sort(key=lambda row: (row["critical_share_of_dataset_pct"], row["critical_rate_all_pct"], row["q1_no_pct"], row["node_rows"]), reverse=True)
    return out


def image_risk(main_rows: list[dict[str, str]], min_rows: int) -> list[dict[str, Any]]:
    out = []
    for image_id, items in group_rows(main_rows, "image_id").items():
        if len(items) < min_rows:
            continue
        base = summarize_group(items)
        q1_yes = summarize_group(items, q1_yes_only=True)
        out.append({
            "image_id": image_id,
            "node_rows": base["nodes"],
            "reviewer_count": len({row.get("id", "") for row in items}),
            "q1_no_pct": base["q1_no_pct"],
            "q1_uncertain_pct": base["q1_uncertain_pct"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "any_issue_rate_all_pct": base["any_issue_node_rate_pct"],
            "critical_rate_q1_yes_pct": q1_yes["critical_node_rate_pct"],
            "any_issue_rate_q1_yes_pct": q1_yes["any_issue_node_rate_pct"],
            "avg_depth": base["avg_depth"],
            "avg_bbox_pct": base["avg_bbox_pct"],
            "leaf_pct": pct(base["leaf_nodes"], base["nodes"]),
        })
    out.sort(key=lambda row: (row["critical_rate_all_pct"], row["any_issue_rate_all_pct"], row["node_rows"]), reverse=True)
    return out


def bbox_size_summary(main_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for bbox_size, items in sorted(group_rows(main_rows, "bbox_size").items()):
        base = summarize_group(items)
        q1_yes = summarize_group(items, q1_yes_only=True)
        out.append({
            "bbox_size": bbox_size or "missing",
            "nodes": base["nodes"],
            "q1_no_pct": base["q1_no_pct"],
            "critical_rate_all_pct": base["critical_node_rate_pct"],
            "critical_rate_q1_yes_pct": q1_yes["critical_node_rate_pct"],
            "any_issue_rate_q1_yes_pct": q1_yes["any_issue_node_rate_pct"],
            "avg_depth": base["avg_depth"],
            "avg_bbox_pct": base["avg_bbox_pct"],
        })
    return out


def tree_summary_distribution(tree_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counters = {slot: Counter() for slot in TREE_QUESTION_COLUMNS}
    totals = Counter()
    for row in tree_rows:
        for slot, column in TREE_QUESTION_COLUMNS.items():
            answer = row.get(column, "")
            if answer:
                counters[slot][answer] += 1
                totals[slot] += 1
    out = []
    for slot in sorted(counters):
        for answer, count in sorted(counters[slot].items(), key=lambda item: (tree_severity(slot, item[0]), item[0])):
            total = totals[slot]
            out.append({
                "question": slot,
                "question_name": TREE_QUESTION_NAMES[slot],
                "answer": answer,
                "severity": severity_label(tree_severity(slot, answer)),
                "count": count,
                "total": total,
                "pct": pct(count, total),
            })
    return out


def tree_image_risk(tree_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for row in tree_rows:
        t1 = row.get("answer_overall_consistency", "")
        t2 = row.get("answer_missing_critical_nodes", "")
        score = max(tree_severity("T1", t1), tree_severity("T2", t2))
        if score <= 0:
            continue
        out.append({
            "id": row.get("id", row.get("reviewer_id", "")),
            "image_id": row.get("image_id", ""),
            "tree_issue_severity": severity_label(score),
            "answer_overall_consistency": t1,
            "answer_missing_critical_nodes": t2,
            "summary_comment": row.get("answer_summary_comment", ""),
        })
    out.sort(key=lambda row: (2 if row["tree_issue_severity"] == "critical" else 1, row["id"], row["image_id"]), reverse=True)
    return out


def pruning_candidates(main_rows: list[dict[str, str]], label_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_nodes = len(main_rows)
    total_critical = sum(has_critical(row) for row in main_rows)
    total_any = sum(has_any_issue(row) for row in main_rows)
    out = []
    for row in label_rows:
        nodes = int(row["node_rows"])
        critical = int(row["critical_nodes_all"])
        any_issue = round(row["any_issue_rate_all_pct"] * nodes / 100)
        node_loss_pct = pct(nodes, total_nodes)
        critical_removed_pct = pct(critical, total_critical)
        any_removed_pct = pct(any_issue, total_any)
        benefit = round((critical_removed_pct + 0.5 * any_removed_pct) / max(node_loss_pct, 0.01), 3)
        out.append({
            "label": row["label"],
            "node_rows_removed": nodes,
            "node_loss_pct": node_loss_pct,
            "critical_removed": critical,
            "critical_removed_share_pct": critical_removed_pct,
            "any_issue_removed_est": any_issue,
            "any_issue_removed_share_pct": any_removed_pct,
            "q1_no_pct": row["q1_no_pct"],
            "critical_rate_all_pct": row["critical_rate_all_pct"],
            "benefit_per_node_loss": benefit,
            "suggested_use": "inspect_or_prune_candidate" if benefit >= 1.5 and nodes >= 10 else "monitor",
        })
    out.sort(key=lambda row: (row["benefit_per_node_loss"], row["critical_removed_share_pct"], row["node_rows_removed"]), reverse=True)
    return out


def pruning_policy_simulation(main_rows: list[dict[str, str]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_nodes = len(main_rows)
    total_critical = sum(has_critical(row) for row in main_rows)
    policies = [
        ("top_10_benefit_labels", {row["label"] for row in candidates[:10]}),
        ("q1_no_rate_ge_20_min10", {row["label"] for row in candidates if row["q1_no_pct"] >= 20 and row["node_rows_removed"] >= 10}),
        ("critical_rate_ge_30_min10", {row["label"] for row in candidates if row["critical_rate_all_pct"] >= 30 and row["node_rows_removed"] >= 10}),
        ("benefit_ge_2_min10", {row["label"] for row in candidates if row["benefit_per_node_loss"] >= 2 and row["node_rows_removed"] >= 10}),
    ]
    out = []
    for policy, labels in policies:
        removed = [row for row in main_rows if row.get("label") in labels]
        removed_critical = sum(has_critical(row) for row in removed)
        remaining_nodes = total_nodes - len(removed)
        remaining_critical = total_critical - removed_critical
        out.append({
            "policy": policy,
            "labels_removed": len(labels),
            "nodes_removed": len(removed),
            "node_loss_pct": pct(len(removed), total_nodes),
            "critical_removed": removed_critical,
            "critical_removed_share_pct": pct(removed_critical, total_critical),
            "baseline_critical_rate_pct": pct(total_critical, total_nodes),
            "remaining_critical_rate_pct": pct(remaining_critical, remaining_nodes),
            "labels": "|".join(sorted(labels)[:50]),
        })
    return out


def insight_recommendations(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    overview = {row["metric"]: row for row in tables["overview_metrics"]}
    out.append({
        "priority": "P0",
        "topic": "Use Q1=yes conditioned statistics",
        "evidence": overview["q1_no_nodes"]["note"] + "; " + overview["q1_uncertain_nodes"]["note"],
        "suggested_action": "Report Q1 distribution separately, then analyze Q2-Q8 on Q1=yes nodes to avoid auto-filled uncertain answers dominating mask quality statistics.",
        "source_table": "question_distribution_q1_yes",
    })
    if tables["label_pruning_candidates"]:
        top = tables["label_pruning_candidates"][0]
        out.append({
            "priority": "P1",
            "topic": "Label-level pruning candidate",
            "evidence": f"{top['label']} removes {top['critical_removed_share_pct']}% of critical nodes at {top['node_loss_pct']}% node loss.",
            "suggested_action": "Inspect high-benefit labels before training/evaluation; prune only if they are systematic ontology artifacts or impossible/ambiguous labels.",
            "source_table": "label_pruning_candidates",
        })
    high_depth = [row for row in tables["depth_summary"] if row["nodes"] >= 100]
    if high_depth:
        worst = max(high_depth, key=lambda row: row["critical_rate_q1_yes_pct"])
        out.append({
            "priority": "P1",
            "topic": "Depth-sensitive quality",
            "evidence": f"Depth {worst['depth']} has {worst['critical_rate_q1_yes_pct']}% Q1=yes critical rate across {worst['nodes']} nodes.",
            "suggested_action": "Use depth-stratified reporting and consider stricter review or pruning for deep nodes if the high-depth risk persists.",
            "source_table": "depth_summary",
        })
    if tables["image_risk"]:
        worst_img = tables["image_risk"][0]
        out.append({
            "priority": "P1",
            "topic": "Image-level outlier",
            "evidence": f"Image {worst_img['image_id']} has {worst_img['critical_rate_all_pct']}% all-critical rate over {worst_img['node_rows']} nodes.",
            "suggested_action": "Open top image outliers manually; bad images can drive label statistics and should be fixed or excluded before model conclusions.",
            "source_table": "image_risk",
        })
    if tables["tree_summary_distribution"]:
        critical_tree = sum(row["count"] for row in tables["tree_summary_distribution"] if row["severity"] == "critical")
        total_tree = sum(row["count"] for row in tables["tree_summary_distribution"])
        out.append({
            "priority": "P2",
            "topic": "Whole-tree quality",
            "evidence": f"Tree-level critical answer count is {critical_tree}/{total_tree} ({pct(critical_tree, total_tree)}%).",
            "suggested_action": "Use tree-level answers as an image-level filter or as a covariate when interpreting node-level error rates.",
            "source_table": "tree_summary_distribution",
        })
    if tables["bbox_size_summary"]:
        worst_bbox = max(tables["bbox_size_summary"], key=lambda row: row["critical_rate_q1_yes_pct"])
        out.append({
            "priority": "P2",
            "topic": "Size-sensitive quality",
            "evidence": f"bbox_size={worst_bbox['bbox_size']} has {worst_bbox['critical_rate_q1_yes_pct']}% Q1=yes critical rate.",
            "suggested_action": "Report bbox-size-stratified metrics; small objects may need different pruning/review policy than large masks.",
            "source_table": "bbox_size_summary",
        })
    return out


def col_name(index: int) -> str:
    out = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        out = chr(65 + remainder) + out
    return out


def is_number(value: Any, column: str) -> bool:
    if value in ("", None):
        return False
    if column.endswith("_id") or column in {"id", "label", "question", "answer", "policy", "topic", "source_table"}:
        return False
    if isinstance(value, (int, float)):
        return True
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", str(value)))


def xlsx_cell(row: int, col: int, column: str, value: Any, header: bool = False) -> str:
    if value in ("", None):
        return ""
    ref = f"{col_name(col)}{row}"
    style = ' s="1"' if header else ""
    if not header and is_number(value, column):
        return f'<c r="{ref}"{style}><v>{xlsx_escape(value)}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{xlsx_escape(value)}</t></is></c>'


def table_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def sheet_xml(rows: list[dict[str, Any]], columns: list[str]) -> str:
    last = f"{col_name(max(len(columns), 1))}{max(len(rows) + 1, 1)}"
    col_xml = "".join(f'<col min="{i}" max="{i}" width="{min(max(len(col) + 2, 10), 36)}" customWidth="1"/>' for i, col in enumerate(columns, 1))
    row_xml = ['<row r="1">' + "".join(xlsx_cell(1, i, col, col, True) for i, col in enumerate(columns, 1)) + "</row>"]
    for row_index, row in enumerate(rows, 2):
        row_xml.append(f'<row r="{row_index}">' + "".join(xlsx_cell(row_index, col_index, col, row.get(col, "")) for col_index, col in enumerate(columns, 1)) + "</row>")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:{last}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{col_xml}</cols><sheetData>{''.join(row_xml)}</sheetData><autoFilter ref="A1:{last}"/></worksheet>'''


def write_xlsx(path: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    names = [name for name, rows in tables.items() if rows]
    workbook_sheets = "".join(f'<sheet name="{xlsx_escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>' for index, name in enumerate(names, 1))
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets></workbook>'''
    wb_rels = "".join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(names) + 1))
    wb_rels += f'<Relationship Id="rId{len(names)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    content_sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for index in range(1, len(names) + 1))
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2F5D7C"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{content_sheets}</Types>''')
        z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{wb_rels}</Relationships>''')
        z.writestr("xl/styles.xml", styles)
        for index, name in enumerate(names, 1):
            columns = table_columns(tables[name])
            z.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml(tables[name], columns))


def table_html(rows: list[dict[str, Any]], max_rows: int = 15) -> str:
    if not rows:
        return "<p class=\"empty\">No rows.</p>"
    columns = table_columns(rows)
    body = []
    for row in rows[:max_rows]:
        body.append("<tr>" + "".join(f"<td>{html_escape(row.get(col, ''))}</td>" for col in columns) + "</tr>")
    more = f"<caption>Showing {min(len(rows), max_rows)} of {len(rows)} rows</caption>" if len(rows) > max_rows else ""
    return f"<table>{more}<thead><tr>{''.join(f'<th>{html_escape(col)}</th>' for col in columns)}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def horizontal_bar_svg(rows: list[dict[str, Any]], label_key: str, value_key: str, title: str, max_rows: int = 12, suffix: str = "%") -> str:
    chart_rows = [row for row in rows if to_float(row.get(value_key)) > 0][:max_rows]
    width = 680
    row_h = 28
    left = 190
    top = 42
    height = max(120, top + row_h * len(chart_rows) + 26)
    max_value = max([to_float(row.get(value_key)) for row in chart_rows] or [1])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="16" y="24" font-size="16" font-weight="700" fill="#212529">{html_escape(title)}</text>',
    ]
    for index, row in enumerate(chart_rows):
        y = top + index * row_h
        value = to_float(row.get(value_key))
        bar_w = (width - left - 90) * value / max_value if max_value else 0
        label = str(row.get(label_key, ""))[:28]
        parts.append(f'<text x="16" y="{y + 17}" font-size="12" fill="#343a40">{html_escape(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y + 3}" width="{bar_w:.1f}" height="18" rx="3" fill="#2f9e44"/>')
        parts.append(f'<text x="{left + bar_w + 8:.1f}" y="{y + 17}" font-size="12" fill="#495057">{html_escape(value)}{suffix}</text>')
    parts.append("</svg>")
    return "".join(parts)


def write_svg(path: Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def write_html_report(path: Path, workbook: Path, tables: dict[str, list[dict[str, Any]]], graph_paths: dict[str, Path]) -> None:
    sections = [
        ("overview_metrics", "Overview", "High-level dataset and quality metrics.", None),
        ("insight_recommendations", "Insight Recommendations", "Action-oriented interpretation for pruning, filtering, and reporting.", None),
        ("user_quality", "User Quality", "Reviewer-level quality and response patterns.", "user_quality.svg"),
        ("question_distribution_all", "Question Distribution: All Answers", "All responses, including auto-filled answers after Q1=no/uncertain.", None),
        ("question_distribution_q1_yes", "Question Distribution: Q1=Yes Only", "Q2-Q8 responses restricted to nodes where Q1=yes.", None),
        ("depth_summary", "Depth Summary", "Quality changes by tree depth.", "depth_summary.svg"),
        ("depth_question_distribution", "Depth x Question", "Depth-conditioned answer distribution on Q1=yes nodes.", None),
        ("leaf_nonleaf_summary", "Leaf vs Non-Leaf", "Leaf/non-leaf comparison and Q8 leaf-stop behavior.", "leaf_nonleaf_summary.svg"),
        ("label_risk", "Label Risk", "Labels that contribute disproportionately to bad or uncertain outcomes.", "label_risk.svg"),
        ("label_pruning_candidates", "Label Pruning Candidates", "Estimated benefit if labels are inspected, merged, or pruned.", "label_pruning_candidates.svg"),
        ("pruning_policy_simulation", "Pruning Policy Simulation", "Coarse removal policies and their impact on critical-rate reduction.", "pruning_policy_simulation.svg"),
        ("image_risk", "Image Risk", "Images that appear to make the dataset look worse.", "image_risk.svg"),
        ("bbox_size_summary", "BBox Size Summary", "Issue rates by object/mask size bucket.", "bbox_size_summary.svg"),
        ("tree_summary_distribution", "Tree Summary Distribution", "Whole-tree response patterns.", "tree_summary_distribution.svg"),
        ("tree_image_risk", "Tree Image Risk", "Images with non-good tree-level answers.", None),
    ]
    nav = "".join(f'<a href="#{name}">{title}</a>' for name, title, _, _ in sections if name in tables)
    cards = []
    for name, title, description, graph_name in sections:
        if name not in tables:
            continue
        graph_html = ""
        if graph_name and graph_name in graph_paths:
            graph_html = graph_paths[graph_name].read_text(encoding="utf-8")
        cards.append(f'''
<section id="{name}" class="page">
  <header><h2>{html_escape(title)}</h2><p>{html_escape(description)}</p></header>
  <div class="panel">
    <div class="tableWrap">{table_html(tables[name], 18)}</div>
    <div class="chartWrap">{graph_html}</div>
  </div>
</section>''')
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Workbook Analysis Report</title>
<style>
body {{ margin:0; font-family: Arial, sans-serif; color:#212529; background:#f8f9fa; }}
.top {{ padding:28px 36px; background:#1f2937; color:white; }}
.top h1 {{ margin:0 0 8px; font-size:28px; }}
.top p {{ margin:0; color:#d1d5db; }}
nav {{ display:flex; gap:8px; flex-wrap:wrap; padding:14px 36px; background:white; border-bottom:1px solid #dee2e6; position:sticky; top:0; z-index:1; }}
nav a {{ color:#1c7ed6; text-decoration:none; font-size:13px; border:1px solid #d0ebff; padding:5px 8px; border-radius:4px; }}
.page {{ padding:30px 36px; page-break-after:always; }}
.page header h2 {{ margin:0 0 4px; font-size:22px; }}
.page header p {{ margin:0 0 16px; color:#495057; }}
.panel {{ display:grid; grid-template-columns:minmax(0, 1.2fr) minmax(380px, .8fr); gap:18px; align-items:start; }}
.tableWrap, .chartWrap {{ background:white; border:1px solid #dee2e6; border-radius:6px; padding:12px; overflow:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:12px; }}
caption {{ caption-side:bottom; text-align:left; padding-top:8px; color:#868e96; }}
th {{ background:#2f5d7c; color:white; position:sticky; top:0; }}
th, td {{ border:1px solid #dee2e6; padding:5px 7px; text-align:left; white-space:nowrap; }}
td {{ background:#fff; }}
.empty {{ color:#868e96; }}
@media (max-width: 980px) {{ .panel {{ grid-template-columns:1fr; }} nav {{ position:static; }} }}
</style>
</head>
<body>
<div class="top">
  <h1>Workbook Analysis Report</h1>
  <p>Workbook: {html_escape(workbook)} · Generated UTC: {datetime.now(timezone.utc).isoformat()}</p>
</div>
<nav>{nav}</nav>
{''.join(cards)}
</body>
</html>'''
    path.write_text(html, encoding="utf-8")


def build_tables(sheets: dict[str, list[dict[str, str]]], min_label_rows: int, min_image_rows: int) -> dict[str, list[dict[str, Any]]]:
    main_rows = sheets.get("main_node_summary") or sheets.get("main_node_rows") or []
    tree_rows = sheets.get("tree_summary", [])
    user_image_rows = sheets.get("user_image_summary", [])
    if not main_rows:
        raise SystemExit("Workbook does not contain main_node_summary.")
    tables: dict[str, list[dict[str, Any]]] = {}
    tables["overview_metrics"] = overview_metrics(main_rows, tree_rows, user_image_rows)
    tables["user_quality"] = user_quality(main_rows, user_image_rows)
    tables["question_distribution_all"] = question_distribution(main_rows, q1_yes_only=False)
    tables["question_distribution_q1_yes"] = question_distribution(main_rows, q1_yes_only=True)
    tables["depth_summary"] = depth_summary(main_rows)
    tables["depth_question_distribution"] = depth_question_distribution(main_rows)
    tables["leaf_nonleaf_summary"] = leaf_nonleaf_summary(main_rows)
    tables["label_risk"] = label_risk(main_rows, min_label_rows)
    tables["image_risk"] = image_risk(main_rows, min_image_rows)
    tables["bbox_size_summary"] = bbox_size_summary(main_rows)
    tables["tree_summary_distribution"] = tree_summary_distribution(tree_rows)
    tables["tree_image_risk"] = tree_image_risk(tree_rows)
    tables["label_pruning_candidates"] = pruning_candidates(main_rows, tables["label_risk"])
    tables["pruning_policy_simulation"] = pruning_policy_simulation(main_rows, tables["label_pruning_candidates"])
    tables["insight_recommendations"] = insight_recommendations(tables)
    return tables


def write_outputs(workbook: Path, output_dir: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    table_dir = output_dir / "tables"
    graph_dir = output_dir / "graphs"
    for name, rows in tables.items():
        write_csv(table_dir / f"{name}.csv", rows)
    graph_specs = {
        "user_quality.svg": ("user_quality", "id", "critical_rate_q1_yes_pct", "User critical rate, Q1=yes"),
        "depth_summary.svg": ("depth_summary", "depth", "critical_rate_q1_yes_pct", "Critical rate by depth, Q1=yes"),
        "leaf_nonleaf_summary.svg": ("leaf_nonleaf_summary", "group", "critical_rate_q1_yes_pct", "Leaf vs non-leaf critical rate"),
        "label_risk.svg": ("label_risk", "label", "critical_share_of_dataset_pct", "Top labels by critical share"),
        "label_pruning_candidates.svg": ("label_pruning_candidates", "label", "benefit_per_node_loss", "Pruning benefit per node loss"),
        "pruning_policy_simulation.svg": ("pruning_policy_simulation", "policy", "critical_removed_share_pct", "Critical removed by policy"),
        "image_risk.svg": ("image_risk", "image_id", "critical_rate_all_pct", "Worst images by critical rate"),
        "bbox_size_summary.svg": ("bbox_size_summary", "bbox_size", "critical_rate_q1_yes_pct", "Critical rate by bbox size"),
        "tree_summary_distribution.svg": ("tree_summary_distribution", "answer", "pct", "Tree answer distribution"),
    }
    graph_paths = {}
    for filename, (table_name, label_key, value_key, title) in graph_specs.items():
        rows = sorted(tables.get(table_name, []), key=lambda row: to_float(row.get(value_key)), reverse=True)
        svg = horizontal_bar_svg(rows, label_key, value_key, title, suffix="" if value_key == "benefit_per_node_loss" else "%")
        graph_path = graph_dir / filename
        write_svg(graph_path, svg)
        graph_paths[filename] = graph_path
    write_xlsx(output_dir / "workbook_analysis_tables.xlsx", tables)
    write_html_report(output_dir / "workbook_analysis_report.html", workbook, tables, graph_paths)


def main() -> None:
    args = parse_args()
    workbook = resolve_path(args.workbook)
    output_dir = Path(args.output_dir) if args.output_dir else workbook.with_name(f"{workbook.stem}_analysis")
    sheets = read_workbook(workbook)
    tables = build_tables(sheets, args.min_label_rows, args.min_image_rows)
    write_outputs(workbook, output_dir, tables)
    print(f"Wrote {output_dir / 'workbook_analysis_report.html'}")
    print(f"Wrote {output_dir / 'workbook_analysis_tables.xlsx'}")
    for name, rows in tables.items():
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main()

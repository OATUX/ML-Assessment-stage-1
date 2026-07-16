#!/usr/bin/env python3
"""
GTMA Stage 1 Auto-Scorer
Usage: python score_submission.py <path_to_submission.md>
       or: python score_submission.py (paste markdown, then Ctrl+D)

Reads candidate submission markdown and scores against rubric in questions.yaml.
"""

import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("Installing pyyaml...")
    os.system("pip install pyyaml")
    import yaml


def load_questions(path="questions.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def extract_candidate_id(body):
    m = re.search(r"Candidate ID:\s*(\S+)", body, re.IGNORECASE)
    return m.group(1) if m else "UNKNOWN"


def extract_answer(body, q_id):
    parts = q_id.replace("q", "").split("_")
    dot = f"{parts[0]}.{parts[1]}"
    # Match "### Question X.Y" or "### Question X.Y: title"
    pat = rf"###\s*Question\s*{re.escape(dot)}(?:\s*[:\-]\s*[^\n]*)?\n(.*?)"
    pat += r"(?=###\s*Question|##\s*Section|#{3,}|\Z)"
    m = re.search(pat, body, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: looser match
    pat2 = rf"Question\s*{re.escape(dot)}.*?\n(.*?)"
    pat2 += r"(?=Question\s*\d+\.\d+|##\s*Section|#{3,}|\Z)"
    m2 = re.search(pat2, body, re.DOTALL | re.IGNORECASE)
    return m2.group(1).strip() if m2 else ""


def check_keywords(answer, keywords):
    if not keywords:
        return True
    lo = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lo)
    return hits >= max(1, len(keywords) // 3)


def score_question(body, question):
    ans = extract_answer(body, question["id"])
    if not ans or len(ans.strip()) < 50:
        return {
            "question_id": question["id"],
            "score": 0,
            "max_points": question["points"],
            "criteria": [{"criterion": "No answer or too short",
                          "matched": False, "points": 0}],
            "answer_length": len(ans) if ans else 0
        }

    criteria_results, total = [], 0
    for criterion in question.get("rubric", []):
        matched = check_keywords(ans, criterion.get("keywords", []))
        pts = criterion["points"] if matched else 0
        total += pts
        criteria_results.append({
            "criterion": criterion["criterion"],
            "matched": matched,
            "points": pts,
            "keywords_found": [kw for kw in criterion.get("keywords", [])
                               if kw.lower() in ans.lower()]
        })

    return {
        "question_id": question["id"],
        "score": total,
        "max_points": question["points"],
        "criteria": criteria_results,
        "answer_length": len(ans)
    }


def score_submission(body, questions):
    res = {
        "candidate_id": extract_candidate_id(body),
        "total_score": 0,
        "max_points": questions["assessment"]["total_points"],
        "pass_threshold": questions["assessment"]["pass_threshold"],
        "critical_fail": False,
        "sections": [],
        "critical_questions": [],
        "feedback": []
    }

    for section in questions["assessment"]["sections"]:
        sec = {"name": section["name"], "score": 0, "max_points": section["points"]}
        for question in section["questions"]:
            qr = score_question(body, question)
            sec["score"] += qr["score"]
            res["total_score"] += qr["score"]
            if question.get("is_critical", False):
                res["critical_questions"].append({
                    "id": question["id"],
                    "score": qr["score"],
                    "max_points": question["points"]
                })
                if qr["score"] == 0:
                    res["critical_fail"] = True
            res["feedback"].append(qr)
        res["sections"].append(sec)

    return res


def print_results(results):
    print("=" * 60)
    print("GTMA STAGE 1 SCORING RESULTS")
    print("=" * 60)
    print(f"Candidate ID: {results['candidate_id']}")
    print(f"Score: {results['total_score']} / {results['max_points']}")
    print(f"Pass Threshold: {results['pass_threshold']}")

    if results["critical_fail"]:
        print(f"Status: FAIL (Critical Question Scored Zero)")
    elif results["total_score"] >= results["pass_threshold"]:
        print(f"Status: PASS")
    else:
        print(f"Status: FAIL (Below Threshold)")

    print()
    print("Section Breakdown:")
    for s in results["sections"]:
        pct = (s["score"] / s["max_points"] * 100) if s["max_points"] > 0 else 0
        print(f"  {s['name']}: {s['score']}/{s['max_points']} ({pct:.0f}%)")

    print()
    print("Critical Questions:")
    for cq in results["critical_questions"]:
        status = "PASS" if cq["score"] > 0 else "FAIL"
        print(f"  {cq['id']}: {cq['score']}/{cq['max_points']} [{status}]")

    print()
    print("Detailed Feedback:")
    for fb in results["feedback"]:
        q_num = fb["question_id"].replace("q", "").replace("_", ".")
        pct = (fb["score"] / fb["max_points"] * 100) if fb["max_points"] > 0 else 0
        print(f"  Q{q_num}: {fb['score']}/{fb['max_points']} ({pct:.0f}%) - {fb['answer_length']} chars")
        if fb["score"] > 0:
            matched = [c["criterion"] for c in fb["criteria"] if c["matched"]]
            if matched:
                print(f"    Criteria met: {', '.join(matched)}")
        else:
            missed = [c["criterion"] for c in fb["criteria"] if not c["matched"]]
            if missed:
                print(f"    Missing: {', '.join(missed)}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Score GTMA Stage 1 submission")
    parser.add_argument("file", nargs="?", help="Path to submission markdown file")
    parser.add_argument("--questions", default="questions.yaml", help="Path to questions YAML")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            body = f.read()
    else:
        print("Paste submission markdown below, then press Ctrl+D (Unix) or Ctrl+Z then Enter (Windows):")
        body = sys.stdin.read()

    if not body.strip():
        print("Error: No submission content provided.", file=sys.stderr)
        sys.exit(1)

    questions = load_questions(args.questions)
    results = score_submission(body, questions)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_results(results)

    # Exit code: 0 = pass, 1 = fail
    if results["critical_fail"] or results["total_score"] < results["pass_threshold"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

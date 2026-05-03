import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.storage import list_research_runs  # noqa: E402


def score_report(run: dict, case: dict | None = None) -> dict:
    report = run.get("report", "")
    feedback = run.get("feedback", "")
    sources = run.get("sources", [])
    required_sections = (case or {}).get(
        "required_sections",
        ["Introduction", "Key Findings", "Conclusion", "Sources"],
    )
    min_citations = (case or {}).get("min_citations", 2)
    min_sources = (case or {}).get("min_sources", 3)

    citations = {item for item in re.findall(r"\[(\d+)\]", report)}
    section_hits = [
        section
        for section in required_sections
        if re.search(rf"#+\s*{re.escape(section)}", report, flags=re.I)
    ]

    checks = {
        "has_required_sections": len(section_hits) == len(required_sections),
        "has_enough_citations": len(citations) >= min_citations,
        "has_enough_sources": len(sources) >= min_sources,
        "has_critic_feedback": len(feedback.strip()) > 120,
    }
    score = round(sum(checks.values()) / len(checks), 2)
    return {
        "topic": run.get("topic"),
        "score": score,
        "checks": checks,
        "citations": sorted(citations),
        "source_count": len(sources),
    }


def main() -> None:
    cases_path = Path(__file__).with_name("cases.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    runs = list_research_runs(limit=50)

    if not runs:
        print("No saved research runs found. Run the app once, then rerun evals.")
        return

    case_by_topic = {case["topic"].lower(): case for case in cases}
    results = [
        score_report(run, case_by_topic.get(run["topic"].lower()))
        for run in runs
    ]

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

import re

from app.agents import build_critic_chain, build_writer_chain
from app.schemas import Finding, ScrapeAttempt, Source, StructuredReport
from app.tools import format_sources, scrape_url_content, search_sources


class ResearchPipelineError(Exception):
    def __init__(self, message: str, state: dict):
        super().__init__(message)
        self.state = state


def normalize_content(value) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts = []
        for item in value:
            parts.append(normalize_content(item))
        return "\n".join(part for part in parts if part)

    if isinstance(value, dict):
        if "text" in value:
            return normalize_content(value["text"])
        if "content" in value:
            return normalize_content(value["content"])
        if "title" in value or "url" in value or "snippet" in value:
            return "\n".join(
                part
                for part in (
                    f"Title: {value.get('title', '')}" if value.get("title") else "",
                    f"URL: {value.get('url', '')}" if value.get("url") else "",
                    f"Snippet: {value.get('snippet') or value.get('content', '')}"
                    if value.get("snippet") or value.get("content")
                    else "",
                )
                if part
            )
        return "\n".join(
            f"{key}: {normalize_content(item)}" for key, item in value.items()
        )

    return str(value)


def parse_structured_report(report: str, sources: list[dict]) -> dict:
    sections = {
        "introduction": "",
        "key_findings": "",
        "conclusion": "",
        "sources": "",
    }
    current = None
    for line in report.splitlines():
        heading = line.strip().lower().lstrip("#").strip()
        if heading.startswith("introduction"):
            current = "introduction"
            continue
        if heading.startswith("key findings"):
            current = "key_findings"
            continue
        if heading.startswith("conclusion"):
            current = "conclusion"
            continue
        if heading.startswith("sources"):
            current = "sources"
            continue
        if current:
            sections[current] += line + "\n"

    citation_ids = sorted({int(item) for item in re.findall(r"\[(\d+)\]", report)})
    typed_sources = [Source.model_validate(source) for source in sources]
    source_map = {source.id: source for source in typed_sources}
    cited_sources = [
        source_map[citation_id]
        for citation_id in citation_ids
        if citation_id in source_map
    ]

    findings = []
    for line in sections["key_findings"].splitlines():
        cleaned = line.strip().lstrip("-*").strip()
        if not cleaned:
            continue
        citations = [int(item) for item in re.findall(r"\[(\d+)\]", cleaned)]
        claim = re.sub(r"\*\*", "", cleaned).split(".")[0].strip()
        findings.append(
            Finding(
                claim=claim[:220],
                explanation=cleaned,
                citations=citations,
            )
        )

    structured = StructuredReport(
        introduction=sections["introduction"].strip(),
        findings=findings,
        conclusion=sections["conclusion"].strip(),
        sources=cited_sources or typed_sources,
        citation_ids=citation_ids,
        citation_coverage=round(len(cited_sources) / max(len(typed_sources), 1), 2),
    )
    return structured.model_dump()


def scrape_with_fallback(sources: list[dict], max_attempts: int = 3) -> tuple[str, list[dict]]:
    attempts = []
    for source in sorted(sources, key=lambda item: item.get("score", 0), reverse=True)[:max_attempts]:
        try:
            text = scrape_url_content(source["url"])
            source["scrape_status"] = "success"
            attempts.append(
                ScrapeAttempt(
                    source_id=source["id"],
                    url=source["url"],
                    status="success",
                ).model_dump()
            )
            return text, attempts
        except Exception as exc:
            source["scrape_status"] = "failed"
            source["scrape_error"] = str(exc)
            attempts.append(
                ScrapeAttempt(
                    source_id=source["id"],
                    url=source["url"],
                    status="failed",
                    error=str(exc),
                ).model_dump()
            )

    fallback = "\n\n".join(
        f"[{source['id']}] {source['title']}: {source['snippet']}"
        for source in sources
    )
    return fallback, attempts


def run_research_pipeline_events(topic: str, raise_on_error: bool = False):
    state = {
        "search_results": "",
        "sources": [],
        "scrape_attempts": [],
        "web_scrap_results": "",
        "report": "",
        "structured_report": {},
        "feedback": "",
    }

    def fail(step: str, field: str, message: str, exc: Exception):
        state[field] = f"{message}: {exc}"
        event = {
            "event": "error",
            "step": step,
            "field": field,
            "value": state[field],
            "state": state,
            "error": message,
        }
        if raise_on_error:
            raise ResearchPipelineError(message, state) from exc
        return event

    yield {"event": "started", "step": "search", "state": state}

    print("\n*------------------------------------------------------*\n")
    print("Step 1 - Search agent is working...")
    print("\n*------------------------------------------------------*\n")

    yield {"event": "step_started", "step": "search", "state": state}

    try:
        state["sources"] = search_sources(
            query=f"recent reliable detailed information about {topic}",
            max_results=5,
        )
        state["search_results"] = format_sources(state["sources"])
        yield {
            "event": "step_completed",
            "step": "search",
            "field": "search_results",
            "value": state["search_results"],
            "sources": state["sources"],
            "state": state,
        }
    except Exception as exc:
        yield fail("search", "search_results", "Search agent failed", exc)
        return

    print("\n*------------------------------------------------------*\n")
    print("Step 2 - Web Scrapping agent is working...")
    print("\n*------------------------------------------------------*\n")

    yield {"event": "step_started", "step": "scrape", "state": state}

    try:
        state["web_scrap_results"], state["scrape_attempts"] = scrape_with_fallback(
            state["sources"],
            max_attempts=3,
        )
        yield {
            "event": "step_completed",
            "step": "scrape",
            "field": "web_scrap_results",
            "value": state["web_scrap_results"],
            "state": state,
        }
    except Exception as exc:
        yield fail("scrape", "web_scrap_results", "Web scraping agent failed", exc)
        return

    print("\n*------------------------------------------------------*\n")
    print("Step 3 - Writer Chain Drafting The Report...")
    print("\n*------------------------------------------------------*\n")

    yield {"event": "step_started", "step": "draft", "state": state}

    research_combined = (
        f"SEARCH RESULTS WITH CITATION IDS: \n {state['search_results']} \n\n"
        f"DETAILED SCRAPPED CONTENT: \n {state['web_scrap_results']}\n\n"
        "Use citation markers like [1], [2], and [3] when making source-backed claims."
    )

    try:
        writer_chain = build_writer_chain()

        state["report"] = normalize_content(writer_chain.invoke({
            "topic": topic,
            "research": research_combined
        }))
        state["structured_report"] = parse_structured_report(
            state["report"],
            state["sources"],
        )
        yield {
            "event": "step_completed",
            "step": "draft",
            "field": "report",
            "value": state["report"],
            "structured_report": state["structured_report"],
            "state": state,
        }
    except Exception as exc:
        yield fail("draft", "report", "Writer chain failed", exc)
        return

    print("\n*------------------------------------------------------*\n")
    print("Step 4 - Critic About Drafted Report")
    print("\n*------------------------------------------------------*\n")

    yield {"event": "step_started", "step": "critique", "state": state}

    try:
        critic_chain = build_critic_chain()

        state["feedback"] = normalize_content(critic_chain.invoke({
            "report": state["report"]
        }))
        yield {
            "event": "step_completed",
            "step": "critique",
            "field": "feedback",
            "value": state["feedback"],
            "state": state,
        }
    except Exception as exc:
        yield fail("critique", "feedback", "Critic chain failed", exc)
        return

    yield {"event": "completed", "step": "done", "state": state}


def run_research_pipeline(topic : str) -> dict:
    state = {}
    for event in run_research_pipeline_events(topic, raise_on_error=True):
        state = event.get("state", state)
    return state

if __name__ == "__main__":
    topic = input("\n Enter a  research topic: ")
    run_research_pipeline(topic=topic)

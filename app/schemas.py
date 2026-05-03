from pydantic import BaseModel, Field, HttpUrl


class Source(BaseModel):
    id: int
    title: str
    url: str
    snippet: str = ""
    score: int = Field(ge=0, le=100)
    scrape_status: str | None = None
    scrape_error: str | None = None


class ScrapeAttempt(BaseModel):
    source_id: int
    url: str
    status: str
    error: str | None = None


class Finding(BaseModel):
    claim: str
    explanation: str = ""
    citations: list[int] = Field(default_factory=list)


class StructuredReport(BaseModel):
    introduction: str = ""
    findings: list[Finding] = Field(default_factory=list)
    conclusion: str = ""
    sources: list[Source] = Field(default_factory=list)
    citation_ids: list[int] = Field(default_factory=list)
    citation_coverage: float = 0.0

    def to_markdown(self) -> str:
        findings_md = "\n".join(
            f"- **{finding.claim}** {finding.explanation}".strip()
            for finding in self.findings
        )
        sources_md = "\n".join(
            f"- [{source.id}] {source.title} - {source.url}"
            for source in self.sources
        )
        return "\n\n".join(
            [
                "## Introduction\n" + self.introduction,
                "## Key Findings\n" + findings_md,
                "## Conclusion\n" + self.conclusion,
                "## Sources\n" + sources_md,
            ]
        )

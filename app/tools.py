from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from rich import print
from app.schemas import Source


def get_tavily_client():
    load_dotenv(override=True)
    return TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def score_source(source: dict, rank: int) -> int:
    url = source.get("url", "")
    domain = urlparse(url).netloc.lower()
    score = max(40, 100 - (rank * 7))

    trusted_domains = (
        ".gov",
        ".edu",
        "who.int",
        "nih.gov",
        "nature.com",
        "science.org",
        "worldbank.org",
        "oecd.org",
        "mckinsey.com",
        "deloitte.com",
        "pwc.com",
    )
    if any(domain.endswith(item) or item in domain for item in trusted_domains):
        score += 12

    if source.get("content") and len(source["content"]) > 180:
        score += 6

    if source.get("published_date"):
        score += 5

    return min(score, 100)


def format_sources(sources: list[dict]) -> str:
    out = []

    for source in sources:
        item = Source.model_validate(source)
        out.append(
            "\n".join(
                [
                    f"Source [{item.id}]",
                    f"Title: {item.title}",
                    f"URL: {item.url}",
                    f"Score: {item.score}",
                    f"Snippet: {item.snippet}",
                ]
            )
        )

    return "\n---------------\n".join(out)


def search_sources(query: str, max_results: int = 5) -> list[dict]:
    tavily = get_tavily_client()
    results = tavily.search(query=query, max_results=max_results)

    sources = []
    for index, result in enumerate(results.get("results", []), start=1):
        source = Source(
            **{
                "id": index,
                "title": result.get("title", "Untitled source"),
                "url": result.get("url", ""),
                "snippet": (result.get("content") or "")[:500],
                "score": score_source(result, index),
            }
        )
        sources.append(source.model_dump())

    return sources


@tool
def web_search(query : str) -> str:
    """Search the web for resent and relaible information on a topic. Returns Titles, URL's and Snippets."""

    return format_sources(search_sources(query=query, max_results=5))

@tool
def web_scrap(url : str) -> str:
    """Scrap the content of a webpage and return the text content from a given URL for deeper reading"""

    return scrape_url_content(url)


def scrape_url_content(url: str) -> str:
    try:
        response = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:3000]
    except Exception as e:
        raise RuntimeError(f"Error scraping the webpage: {str(e)}") from e
    

# print(web_scrap.invoke("https://en.wikipedia.org/wiki/News"))

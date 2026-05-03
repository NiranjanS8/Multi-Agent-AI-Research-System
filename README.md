# Multi-Agent AI Research System

A portfolio-grade agentic research assistant built with FastAPI, LangChain, Mistral Small, Tavily Search, web scraping, streaming responses, source quality scoring, citation-aware reports, critic feedback, and SQLite research history.

## Why This Project Matters

This project demonstrates practical agentic AI engineering rather than a single prompt call. The system coordinates multiple stages, uses external tools, streams progress to the UI, preserves partial outputs, scores sources, asks the writer to cite evidence, critiques the generated report, and stores completed runs for later review.

## Agent Workflow

1. Search: fetches reliable web sources through Tavily.
2. Source scoring: ranks results using position, trusted domains, snippet depth, and recency signals.
3. Scrape: retries the highest-scored sources and falls back to snippets if scraping fails.
4. Draft: generates a Markdown report plus a structured citation-aware report object.
5. Critique: reviews clarity, depth, completeness, flow, and source quality.
6. Persist: saves topic, sources, report, feedback, status, and timestamp to SQLite.

## Features

- Streaming pipeline updates over `POST /api/research/stream`.
- Job-based execution with persisted job and step state.
- Step-by-step frontend progress states.
- Citation-aware report prompting.
- Structured report extraction with citation coverage metadata.
- Source quality scores displayed in the UI.
- SQLite research history in `research_history.db`.
- Retry and fallback strategy for scraping.
- Partial failure handling, so completed stages are not lost if a later stage fails.
- Clean research-console frontend focused on readability.

## Tech Stack

- FastAPI
- LangChain
- Mistral Small via `langchain-mistralai`
- Tavily Search
- BeautifulSoup and Requests
- SQLite
- Vanilla HTML, CSS, and JavaScript

## Project Structure

```text
app/
  main.py        FastAPI app, API routes, streaming endpoint
  pipeline.py    Research workflow and step events
  agents.py      Mistral writer and critic chains
  schemas.py     Typed source, scrape, finding, report contracts
  tools.py       Tavily search, source scoring, web scraping
  storage.py     SQLite research history
static/
  index.html     Frontend shell
  styles.css     Research workspace styling
  app.js         Streaming UI and result rendering
main.py          Uvicorn compatibility shim
pipeline.py      CLI compatibility shim
evals/
  cases.json     Evaluation topics and expectations
  run_evals.py   Lightweight report quality evaluator
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file with your keys:

```env
TAVILY_API_KEY=your_tavily_key
MISTRAL_API_KEY=your_mistral_key
MISTRAL_MODEL=mistral-small-latest
```

## Run the Web App

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Run the CLI

```powershell
.\.venv\Scripts\python.exe pipeline.py
```

## API

- `GET /api/health` checks server status.
- `POST /api/research` runs the full pipeline and returns JSON.
- `POST /api/research/stream` streams newline-delimited JSON events as each stage completes.
- `POST /api/research/jobs` creates a persisted research job.
- `GET /api/research/jobs/{job_id}` returns job and step state.
- `GET /api/research/jobs/{job_id}/stream` streams and persists a created job.
- `GET /api/research/history` lists saved research runs.
- `GET /api/research/history/{run_id}` returns a saved run.

Example request:

```json
{
  "topic": "AI in drug discovery"
}
```

## Evals

After saving at least one run, execute:

```powershell
.\.venv\Scripts\python.exe evals\run_evals.py
```

The evaluator checks report sections, citation count, source count, and critic feedback.

## Future Improvements

- Add user accounts and per-user histories.
- Add automated evals for citation coverage, source relevance, and hallucination risk.
- Add export to PDF or Markdown.
- Add fallback scraping when the selected source fails.
- Add deployment with a live demo URL.

const form = document.querySelector("#research-form");
const topicInput = document.querySelector("#topic");
const submitButton = form.querySelector("button");
const statusText = document.querySelector("#form-status");
const historyList = document.querySelector("#history-list");

const panels = {
  search_results: document.querySelector("#search-results"),
  report: document.querySelector("#report-results"),
  feedback: document.querySelector("#feedback-results"),
};

const stepNodes = {
  search: document.querySelector('[data-step="search"]'),
  scrape: document.querySelector('[data-step="scrape"]'),
  draft: document.querySelector('[data-step="draft"]'),
  critique: document.querySelector('[data-step="critique"]'),
};

const stepLabels = {
  search: "Search",
  scrape: "Scrape",
  draft: "Draft",
  critique: "Critique",
};

const fieldToPanel = {
  search_results: { panel: panels.search_results, type: "search" },
  report: { panel: panels.report, type: "markdown" },
  feedback: { panel: panels.feedback, type: "markdown" },
};

function escapeHtml(value) {
  return valueToText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function valueToText(value) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map(valueToText).filter(Boolean).join("\n\n");
  }

  if (typeof value === "object") {
    if (typeof value.text === "string") {
      return value.text;
    }
    if (typeof value.content === "string") {
      return value.content;
    }
    if (value.title || value.url || value.snippet) {
      return [
        value.title ? `Title: ${value.title}` : "",
        value.url ? `URL: ${value.url}` : "",
        value.snippet || value.description ? `Snippet: ${value.snippet || value.description}` : "",
      ]
        .filter(Boolean)
        .join("\n");
    }

    return Object.entries(value)
      .map(([key, item]) => `${key}: ${valueToText(item)}`)
      .join("\n");
  }

  return String(value);
}

function renderInlineMarkdown(value) {
  let text = escapeHtml(value);

  text = text.replace(
    /(https?:\/\/[^\s<)]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");

  return text;
}

function renderFormattedOutput(value) {
  const source = valueToText(value)
    .trim()
    .replace(/^```(?:markdown|md)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
  if (!source) {
    return "<p>No output returned.</p>";
  }

  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;

  function flushParagraph() {
    if (!paragraph.length) {
      return;
    }

    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function closeList() {
    if (!listType) {
      return;
    }

    html.push(`</${listType}>`);
    listType = null;
  }

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      closeList();
      return;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    const titledLine = trimmed.match(/^([A-Z][A-Za-z\s/&-]{2,40}):\s*(.*)$/);
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);

    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 4);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }

    if (titledLine && !trimmed.startsWith("URL:")) {
      flushParagraph();
      closeList();
      html.push(
        `<h4>${renderInlineMarkdown(titledLine[1])}</h4>${
          titledLine[2] ? `<p>${renderInlineMarkdown(titledLine[2])}</p>` : ""
        }`,
      );
      return;
    }

    if (bullet || numbered) {
      flushParagraph();
      const nextType = bullet ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        html.push(`<${nextType}>`);
        listType = nextType;
      }
      html.push(`<li>${renderInlineMarkdown((bullet || numbered)[1])}</li>`);
      return;
    }

    paragraph.push(trimmed);
  });

  flushParagraph();
  closeList();

  return html.join("");
}

function parseSearchBlocks(value) {
  if (Array.isArray(value)) {
    return value
      .flatMap((item) => {
        if (typeof item === "object" && item !== null) {
          return [
            {
              title: item.title || item.name,
              url: item.url || item.link,
              snippet: item.snippet || item.content || item.description,
            },
          ];
        }
        return parseSearchBlocks(item);
      })
      .filter((item) => item.title || item.url || item.snippet);
  }

  if (typeof value === "object" && value !== null) {
    return parseSearchBlocks(valueToText(value));
  }

  const source = valueToText(value).trim();
  if (!source) {
    return [];
  }

  return source
    .split(/\n-{5,}\n/g)
    .map((block) => {
      const title = block.match(/Title:\s*(.+)/i)?.[1]?.trim();
      const url = block.match(/URL:\s*(https?:\/\/\S+)/i)?.[1]?.trim();
      const snippet = block.match(/Snippet:\s*([\s\S]+)/i)?.[1]?.trim();
      return { title, url, snippet };
    })
    .filter((item) => item.title || item.url || item.snippet);
}

function renderSearchResults(value) {
  const results = parseSearchBlocks(value);

  if (!results.length) {
    return renderFormattedOutput(value || "No search output returned.");
  }

  return `<div class="search-results-list">${results
    .map((result, index) => {
      const safeTitle = renderInlineMarkdown(result.title || `Source ${index + 1}`);
      const safeUrl = result.url ? escapeHtml(result.url) : "";
      const safeSnippet = renderInlineMarkdown(result.snippet || "No snippet returned.");
      const safeScore = result.score ? escapeHtml(result.score) : "N/A";

      return `<article class="source-card">
        <div class="source-index">${String(index + 1).padStart(2, "0")}</div>
        <div class="source-body">
          <div class="source-title-row">
            <h4>${safeTitle}</h4>
            <span class="source-score">${safeScore}</span>
          </div>
          ${
            safeUrl
              ? `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>`
              : ""
          }
          <p>${safeSnippet}</p>
        </div>
      </article>`;
    })
    .join("")}</div>`;
}

function setPanel(panel, value, type = "markdown") {
  panel.innerHTML = type === "search" ? renderSearchResults(value) : renderFormattedOutput(value);
}

function resetSteps() {
  Object.entries(stepNodes).forEach(([step, node], index) => {
    if (!node) {
      return;
    }

    node.classList.remove("is-running", "is-complete", "is-error");
    node.querySelector(".step-check").textContent = String(index + 1).padStart(2, "0");
    node.setAttribute("aria-label", `${stepLabels[step]} waiting`);
  });
}

function setStepStatus(step, status) {
  const node = stepNodes[step];
  if (!node) {
    return;
  }

  node.classList.toggle("is-running", status === "running");
  node.classList.toggle("is-complete", status === "complete");
  node.classList.toggle("is-error", status === "error");

  if (status === "complete") {
    node.querySelector(".step-check").textContent = "OK";
    node.setAttribute("aria-label", `${stepLabels[step]} complete`);
  } else if (status === "error") {
    node.querySelector(".step-check").textContent = "!";
    node.setAttribute("aria-label", `${stepLabels[step]} failed`);
  } else if (status === "running") {
    node.querySelector(".step-check").textContent = "...";
    node.setAttribute("aria-label", `${stepLabels[step]} running`);
  }
}

function setStatus(message, isError = false) {
  statusText.textContent = message;
  statusText.classList.toggle("error", isError);
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.querySelector("span").textContent = isLoading ? "Running" : "Run research";
}

function updatePanels(data) {
  setPanel(
    panels.search_results,
    data.sources?.length ? data.sources : data.search_results || "No search output returned.",
    "search",
  );
  setPanel(panels.report, data.report || "No report returned.");
  setPanel(panels.feedback, data.feedback || "No critic feedback returned.");
}

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function handleStreamEvent(data) {
  if (data.event === "step_started") {
    setStepStatus(data.step, "running");
    setStatus(`${stepLabels[data.step].toUpperCase()} IS RUNNING.`);
    return;
  }

  if (data.event === "step_completed") {
    const target = fieldToPanel[data.field];
    if (target) {
      setPanel(target.panel, data.value, target.type);
    }
    setStepStatus(data.step, "complete");
    setStatus(`${stepLabels[data.step].toUpperCase()} COMPLETE.`);
    return;
  }

  if (data.event === "completed") {
    setStatus("REPORT COMPLETE.");
    return;
  }

  if (data.event === "saved") {
    loadHistory();
    return;
  }

  if (data.event === "error") {
    if (data.field && fieldToPanel[data.field]) {
      const target = fieldToPanel[data.field];
      setPanel(target.panel, data.value || data.error, target.type);
    }
    setStepStatus(data.step, "error");
    setStatus(data.error || "PIPELINE FAILED.", true);
  }
}


function renderHistory(items) {
  if (!historyList) {
    return;
  }

  if (!items.length) {
    historyList.innerHTML = "No saved runs yet.";
    historyList.classList.add("empty-state");
    return;
  }

  historyList.classList.remove("empty-state");
  historyList.innerHTML = items
    .map((item) => {
      const date = new Date(item.created_at).toLocaleString();
      return `<button class="history-item" type="button" data-run-id="${escapeHtml(item.id)}">
        <div>
          <strong>${escapeHtml(item.topic)}</strong>
          <small>${escapeHtml(date)} | ${escapeHtml(item.status)} | ${
            item.sources?.length || 0
          } sources</small>
        </div>
      </button>`;
    })
    .join("");
}

async function loadSavedRun(runId) {
  setStatus("LOADING SAVED RUN.");

  const response = await fetch(`/api/research/history/${runId}`);
  const data = await readResponseBody(response);
  if (!response.ok) {
    throw new Error(data.detail || "Could not load saved run.");
  }

  if (topicInput && data.topic) {
    topicInput.value = data.topic;
  }

  updatePanels(data);
  resetSteps();
  ["search", "scrape", "draft", "critique"].forEach((step) => {
    setStepStatus(step, "complete");
  });
  setStatus(`LOADED SAVED RUN: ${data.topic}`);
  document.querySelector("#output").scrollIntoView({ behavior: "smooth" });
}

async function loadHistory() {
  if (!historyList) {
    return;
  }

  try {
    const response = await fetch("/api/research/history?limit=5");
    if (!response.ok) {
      return;
    }
    renderHistory(await response.json());
  } catch {
    // History is nice to have; research should keep working without it.
  }
}

async function streamResearch(topic) {
  const response = await fetch("/api/research/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ topic }),
  });

  if (!response.ok || !response.body) {
    const data = await readResponseBody(response);
    throw new Error(data.detail || "Research request failed.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }

      handleStreamEvent(JSON.parse(trimmed));
    });

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    handleStreamEvent(JSON.parse(buffer.trim()));
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const topic = topicInput.value.trim();
  if (topic.length < 3) {
    setStatus("ENTER AT LEAST THREE CHARACTERS.", true);
    topicInput.focus();
    return;
  }

  setLoading(true);
  resetSteps();
  setStatus("AGENTS ARE STARTING.");

  Object.values(panels).forEach((panel) => {
    setPanel(panel, "Running...");
  });
  document.querySelector("#output").scrollIntoView({ behavior: "smooth" });

  try {
    await streamResearch(topic);
  } catch (error) {
    setStatus(error.message, true);
    Object.values(panels).forEach((panel) => {
      setPanel(
        panel,
        "Request failed. Check the status message, API keys, network access, and server logs.",
      );
    });
  } finally {
    setLoading(false);
  }
});

if (historyList) {
  historyList.addEventListener("click", async (event) => {
    const item = event.target.closest("[data-run-id]");
    if (!item) {
      return;
    }

    try {
      await loadSavedRun(item.dataset.runId);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

loadHistory();

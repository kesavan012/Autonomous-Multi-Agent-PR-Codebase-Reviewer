const form = document.querySelector("#review-form");
const urlInput = document.querySelector("#pr-url");
const reviewButton = document.querySelector("#review-button");
const area = document.querySelector("#review-area");
const emptyState = document.querySelector("#empty-state");
const loadingState = document.querySelector("#loading-state");
const errorState = document.querySelector("#error-state");
const reportElement = document.querySelector("#report");
const filtersElement = document.querySelector("#filters");
const findingsElement = document.querySelector("#findings");
const noFindings = document.querySelector("#no-findings");
let reportFindings = [];
let activeFilter = "all";

function renderIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function makeMetric(value, label) {
  const item = document.createElement("div");
  item.className = "metric";
  const number = document.createElement("span");
  number.className = "metric-value";
  number.textContent = value;
  const caption = document.createElement("span");
  caption.className = "metric-label";
  caption.textContent = label;
  item.append(number, caption);
  return item;
}

function renderFilters() {
  filtersElement.replaceChildren();
  const severities = ["all", "critical", "high", "medium", "low"];
  for (const severity of severities) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter${activeFilter === severity ? " active" : ""}`;
    button.textContent = severity === "all" ? "All" : severity[0].toUpperCase() + severity.slice(1);
    button.setAttribute("aria-pressed", String(activeFilter === severity));
    button.addEventListener("click", () => {
      activeFilter = severity;
      renderFilters();
      renderFindings();
    });
    filtersElement.append(button);
  }
}

function renderFindings() {
  const filtered = reportFindings.filter((finding) => activeFilter === "all" || finding.severity === activeFilter);
  findingsElement.replaceChildren();
  noFindings.hidden = filtered.length !== 0;
  for (const finding of filtered) {
    const row = document.createElement("article");
    row.className = "finding";
    const severity = document.createElement("span");
    severity.className = `severity severity-${finding.severity}`;
    severity.textContent = finding.severity;
    const content = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = finding.title;
    const body = document.createElement("p");
    body.textContent = finding.body;
    const metadata = document.createElement("div");
    metadata.className = "finding-meta";
    const file = document.createElement("span");
    file.textContent = `${finding.path}:${finding.line}`;
    const category = document.createElement("span");
    category.textContent = finding.category;
    const confidence = document.createElement("span");
    confidence.className = "confidence";
    confidence.textContent = `${Math.round(finding.confidence * 100)}% confidence`;
    metadata.append(file, category, confidence);
    content.append(title, body, metadata);
    row.append(severity, content);
    findingsElement.append(row);
  }
  renderIcons();
}

function showReport(report) {
  reportFindings = report.findings;
  activeFilter = "all";
  document.querySelector("#report-repo").textContent = `${report.repository} · #${report.pull_request}`;
  document.querySelector("#report-title").textContent = report.title;
  document.querySelector("#finding-total").textContent = String(report.findings.length);
  const metrics = document.querySelector("#metrics");
  metrics.replaceChildren(
    makeMetric(String(report.findings.length), "POTENTIAL ISSUES"),
    makeMetric(String(report.files_reviewed), "FILES SCANNED"),
    makeMetric(String(report.lines_reviewed), "ADDED LINES")
  );
  renderFilters();
  renderFindings();
  emptyState.hidden = true;
  loadingState.hidden = true;
  errorState.hidden = true;
  reportElement.hidden = false;
  area.setAttribute("aria-busy", "false");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  emptyState.hidden = true;
  reportElement.hidden = true;
  errorState.hidden = true;
  loadingState.hidden = false;
  area.setAttribute("aria-busy", "true");
  reviewButton.disabled = true;

  try {
    const response = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim() }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      const message = Array.isArray(detail)
        ? detail.map((issue) => issue.msg).filter(Boolean).join(" ")
        : detail;
      throw new Error(message || "Review could not be completed.");
    }
    showReport(data);
  } catch (error) {
    loadingState.hidden = true;
    errorState.textContent = error.message || "The review request failed. Check your connection and try again.";
    errorState.hidden = false;
    area.setAttribute("aria-busy", "false");
  } finally {
    reviewButton.disabled = false;
  }
});

renderIcons();
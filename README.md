# Patchwork

Patchwork is a small pull-request review service. It fetches a GitHub PR diff, retrieves surrounding functions from changed files, and runs a bounded set of static checks against added lines. Its LangGraph pipeline separates context retrieval, auditing, and Pydantic-validated synthesis. Tree-sitter extracts function/class context; Qdrant's in-memory mode ranks related symbols when those optional integrations are available.

[GitHub Repository](https://github.com/kesavan012/Autonomous-Multi-Agent-PR-Codebase-Reviewer) | [Live Demo](https://autonomous-multi-agent-pr-codebase.onrender.com/)

The audit rules are deterministic heuristics, not an LLM judgment or a substitute for a human review. They currently flag risky dynamic execution, unsafe subprocess use, pickle/YAML deserialization, disabled TLS verification, and likely hard-coded credentials. They do not execute submitted code.

## Run locally

Requires Python 3.11+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GITHUB_TOKEN = "github_pat_..." # optional; useful for private repos or API rate limits
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Public repositories work without a token, subject to GitHub's unauthenticated API rate limit. Never put a token in the browser; the server reads it from `GITHUB_TOKEN`.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

## Docker

```powershell
docker build -t patchwork .
docker run --rm -p 8000:8000 -e GITHUB_TOKEN patchwork
```

The container listens on port 8000 by default and respects the `PORT` environment variable for Render-style deployments.

## API

`POST /api/review` accepts `{"url":"https://github.com/owner/repo/pull/42"}` and returns a report with `findings`, changed-file/line counts, and PR metadata. `GET /api/health` is a liveness check.

The service only accepts GitHub pull-request URLs and requests fixed GitHub API/raw-content hosts. It limits diff size to 500 KB, source context to eight files and 160 KB per file, and outbound request time. For a production deployment, add authentication, request throttling, audit logging, and a managed Qdrant collection before exposing the service publicly.
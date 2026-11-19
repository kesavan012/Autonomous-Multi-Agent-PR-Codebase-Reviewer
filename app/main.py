from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents import review_pull_request
from app.github import GitHubRequestError, InvalidPullRequestUrl, fetch_pull_request, parse_pull_request_url
from app.reviewer import ReviewReport


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=12, max_length=500)

    @field_validator("url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        try:
            parse_pull_request_url(value)
        except InvalidPullRequestUrl as error:
            raise ValueError(str(error)) from error
        return value


class ReviewResponse(ReviewReport):
    repository: str
    pull_request: int
    title: str
    mode: Literal["static"] = "static"


app = FastAPI(title="Patchwork", version="1.0.0")
static_dir = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=static_dir), name="assets")


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/review", response_model=ReviewResponse)
async def review(request: ReviewRequest) -> ReviewResponse:
    try:
        pull_request = await fetch_pull_request(request.url, os.getenv("GITHUB_TOKEN"))
    except InvalidPullRequestUrl as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GitHubRequestError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    report = review_pull_request(pull_request.patch, pull_request.sources)
    return ReviewResponse(
        **report.model_dump(),
        repository=f"{pull_request.owner}/{pull_request.repository}",
        pull_request=pull_request.number,
        title=pull_request.title,
    )
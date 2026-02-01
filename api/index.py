from __future__ import annotations

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.github_library_analyzer import GitHubError, GitHubLibraryAnalyzer

app = FastAPI(title="GitHub Library Usage Explorer")
templates = Jinja2Templates(directory="templates")


def _serialize_block(block):
    return {
        "repository": block.repository,
        "file_path": block.file_path,
        "html_url": block.html_url,
        "start_line": block.start_line,
        "end_line": block.end_line,
        "symbol": block.symbol,
        "snippet": block.snippet,
    }


def _run_analysis(library: str, max_files: int):
    bounded_max = max(1, min(max_files, 20))
    analyzer = GitHubLibraryAnalyzer()
    try:
        return analyzer.analyze_library(library, max_files=bounded_max)
    finally:
        analyzer.close()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "results": None, "error": None},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze_form(
    request: Request,
    library: str = Form(...),
    max_files: int = Form(5),
) -> HTMLResponse:
    error = None
    results = []
    try:
        results = _run_analysis(library, max_files)
    except GitHubError as exc:
        error = str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        error = f"Unexpected error: {exc}"
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "results": [_serialize_block(block) for block in results],
            "error": error,
            "library": library,
            "max_files": max_files,
        },
    )


@app.get("/api/analyze", response_class=JSONResponse)
async def analyze_api(library: str, max_files: int = 5) -> JSONResponse:
    try:
        results = _run_analysis(library, max_files)
    except GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"library": library, "results": [_serialize_block(block) for block in results]})

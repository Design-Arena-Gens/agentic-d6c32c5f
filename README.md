# GitHub Library Usage Explorer

Search public GitHub repositories for Python code files that import a specific library and surface the code blocks where the library is used. The project provides both a reusable Python module/CLI and a lightweight FastAPI web interface suitable for deployment on Vercel.

## Features

- GitHub code search integration with optional personal access token support.
- Accurate usage detection powered by Python's `ast` module (handles aliases and `from ... import ...` statements).
- CLI utility with JSON output mode for scripting and automation.
- FastAPI-powered web UI with dark-mode friendly styling.

## Getting Started

### Prerequisites

- Python 3.11+
- (Optional) GitHub personal access token with `public_repo` scope to increase rate limits.

### Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### CLI Usage

```bash
python -m src.cli numpy --max-files 3
```

Set `GITHUB_TOKEN` in your environment (or pass `--token`) to avoid anonymous rate limits.

### Running the FastAPI App Locally

```bash
uvicorn api.index:app --reload --port 8000
```

Open `http://localhost:8000` to use the web interface.

## Configuration

- `GITHUB_TOKEN`: optional environment variable used by both the CLI and web app.
- `--max-files`: controls how many candidate files from GitHub to inspect (default 5, max 20 via the web form).

## Project Structure

```
├── api/                  # FastAPI entrypoint for Vercel/serverless
├── src/                  # Core analysis logic and CLI wrapper
├── templates/            # HTML template for the web UI
├── requirements.txt      # Python dependencies
├── README.md             # Documentation
```

## Deployment Notes

This project is designed for Vercel's Python runtime (`@vercel/python`). The `api/index.py` entrypoint exposes both HTML and JSON responses, enabling use as a web UI or API.

## License

MIT

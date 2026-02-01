import argparse
import json
import sys
from typing import Optional

from .github_library_analyzer import CodeBlock, GitHubError, GitHubLibraryAnalyzer


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search GitHub for code snippets that use a specific Python library.",
    )
    parser.add_argument("library", help="Target library name, e.g. 'numpy'")
    parser.add_argument(
        "--max-files",
        type=int,
        default=5,
        help="Maximum number of files to inspect (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of human-readable snippets.",
    )
    parser.add_argument(
        "--token",
        help="Override the GitHub token (otherwise reads the GITHUB_TOKEN environment variable).",
    )
    return parser.parse_args(argv)


def format_snippet(block: CodeBlock) -> str:
    header = f"{block.repository}:{block.file_path}:{block.start_line}-{block.end_line} [{block.symbol}]"
    separator = "-" * len(header)
    return f"{header}\n{separator}\n{block.snippet}\n"


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.max_files <= 0:
        print("Error: --max-files must be greater than zero.", file=sys.stderr)
        return 2
    analyzer = GitHubLibraryAnalyzer(token=args.token)
    try:
        blocks = analyzer.analyze_library(args.library, max_files=args.max_files)
    except GitHubError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        analyzer.close()

    if args.json:
        payload = [
            {
                "repository": block.repository,
                "file_path": block.file_path,
                "html_url": block.html_url,
                "start_line": block.start_line,
                "end_line": block.end_line,
                "symbol": block.symbol,
                "snippet": block.snippet,
            }
            for block in blocks
        ]
        print(json.dumps(payload, indent=2))
    else:
        if not blocks:
            print("No usages found.")
        for block in blocks:
            print(format_snippet(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

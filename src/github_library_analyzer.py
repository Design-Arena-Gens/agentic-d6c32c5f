from __future__ import annotations

import ast
import base64
import os
import textwrap
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

import httpx

GITHUB_API_URL = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised when the GitHub API responds with an error."""


@dataclass
class CodeBlock:
    repository: str
    file_path: str
    html_url: str
    start_line: int
    end_line: int
    symbol: str
    snippet: str


class GitHubLibraryAnalyzer:
    """High-level interface for locating library usages in public GitHub code."""

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        request_timeout: float = 20.0,
    ) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "library-usage-analyzer",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.Client(base_url=GITHUB_API_URL, timeout=request_timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def analyze_library(
        self,
        library: str,
        *,
        max_files: int = 5,
        per_page: int = 10,
    ) -> List[CodeBlock]:
        """Fetch Python files from GitHub that import the requested library and extract usage blocks."""
        items = list(self._iter_code_search_results(library, per_page=per_page, limit=max_files))
        results: List[CodeBlock] = []
        for item in items:
            try:
                source = self._download_source(item["url"])
            except Exception:  # pragma: no cover - defensive
                continue
            try:
                extractor = _LibraryUsageExtractor(library, source)
            except SyntaxError:
                continue
            blocks = extractor.extract_blocks()
            for block in blocks:
                results.append(
                    CodeBlock(
                        repository=item["repository"]["full_name"],
                        file_path=item["path"],
                        html_url=item["html_url"],
                        start_line=block.start_line,
                        end_line=block.end_line,
                        symbol=block.symbol,
                        snippet=block.snippet,
                    )
                )
        return results

    def _iter_code_search_results(
        self,
        library: str,
        *,
        per_page: int,
        limit: int,
    ) -> Iterable[Dict]:
        gathered = 0
        page = 1
        query = f'"{library}" language:Python in:file'
        while gathered < limit:
            response = self._client.get("/search/code", params={"q": query, "per_page": per_page, "page": page})
            if response.status_code == 403 and "rate limit" in response.text.lower():
                raise GitHubError("GitHub API rate limit exceeded. Provide a token via the GITHUB_TOKEN environment variable.")
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items", [])
            if not items:
                break
            for item in items:
                if item["name"].endswith(".py"):
                    yield item
                    gathered += 1
                    if gathered >= limit:
                        break
            page += 1

    def _download_source(self, api_url: str) -> str:
        response = self._client.get(api_url)
        response.raise_for_status()
        data = response.json()
        if "content" not in data:
            raise GitHubError("Unexpected GitHub API payload - missing file content.")
        encoding = data.get("encoding")
        if encoding != "base64":
            raise GitHubError(f"Unsupported content encoding: {encoding}")
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


@dataclass
class _BlockCapture:
    start_line: int
    end_line: int
    symbol: str
    snippet: str


class _LibraryUsageExtractor:
    """AST-based extractor that locates code blocks referencing a target library."""

    def __init__(self, library: str, source: str) -> None:
        self.library = library
        self.source = source
        self.lines = source.splitlines()
        self.tree = ast.parse(source)
        self.parent: Dict[ast.AST, ast.AST] = {}

    def extract_blocks(self) -> List[_BlockCapture]:
        self._populate_parent_links()
        alias_collector = _AliasCollector(self.library)
        alias_collector.visit(self.tree)
        alias_names = alias_collector.aliases
        if not alias_names:
            return []
        usage_collector = _UsageCollector(self.lines, alias_names, self.parent)
        usage_collector.visit(self.tree)
        return usage_collector.blocks

    def _populate_parent_links(self) -> None:
        stack = [self.tree]
        while stack:
            node = stack.pop()
            for child in ast.iter_child_nodes(node):
                self.parent[child] = node
                stack.append(child)


class _AliasCollector(ast.NodeVisitor):
    """Collect names that reference the target library inside the module."""

    def __init__(self, library: str) -> None:
        self.base = library
        self.base_root = library.split(".")[0]
        self.aliases: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if self._matches_library(alias.name):
                if alias.asname:
                    self.aliases.add(alias.asname)
                else:
                    self.aliases.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module
        if module and self._matches_library(module):
            for alias in node.names:
                if alias.name == "*":
                    self.aliases.add(module.split(".")[-1])
                    self.aliases.add(self.base_root)
                else:
                    self.aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def _matches_library(self, module_name: str) -> bool:
        return module_name == self.base or module_name.startswith(f"{self.base}.") or module_name.split(".")[0] == self.base_root


class _UsageCollector(ast.NodeVisitor):
    """Find code blocks containing references to collected aliases."""

    def __init__(self, lines: List[str], aliases: Set[str], parent: Dict[ast.AST, ast.AST]) -> None:
        self.lines = lines
        self.aliases = aliases
        self.parent = parent
        self.blocks_map: Dict[Tuple[int, int], _BlockCapture] = {}

    @property
    def blocks(self) -> List[_BlockCapture]:
        return list(self.blocks_map.values())

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.aliases and not self._part_of_attribute(node):
            self._record(node, node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root = self._attribute_root(node)
        if isinstance(root, ast.Name) and root.id in self.aliases:
            symbol = self._attribute_full_name(node)
            self._record(node, symbol)
        self.generic_visit(node)

    def _record(self, node: ast.AST, symbol: str) -> None:
        container = self._enclosing_block(node)
        if container is None:
            return
        start = getattr(container, "lineno", None)
        end = getattr(container, "end_lineno", None)
        if start is None:
            return
        if end is None:
            end = start
        key = (start, end)
        if key in self.blocks_map:
            return
        snippet_lines = self.lines[start - 1 : end]
        snippet = textwrap.dedent("\n".join(snippet_lines)).strip()
        self.blocks_map[key] = _BlockCapture(
            start_line=start,
            end_line=end,
            symbol=symbol,
            snippet=snippet,
        )

    def _part_of_attribute(self, node: ast.Name) -> bool:
        parent = self.parent.get(node)
        return isinstance(parent, ast.Attribute) and parent.value is node

    def _attribute_root(self, node: ast.Attribute) -> ast.AST:
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            current = current.value
        return current

    def _attribute_full_name(self, node: ast.Attribute) -> str:
        parts: List[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _enclosing_block(self, node: ast.AST) -> Optional[ast.AST]:
        current: Optional[ast.AST] = node
        closest_stmt: Optional[ast.AST] = None
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return current
            if isinstance(current, ast.stmt):
                closest_stmt = current
            current = self.parent.get(current)
        return closest_stmt

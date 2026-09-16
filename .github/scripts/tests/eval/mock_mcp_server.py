"""Lightweight Stdio Mock MCP Server for GitHub MCP tools.

Implements JSON-RPC 2.0 stdio server protocol emulating GitHub MCP tools
(list_pull_request_files, get_file_contents) using golden test case fixtures (EvalCase),
enabling offline agent inference and testing without Docker or live GitHub credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure current and parent scripts directories are on sys.path
_curr_dir = os.path.dirname(os.path.abspath(__file__))
if _curr_dir not in sys.path:
    sys.path.insert(0, _curr_dir)

_scripts_dir = os.path.abspath(os.path.join(_curr_dir, "..", ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from evalset_schema import EvalCase

try:
    from google.antigravity import types
except ImportError:
    types = None

__all__ = [
    "MockGitHubMcpServer",
    "create_mock_github_mcp_server",
    "create_mock_mcp_config",
]


class MockGitHubMcpServer:
    """Implements JSON-RPC 2.0 Stdio protocol for GitHub MCP tools."""

    def __init__(self, fixture_path: str):
        self.fixture = self._load_fixture(fixture_path)

    def _load_fixture(self, path: str) -> EvalCase:
        """Loads golden test case fixture from JSON."""
        return EvalCase.from_file(path)

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Returns standard MCP initialize result."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "mock-github-mcp",
                    "version": "1.0.0"
                }
            }
        }

    def handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        """Returns schemas for get_file_contents and list_pull_request_files."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "list_pull_request_files",
                        "description": "Lists all modified files and diff patches for a pull request.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "owner": {"type": "string", "description": "Repository owner"},
                                "repo": {"type": "string", "description": "Repository name"},
                                "pull_number": {"type": "integer", "description": "Pull request number"}
                            }
                        }
                    },
                    {
                        "name": "get_file_contents",
                        "description": "Fetches the raw contents of a repository file.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "owner": {"type": "string", "description": "Repository owner"},
                                "repo": {"type": "string", "description": "Repository name"},
                                "path": {"type": "string", "description": "Path to file"},
                                "ref": {"type": "string", "description": "Commit or ref"}
                            },
                            "required": ["path"]
                        }
                    }
                ]
            }
        }

    def handle_tools_call(self, request_id: Any, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executes tool calls returning fixture file contents and diff hunks."""
        if name == "list_pull_request_files":
            files: List[Dict[str, Any]] = []
            if self.fixture.modified_files:
                for fn, lines in self.fixture.modified_files.items():
                    files.append({
                        "filename": fn,
                        "status": "modified",
                        "patch": self.fixture.diff_content,
                        "additions": len(lines),
                        "deletions": 0,
                        "changes": len(lines),
                    })
            elif self.fixture.file_tree:
                for fn in self.fixture.file_tree.keys():
                    files.append({
                        "filename": fn,
                        "status": "modified",
                        "patch": self.fixture.diff_content,
                        "additions": 1,
                        "deletions": 0,
                        "changes": 1,
                    })
            else:
                files.append({
                    "filename": "unknown.py",
                    "status": "modified",
                    "patch": self.fixture.diff_content,
                    "additions": 0,
                    "deletions": 0,
                    "changes": 0,
                })

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(files)
                        }
                    ]
                }
            }
        elif name == "get_file_contents":
            path = args.get("path") or args.get("file_path") or args.get("filepath") or ""
            content = self.fixture.file_tree.get(path)
            if content is None:
                # Fallback to key suffix or basename match
                for k, v in self.fixture.file_tree.items():
                    if k == path or k.endswith(path) or path.endswith(k) or os.path.basename(k) == os.path.basename(path):
                        content = v
                        break
            if content is None:
                content = ""

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": content
                        }
                    ]
                }
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: '{name}'"
                }
            }

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatches an incoming JSON-RPC 2.0 request dictionary."""
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            return self.handle_initialize(req_id, params)
        elif method in ("notifications/initialized", "initialized"):
            # Notifications do not return a response if id is None
            if req_id is not None:
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}
            return None
        elif method == "tools/list":
            return self.handle_tools_list(req_id)
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or params.get("args") or {}
            return self.handle_tools_call(req_id, tool_name, tool_args)
        elif method == "ping":
            if req_id is not None:
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}
            return None
        else:
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found."
                    }
                }
            return None

    def send_response(self, resp: Any) -> None:
        """Writes JSON-RPC response to stdout with explicit flush."""
        data = json.dumps(resp)
        sys.stdout.write(data + "\n")
        sys.stdout.flush()

    def run_stdio_loop(self) -> None:
        """Reads newline-delimited or framed JSON-RPC from sys.stdin and writes to sys.stdout."""
        stdin = sys.stdin
        while True:
            line = stdin.readline()
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.lower().startswith("content-length:"):
                try:
                    length = int(line_str.split(":", 1)[1].strip())
                except ValueError:
                    continue
                # Read until empty line separating header and body
                while True:
                    sep = stdin.readline()
                    if not sep or sep.strip() == "":
                        break
                body = stdin.read(length)
                if not body:
                    break
                try:
                    req = json.loads(body)
                except json.JSONDecodeError:
                    continue
            else:
                try:
                    req = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

            if isinstance(req, list):
                batch_resps = []
                for item in req:
                    if isinstance(item, dict):
                        r = self.handle_request(item)
                        if r is not None:
                            batch_resps.append(r)
                if batch_resps:
                    self.send_response(batch_resps)
            elif isinstance(req, dict):
                resp = self.handle_request(req)
                if resp is not None:
                    self.send_response(resp)


def create_mock_github_mcp_server(fixture_path: str) -> Any:
    """Factory creating types.McpStdioServer configured to run mock_mcp_server.py."""
    server_path = os.path.abspath(__file__)
    resolved_fixture = os.path.abspath(fixture_path)

    if types is not None and hasattr(types, "McpStdioServer"):
        return types.McpStdioServer(
            name="github",
            command=sys.executable,
            args=[server_path, "--fixture", resolved_fixture],
        )

    # Offline/fallback duck-typed McpStdioServer container
    class MockMcpStdioServer:
        def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
            self.name = name
            self.command = command
            self.args = args or []
            self.env = env or {}

    return MockMcpStdioServer(
        name="github",
        command=sys.executable,
        args=[server_path, "--fixture", resolved_fixture],
    )


# Backward-compatible alias
create_mock_mcp_config = create_mock_github_mcp_server


def main() -> None:
    """CLI entrypoint for running the mock MCP server over stdio."""
    parser = argparse.ArgumentParser(description="Mock GitHub MCP Stdio Server")
    parser.add_argument(
        "--fixture",
        required=True,
        help="Absolute or relative path to the EvalCase golden JSON fixture",
    )
    args = parser.parse_args()

    server = MockGitHubMcpServer(args.fixture)
    server.run_stdio_loop()


if __name__ == "__main__":
    main()

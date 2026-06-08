"""MCP server configuration loader.

Reads .vscode/mcp.json to discover configured MCP servers and their
connection details (URL, auth headers, transport type).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str
    type: str = "http"  # "http" = Streamable HTTP, "stdio" = subprocess
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    command: str | None = None  # For stdio transport
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    """Parsed MCP configuration from .vscode/mcp.json."""

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


def load_mcp_config(workspace_root: str | Path | None = None) -> MCPConfig:
    """Load MCP server configuration from .vscode/mcp.json.

    Args:
        workspace_root: Path to the workspace root. Defaults to searching
                       up from CWD for a .vscode/mcp.json file.

    Returns:
        Parsed MCPConfig with server connection details.
    """
    if workspace_root is None:
        workspace_root = _find_workspace_root()

    config_path = Path(workspace_root) / ".vscode" / "mcp.json"
    if not config_path.exists():
        return MCPConfig()

    raw = json.loads(config_path.read_text())
    servers: dict[str, MCPServerConfig] = {}

    for name, server_data in raw.get("servers", {}).items():
        inferred_type = "stdio" if server_data.get("command") else "http"
        servers[name] = MCPServerConfig(
            name=name,
            type=server_data.get("type", inferred_type),
            url=server_data.get("url", ""),
            headers=server_data.get("headers", {}),
            command=server_data.get("command"),
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
        )

    return MCPConfig(servers=servers)


def get_server_config(server_name: str, workspace_root: str | Path | None = None) -> MCPServerConfig | None:
    """Get configuration for a specific MCP server by name.

    Args:
        server_name: The server name as defined in mcp.json (e.g., "scrapebadger").
        workspace_root: Optional workspace root path.

    Returns:
        MCPServerConfig or None if not found.
    """
    config = load_mcp_config(workspace_root)
    return config.servers.get(server_name)


def _find_workspace_root() -> Path:
    """Find workspace root by searching up for .vscode/mcp.json."""
    env_root = os.getenv("AGENT_ORCHESTRATION_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / ".vscode" / "mcp.json").exists():
            return candidate

    candidates = [Path.cwd(), Path(__file__).resolve().parent.parent]
    for start in candidates:
        for parent in [start, *start.parents]:
            if (parent / ".vscode" / "mcp.json").exists():
                return parent
    # Fallback to CWD
    return Path.cwd()

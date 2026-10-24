"""MCP client for agent and supervisor access to tools."""
import json
from typing import Any, Dict, List, Optional

from .server import MCPServer


class MCPClient:
    """Client for invoking MCP tools."""

    def __init__(self, server: Optional[MCPServer] = None):
        self.server = server or MCPServer()

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.server.list_tools()

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        return self.server.call_tool(tool_name, kwargs)

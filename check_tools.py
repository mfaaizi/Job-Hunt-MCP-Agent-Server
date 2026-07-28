"""
Diagnostic: confirms which tools are registered on the shared FastMCP instance
after importing server.main, exactly as `python -m server.main` would do it.
Run: python check_tools.py
"""
import asyncio

import server.main  # noqa: F401  (this executes all tool-registration imports)
from server.app import mcp

tools = asyncio.run(mcp.list_tools())
print("Registered tools:", [t.name for t in tools])
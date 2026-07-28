"""
Holds the single shared FastMCP instance.

This lives in its own module (not server/main.py) deliberately. If tool
modules imported `mcp` from server.main, running `python -m server.main`
would cause Python to import server.main a second time under a different
module name (since __main__ != server.main), creating a duplicate FastMCP
instance and silently registering tools on the wrong one. Importing from
this neutral module instead avoids that trap entirely.
"""
from fastmcp import FastMCP

mcp = FastMCP("job-agent")

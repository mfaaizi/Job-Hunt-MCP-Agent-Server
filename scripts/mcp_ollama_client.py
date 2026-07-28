"""
Minimal MCP <-> Ollama bridge client.

Why this exists: ollmcp's rich TUI depends on the `tty`/`termios` modules,
which are Unix-only and crash on Windows. This script does the same core
job (let a local Ollama model call tools on an MCP server) without any
platform-specific terminal handling — just plain stdin/stdout, so it works
identically on Windows, macOS, and Linux.

Usage:
    python scripts/mcp_ollama_client.py --model llama3.2:3b

Type messages at the prompt. Type 'exit' or 'quit' to stop.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import ollama
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_MODULE = "server.main"


def mcp_tools_to_ollama_format(mcp_tools: list) -> list[dict]:
    """Convert MCP Tool objects into the tool-schema shape Ollama's /api/chat expects.
    Both use JSON Schema for parameters, so this is a near-direct mapping."""
    ollama_tools = []
    for tool in mcp_tools:
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        })
    return ollama_tools


async def run_tool_calling_loop(session: ClientSession, model: str, messages: list[dict]) -> str:
    """
    Repeatedly calls Ollama with the current message history + available tools.
    If the model requests tool calls, executes them via MCP and feeds results
    back, looping until the model produces a plain text answer.
    """
    mcp_tools_result = await session.list_tools()
    ollama_tools = mcp_tools_to_ollama_format(mcp_tools_result.tools)

    max_rounds = 6  # safety cap against runaway tool-call loops
    for _ in range(max_rounds):
        response = ollama.chat(model=model, messages=messages, tools=ollama_tools)
        message = response["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content", "")

        for call in tool_calls:
            tool_name = call["function"]["name"]
            tool_args = call["function"]["arguments"]
            if isinstance(tool_args, str):
                tool_args = json.loads(tool_args)

            print(f"  -> calling tool: {tool_name}({tool_args})")

            try:
                result = await session.call_tool(tool_name, tool_args)
                result_text = "\n".join(
                    block.text for block in result.content if hasattr(block, "text")
                )
            except Exception as e:
                result_text = f"Tool call failed: {e}"

            messages.append({
                "role": "tool",
                "content": result_text,
            })

    return "(stopped: too many tool-call rounds without a final answer)"


async def main():
    parser = argparse.ArgumentParser(description="Minimal MCP <-> Ollama bridge (Windows-safe)")
    parser.add_argument("--model", "-m", required=True, help="Ollama model tag, e.g. llama3.2:3b")
    args = parser.parse_args()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", SERVER_MODULE],
        cwd=str(PROJECT_ROOT),
    )

    print(f"Starting job-agent MCP server and connecting with model '{args.model}'...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"Connected. Available tools: {tool_names}\n")

            messages: list[dict] = []
            while True:
                try:
                    user_input = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting.")
                    break

                if user_input.lower() in ("exit", "quit", "bye"):
                    print("Exiting.")
                    break
                if not user_input:
                    continue

                messages.append({"role": "user", "content": user_input})
                answer = await run_tool_calling_loop(session, args.model, messages)
                print(f"\n{answer}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""Optional real SDK integration check: python tests/integration_mcp.py

Requires pip install -e . and mcp>=2; no external API, runs in memory.
"""
import asyncio
import os
import tempfile
import sys
from pathlib import Path

# Direct script invocation must test this source copy, not an editable global install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run() -> None:
    with tempfile.TemporaryDirectory() as temp:
        os.environ["CONTINUUM_DB"] = os.path.join(temp, "integration.sqlite3")
        os.environ.update(CONTINUUM_ACTOR="integration", CONTINUUM_WORKSPACE="lab", CONTINUUM_RUN_ID="integration")
        from mcp import Client
        from continuum.mcp_server import mcp
        async with Client(mcp) as client:
            first = await client.call_tool("continuum_bootstrap", {"workspace": "lab"})
            assert not first.is_error, first
            created = await client.call_tool("continuum_create_task", {
                "title": "Integration test", "objective": "MCP transport check", "next_step": "read task"
            })
            assert not created.is_error, created
            second = await client.call_tool("continuum_list_tasks", {"workspace": "lab"})
            assert not second.is_error, second
            print("MCP SDK integration: PASS")


if __name__ == "__main__":
    asyncio.run(run())

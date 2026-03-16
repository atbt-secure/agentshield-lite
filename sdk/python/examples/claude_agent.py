"""
Real-world example: Claude agent with AgentShield protection.

Uses Claude's tool use (function calling) to build an agent that can:
  - Query a database
  - Read/write files
  - Call external APIs

Every tool call is intercepted by AgentShield BEFORE execution.
High-risk or policy-violating calls are blocked automatically.

Requirements:
  pip install anthropic agentshield
  make dev   (in a separate terminal — start the AgentShield backend)

Usage:
  python claude_agent.py
  python claude_agent.py --prompt "Delete all old log entries"   # will be blocked
"""

import asyncio
import argparse
import json
import os
from typing import Any

import anthropic
import httpx

from agentshield import AgentShieldClient

# ── Configuration ─────────────────────────────────────────────────────────────

AGENTSHIELD_URL = os.getenv("AGENTSHIELD_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Tool definitions (Claude tool schema) ────────────────────────────────────

TOOLS: list[anthropic.types.ToolParam] = [
    {
        "name": "database_query",
        "description": "Run a read-only SQL SELECT query against the application database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL SELECT statement to execute.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return.",
                    "default": 100,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "database_delete",
        "description": "Delete rows from the database matching a condition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name."},
                "condition": {
                    "type": "string",
                    "description": "WHERE clause condition (e.g. 'created_at < NOW() - INTERVAL 30 DAYS').",
                },
            },
            "required": ["table", "condition"],
        },
    },
    {
        "name": "file_read",
        "description": "Read the contents of a file from the local filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "file_write",
        "description": "Write content to a file on the local filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write to."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "http_get",
        "description": "Make an HTTP GET request to an external URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch."},
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers.",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email to a recipient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Email body text."},
            },
            "required": ["to", "subject", "body"],
        },
    },
]

# ── Simulated tool implementations ───────────────────────────────────────────

def _execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Simulated tool execution (replace with real implementations)."""
    if tool_name == "database_query":
        query = tool_input["query"]
        # Simulate query results
        return json.dumps([
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ])

    elif tool_name == "database_delete":
        table = tool_input["table"]
        condition = tool_input["condition"]
        # Simulate — in real code this would execute SQL
        return f"DELETE FROM {table} WHERE {condition}: 42 rows affected"

    elif tool_name == "file_read":
        path = tool_input["path"]
        try:
            with open(path) as f:
                return f.read()[:2000]  # cap output
        except FileNotFoundError:
            return f"Error: file not found: {path}"

    elif tool_name == "file_write":
        path = tool_input["path"]
        content = tool_input["content"]
        # Simulate — restrict to /tmp in demo
        safe_path = f"/tmp/agentshield_demo_{os.path.basename(path)}"
        with open(safe_path, "w") as f:
            f.write(content)
        return f"Written to {safe_path} ({len(content)} bytes)"

    elif tool_name == "http_get":
        url = tool_input["url"]
        headers = tool_input.get("headers", {})
        try:
            resp = httpx.get(url, headers=headers, timeout=5.0, follow_redirects=True)
            return resp.text[:1000]  # cap output
        except Exception as e:
            return f"HTTP error: {e}"

    elif tool_name == "send_email":
        to = tool_input["to"]
        subject = tool_input["subject"]
        # Simulate — log instead of sending
        print(f"  📧 [SIMULATED] Email to {to}: {subject}")
        return f"Email sent to {to}: {subject}"

    return f"Unknown tool: {tool_name}"


# ── Map tool names to AgentShield tool/action categories ─────────────────────

def _tool_to_shield_params(tool_name: str) -> tuple[str, str]:
    """Map Claude tool names to (tool_category, action) for AgentShield."""
    mapping = {
        "database_query":  ("database", "query"),
        "database_delete": ("database", "delete"),
        "file_read":       ("files",    "read"),
        "file_write":      ("files",    "write"),
        "http_get":        ("http",     "get"),
        "send_email":      ("email",    "send_email"),
    }
    return mapping.get(tool_name, ("unknown", tool_name))


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run_agent(user_prompt: str, agent_id: str = "claude-demo-agent-v1") -> None:
    # Validate backend is reachable
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{AGENTSHIELD_URL}/health", timeout=3.0)
            resp.raise_for_status()
    except Exception:
        print(f"⚠️  AgentShield backend not reachable at {AGENTSHIELD_URL}")
        print("   Start it with: make dev")
        print("   Continuing WITHOUT protection (demo mode)\n")
        shield = None
    else:
        shield = AgentShieldClient(
            base_url=AGENTSHIELD_URL,
            agent_id=agent_id,
            raise_on_block=False,  # We handle blocks ourselves for better UX
        )

    anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": user_prompt}
    ]

    print(f"\n🛡️  AgentShield Demo Agent")
    print(f"   Agent ID : {agent_id}")
    print(f"   Protected: {'yes' if shield else 'no (backend offline)'}")
    print(f"   Prompt   : {user_prompt}\n")
    print("─" * 60)

    iteration = 0
    while True:
        iteration += 1

        # Call Claude (claude-opus-4-6 with adaptive thinking for complex tasks)
        response = anthropic_client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=(
                "You are a helpful AI assistant with access to database, file system, "
                "HTTP, and email tools. Be efficient and complete the task. "
                "If a tool call is blocked by security policy, explain what happened "
                "and suggest a safe alternative."
            ),
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        # Print any text Claude produced
        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"\n🤖 Claude: {block.text}\n")

        # Done — no more tool calls
        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_results: list[anthropic.types.ToolResultBlockParam] = []
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        for tool_use in tool_use_blocks:
            tool_name = tool_use.name
            tool_input = tool_use.input
            shield_tool, shield_action = _tool_to_shield_params(tool_name)

            print(f"🔧 Tool call: {tool_name}")
            print(f"   Input : {json.dumps(tool_input, indent=None)[:120]}")

            # ── AgentShield interception ──────────────────────────────────
            if shield:
                result = await shield.intercept(
                    tool=shield_tool,
                    action=shield_action,
                    prompt=user_prompt,
                    tool_input=tool_input,
                )

                risk_color = (
                    "🔴" if result.risk_score >= 81
                    else "🟠" if result.risk_score >= 61
                    else "🟡" if result.risk_score >= 31
                    else "🟢"
                )
                print(f"   Shield: {risk_color} risk={result.risk_score:.0f} "
                      f"decision={result.policy_decision} "
                      f"(log #{result.log_id})")

                if not result.allowed:
                    print(f"   ⛔ BLOCKED: {result.message}")
                    tool_result_content = (
                        f"[BLOCKED by AgentShield] {result.message}. "
                        f"Risk score: {result.risk_score:.0f}/100. "
                        f"Flags: {', '.join(result.risk_flags) or 'none'}."
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result_content,
                        "is_error": True,
                    })
                    continue

                if result.risk_flags:
                    print(f"   ⚠️  Flags: {', '.join(result.risk_flags)}")
            else:
                print("   Shield: skipped (backend offline)")

            # ── Execute the tool ──────────────────────────────────────────
            tool_output = _execute_tool(tool_name, tool_input)
            print(f"   Output: {str(tool_output)[:80]}{'...' if len(str(tool_output)) > 80 else ''}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": tool_output,
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if iteration >= 10:
            print("\n⚠️  Max iterations reached.")
            break

    print("\n" + "─" * 60)
    print("✅ Agent finished.")
    if shield:
        print(f"   View activity at http://localhost:8080")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Claude agent with AgentShield protection")
    parser.add_argument(
        "--prompt",
        default="Get a list of users from the database and send a summary email to admin@company.com",
        help="The task for the agent to perform",
    )
    parser.add_argument("--agent-id", default="claude-demo-agent-v1")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY environment variable is not set.")
        return

    await run_agent(args.prompt, args.agent_id)


if __name__ == "__main__":
    asyncio.run(main())

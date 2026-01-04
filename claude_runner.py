"""Wrapper for running Claude Code in headless mode."""
import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import CLAUDE_CODE_PATH, CLAUDE_WORKING_DIR

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResponse:
    """Response from Claude Code."""
    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    images: Optional[list[str]] = None  # Base64 encoded images from screenshots


async def run_claude(
    prompt: str,
    session_id: Optional[str] = None,
    continue_recent: bool = False,
    working_dir: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    timeout: int = 300,
    enable_browser: bool = True,
) -> ClaudeResponse:
    """
    Run Claude Code in headless mode.

    Args:
        prompt: The prompt to send to Claude Code
        session_id: Specific session ID to resume (--resume)
        continue_recent: Continue most recent session (--continue)
        working_dir: Working directory for Claude Code
        allowed_tools: List of allowed tools (default: common tools)
        timeout: Timeout in seconds
        enable_browser: Enable browser automation tools (requires Chrome extension)

    Returns:
        ClaudeResponse with output and session info
    """
    cmd = [CLAUDE_CODE_PATH, "-p", prompt, "--output-format", "json"]

    # Enable all tools without permission prompts (needed for MCP/browser)
    if enable_browser:
        cmd.append("--dangerously-skip-permissions")

    if session_id:
        cmd.extend(["--resume", session_id])
    elif continue_recent:
        cmd.append("--continue")

    # Only restrict tools if explicitly specified (browser mode allows all)
    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])
    elif not enable_browser:
        # Default safe set of tools when browser is disabled
        cmd.extend(["--allowedTools", "Read,Edit,Write,Bash,Glob,Grep,Task,TodoWrite,WebSearch,WebFetch"])

    work_dir = working_dir or CLAUDE_WORKING_DIR

    logger.info(f"Running Claude Code: {' '.join(cmd)}")
    logger.info(f"Working directory: {work_dir}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            logger.error(f"Claude Code failed: {stderr_text}")
            return ClaudeResponse(
                success=False,
                output="",
                error=f"Claude Code error: {stderr_text or 'Unknown error'}"
            )

        # Parse JSON output to extract session_id and result
        response = parse_claude_output(stdout_text)
        return response

    except asyncio.TimeoutError:
        logger.error(f"Claude Code timed out after {timeout}s")
        return ClaudeResponse(
            success=False,
            output="",
            error=f"Claude Code timed out after {timeout} seconds"
        )
    except Exception as e:
        logger.exception("Error running Claude Code")
        return ClaudeResponse(
            success=False,
            output="",
            error=f"Error running Claude Code: {str(e)}"
        )


def parse_claude_output(output: str) -> ClaudeResponse:
    """Parse Claude Code JSON output."""
    try:
        # Claude Code outputs multiple JSON objects, one per line for streaming
        # The final complete result is what we want
        lines = output.strip().split("\n")

        session_id = None
        result_text = ""
        images = []

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)

                # Extract session_id if present
                if "session_id" in data:
                    session_id = data["session_id"]

                # Extract the result/output
                if "result" in data:
                    result_text = data["result"]
                elif "content" in data:
                    result_text = data["content"]
                elif "message" in data:
                    result_text = data["message"]

                # Extract images from tool results (screenshots)
                if "tool_results" in data:
                    for tool_result in data["tool_results"]:
                        if isinstance(tool_result, dict):
                            # Check for image content
                            content = tool_result.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "image":
                                        img_data = item.get("data") or item.get("source", {}).get("data")
                                        if img_data:
                                            images.append(img_data)

            except json.JSONDecodeError:
                # Not JSON, might be plain text output
                result_text = line

        # If we didn't find structured output, use the raw output
        if not result_text:
            result_text = output

        # Filter out <thinking> tags from output
        import re
        result_text = re.sub(r'<thinking>.*?</thinking>\s*', '', result_text, flags=re.DOTALL)
        result_text = result_text.strip()

        return ClaudeResponse(
            success=True,
            output=result_text,
            session_id=session_id,
            images=images if images else None
        )

    except Exception as e:
        logger.exception("Error parsing Claude output")
        # Return raw output on parse error
        return ClaudeResponse(
            success=True,
            output=output,
            error=f"Parse warning: {str(e)}"
        )


async def test_claude_connection() -> bool:
    """Test if Claude Code is available and working."""
    try:
        result = await run_claude(
            "Say 'Claude Code is working!' and nothing else.",
            timeout=30
        )
        return result.success and "working" in result.output.lower()
    except Exception as e:
        logger.error(f"Claude Code connection test failed: {e}")
        return False


if __name__ == "__main__":
    # Quick test
    import asyncio
    logging.basicConfig(level=logging.INFO)

    async def main():
        print("Testing Claude Code connection...")
        if await test_claude_connection():
            print("Claude Code is working!")
        else:
            print("Claude Code test failed")

    asyncio.run(main())

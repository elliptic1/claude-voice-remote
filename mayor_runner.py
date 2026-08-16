"""Runner for Mayor-style Claude Code execution.

Runs Claude Code from the Gastown HQ directory with access to all workspaces.
This bypasses the tmux-based Mayor session for faster synchronous responses.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Gastown HQ directory - has CLAUDE.md with project context
MAYOR_DIR = os.path.expanduser("~/gt")
CLAUDE_CODE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")

# Store session ID for conversation continuity
_mayor_session_id: Optional[str] = None


@dataclass
class MayorResponse:
    """Response from the Mayor."""
    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None


def check_mayor_running() -> bool:
    """Check if the Gastown HQ directory exists."""
    return os.path.exists(MAYOR_DIR) and os.path.exists(os.path.join(MAYOR_DIR, "CLAUDE.md"))


def start_mayor() -> bool:
    """No-op for compatibility - Mayor dir should already exist."""
    return check_mayor_running()


async def run_mayor(
    prompt: str,
    timeout: int = 3000,
) -> MayorResponse:
    """
    Run Claude Code from the Mayor's directory.

    This gives Claude access to:
    - ~/gt/CLAUDE.md (Mayor context with project info)
    - /media/todd/androiddev/workspace (via additionalDirectories)

    Args:
        prompt: The prompt to send
        timeout: Maximum time to wait for response

    Returns:
        MayorResponse with output
    """
    global _mayor_session_id

    if not check_mayor_running():
        return MayorResponse(
            success=False,
            output="",
            error="Mayor directory not found. Run 'gt install ~/gt --git' first."
        )

    cmd = [
        CLAUDE_CODE_PATH,
        "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions",
    ]

    # Resume previous session if we have one
    if _mayor_session_id:
        cmd.extend(["--resume", _mayor_session_id])

    logger.info(f"Running Mayor Claude: {prompt[:100]}...")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=MAYOR_DIR,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            logger.error(f"Mayor Claude failed: {stderr_text}")
            return MayorResponse(
                success=False,
                output="",
                error=f"Mayor error: {stderr_text or 'Unknown error'}"
            )

        # Parse JSON output
        response = parse_claude_output(stdout_text)
        return response

    except asyncio.TimeoutError:
        logger.error(f"Mayor Claude timed out after {timeout}s")
        return MayorResponse(
            success=False,
            output="",
            error=f"Mayor timed out after {timeout} seconds"
        )
    except Exception as e:
        logger.exception("Error running Mayor Claude")
        return MayorResponse(
            success=False,
            output="",
            error=f"Error: {str(e)}"
        )


def parse_claude_output(output: str) -> MayorResponse:
    """Parse Claude Code JSON output."""
    global _mayor_session_id

    try:
        lines = output.strip().split("\n")
        result_text = ""
        session_id = None

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)

                # Extract session_id if present
                if "session_id" in data:
                    session_id = data["session_id"]

                if "result" in data:
                    result_text = data["result"]
                elif "content" in data:
                    result_text = data["content"]
                elif "message" in data:
                    result_text = data["message"]

            except json.JSONDecodeError:
                result_text = line

        if not result_text:
            result_text = output

        # Store session ID for next request
        if session_id:
            _mayor_session_id = session_id
            logger.info(f"Mayor session ID: {session_id}")

        # Clean up response
        result_text = clean_response(result_text)

        return MayorResponse(
            success=True,
            output=result_text,
            session_id=session_id
        )

    except Exception as e:
        logger.exception("Error parsing Claude output")
        return MayorResponse(
            success=True,
            output=output,
            error=f"Parse warning: {str(e)}"
        )


def reset_mayor_session() -> None:
    """Reset the Mayor session to start fresh."""
    global _mayor_session_id
    _mayor_session_id = None
    logger.info("Mayor session reset")


def get_mayor_session_id() -> Optional[str]:
    """Get the current Mayor session ID."""
    return _mayor_session_id


def clean_response(text: str) -> str:
    """Clean up the response text."""
    # Remove thinking tags
    text = re.sub(r'<thinking>.*?</thinking>\s*', '', text, flags=re.DOTALL)
    return text.strip()


async def test_mayor_connection() -> bool:
    """Test if the Mayor is available and responding."""
    try:
        if not check_mayor_running():
            return False

        result = await run_mayor(
            "Say 'Mayor online' and nothing else.",
            timeout=30
        )
        return result.success and "online" in result.output.lower()
    except Exception as e:
        logger.error(f"Mayor connection test failed: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        print("Testing Mayor connection...")

        if not check_mayor_running():
            print("Mayor directory not found!")
            return

        print("Sending test prompt...")
        result = await run_mayor("What projects can you see? List them briefly.")

        if result.success:
            print(f"\nMayor responded:\n{result.output}")
        else:
            print(f"\nMayor error: {result.error}")

    asyncio.run(main())

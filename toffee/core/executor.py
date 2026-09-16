"""
Subprocess execution helpers for Terraform commands.
"""

import subprocess
from typing import Dict, List, Optional, Tuple


def run_streamed(
    cmd: List[str], process_env: Optional[Dict[str, str]] = None
) -> int:
    """
    Run a Terraform command with inherited stdio so interactive prompts work.

    Args:
        cmd: Full command as a list of strings

    Returns:
        Process exit code
    """
    return subprocess.Popen(cmd, env=process_env).wait()


def run_captured(
    cmd: List[str], process_env: Optional[Dict[str, str]] = None
) -> Tuple[int, str]:
    """
    Run a Terraform command capturing combined stdout/stderr.

    Used for parallel execution so each environment's output can be printed
    as one grouped block instead of interleaving with other processes.

    Args:
        cmd: Full command as a list of strings

    Returns:
        Tuple of (exit_code, combined_output)
    """
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=process_env,
    )
    return process.returncode, process.stdout

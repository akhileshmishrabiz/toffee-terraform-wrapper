"""
Subprocess execution helpers for Terraform commands.
"""

import subprocess
from typing import List


def run_terraform_command(cmd: List[str]) -> int:
    """
    Run a Terraform command with inherited stdio so interactive prompts work.

    Args:
        cmd: Full command as a list of strings

    Returns:
        Process exit code
    """
    process = subprocess.Popen(cmd)
    return process.wait()

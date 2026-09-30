"""
Subprocess execution helpers for Terraform commands.
"""

import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence, Tuple

Job = Tuple[List[str], Optional[Dict[str, str]]]
CapturedResult = Tuple[int, bytes, bytes]


class _SignalForwarding:
    """Let Terraform shut down cleanly before Toffee exits.

    Ctrl-C reaches Terraform directly through the terminal's process group, so
    Toffee ignores it while waiting. SIGTERM is only sent to Toffee, so it is
    forwarded. Signal handlers can only be installed from the main thread.
    """

    def __init__(self) -> None:
        self._processes: List[subprocess.Popen] = []
        self._lock = threading.Lock()
        self._previous: Dict[int, object] = {}

    def track(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.append(process)

    def _ignore(self, signum, frame) -> None:
        pass

    def _forward(self, signum, frame) -> None:
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            if process.poll() is None:
                try:
                    process.send_signal(signum)
                except OSError:
                    pass

    def __enter__(self) -> "_SignalForwarding":
        if threading.current_thread() is threading.main_thread():
            # A Python handler (unlike SIG_IGN) is reset for child processes.
            self._previous[signal.SIGINT] = signal.signal(signal.SIGINT, self._ignore)
            self._previous[signal.SIGTERM] = signal.signal(
                signal.SIGTERM, self._forward
            )
        return self

    def __exit__(self, *exc_info) -> None:
        for signum, handler in self._previous.items():
            signal.signal(signum, handler)


def _exit_status(returncode: int) -> int:
    """Map "killed by signal N" to the shell convention 128 + N."""
    return 128 - returncode if returncode < 0 else returncode


def run_streamed(cmd: List[str], process_env: Optional[Dict[str, str]] = None) -> int:
    """
    Run a Terraform command with inherited stdio so interactive prompts work.

    Args:
        cmd: Full command as a list of strings

    Returns:
        Process exit code
    """
    with _SignalForwarding() as forwarding:
        process = subprocess.Popen(cmd, env=process_env)
        forwarding.track(process)
        return _exit_status(process.wait())


def run_parallel(jobs: Sequence[Job], max_workers: int = 8) -> List[CapturedResult]:
    """
    Run commands concurrently, capturing stdout and stderr separately as bytes.

    Stdin is closed so a command that unexpectedly prompts fails instead of
    waiting forever for input nobody can see. Results keep the order of jobs.
    """
    with _SignalForwarding() as forwarding:

        def run(job: Job) -> CapturedResult:
            cmd, process_env = job
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=process_env,
                )
            except OSError as e:
                return 1, b"", f"Error executing command: {e}\n".encode()
            forwarding.track(process)
            stdout, stderr = process.communicate()
            return _exit_status(process.returncode), stdout, stderr

        with ThreadPoolExecutor(
            max_workers=max(1, min(len(jobs), max_workers))
        ) as pool:
            return list(pool.map(run, jobs))

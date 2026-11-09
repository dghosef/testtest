"""Words for a child process's exit status, for log lines and error messages."""

import signal


def describe_exitcode(exitcode: int | None) -> str:
    """Render ``multiprocessing.Process.exitcode`` as the exit code, the name of
    the signal that killed the process, or unknown while it is still running."""
    if exitcode is None:
        return "an unknown status"
    if exitcode < 0:
        try:
            return f"signal {signal.Signals(-exitcode).name}"
        except ValueError:
            return f"signal {-exitcode}"
    return f"exit code {exitcode}"


def first_failed(exitcodes: list[int | None]) -> int | None:
    """Return the index of the first process that failed (a non-zero exit code or
    killed by a signal), or ``None`` when none has failed or exited yet."""
    for index, code in enumerate(exitcodes):
        if code is not None and code != 0:
            return index
    return None

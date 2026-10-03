"""Cooperative job cancellation and interruptible subprocesses.

Whisper inference is checked between stages; FFmpeg/yt-dlp process groups are
terminated promptly. Context-local state keeps concurrent jobs independent.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

_CANCEL: ContextVar[threading.Event | None] = ContextVar("clipforge_cancel", default=None)


class JobCancelled(Exception):
    pass


@contextmanager
def cancellation_scope(event: threading.Event):
    token = _CANCEL.set(event)
    try:
        yield
    finally:
        _CANCEL.reset(token)


def check_cancelled() -> None:
    event = _CANCEL.get()
    if event is not None and event.is_set():
        raise JobCancelled("Job cancelled.")


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
    except ProcessLookupError:
        process.communicate()


def run_process(args: list[str], *, timeout: float = 3600, cwd=None,
                capture_output: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    check_cancelled()
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(
        args, cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text, start_new_session=True,
    )
    try:
        while True:
            check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(0.25, remaining))
                check_cancelled()
                return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(args, timeout)
    except BaseException:
        _terminate(process)
        raise

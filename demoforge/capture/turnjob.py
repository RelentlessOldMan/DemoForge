"""Nothing the agent starts outlives its turn.

A headless turn ends when the agent stops talking. Anything it launched that is
still running (a detached ``Start-Process``, a ``nohup``) would keep using the
machine with nobody waiting for it, and its results would never reach the
conversation. The agent is told so up front (:data:`TURN_NOTE`), and this module
enforces it: on Windows the CLI runs in a job object that kills every process in
it when closed; elsewhere it leads a new session whose process group is killed.
"""

from __future__ import annotations

import os
import signal
import subprocess

# Appended to the agent's system prompt, so it plans its work for the session it
# is really in: a person who sees its reply, and nothing running in between.
TURN_NOTE = (
    "This session is non-interactive between messages. When you end your reply, "
    "every process you started that is still running is stopped, and nothing "
    "wakes you up later: you cannot check back on a run. Finish any long command "
    "in the foreground before you reply; a single command may run for up to "
    "{minutes} minutes. If the work asked for would take longer than that, say "
    "so and propose a run that fits."
)

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)


def popen_kwargs() -> dict:
    """Extra ``Popen`` arguments for a process that :class:`TurnJob` can contain."""
    return {} if os.name == "nt" else {"start_new_session": True}


class TurnJob:
    """Holds a turn's process tree; :meth:`close` ends whatever is left of it."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self._job = None
        if os.name == "nt":
            job = _k32.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _ExtendedLimits()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = _k32.SetInformationJobObject(
                job, _JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info))
            handle = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid)
            try:
                if not ok or not handle or not _k32.AssignProcessToJobObject(job, handle):
                    err = ctypes.get_last_error()
                    _k32.CloseHandle(job)
                    raise ctypes.WinError(err)
            finally:
                if handle:
                    _k32.CloseHandle(handle)
            self._job = job

    def close(self) -> None:
        """Kill every process still in the turn's tree. Safe to call twice."""
        if os.name == "nt":
            if self._job:
                _k32.CloseHandle(self._job)  # KILL_ON_JOB_CLOSE ends the tree
                self._job = None
            return
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

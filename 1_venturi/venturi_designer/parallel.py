"""
parallel.py
===========
How many processes the project may use, and a small ordered process pool.

One cap for the TOTAL number of processes of a run (SISTEMA["processi"] of input.py):

    None        automatic: min(physical cores, floor(0.6 x free RAM / 1.5 GB)), at least 1
    n >= 1      that many

The cap is a budget that is split going inwards. Every level that has several independent jobs
(cases of a series, then the Statore/NoStatore variants, then the inner jobs of the venturi: scan
cases, alternatives, exit scan points, grid study) takes

    workers = min(number of jobs, budget)        processes of its own
    child budget = budget // workers             what each worker may still use inside

so the workers of all the levels together never exceed the budget. A budget of 1 means no pool at
all: the plain sequential code, as before. A process that was given a budget of 1 runs everything
inside it in sequence.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

GB = 1024 ** 3
GB_PER_PROCESS = 1.5       # memory one process of the chain may take (flow solver, fan)
RAM_SHARE = 0.6            # share of the free RAM the processes may take together


def free_ram_bytes() -> Optional[int]:
    """Free physical RAM [bytes]: psutil if installed, else GlobalMemoryStatusEx (Windows),
    else sysconf (Linux); None if it cannot be known."""
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:
            return None
        return None
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError, AttributeError):
        return None


def physical_cores() -> int:
    """Physical cores: psutil if installed, else half of the logical ones (hyper-threading)."""
    try:
        import psutil
        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def auto_processes(cores: Optional[int] = None, free_bytes: Optional[int] = None) -> int:
    """min(physical cores, floor(0.6 x free RAM / 1.5 GB)), at least 1 (RAM unknown: cores)."""
    cores = physical_cores() if cores is None else int(cores)
    free = free_ram_bytes() if free_bytes is None else free_bytes
    n = cores
    if free is not None:
        n = min(n, int(RAM_SHARE * free // (GB_PER_PROCESS * GB)))
    return max(1, n)


def resolve_processes(value) -> int:
    """SISTEMA["processi"]: None = automatic, else an integer >= 1."""
    if value is None:
        return auto_processes()
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"SISTEMA['processi'] = {value!r}: use None or an integer >= 1.")
    return value


def split_budget(n_jobs: int, budget: Optional[int]) -> Tuple[int, int]:
    """(workers of this level, budget of each worker) for n_jobs jobs and a total budget."""
    budget = max(1, int(budget or 1))
    workers = max(1, min(int(n_jobs), budget))
    return workers, max(1, budget // workers)


def map_ordered(func: Callable, payloads: Sequence, workers: int,
                on_done: Optional[Callable] = None) -> List:
    """[func(p) for p in payloads] in worker processes, results in the order of payloads.

    func must be a module level function and the payloads picklable (Windows spawn).
    on_done(index, result) is called in this process as each job finishes. An exception of a
    job is raised here when its result is collected, after the other jobs have finished.
    """
    payloads = list(payloads)
    results: List = [None] * len(payloads)
    if workers <= 1 or len(payloads) <= 1:
        for i, p in enumerate(payloads):
            results[i] = func(p)
            if on_done:
                on_done(i, results[i])
        return results
    errors: List = []
    with ProcessPoolExecutor(max_workers=min(workers, len(payloads))) as pool:
        futures = {pool.submit(func, p): i for i, p in enumerate(payloads)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except BaseException as exc:          # the others go on; the first one is raised below
                errors.append(exc)
                continue
            if on_done:
                on_done(i, results[i])
    if errors:
        raise errors[0]
    return results

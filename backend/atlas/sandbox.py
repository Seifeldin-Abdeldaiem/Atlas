"""Parse untrusted files in a child process with a memory cap and a timeout,
so a hostile or pathological file can't take down the worker."""

from __future__ import annotations

import multiprocessing as mp
import resource

from .errors import AtlasError, IngestError
from .ingest import IngestResult, ingest
from .ingest.types import Limits


def _child(conn, data: bytes, sheet: str | None, limits: Limits, memory_bytes: int) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (ValueError, OSError):
        pass  # not permitted on this platform; the timeout still applies
    try:
        conn.send(("ok", ingest(data, sheet=sheet, limits=limits)))
    except AtlasError as error:
        conn.send(("error", error.code))
    except MemoryError:
        conn.send(("error", "file_too_complex"))
    except Exception:
        conn.send(("error", "unreadable_file"))
    finally:
        conn.close()


def run_ingest(data: bytes, sheet: str | None, limits: Limits, timeout_seconds: int, memory_mb: int) -> IngestResult:
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(child, data, sheet, limits, memory_mb * 1024 * 1024), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(timeout_seconds):
            raise IngestError("file_too_complex")
        status, value = parent.recv()
    except EOFError:
        # Child died without answering (e.g. killed for exceeding memory).
        raise IngestError("file_too_complex") from None
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()
    if status == "error":
        raise IngestError(value)
    return value


def _child_call(conn, fn, args, memory_bytes: int) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (ValueError, OSError):
        pass
    try:
        conn.send(("ok", fn(*args)))
    except MemoryError:
        conn.send(("error", "file_too_complex"))
    except Exception:
        conn.send(("error", "export_failed"))
    finally:
        conn.close()


def run_limited(fn, args: tuple, timeout_seconds: int, memory_mb: int):
    """Run fn(*args) in a child process with a memory cap and a timeout (used
    to write export files). fn must be a module-level function."""
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child_call, args=(child, fn, args, memory_mb * 1024 * 1024), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(timeout_seconds):
            raise AtlasError("export_failed")
        status, value = parent.recv()
    except EOFError:
        raise AtlasError("export_failed") from None
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()
    if status == "error":
        raise AtlasError(value)
    return value

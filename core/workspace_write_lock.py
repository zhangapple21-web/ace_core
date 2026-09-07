import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict


class WorkspaceWriteLock:
    def __init__(self, workspace: Path, owner_id: str, run_id: str = ""):
        self.workspace = Path(workspace)
        self.owner_id = owner_id
        self.run_id = run_id
        self.lock_file = self.workspace / ".workspace.write.lock"
        self.token = ""

    def __enter__(self) -> "WorkspaceWriteLock":
        result = self.acquire()
        if not result.get("acquired"):
            raise RuntimeError(result.get("reason", "workspace_write_locked"))
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        self.release()
        return False

    def acquire(self) -> Dict[str, Any]:
        self.workspace.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        owner = {
            "pid": os.getpid(),
            "owner_id": self.owner_id,
            "run_id": self.run_id or None,
            "token": token,
            "created_at": time.time(),
            "process_started_at": self._process_started_at(os.getpid()),
        }
        for _ in range(2):
            try:
                descriptor = os.open(
                    str(self.lock_file),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                current_owner = self._read_owner()
                if not current_owner or self._owner_alive(current_owner):
                    return self._conflict(current_owner)
                try:
                    self.lock_file.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(owner, handle)
                handle.flush()
                os.fsync(handle.fileno())
            self.token = token
            return {"acquired": True, "owner": owner}
        return self._conflict(self._read_owner())

    def _conflict(self, owner: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "acquired": False,
            "reason": "workspace_write_locked",
            "owner": owner,
            "lock_file": str(self.lock_file),
            "recommendation": "wait_for_current_owner_or_verify_stale_lock",
        }

    def release(self) -> None:
        if not self.token:
            return
        try:
            owner = self._read_owner()
            if owner.get("token") == self.token:
                self.lock_file.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.token = ""

    def _process_started_at(self, pid: int) -> float | None:
        if os.name == "nt":
            try:
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
                if not handle:
                    return None
                try:
                    creation = ctypes.c_ulonglong()
                    exit_time = ctypes.c_ulonglong()
                    kernel_time = ctypes.c_ulonglong()
                    user_time = ctypes.c_ulonglong()
                    ok = ctypes.windll.kernel32.GetProcessTimes(
                        handle,
                        ctypes.byref(creation),
                        ctypes.byref(exit_time),
                        ctypes.byref(kernel_time),
                        ctypes.byref(user_time),
                    )
                    if not ok:
                        return None
                    return creation.value / 10_000_000 - 11644473600
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                return None
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            start_ticks = int(stat.rsplit(")", 1)[1].split()[19])
            clock_ticks = os.sysconf("SC_CLK_TCK")
            boot_time = time.time() - time.monotonic()
            return boot_time + start_ticks / clock_ticks
        except (OSError, ValueError, IndexError, AttributeError):
            return None

    def _owner_alive(self, owner: Dict[str, Any]) -> bool:
        pid = owner.get("pid") if isinstance(owner, dict) else None
        recorded_start = owner.get("process_started_at") if isinstance(owner, dict) else None
        if not isinstance(pid, int) or pid <= 0:
            return False
        if isinstance(recorded_start, (int, float)):
            current_start = self._process_started_at(pid)
            if current_start is not None and abs(current_start - float(recorded_start)) > 1.0:
                return False
        if os.name == "nt":
            try:
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    return False
                try:
                    exit_code = ctypes.c_ulong()
                    return bool(
                        ctypes.windll.kernel32.GetExitCodeProcess(
                            handle,
                            ctypes.byref(exit_code),
                        )
                        and exit_code.value == 259
                    )
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _read_owner(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.lock_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

"""0D Windows ownership primitives; no PID-name based or remote process control.

Child creation is suspended until its handle is assigned to a kill-on-close job.
Only the newly created handle may be terminated if assignment/resume fails.
All later cleanup closes that owned job; no process-tree guessing is performed.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
import socket
import subprocess


class WindowsError(RuntimeError):
    pass


class BasicLimit(c.Structure):
    _fields_ = [("ProcessTime", c.c_longlong), ("JobTime", c.c_longlong),
                ("LimitFlags", w.DWORD), ("MinWS", c.c_size_t), ("MaxWS", c.c_size_t),
                ("ActiveProcessLimit", w.DWORD), ("Affinity", c.c_size_t),
                ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]


class ExtendedLimit(c.Structure):
    _fields_ = [("Basic", BasicLimit), ("Io", c.c_ulonglong * 6),
                ("ProcessMemoryLimit", c.c_size_t), ("JobMemoryLimit", c.c_size_t),
                ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]


class MemoryStatus(c.Structure):
    _fields_ = [("length", w.DWORD), ("load", w.DWORD)] + [
        (name, c.c_ulonglong) for name in
        ("total", "available", "page_total", "page_available", "virtual", "virtual_available", "extended")]


class NativeWindows:
    def __init__(self):
        if os.name != "nt":
            raise WindowsError("Windows only")
        self.k = c.WinDLL("kernel32", use_last_error=True)
        self.a = c.WinDLL("advapi32", use_last_error=True)
        def bind(dll, name, result, *args):
            fn = getattr(dll, name)
            fn.restype, fn.argtypes = result, list(args)
        bind(self.k, "CloseHandle", w.BOOL, w.HANDLE)
        bind(self.k, "LocalFree", w.HANDLE, w.HANDLE)
        bind(self.k, "CreateMutexW", w.HANDLE, c.c_void_p, w.BOOL, w.LPCWSTR)
        bind(self.k, "ReleaseMutex", w.BOOL, w.HANDLE)
        bind(self.k, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        bind(self.k, "CreateEventW", w.HANDLE, c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR)
        bind(self.k, "OpenEventW", w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
        bind(self.k, "SetEvent", w.BOOL, w.HANDLE)
        bind(self.k, "CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
        bind(self.k, "SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
        bind(self.k, "QueryInformationJobObject", w.BOOL, w.HANDLE, c.c_int,
             c.c_void_p, w.DWORD, c.POINTER(w.DWORD))
        bind(self.k, "AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
        bind(self.k, "IsProcessInJob", w.BOOL, w.HANDLE, w.HANDLE, c.POINTER(w.BOOL))
        bind(self.k, "ResumeThread", w.DWORD, w.HANDLE)
        bind(self.k, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
        bind(self.k, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        bind(self.k, "GetProcessId", w.DWORD, w.HANDLE)
        bind(self.k, "GetProcessTimes", w.BOOL, w.HANDLE,
             *([c.POINTER(w.FILETIME)] * 4))
        bind(self.k, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD,
             w.LPWSTR, c.POINTER(w.DWORD))
        bind(self.k, "GlobalMemoryStatusEx", w.BOOL, c.POINTER(MemoryStatus))
        bind(self.a, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, c.POINTER(w.HANDLE))
        bind(self.a, "GetTokenInformation", w.BOOL, w.HANDLE, c.c_int,
             c.c_void_p, w.DWORD, c.POINTER(w.DWORD))
        bind(self.a, "ConvertSidToStringSidW", w.BOOL, c.c_void_p, c.POINTER(w.LPWSTR))

    def checked(self, result, message):
        if not result:
            raise WindowsError(f"{message} (WinError {c.get_last_error()})")
        return result

    def close(self, handle):
        if handle:
            self.k.CloseHandle(handle)

    def alive(self, handle):
        return self.k.WaitForSingleObject(handle, 0) == 258

    @contextmanager
    def process(self, pid):
        if type(pid) is not int or pid <= 0:
            raise WindowsError("Invalid PID")
        handle = self.checked(self.k.OpenProcess(0x1000 | 0x100000, False, pid),
                              "Cannot query process")
        try:
            yield handle
        finally:
            self.close(handle)

    def sid(self, handle):
        token = w.HANDLE()
        self.checked(self.a.OpenProcessToken(handle, 8, c.byref(token)), "Cannot read owner token")
        try:
            needed = w.DWORD()
            self.a.GetTokenInformation(token, 1, None, 0, c.byref(needed))
            buf = c.create_string_buffer(needed.value)
            self.checked(self.a.GetTokenInformation(token, 1, buf, needed, c.byref(needed)),
                         "Cannot read token user")
            sid_pointer = c.cast(buf, c.POINTER(c.c_void_p))[0]
            value = w.LPWSTR()
            self.checked(self.a.ConvertSidToStringSidW(sid_pointer, c.byref(value)),
                         "Cannot format owner SID")
            try:
                return value.value
            finally:
                self.k.LocalFree(c.cast(value, w.HANDLE))
        finally:
            self.close(token)

    def identity(self, handle):
        if not self.alive(handle):
            raise WindowsError("Process has exited")
        times = [w.FILETIME() for _ in range(4)]
        self.checked(self.k.GetProcessTimes(handle, *(c.byref(t) for t in times)),
                     "Cannot read creation time")
        path, length = c.create_unicode_buffer(32768), w.DWORD(32768)
        self.checked(self.k.QueryFullProcessImageNameW(handle, 0, path, c.byref(length)),
                     "Cannot read executable path")
        return {"pid": int(self.k.GetProcessId(handle)),
                "created_filetime": times[0].dwHighDateTime << 32 | times[0].dwLowDateTime,
                "exe": path.value, "owner_sid": self.sid(handle)}

    @staticmethod
    def same(expected, observed):
        return (type(expected) is dict and type(observed) is dict
                and type(expected.get("pid")) is int and expected["pid"] > 0
                and type(expected.get("created_filetime")) is int and expected["created_filetime"] > 0
                and type(expected.get("exe")) is str and bool(expected["exe"])
                and type(expected.get("owner_sid")) is str and bool(expected["owner_sid"])
                and expected["pid"] == observed.get("pid")
                and expected["created_filetime"] == observed.get("created_filetime")
                and expected["exe"].casefold() == str(observed.get("exe", "")).casefold()
                and expected["owner_sid"] == observed.get("owner_sid"))

    def memory(self):
        info = MemoryStatus()
        info.length = c.sizeof(info)
        self.checked(self.k.GlobalMemoryStatusEx(c.byref(info)), "RAM telemetry unknown")
        return {"total_gib": info.total / 2**30, "free_gib": info.available / 2**30}

    def listeners(self):
        """IPv4 listening PID table; never bind or connect to a LAN endpoint."""
        dll = c.WinDLL("iphlpapi", use_last_error=True)
        query = dll.GetExtendedTcpTable
        query.argtypes = [c.c_void_p, c.POINTER(w.DWORD), w.BOOL, w.ULONG, c.c_int, w.ULONG]
        query.restype = w.DWORD
        size = w.DWORD()
        result = query(None, c.byref(size), False, 2, 3, 0)
        if result != 122 or not size.value:
            raise WindowsError("TCP listener inventory unknown")
        buf = c.create_string_buffer(size.value)
        if query(buf, c.byref(size), False, 2, 3, 0) != 0:
            raise WindowsError("TCP listener inventory changed/unavailable")
        count = c.cast(buf, c.POINTER(w.DWORD))[0]
        if 4 + count * 24 > size.value:
            raise WindowsError("Invalid listener inventory")
        rows = []
        for i in range(count):
            row = (w.DWORD * 6).from_buffer(buf, 4 + i * 24)
            rows.append({"port": socket.ntohs(row[2] & 0xffff), "pid": int(row[5])})
        return rows

    def job_pids(self, job):
        buf = c.create_string_buffer(8 + 128 * c.sizeof(c.c_size_t))
        self.checked(self.k.QueryInformationJobObject(job, 3, buf, c.sizeof(buf), None),
                     "Cannot enumerate owned job")
        assigned, count = (w.DWORD * 2).from_buffer(buf)
        if count > 128 or count != assigned:
            raise WindowsError("Unexpected owned process count")
        return list((c.c_size_t * count).from_buffer(buf, 8))

    @contextmanager
    def mutex(self, name):
        handle = self.checked(self.k.CreateMutexW(None, False, name), "Cannot open lifecycle mutex")
        acquired = False
        try:
            result = self.k.WaitForSingleObject(handle, 0)
            if result not in (0, 128):
                raise WindowsError("Colibri2 lifecycle already owned; no action")
            acquired = True
            yield
        finally:
            if acquired:
                self.k.ReleaseMutex(handle)
            self.close(handle)

    def event(self, name):
        handle = self.checked(self.k.CreateEventW(None, True, False, name), "Cannot create stop event")
        if c.get_last_error() == 183:
            self.close(handle)
            raise WindowsError("Session stop event already exists")
        return handle

    def signal_event(self, name):
        handle = self.checked(self.k.OpenEventW(2, False, name), "No owned supervisor stop event")
        try:
            self.checked(self.k.SetEvent(handle), "Cannot signal owned stop event")
        finally:
            self.close(handle)

    def job(self, name, private_limit_gib):
        handle = self.checked(self.k.CreateJobObjectW(None, name), "Cannot create owned job")
        if c.get_last_error() == 183:
            self.close(handle)
            raise WindowsError("Session job already exists")
        limits = ExtendedLimit()
        # KILL_ON_JOB_CLOSE | JOB_MEMORY | PRIORITY_CLASS; no breakaway allowed.
        limits.Basic.LimitFlags = 0x2000 | 0x200 | 0x20
        limits.Basic.PriorityClass = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
        limits.JobMemoryLimit = int(private_limit_gib * 2**30)
        if not self.k.SetInformationJobObject(handle, 9, c.byref(limits), c.sizeof(limits)):
            self.close(handle)
            raise WindowsError("Cannot apply job limits; no child started")
        return handle

    def member(self, process_handle, job):
        value = w.BOOL()
        self.checked(self.k.IsProcessInJob(process_handle, job, c.byref(value)), "Cannot verify job member")
        return bool(value.value)

    def spawn_contained(self, command, env, cwd, stdout, stderr, job):
        """Create suspended, assign job, then resume. Never retry on ambiguity."""
        import _winapi
        import msvcrt
        startup = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESTDHANDLES
        with open(os.devnull, "rb") as stdin:
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, stdout, stderr)]
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            startup.lpAttributeList = {"handle_list": handles}
            hp = ht = None
            try:
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                hp, ht, _, _ = _winapi.CreateProcess(
                    command[0], subprocess.list2cmdline(command), None, None, True,
                    0x4 | 0x08000000 | 0x200 | 0x4000, env, cwd, startup,
                )
                self.checked(self.k.AssignProcessToJobObject(job, hp), "Job assignment failed")
                record = self.identity(hp)
                if self.k.ResumeThread(ht) == 0xFFFFFFFF:
                    raise WindowsError("Cannot resume owned gateway")
                return hp, record
            except Exception:
                # hp is solely the exact handle just returned by CreateProcess.
                # No PID lookup, image-name kill, or fallback to another target.
                if hp:
                    self.checked(self.k.TerminateProcess(hp, 1), "Cannot discard suspended child")
                    self.close(hp)
                raise
            finally:
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
                self.close(ht)

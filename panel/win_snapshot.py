"""Read process counters in one Windows system query instead of per PID."""

import ctypes
from ctypes import wintypes
import time


class UnicodeString(ctypes.Structure):
    _fields_ = [('Length', wintypes.USHORT), ('MaximumLength', wintypes.USHORT),
                ('Buffer', ctypes.c_void_p)]


class ProcessInformation(ctypes.Structure):
    # SYSTEM_PROCESS_INFORMATION on Windows 10/11 x64. Fields through the
    # working set are needed; later counters and thread entries are skipped.
    _fields_ = [
        ('NextEntryOffset', wintypes.ULONG), ('NumberOfThreads', wintypes.ULONG),
        ('WorkingSetPrivateSize', ctypes.c_int64), ('HardFaultCount', wintypes.ULONG),
        ('NumberOfThreadsHighWatermark', wintypes.ULONG), ('CycleTime', ctypes.c_uint64),
        ('CreateTime', ctypes.c_int64), ('UserTime', ctypes.c_int64),
        ('KernelTime', ctypes.c_int64), ('ImageName', UnicodeString),
        ('BasePriority', wintypes.LONG), ('UniqueProcessId', ctypes.c_void_p),
        ('InheritedFromUniqueProcessId', ctypes.c_void_p),
        ('HandleCount', wintypes.ULONG), ('SessionId', wintypes.ULONG),
        ('UniqueProcessKey', ctypes.c_size_t), ('PeakVirtualSize', ctypes.c_size_t),
        ('VirtualSize', ctypes.c_size_t), ('PageFaultCount', wintypes.ULONG),
        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
    ]


def query_processes():
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise OSError('Bulk process sampling requires Windows x64')
    query = ctypes.WinDLL('ntdll').NtQuerySystemInformation
    query.argtypes = [wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
                      ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    capacity = 1024 * 1024
    for _ in range(8):
        buffer = ctypes.create_string_buffer(capacity)
        required = wintypes.ULONG()
        status = query(5, buffer, capacity, ctypes.byref(required))
        if status == -1073741820:  # STATUS_INFO_LENGTH_MISMATCH
            capacity = max(capacity * 2, required.value + 65536)
            if capacity > 128 * 1024 * 1024:
                break
            continue
        if status < 0:
            raise OSError(f'Windows process query failed: 0x{status & 0xffffffff:08x}')
        used = required.value
        if not 0 < used <= capacity:
            raise ValueError('Invalid Windows process buffer length')
        return _decode(buffer, used)
    raise OSError('Windows process list kept changing during sampling')


def _decode(buffer, used):
    base = ctypes.addressof(buffer)
    offset = 0
    rows = []
    while offset + ctypes.sizeof(ProcessInformation) <= used:
        entry = ProcessInformation.from_buffer(buffer, offset)
        pid = entry.UniqueProcessId or 0
        image = entry.ImageName
        if image.Length:
            address = image.Buffer or 0
            if (image.Length % 2 or image.Length > image.MaximumLength
                    or address < base or address + image.Length > base + used):
                raise ValueError('Invalid Windows process name pointer')
            name = ctypes.wstring_at(address, image.Length // 2)
        else:
            name = 'System Idle Process' if pid == 0 else 'System' if pid == 4 else '未知进程'
        rows.append({'pid': pid, 'name': name,
                     'create_time': entry.CreateTime / 10_000_000 - 11_644_473_600,
                     'memory': entry.WorkingSetSize,
                     'cpu_total': (entry.UserTime + entry.KernelTime) / 10_000_000})
        step = entry.NextEntryOffset
        if step == 0:
            return rows
        if step < ctypes.sizeof(ProcessInformation) or offset + step >= used:
            raise ValueError('Invalid Windows process entry offset')
        offset += step
    raise ValueError('Truncated Windows process list')


class WindowsProcessSampler:
    def __init__(self):
        self.previous = {}
        self.sampled_at = None

    def sample(self, cpus):
        rows = query_processes()
        now = time.monotonic()
        elapsed = now - self.sampled_at if self.sampled_at is not None else 0
        counters = {}
        for row in rows:
            identity = (row['pid'], row['create_time'])
            total = row.pop('cpu_total')
            before = self.previous.get(identity)
            cpu = (total - before) / elapsed / max(1, cpus) * 100 if before is not None and elapsed > 0 else 0
            row['cpu'] = round(max(0, min(100, cpu)), 1)
            counters[identity] = total
        self.previous = counters
        self.sampled_at = now
        return rows

"""Windows reload protocol regression using only hidden, self-created receivers.

Usage: python tests/neko24_reload.py <mdlcompiler> [--require-all] [-v]

The receiver and compiler run on a private desktop, which is never displayed.
Tests explicitly skip if a real Valve001 or mx_class window is already present.
This verifies the wire protocol and bounded delivery, not an actual game reload.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

from validate_outputs import validate


COMPILER = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None
WINDOWS = sys.platform == 'win32'
MODEL_NAME = 'reload/nested/model'
MODEL_TITLE = r'models\reload\nested\model.mdl'
WM_COMMAND, WM_COPYDATA, WM_QUIT = 0x111, 0x4A, 0x12
PAUSE, BARRIER = 0x8001, 0x8002


if WINDOWS:
    import msvcrt
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM)
    ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', WNDPROC),
                    ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                    ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                    ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
                    ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]

    class COPYDATASTRUCT(ctypes.Structure):
        _fields_ = [('dwData', ctypes.c_size_t), ('cbData', wintypes.DWORD),
                    ('lpData', ctypes.c_void_p)]

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                    ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
                    ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
                    ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD),
                    ('dwXCountChars', wintypes.DWORD), ('dwYCountChars', wintypes.DWORD),
                    ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                    ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                    ('lpReserved2', ctypes.POINTER(ctypes.c_byte)),
                    ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE),
                    ('hStdError', wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

    def prototype(dll, name, result, *arguments):
        function = getattr(dll, name)
        function.restype, function.argtypes = result, arguments
        return function

    prototype(kernel32, 'GetModuleHandleW', wintypes.HMODULE, wintypes.LPCWSTR)
    prototype(kernel32, 'GetCurrentThreadId', wintypes.DWORD)
    prototype(kernel32, 'CreateProcessW', wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPWSTR,
              ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
              ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFO),
              ctypes.POINTER(PROCESS_INFORMATION))
    prototype(kernel32, 'WaitForSingleObject', wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
    prototype(kernel32, 'GetExitCodeProcess', wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    prototype(kernel32, 'TerminateProcess', wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
    prototype(kernel32, 'CloseHandle', wintypes.BOOL, wintypes.HANDLE)
    prototype(user32, 'CreateDesktopW', wintypes.HANDLE, wintypes.LPCWSTR,
              wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
    prototype(user32, 'CloseDesktop', wintypes.BOOL, wintypes.HANDLE)
    prototype(user32, 'GetThreadDesktop', wintypes.HANDLE, wintypes.DWORD)
    prototype(user32, 'SetThreadDesktop', wintypes.BOOL, wintypes.HANDLE)
    prototype(user32, 'EnumWindows', wintypes.BOOL, ENUMPROC, wintypes.LPARAM)
    prototype(user32, 'EnumDesktopWindows', wintypes.BOOL, wintypes.HANDLE, ENUMPROC, wintypes.LPARAM)
    prototype(user32, 'GetClassNameW', ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    prototype(user32, 'GetWindowTextW', ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    prototype(user32, 'RegisterClassW', wintypes.ATOM, ctypes.POINTER(WNDCLASS))
    prototype(user32, 'UnregisterClassW', wintypes.BOOL, wintypes.LPCWSTR, wintypes.HINSTANCE)
    prototype(user32, 'CreateWindowExW', wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR,
              wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p)
    prototype(user32, 'DestroyWindow', wintypes.BOOL, wintypes.HWND)
    prototype(user32, 'DefWindowProcW', LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    prototype(user32, 'GetMessageW', wintypes.BOOL, ctypes.POINTER(wintypes.MSG),
              wintypes.HWND, wintypes.UINT, wintypes.UINT)
    prototype(user32, 'DispatchMessageW', LRESULT, ctypes.POINTER(wintypes.MSG))
    prototype(user32, 'PostThreadMessageW', wintypes.BOOL, wintypes.DWORD,
              wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    def run_on_desktop(arguments, desktop, cwd=None, timeout=30):
        # subprocess.STARTUPINFO supports only a subset of native fields:
        # assigning lpDesktop to it silently leaves the child on Default.
        # Use the native structure so isolation is actually enforced.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error, open(os.devnull, 'rb') as source:
            handles = [msvcrt.get_osfhandle(stream.fileno()) for stream in (source, output, error)]
            startup = STARTUPINFO(cb=ctypes.sizeof(STARTUPINFO), lpDesktop=desktop,
                                  dwFlags=0x100, hStdInput=handles[0],
                                  hStdOutput=handles[1], hStdError=handles[2])
            process = PROCESS_INFORMATION()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            try:
                if not kernel32.CreateProcessW(arguments[0], command, None, None, True,
                                               subprocess.CREATE_NO_WINDOW, None,
                                               str(cwd) if cwd else None,
                                               ctypes.byref(startup), ctypes.byref(process)):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                for handle in handles:
                    os.set_handle_inheritable(handle, False)
            try:
                waited = kernel32.WaitForSingleObject(process.hProcess, int(timeout * 1000))
                if waited == 258:
                    kernel32.TerminateProcess(process.hProcess, 1)
                    kernel32.WaitForSingleObject(process.hProcess, 5000)
                    output.seek(0)
                    error.seek(0)
                    raise subprocess.TimeoutExpired(arguments, timeout, output.read(), error.read())
                if waited != 0:
                    raise ctypes.WinError(ctypes.get_last_error())
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
                    raise ctypes.WinError(ctypes.get_last_error())
                output.seek(0)
                error.seek(0)
                return subprocess.CompletedProcess(arguments, code.value,
                                                   output.read().decode('utf-8', errors='replace'),
                                                   error.read().decode('utf-8', errors='replace'))
            finally:
                kernel32.CloseHandle(process.hThread)
                kernel32.CloseHandle(process.hProcess)

    def current_desktop_name():
        prototype(user32, 'GetUserObjectInformationW', wintypes.BOOL, wintypes.HANDLE,
                  ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
        name, needed = ctypes.create_unicode_buffer(256), wintypes.DWORD()
        desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        if not user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        return name.value

    def matching_windows(desktop=None):
        found = {}

        @ENUMPROC
        def visit(hwnd, _):
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, len(name))
            if name.value in ('Valve001', 'mx_class'):
                found[int(hwnd)] = name.value
            return True

        ok = (user32.EnumDesktopWindows(desktop, visit, 0) if desktop
              else user32.EnumWindows(visit, 0))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return found

    class Receivers:
        def __init__(self):
            self.name = 'NewPageReloadTest_' + uuid.uuid4().hex
            self.desktop = user32.CreateDesktopW(self.name, None, None, 0, 0x10000000, None)
            if not self.desktop:
                raise unittest.SkipTest('Cannot create isolated Win32 desktop: ' +
                                        str(ctypes.WinError(ctypes.get_last_error())))
            self.windows, self.messages, self.errors = {}, [], []
            self.ready, self.barrier = threading.Event(), threading.Event()
            self.paused, self.resume = threading.Event(), threading.Event()
            self.thread_id = None
            self.thread = threading.Thread(target=self.run, name='reload-test-receivers', daemon=True)
            self.thread.start()
            if not self.ready.wait(5) or self.errors:
                self.close()
                raise RuntimeError('Receiver setup failed: ' + repr(self.errors))

        def run(self):
            instance = kernel32.GetModuleHandleW(None)
            self.thread_id = kernel32.GetCurrentThreadId()
            original_desktop = user32.GetThreadDesktop(self.thread_id)
            registered = []

            @WNDPROC
            def window_proc(hwnd, message, wparam, lparam):
                try:
                    if message in (WM_COMMAND, WM_COPYDATA):
                        title = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(hwnd, title, len(title))
                        item = {'window': self.windows.get(int(hwnd)), 'message': message,
                                'wparam': int(wparam), 'title': title.value}
                        if message == WM_COPYDATA:
                            data = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
                            if data.cbData > 4096:
                                raise ValueError('Unexpected oversized reload payload')
                            item.update(dwData=int(data.dwData), cbData=int(data.cbData),
                                        payload=ctypes.string_at(data.lpData, data.cbData))
                        else:
                            item['lparam'] = int(lparam)
                        self.messages.append(item)
                        return 1
                except Exception as error:
                    self.errors.append(repr(error))
                    return 0
                return user32.DefWindowProcW(hwnd, message, wparam, lparam)

            try:
                if not user32.SetThreadDesktop(self.desktop):
                    raise ctypes.WinError(ctypes.get_last_error())
                for name in ('Valve001', 'mx_class'):
                    definition = WNDCLASS(lpfnWndProc=window_proc, hInstance=instance, lpszClassName=name)
                    if not user32.RegisterClassW(ctypes.byref(definition)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    registered.append(name)
                # Create the decoy last: a class-only lookup would choose it.
                for kind, name, title in [('game', 'Valve001', 'NewPageMergeMDL protocol fixture'),
                                          ('viewer', 'mx_class', MODEL_TITLE),
                                          ('decoy', 'mx_class', 'unrelated self-created viewer')]:
                    hwnd = user32.CreateWindowExW(0, name, title, 0, 0, 0, 1, 1,
                                                 None, None, instance, None)
                    if not hwnd:
                        raise ctypes.WinError(ctypes.get_last_error())
                    self.windows[int(hwnd)] = kind
                self.ready.set()
                msg = wintypes.MSG()
                while True:
                    result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                    if result == -1:
                        raise ctypes.WinError(ctypes.get_last_error())
                    if result == 0:
                        break
                    if msg.message == PAUSE:
                        self.paused.set()
                        # Timeout prevents a failed assertion from leaking a stuck thread.
                        self.resume.wait(15)
                    elif msg.message == BARRIER:
                        self.barrier.set()
                    else:
                        user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as error:
                self.errors.append(repr(error))
                self.ready.set()
            finally:
                for hwnd in reversed(self.windows):
                    user32.DestroyWindow(hwnd)
                for name in reversed(registered):
                    user32.UnregisterClassW(name, instance)
                user32.SetThreadDesktop(original_desktop)

        def post(self, message):
            if not user32.PostThreadMessageW(self.thread_id, message, 0, 0):
                raise ctypes.WinError(ctypes.get_last_error())

        def flush(self):
            self.barrier.clear()
            self.post(BARRIER)
            if not self.barrier.wait(5) or self.errors:
                raise RuntimeError('Receiver message pump failed: ' + repr(self.errors))

        def pause(self):
            self.resume.clear()
            self.paused.clear()
            self.post(PAUSE)
            if not self.paused.wait(5):
                raise RuntimeError('Receiver did not enter its non-pumping state')

        def close(self):
            self.resume.set()
            if self.thread.is_alive() and self.thread_id:
                self.post(WM_QUIT)
                self.thread.join(5)
            if self.thread.is_alive():
                raise RuntimeError('Hidden receiver thread did not stop')
            if self.desktop:
                if not user32.CloseDesktop(self.desktop):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.desktop = None


@unittest.skipUnless(WINDOWS, 'Reload protocol is Windows-only')
class ReloadProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if COMPILER is None or not COMPILER.is_file():
            raise RuntimeError('Pass an existing compiler executable as the first argument')
        if matching_windows():
            raise unittest.SkipTest('Existing Valve001/mx_class window found; no reload messages sent')
        cls.receivers = Receivers()
        cls.addClassCleanup(cls.receivers.close)
        # Check the real child desktop before ever launching the compiler.
        probe = run_on_desktop([sys.executable, '-c',
                                'import neko24_reload; print(neko24_reload.current_desktop_name())'],
                               cls.receivers.name, cwd=Path(__file__).parent)
        if probe.returncode or probe.stdout.strip() != cls.receivers.name:
            raise RuntimeError('Child desktop isolation failed: ' + probe.stdout + probe.stderr)

    def setUp(self):
        if matching_windows():
            self.skipTest('Existing Valve001/mx_class window found; no reload messages sent')
        self.assertEqual(set(matching_windows(self.receivers.desktop)), set(self.receivers.windows))
        self.receivers.flush()
        self.receivers.messages.clear()
        self.tmp = tempfile.TemporaryDirectory(prefix='np-neko24-reload-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'gameinfo.txt').write_text(
            'GameInfo { FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
        (self.root / 'mesh.smd').write_text(
            'version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n'
            'triangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n'
            '0 0 1 0 0 0 1 0 1\nend\n')
        self.qc = self.root / 'model.qc'
        self.qc.write_text(f'$modelname {MODEL_NAME}\n$body body mesh.smd\n$sequence idle mesh.smd\n')

    def compile(self, *options, success=True, timeout=30):
        # Recheck before launch; private desktop isolation also closes the race
        # with a real game/viewer launched after this check.
        if matching_windows():
            self.skipTest('Existing Valve001/mx_class window found; no reload messages sent')
        started = time.monotonic()
        completed = run_on_desktop([str(COMPILER), str(self.qc), '-game', str(self.root), *options],
                                   self.receivers.name, cwd=self.root, timeout=timeout)
        elapsed = time.monotonic() - started
        self.compiler_output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode == 0, success, self.compiler_output)
        if success and '-verify' not in options:
            result = validate(self.root / 'models' / (MODEL_NAME + '.mdl'))
            self.assertEqual(result['vertices'], 3)
        return elapsed

    def assert_no_notification(self):
        self.receivers.flush()
        self.assertEqual(self.receivers.messages, [])

    def test_success_notifies_game_and_exact_viewer_title(self):
        self.compile('-reloadhlmv')
        self.receivers.flush()
        messages = self.receivers.messages
        self.assertEqual(len(messages), 2, repr(messages) + '\n' + self.compiler_output)
        game = next(message for message in messages if message['window'] == 'game')
        expected = ('l4n_reload_model ' + MODEL_TITLE + '\n\0').encode('ascii')
        self.assertEqual(game['message'], WM_COPYDATA)
        self.assertEqual(game['wparam'], 0)
        self.assertEqual(game['dwData'], 0)
        self.assertEqual(game['cbData'], len(expected))
        self.assertEqual(game['payload'], expected)
        viewer = next(message for message in messages if message['window'] == 'viewer')
        self.assertEqual(viewer, {'window': 'viewer', 'message': WM_COMMAND,
                                 'wparam': 1017, 'lparam': 0, 'title': MODEL_TITLE})

    def test_verify_does_not_notify_or_write_model(self):
        self.compile('-reloadhlmv', '-verify')
        self.assert_no_notification()
        self.assertFalse((self.root / 'models' / (MODEL_NAME + '.mdl')).exists())

    def test_failed_compile_does_not_notify(self):
        self.qc.write_text(f'$modelname {MODEL_NAME}\n$body body missing.smd\n')
        self.compile('-reloadhlmv', success=False)
        self.assert_no_notification()
        self.assertFalse((self.root / 'models' / (MODEL_NAME + '.mdl')).exists())

    def test_without_reload_option_does_not_notify(self):
        self.compile()
        self.assert_no_notification()

    def test_unresponsive_receiver_does_not_block_compilation(self):
        self.receivers.pause()
        try:
            # Deliberately longer than the 1 s send timeout but short enough to
            # catch accidental unbounded SendMessage without hanging the suite.
            elapsed = self.compile('-reloadhlmv', timeout=8)
            self.assertLess(elapsed, 6)
        finally:
            self.receivers.resume.set()
        self.receivers.flush()
        viewers = [message for message in self.receivers.messages if message['window'] != 'game']
        self.assertEqual(viewers, [{'window': 'viewer', 'message': WM_COMMAND,
                                    'wparam': 1017, 'lparam': 0, 'title': MODEL_TITLE}])


if __name__ == '__main__':
    require_all = '--require-all' in sys.argv
    if require_all:
        sys.argv.remove('--require-all')
    program = unittest.main(exit=False)
    if require_all and program.result.skipped:
        print('All Windows reload protocol cases are required for package verification.', file=sys.stderr)
    sys.exit(0 if program.result.wasSuccessful() and
             not (require_all and program.result.skipped) else 1)

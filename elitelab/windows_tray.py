"""Minimal native Windows notification-area icon for the desktop supervisor."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HANDLE),
                ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                ('Data4', ctypes.c_ubyte * 8)]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT),
                ('uFlags', wintypes.UINT), ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON),
                ('szTip', wintypes.WCHAR * 128), ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD),
                ('szInfo', wintypes.WCHAR * 256), ('uTimeoutOrVersion', wintypes.UINT),
                ('szInfoTitle', wintypes.WCHAR * 64), ('dwInfoFlags', wintypes.DWORD), ('guidItem', GUID),
                ('hBalloonIcon', wintypes.HICON)]


def signature(lib, name, restype, *argtypes):
    fn = getattr(lib, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


register = signature(user32, 'RegisterClassW', wintypes.ATOM, ctypes.POINTER(WNDCLASS))
create = signature(user32, 'CreateWindowExW', wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
defproc = signature(user32, 'DefWindowProcW', LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
destroy = signature(user32, 'DestroyWindow', wintypes.BOOL, wintypes.HWND)
post = signature(user32, 'PostMessageW', wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
getmsg = signature(user32, 'GetMessageW', wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
translate = signature(user32, 'TranslateMessage', wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
dispatch = signature(user32, 'DispatchMessageW', LRESULT, ctypes.POINTER(wintypes.MSG))
postquit = signature(user32, 'PostQuitMessage', None, ctypes.c_int)
create_menu = signature(user32, 'CreatePopupMenu', wintypes.HMENU)
append_menu = signature(user32, 'AppendMenuW', wintypes.BOOL, wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
destroy_menu = signature(user32, 'DestroyMenu', wintypes.BOOL, wintypes.HMENU)
track_menu = signature(user32, 'TrackPopupMenu', wintypes.UINT, wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                       ctypes.c_int, wintypes.HWND, wintypes.LPVOID)
foreground = signature(user32, 'SetForegroundWindow', wintypes.BOOL, wintypes.HWND)
cursor = signature(user32, 'GetCursorPos', wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
load_icon = signature(user32, 'LoadIconW', wintypes.HICON, wintypes.HINSTANCE, wintypes.LPCWSTR)
module_handle = signature(kernel32, 'GetModuleHandleW', wintypes.HINSTANCE, wintypes.LPCWSTR)
notify_icon = signature(shell32, 'Shell_NotifyIconW', wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA))
register_message = signature(user32, 'RegisterWindowMessageW', wintypes.UINT, wintypes.LPCWSTR)

WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_TRAY = 0x8001
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
NIM_ADD, NIM_DELETE = 0, 2


class WindowsTray:
    def __init__(self, control, notify):
        self.control, self.notify = control, notify
        self.callback = WNDPROC(self._window_proc)
        self.taskbar_created = register_message('TaskbarCreated')
        self.handle = None
        self.icon_added = False
        instance = module_handle(None)
        classname = 'EliteLabDesktopTray'
        cls = WNDCLASS(); cls.lpfnWndProc = self.callback; cls.hInstance = instance; cls.lpszClassName = classname
        if not register(ctypes.byref(cls)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = create(0, classname, 'EliteLab tray', 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.icon = NOTIFYICONDATA(); self.icon.cbSize = ctypes.sizeof(self.icon)
        self.icon.hWnd = self.handle; self.icon.uID = 1; self.icon.uFlags = 0x1 | 0x2 | 0x4
        self.icon.uCallbackMessage = WM_TRAY
        self.icon.hIcon = load_icon(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))
        self.icon.szTip = 'EliteLab'
        if not self._add_icon():
            destroy(self.handle)
            raise OSError('Could not create the Windows notification-area icon')

    def _add_icon(self):
        self.icon_added = bool(notify_icon(NIM_ADD, ctypes.byref(self.icon)))
        return self.icon_added

    def close(self):
        if self.handle:
            post(self.handle, WM_CLOSE, 0, 0)

    def _create_menu(self):
        menu = create_menu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            append_menu(menu, 0, 1, 'Open dashboard')
            append_menu(menu, 0, 2, 'Open setup')
            try:
                startup = self.control.autostart_status()
            except OSError:
                startup = 'unavailable'
            flags = 0x0008 if startup == 'enabled' else (0x0003 if startup in ('conflict', 'unavailable') else 0)
            label = 'Start at sign-in' + (' (another copy)' if startup == 'conflict' else ' (unavailable)' if startup == 'unavailable' else '')
            append_menu(menu, flags, 4, label)
            append_menu(menu, 0, 3, 'Quit EliteLab')
            return menu
        except BaseException:
            destroy_menu(menu)
            raise

    def _menu(self):
        menu = self._create_menu()
        try:
            point = wintypes.POINT()
            if not cursor(ctypes.byref(point)):
                return
            foreground(self.handle)
            # Native menus deliver WM_COMMAND after TrackPopupMenu returns.
            track_menu(menu, 0x0002, point.x, point.y, 0, self.handle, None)
            post(self.handle, 0, 0, 0)
        finally:
            destroy_menu(menu)

    def _command(self, chosen):
        if chosen == 1:
            self._open(False)
        elif chosen == 2:
            self._open(True)
        elif chosen == 4:
            self.control.toggle_autostart()
        elif chosen == 3 and not self.control.shutdown():
            self.notify('EliteLab is not available on loopback yet. If it is bound to a specific network address, use the dashboard controls.')

    def _open(self, setup):
        if not self.control.open(setup):
            self.notify('EliteLab is not available on loopback yet. If it is bound to a specific network address, use the dashboard controls.')

    def _window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_COMMAND and lparam == 0 and (wparam >> 16) == 0:
                self._command(wparam & 0xffff)
                return 0
            if self.taskbar_created and msg == self.taskbar_created:
                if not self._add_icon():
                    self.notify('The tray icon could not be restored. Use Quit in the dashboard to stop EliteLab.')
                return 0
            if msg == WM_TRAY:
                if lparam == WM_RBUTTONUP:
                    self._menu()
                elif lparam == WM_LBUTTONDBLCLK:
                    self._open(False)
                return 0
            if msg == WM_CLOSE:
                destroy(hwnd); return 0
            if msg == WM_DESTROY:
                if self.icon_added:
                    notify_icon(NIM_DELETE, ctypes.byref(self.icon))
                self.handle = None
                postquit(0); return 0
            return defproc(hwnd, msg, wparam, lparam)
        except Exception:
            try:
                self.notify('The tray action could not be completed. Use the dashboard controls.')
            except Exception:
                pass
            return defproc(hwnd, msg, wparam, lparam)

    def loop(self):
        msg = wintypes.MSG()
        while True:
            status = getmsg(ctypes.byref(msg), None, 0, 0)
            if status == -1:
                raise ctypes.WinError(ctypes.get_last_error())
            if status == 0:
                break
            translate(ctypes.byref(msg)); dispatch(ctypes.byref(msg))

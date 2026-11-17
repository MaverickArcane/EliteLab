"""Exercise actual native window styles and controls using a labeled synthetic HUD."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elitelab.overlay import MODES


def main():
    user = C.WinDLL('user32', use_last_error=True)
    def bind(name, result, *args):
        fn = getattr(user, name); fn.restype = result; fn.argtypes = args
        return fn
    find = bind('FindWindowW', W.HWND, W.LPCWSTR, W.LPCWSTR)
    style = bind('GetWindowLongW', C.c_long, W.HWND, C.c_int)
    post = bind('PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    rect = bind('GetWindowRect', W.BOOL, W.HWND, C.POINTER(W.RECT))
    layers = bind('GetLayeredWindowAttributes', W.BOOL, W.HWND, C.POINTER(W.COLORREF), C.POINTER(W.BYTE), C.POINTER(W.DWORD))
    win_dpi = bind('GetDpiForWindow', W.UINT, W.HWND)
    visible = bind('IsWindowVisible', W.BOOL, W.HWND)
    gettitle = bind('GetWindowTextW', C.c_int, W.HWND, W.LPWSTR, C.c_int)
    class_name = 'EliteLabRhinoNavigationOverlayV1Demo'
    def wait(fn, message):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            value = fn()
            if value: return value
            time.sleep(.05)
        raise AssertionError(message)
    def attributes(hwnd):
        key, alpha, flags = W.COLORREF(), W.BYTE(), W.DWORD()
        assert layers(hwnd, C.byref(key), C.byref(alpha), C.byref(flags))
        return key.value, alpha.value, flags.value
    def title(hwnd):
        value = C.create_unicode_buffer(256); gettitle(hwnd, value, len(value)); return value.value
    assert not find(class_name, None), 'A demo HUD already exists; do not interfere with it'
    with tempfile.TemporaryDirectory(prefix='rhino-native-smoke-') as tmp:
        env = {**os.environ, 'ELITELAB_DATA_DIR': tmp, 'ELITELAB_SETTINGS': str(Path(tmp)/'settings.json')}
        # Call run directly to preserve exceptions in stderr instead of displaying a modal error.
        code = "from pathlib import Path; from elitelab.rhino_overlay import run; import os; run(None,Path(os.environ['ELITELAB_DATA_DIR'])/'rhino-overlay.json',True,30)"
        log_path = ROOT / 'artifacts/rhino-native-smoke.log'
        log_path.parent.mkdir(exist_ok=True)
        with log_path.open('w') as log:
            child = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, env=env, stdout=log, stderr=log,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                hwnd = wait(lambda: find(class_name, None), 'Native window did not appear; inspect ' + str(log_path))
                wait(lambda: style(hwnd, -20) & 8, 'HUD not topmost by default')
                assert style(hwnd, -16) & 0x00C40000 == 0, 'Native frame/caption still present'
                assert attributes(hwnd) == (0, 255, 3), attributes(hwnd)
                factor = win_dpi(hwnd) / 96
                def click(x, y):
                    post(hwnd, 0x0201, 1, (round(y*factor) << 16) | round(x*factor))
                def command(value):
                    post(hwnd, 0x0111, value, 0)
                click(185, 18)
                wait(lambda: not style(hwnd, -20) & 8, 'Unpin failed')
                click(185, 18)
                wait(lambda: style(hwnd, -20) & 8, 'Pin failed')
                command(2)
                wait(lambda: attributes(hwnd)[2] == 2, 'Shaded background failed')
                command(3)
                wait(lambda: attributes(hwnd)[1] == 230, 'Opacity control failed')
                command(4)
                wait(lambda: attributes(hwnd)[1] == 255, 'Opacity restore failed')
                command(2)
                wait(lambda: attributes(hwnd)[2] == 3, 'Clear background failed')
                click(250, 18)
                wait(lambda: style(hwnd, -20) & 0x20, 'Lock did not enable click-through')
                post(hwnd, 0x0312, 3, 0)
                wait(lambda: not style(hwnd, -20) & 0x20, 'Recovery hotkey did not unlock')
                post(hwnd, 0x0312, 1, 0)
                wait(lambda: not visible(hwnd), 'Hide hotkey failed')
                # Duplicate launcher must exit, retaining the first HWND.
                duplicate_code = code.replace('True,30)', "True,30,requested_activity='flight')")
                duplicate = subprocess.run([sys.executable, '-c', duplicate_code], cwd=ROOT, env=env, capture_output=True,
                                           timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                assert duplicate.returncode == 0, duplicate.stderr
                assert find(class_name, None) == hwnd
                wait(lambda: visible(hwnd) and style(hwnd, -20) & 8, 'Reopen did not show and pin HUD')
                wait(lambda: MODES['flight'].label in title(hwnd), 'Reopen did not select requested activity')
                # Every activity must repaint without a callback exception. Capture Rhino progress.
                for activity, mode in enumerate(MODES.values()):
                    command(20 + activity)
                    wait(lambda: mode.label in title(hwnd), 'Activity did not switch: ' + mode.label)
                    time.sleep(.1)
                    assert child.poll() is None, log_path.read_text()
                command(20 + list(MODES).index('rhino'))
                time.sleep(.3)
                # Optional screenshot capture uses Windows itself; no imaging dependency.
                area = W.RECT(); rect(hwnd, C.byref(area))
                capture = ROOT / 'artifacts/rhino/rhino-native.png'; capture.parent.mkdir(exist_ok=True)
                powershell = """Add-Type -AssemblyName System.Drawing
$capture = New-Object System.Drawing.Bitmap(%d, %d)
$graphics = [System.Drawing.Graphics]::FromImage($capture)
$graphics.CopyFromScreen(%d, %d, 0, 0, $capture.Size)
$capture.Save('%s')
$graphics.Dispose()
$capture.Dispose()
""" % (area.right-area.left, area.bottom-area.top, area.left, area.top, str(capture).replace("'", "''"))
                subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', powershell], check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                click(390, 18)
                assert child.wait(timeout=5) == 0, log_path.read_text()
                assert not find(class_name, None)
                print(f'Native HUD passed: borderless, transparency, opacity, pin/unpin, click-through lock, recovery/hide hotkeys, {len(MODES)} activities, reopen with requested activity and close.')
                print('Screenshot: ' + str(capture))
            finally:
                if child.poll() is None:
                    if find(class_name, None): post(find(class_name, None), 0x0010, 0, 0)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()


if __name__ == '__main__':
    main()

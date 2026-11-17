"""Shared native HUD shell; activity cards supply content without owning windows."""
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
from pathlib import Path
import logging

from .overlay import MODES, demo_card

CLASS_NAME = 'EliteLabRhinoNavigationOverlayV1'
WIDTH, HEIGHT = 420, 360
KEY_COLOR = 0x00000000


def load_preferences(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {}
        result = {}
        for key in ('pinned', 'glass'):
            if isinstance(data.get(key), bool):
                result[key] = data[key]
        if type(data.get('opacity')) is int and 30 <= data['opacity'] <= 100:
            result['opacity'] = data['opacity']
        if isinstance(data.get('activity'), str) and data['activity'] in MODES:
            result['activity'] = data['activity']
        for key in ('x', 'y'):
            if type(data.get(key)) is int and -100000 <= data[key] <= 100000:
                result[key] = data[key]
        return result
    except (OSError, ValueError):
        return {}


def save_preferences(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(data) + '\n', encoding='utf-8')
    os.replace(staged, path)


def run(feed, preferences, demo=False, close_after=0, activity=None, requested_activity=None):
    # Imported lazily so preference/model tests can run on every platform.
    user = C.WinDLL('user32', use_last_error=True)
    gdi = C.WinDLL('gdi32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)

    def bind(lib, name, result, *args):
        fn = getattr(lib, name); fn.restype = result; fn.argtypes = args
        return fn

    lresult = C.c_ssize_t
    callback_type = C.WINFUNCTYPE(lresult, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

    class WindowClass(C.Structure):
        _fields_ = [('style', W.UINT), ('callback', callback_type), ('cls_extra', C.c_int), ('win_extra', C.c_int),
                    ('instance', W.HINSTANCE), ('icon', W.HICON), ('cursor', W.HANDLE), ('brush', W.HBRUSH),
                    ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]

    class Paint(C.Structure):
        _fields_ = [('dc', W.HDC), ('erase', W.BOOL), ('rect', W.RECT), ('restore', W.BOOL),
                    ('inc_update', W.BOOL), ('reserved', C.c_byte * 32)]

    register = bind(user, 'RegisterClassW', W.ATOM, C.POINTER(WindowClass))
    create = bind(user, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                  C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
    default = bind(user, 'DefWindowProcW', lresult, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    find = bind(user, 'FindWindowW', W.HWND, W.LPCWSTR, W.LPCWSTR)
    show = bind(user, 'ShowWindow', W.BOOL, W.HWND, C.c_int)
    post = bind(user, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    position = bind(user, 'SetWindowPos', W.BOOL, W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
    layered = bind(user, 'SetLayeredWindowAttributes', W.BOOL, W.HWND, W.COLORREF, C.c_ubyte, W.DWORD)
    getrect = bind(user, 'GetWindowRect', W.BOOL, W.HWND, C.POINTER(W.RECT))
    getstyle = bind(user, 'GetWindowLongW', C.c_long, W.HWND, C.c_int)
    setstyle = bind(user, 'SetWindowLongW', C.c_long, W.HWND, C.c_int, C.c_long)
    settitle = bind(user, 'SetWindowTextW', W.BOOL, W.HWND, W.LPCWSTR)
    hotkey = bind(user, 'RegisterHotKey', W.BOOL, W.HWND, C.c_int, W.UINT, W.UINT)
    unhotkey = bind(user, 'UnregisterHotKey', W.BOOL, W.HWND, C.c_int)
    invalidate = bind(user, 'InvalidateRect', W.BOOL, W.HWND, C.POINTER(W.RECT), W.BOOL)
    begin = bind(user, 'BeginPaint', W.HDC, W.HWND, C.POINTER(Paint))
    end = bind(user, 'EndPaint', W.BOOL, W.HWND, C.POINTER(Paint))
    fill = bind(user, 'FillRect', C.c_int, W.HDC, C.POINTER(W.RECT), W.HBRUSH)
    frame = bind(user, 'FrameRect', C.c_int, W.HDC, C.POINTER(W.RECT), W.HBRUSH)
    text = bind(user, 'DrawTextW', C.c_int, W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.RECT), W.UINT)
    timer = bind(user, 'SetTimer', C.c_size_t, W.HWND, C.c_size_t, W.UINT, W.LPVOID)
    killtimer = bind(user, 'KillTimer', W.BOOL, W.HWND, C.c_size_t)
    destroy = bind(user, 'DestroyWindow', W.BOOL, W.HWND)
    quit_loop = bind(user, 'PostQuitMessage', None, C.c_int)
    getmessage = bind(user, 'GetMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
    translate = bind(user, 'TranslateMessage', W.BOOL, C.POINTER(W.MSG))
    dispatch = bind(user, 'DispatchMessageW', lresult, C.POINTER(W.MSG))
    send = bind(user, 'SendMessageW', lresult, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    release = bind(user, 'ReleaseCapture', W.BOOL)
    track_popup = bind(user, 'TrackPopupMenu', W.UINT, W.HMENU, W.UINT, C.c_int, C.c_int, C.c_int, W.HWND, W.LPVOID)
    menu_create = bind(user, 'CreatePopupMenu', W.HMENU)
    menu_add = bind(user, 'AppendMenuW', W.BOOL, W.HMENU, W.UINT, C.c_size_t, W.LPCWSTR)
    menu_destroy = bind(user, 'DestroyMenu', W.BOOL, W.HMENU)
    cursor_pos = bind(user, 'GetCursorPos', W.BOOL, C.POINTER(W.POINT))
    foreground = bind(user, 'SetForegroundWindow', W.BOOL, W.HWND)
    monitor = bind(user, 'MonitorFromRect', W.HANDLE, C.POINTER(W.RECT), W.DWORD)
    brush = bind(gdi, 'CreateSolidBrush', W.HBRUSH, W.COLORREF)
    pen = bind(gdi, 'CreatePen', W.HANDLE, C.c_int, C.c_int, W.COLORREF)
    select = bind(gdi, 'SelectObject', W.HANDLE, W.HDC, W.HANDLE)
    delete = bind(gdi, 'DeleteObject', W.BOOL, W.HANDLE)
    bk_mode = bind(gdi, 'SetBkMode', C.c_int, W.HDC, C.c_int)
    txt_color = bind(gdi, 'SetTextColor', W.COLORREF, W.HDC, W.COLORREF)
    font_create = bind(gdi, 'CreateFontW', W.HANDLE, C.c_int, C.c_int, C.c_int, C.c_int, C.c_int,
                       W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.LPCWSTR)
    polygon = bind(gdi, 'Polygon', W.BOOL, W.HDC, C.POINTER(W.POINT), C.c_int)
    ellipse = bind(gdi, 'Ellipse', W.BOOL, W.HDC, C.c_int, C.c_int, C.c_int, C.c_int)
    move = bind(gdi, 'MoveToEx', W.BOOL, W.HDC, C.c_int, C.c_int, C.POINTER(W.POINT))
    line = bind(gdi, 'LineTo', W.BOOL, W.HDC, C.c_int, C.c_int)
    module = bind(kernel, 'GetModuleHandleW', W.HINSTANCE, W.LPCWSTR)
    mutex_create = bind(kernel, 'CreateMutexW', W.HANDLE, W.LPVOID, W.BOOL, W.LPCWSTR)
    close_handle = bind(kernel, 'CloseHandle', W.BOOL, W.HANDLE)

    # One HUD per desktop session. Reopening shows the existing window.
    class_name = CLASS_NAME + ('Demo' if demo else '')
    mutex = mutex_create(None, False, 'Local\\' + class_name)
    if not mutex:
        raise C.WinError(C.get_last_error())
    if C.get_last_error() == 183:
        handle = find(class_name, None)
        if handle:
            requested = list(MODES).index(requested_activity) + 1 if requested_activity in MODES else 0
            post(handle, 0x8001, requested, 0)
        close_handle(mutex)
        return
    try:
        bind(user, 'SetProcessDpiAwarenessContext', W.BOOL, W.HANDLE)(W.HANDLE(-2))
        dpi = bind(user, 'GetDpiForSystem', W.UINT)()
    except AttributeError:
        dpi = 96
    scale = dpi / 96
    px = lambda n: round(n * scale)
    settings = {'pinned': True, 'glass': True, 'opacity': 100, 'activity': 'overview', **load_preferences(preferences)}
    if activity in MODES:
        settings['activity'] = activity
    if feed:
        feed.select(settings['activity'])
    fonts = {}
    errors = []
    current = demo_card(settings['activity']) if demo else feed.view()
    handle = None
    locked, hidden = False, False
    registered = set()

    def persist():
        if demo:
            return
        try:
            save_preferences(preferences, settings)
        except OSError:
            pass  # A read-only profile must not prevent closing or using the HUD.

    def apply():
        settitle(handle, 'EliteLab HUD / ' + MODES[settings['activity']].label)
        extended = getstyle(handle, -20)
        setstyle(handle, -20, (extended | 0x20) if locked else (extended & ~0x20))
        if not position(handle, W.HWND(-1 if settings['pinned'] else -2), 0, 0, 0, 0, 0x0013):
            raise C.WinError(C.get_last_error())
        if not layered(handle, KEY_COLOR, round(settings['opacity'] * 255 / 100), 3 if settings['glass'] else 2):
            raise C.WinError(C.get_last_error())
        invalidate(handle, None, True)

    def command(action):
        nonlocal locked, hidden, current
        if action == 1:
            settings['pinned'] = not settings['pinned']
        elif action == 2:
            settings['glass'] = not settings['glass']
        elif action == 3:
            settings['opacity'] = max(30, settings['opacity'] - 10)
        elif action == 4:
            settings['opacity'] = min(100, settings['opacity'] + 10)
        elif action == 5:
            destroy(handle); return
        elif action == 6:
            if 3 not in registered:
                return  # Never make controls unreachable without a working recovery key.
            locked = not locked
        elif action == 7:
            hidden = not hidden
            show(handle, 0 if hidden else 4)
        elif action == 8:
            locked, hidden = False, False
            settings['pinned'] = True
            show(handle, 4)
        elif 20 <= action < 20 + len(MODES):
            settings['activity'] = list(MODES)[action - 20]
            if feed:
                feed.select(settings['activity'])
            current = demo_card(settings['activity']) if demo else feed.view()
        else:
            return
        apply(); persist()

    def popup(activities=False):
        menu = menu_create(); point = W.POINT(); cursor_pos(C.byref(point))
        try:
            groups = {}
            for index, (key, mode) in enumerate(MODES.items()):
                if mode.group not in groups:
                    groups[mode.group] = menu_create()
                    menu_add(menu, 0x10, groups[mode.group], mode.group)
                menu_add(groups[mode.group], 8 if settings['activity'] == key else 0, 20 + index, mode.label)
            if not activities:
                menu_add(menu, 0x800, 0, None)
                menu_add(menu, 8 if settings['pinned'] else 0, 1, 'Pin on top')
                menu_add(menu, (8 if locked else 0) | (0 if 3 in registered else 3), 6, 'Lock clicks through - Ctrl+Alt+L')
                menu_add(menu, 8 if settings['glass'] else 0, 2, 'Clear background')
                menu_add(menu, 0, 3, 'More transparent (-10%)')
                menu_add(menu, 0, 4, 'More visible (+10%)')
                menu_add(menu, 0, 7, 'Hide HUD - Ctrl+Alt+H')
                menu_add(menu, 0, 8, 'Recover: show, pin and unlock - Ctrl+Alt+R')
                menu_add(menu, 0, 5, 'Close HUD')
            foreground(handle)
            command(track_popup(menu, 0x0102, point.x, point.y, 0, handle, None))
        finally:
            menu_destroy(menu)

    def font(size, bold=False):
        key = (size, bold)
        if key not in fonts:
            # Grayscale antialiasing avoids both jagged glyphs and ClearType color fringes.
            fonts[key] = font_create(-px(size), 0, 0, 0, 600 if bold else 400, 0, 0, 0, 1, 0, 0, 4, 0, 'Segoe UI')
        return fonts[key]

    def rgb(r, g, b):
        return r | (g << 8) | (b << 16)

    dark, white, muted, amber, green = rgb(12, 17, 24), rgb(239, 244, 249), rgb(174, 193, 210), rgb(255, 180, 84), rgb(116, 223, 186)

    def label(dc, value, x, y, width, size=12, color=None, bold=False, wrap=False):
        value = str(value).replace('\n', ' ').replace('\r', ' ')
        previous = select(dc, font(size, bold))
        rectangle = W.RECT(px(x), px(y), px(x + width), px(y + (45 if wrap else size + 9)))
        flags = (0x10 if wrap else 0x20) | 0x8000 | 0x800  # word wrap/single line, ellipsis, literal ampersand
        # A light drop shadow keeps contrast without thickening every glyph edge.
        txt_color(dc, dark)
        for dx, dy in ((1, 1),):
            shadow = W.RECT(rectangle.left + px(dx), rectangle.top + px(dy), rectangle.right + px(dx), rectangle.bottom + px(dy))
            text(dc, value, -1, C.byref(shadow), flags)
        txt_color(dc, white if color is None else color)
        text(dc, value, -1, C.byref(rectangle), flags)
        select(dc, previous)

    def paint(dc):
        bg = brush(KEY_COLOR if settings['glass'] else dark)
        area = W.RECT(0, 0, px(WIDTH), px(HEIGHT))
        fill(dc, C.byref(area), bg); delete(bg); bk_mode(dc, 1)
        accent = green if current.tone == 'green' else amber

        def box(left, top, right, bottom, color=muted):
            rect = W.RECT(px(left), px(top), px(right), px(bottom))
            ink = brush(color if settings['glass'] else dark)
            try:
                (frame if settings['glass'] else fill)(dc, C.byref(rect), ink)
            finally:
                delete(ink)

        box(12, 5, 146, 31)
        label(dc, 'ELITELAB / HUD', 19, 10, 122, 11, amber, True)
        for left, right, caption, active in ((152, 220, 'PINNED' if settings['pinned'] else 'PIN', settings['pinned']),
                                           (225, 290, 'LOCKED' if locked else 'LOCK', locked),
                                           (295, 365, 'MENU', False), (372, 407, 'X', False)):
            box(left, 5, right, 31, amber if active else muted)
            label(dc, caption, left + 8, 11, right-left-12, 10, amber if active else muted, True)
        box(12, 40, 407, 65)
        label(dc, MODES[settings['activity']].label + '  v', 21, 45, 330, 12, white, True)
        if demo:
            label(dc, 'DEMO', 354, 46, 47, 9, amber)
        label(dc, current.title, 14, 77, 390, 17, white, True)
        label(dc, current.context, 14, 101, 390, 11, muted)

        ring = pen(0, px(1), muted); old_pen = select(dc, ring)
        hollow = bind(gdi, 'GetStockObject', W.HANDLE, C.c_int)(5)
        old_brush = select(dc, hollow)
        visual = current.visual
        cx, cy = 66, 191
        ellipse(dc, px(cx-48), px(cy-48), px(cx+48), px(cy+48))
        if visual.get('kind') == 'compass':
            label(dc, 'FWD', cx-14, cy-63, 30, 9, muted)
            heading = visual.get('heading')
            for index in range(12):
                angle = math.radians(index * 30 - (heading or 0))
                move(dc, px(cx + 42*math.sin(angle)), px(cy - 42*math.cos(angle)), None)
                line(dc, px(cx + 47*math.sin(angle)), px(cy - 47*math.cos(angle)))
            if heading is not None:
                for index, cardinal in enumerate(('N', 'E', 'S', 'W')):
                    angle = math.radians(index*90-heading)
                    label(dc, cardinal, cx-6+34*math.sin(angle), cy-7-34*math.cos(angle), 14, 10, muted, True)
            if visual.get('turn') is not None:
                angle = math.radians(visual['turn'])
                points = [W.POINT(px(cx+x*math.cos(angle)-y*math.sin(angle)), px(cy+x*math.sin(angle)+y*math.cos(angle)))
                          for x,y in ((0,-26),(17,21),(0,12),(-17,21))]
                ink = brush(accent); edge = pen(0,px(2),dark)
                select(dc,ink); select(dc,edge); polygon(dc,(W.POINT*len(points))(*points),len(points))
                select(dc,hollow); select(dc,ring); delete(ink); delete(edge)
            else:
                label(dc, 'OK' if visual.get('arrived') else '--', cx-17, cy-14, 40, 24, accent)
        elif visual.get('kind') == 'badge':
            label(dc, visual.get('label', 'HUD'), cx-32, cy-22, 68, 10, muted, True)
            value = str(visual.get('text', '--'))
            label(dc, value, cx-33, cy-4, 72, 22 if len(value) < 5 else 13, accent, True)
        else:
            value = visual.get('value')
            if value is not None:
                edge = pen(0,px(3),accent); select(dc,edge)
                for index in range(max(0,min(60,round(value*.6)))):
                    angle = math.radians(index*6)
                    move(dc,px(cx+42*math.sin(angle)),px(cy-42*math.cos(angle)),None)
                    line(dc,px(cx+47*math.sin(angle)),px(cy-47*math.cos(angle)))
                select(dc,ring);delete(edge)
            label(dc, visual.get('label','ORE'),cx-19,cy-20,43,10,muted,True)
            label(dc, f'{value:.0f}%' if value is not None else '--',cx-28,cy-4,65,21,accent,True)
        select(dc,old_brush);select(dc,old_pen);delete(ring)

        label(dc,current.status,135,126,269,9,muted)
        label(dc,current.primary_label,135,143,269,10,muted)
        label(dc,current.primary,133,158,275,38 if len(current.primary)<12 else 18 if len(current.primary)>24 else 20,accent,True,wrap=len(current.primary)>24)
        label(dc,current.secondary,135,205,269,14,accent)
        label(dc,current.metric,135,229,269,24,white,True)
        label(dc,current.metric_label,135,260,269,9,muted)
        for index,(caption,value) in enumerate(current.stats[:2]):
            x=14+index*205
            label(dc,caption,x,281,192,9,muted)
            label(dc,value,x,295,192,17,white,True)
        label(dc,current.warning or current.note,14,320,392,10,amber if current.warning else muted)
        hint = 'Ctrl+Alt+R: recover / unlock' if 3 in registered else 'Reopen HUD shortcut to recover; hotkey unavailable'
        label(dc,hint,14,339,335,9,muted)
        label(dc,f"{settings['opacity']}%",365,339,42,9,muted)

    def window_proc(hwnd, message, wparam, lparam):
        nonlocal current
        try:
            if message == 0x000F:  # WM_PAINT
                ps = Paint(); dc = begin(hwnd, C.byref(ps))
                try:
                    paint(dc)
                finally:
                    end(hwnd, C.byref(ps))
                return 0
            if message == 0x0014:  # WM_ERASEBKGND
                return 1
            if message == 0x0113:  # WM_TIMER
                if wparam == 2:
                    destroy(hwnd); return 0
                next_view = demo_card(settings['activity']) if demo else feed.view()
                if next_view != current:
                    current = next_view; invalidate(hwnd, None, False)
                return 0
            if message == 0x0201:  # WM_LBUTTONDOWN
                if locked:
                    return 0
                x, y = (lparam & 0xffff) / scale, ((lparam >> 16) & 0xffff) / scale
                if y <= 32:
                    if 295 <= x < 365:
                        popup(); return 0
                    for left, right, action in ((152, 220, 1), (225, 290, 6), (372, 407, 5)):
                        if left <= x < right:
                            command(action); return 0
                    release(); send(hwnd, 0x00A1, 2, 0)  # caption drag without a native title bar
                elif 40 <= y <= 65:
                    popup(activities=True)
                return 0
            if message == 0x0232:  # WM_EXITSIZEMOVE
                rect = W.RECT(); getrect(hwnd, C.byref(rect))
                settings.update(x=rect.left, y=rect.top); persist(); return 0
            if message == 0x0205:  # WM_RBUTTONUP
                if not locked:
                    popup()
                return 0
            if message == 0x0111 and lparam == 0 and (wparam >> 16) == 0:  # WM_COMMAND
                command(wparam & 0xffff); return 0
            if message == 0x0312:  # WM_HOTKEY
                if wparam in registered:
                    command({1: 7, 2: 6, 3: 8}[wparam])
                return 0
            if message == 0x8001:
                if 1 <= wparam <= len(MODES):
                    command(19 + wparam)
                command(8); return 0
            if message == 0x0010:
                destroy(hwnd); return 0
            if message == 0x0002:
                for key in registered:
                    unhotkey(hwnd, key)
                killtimer(hwnd, 1); killtimer(hwnd, 2); quit_loop(0); return 0
            return default(hwnd, message, wparam, lparam)
        except Exception as error:
            logging.getLogger(__name__).exception('HUD window callback failed')
            errors.append(str(error))
            post(hwnd, 0x0010, 0, 0)
            return 0

    callback = callback_type(window_proc)
    try:
        instance = module(None)
        cls = WindowClass(); cls.callback = callback; cls.instance = instance; cls.name = class_name
        cls.cursor = bind(user, 'LoadCursorW', W.HANDLE, W.HINSTANCE, W.LPCWSTR)(None, C.cast(C.c_void_p(32512), W.LPCWSTR))
        if not register(C.byref(cls)):
            raise C.WinError(C.get_last_error())
        x, y = settings.get('x', px(40)), settings.get('y', px(70))
        rect = W.RECT(x, y, x + px(WIDTH), y + px(HEIGHT))
        if not monitor(C.byref(rect), 0):
            x, y = px(40), px(70)
        # Clamp to the nearest monitor's work area when size or display setup changes.
        class MonitorInfo(C.Structure):
            _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT), ('flags', W.DWORD)]
        info = MonitorInfo(); info.size = C.sizeof(info)
        getmonitor = bind(user, 'GetMonitorInfoW', W.BOOL, W.HANDLE, C.POINTER(MonitorInfo))
        target_monitor = monitor(C.byref(W.RECT(x,y,x+px(WIDTH),y+px(HEIGHT))), 2)
        if getmonitor(target_monitor,C.byref(info)):
            x=max(info.work.left,min(x,info.work.right-px(WIDTH)))
            y=max(info.work.top,min(y,info.work.bottom-px(HEIGHT)))
        # WS_POPUP, LAYERED, TOOLWINDOW, NOACTIVATE; no frame, taskbar entry or focus grab.
        handle = create(0x08080080 | (8 if settings['pinned'] else 0), class_name, 'EliteLab HUD', 0x80000000,
                        x, y, px(WIDTH), px(HEIGHT), None, None, instance, None)
        if not handle:
            raise C.WinError(C.get_last_error())
        for key, letter in ((1,'H'),(2,'L'),(3,'R')):
            # Test/demo windows use Shift as well, leaving the live HUD's hotkeys alone.
            if hotkey(handle,key,0x4003 | (4 if demo else 0),ord(letter)):
                registered.add(key)
        apply(); show(handle, 4); persist()  # show without activating over the game
        timer(handle, 1, 250, None)
        if close_after:
            timer(handle, 2, close_after * 1000, None)
        if not demo:
            feed.start()
        msg = W.MSG()
        while True:
            result = getmessage(C.byref(msg), None, 0, 0)
            if result == -1:
                raise C.WinError(C.get_last_error())
            if result == 0:
                break
            translate(C.byref(msg)); dispatch(C.byref(msg))
        if errors:
            raise RuntimeError(errors[0])
    finally:
        if feed:
            feed.close()
        for value in fonts.values():
            delete(value)
        close_handle(mutex)

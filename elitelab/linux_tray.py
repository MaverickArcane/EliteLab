"""GTK controls and an optional Ayatana indicator for the Debian package.

GTK is imported only when the packaged desktop entry is launched. A control
window stays available when the desktop has no indicator host.
"""
import threading


class LinuxTray:
    def __init__(self, control, notify):
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
        if not Gtk.init_check()[0]:
            raise OSError('A graphical desktop is required for the tray.')
        self.Gtk, self.GLib = Gtk, GLib
        self.control, self.notify = control, notify
        self.closed = threading.Event()
        self.destroyed = False
        self.busy = False
        self.indicator = None
        self.window = Gtk.Window(title='EliteLab')
        self.window.set_border_width(20)
        self.window.set_default_size(340, 240)
        self.window.connect('delete-event', self._delete)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window.add(box)
        heading = Gtk.Label(label='EliteLab controls')
        box.pack_start(heading, False, False, 0)
        self.message = Gtk.Label(label='Your dashboard runs in your browser.')
        self.message.set_line_wrap(True)
        box.pack_start(self.message, False, False, 0)
        self.menu = Gtk.Menu()
        self.buttons = {}
        for label, action in (('Open dashboard', lambda: control.open()),
                              ('Open setup', lambda: control.open(setup=True)),
                              ('Quit EliteLab', control.shutdown)):
            button = Gtk.Button(label=label)
            button.connect('clicked', lambda _widget, fn=action: self._action(fn))
            box.pack_start(button, False, False, 0)
            self.buttons[label] = button
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda _widget, fn=action: self._action(fn))
            self.menu.append(item)
        self.startup_button = Gtk.Button()
        self.startup_button.connect('clicked', lambda _widget: self._startup())
        box.pack_start(self.startup_button, False, False, 0)
        self.startup_item = Gtk.MenuItem()
        self.startup_item.connect('activate', lambda _widget: self._startup())
        self.menu.append(self.startup_item)
        self._startup_label()
        self.menu.show_all()
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3 as Indicator
            self.indicator_api = Indicator
            self.indicator = Indicator.Indicator.new('elitelab', 'applications-games', Indicator.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_title('EliteLab')
            self.indicator.set_menu(self.menu)
            self.indicator.connect('connection-changed', self._connection)
            self.indicator.set_status(Indicator.IndicatorStatus.ACTIVE)
        except (ImportError, ValueError):
            pass
        self.window.show_all()
        self._connection(self.indicator, bool(self.indicator and self.indicator.get_property('connected')))

    def _connection(self, _indicator, connected):
        if self.closed.is_set():
            return
        if connected:
            self.window.hide()
        else:
            self.window.show_all()

    def _delete(self, *_args):
        if self.indicator and self.indicator.get_property('connected'):
            self.window.hide()
        else:
            self.message.set_text('Use Quit EliteLab to stop the dashboard and close these controls.')
        return True

    def _startup_label(self):
        try:
            status = self.control.autostart_status()
            label = {'enabled':'Disable start at login', 'disabled':'Enable start at login',
                     'conflict':'Login entry managed elsewhere'}[status]
            enabled = status != 'conflict'
        except (OSError, ValueError):
            label, enabled = 'Login startup unavailable', False
        for widget in (self.startup_button, self.startup_item):
            widget.set_label(label)
            widget.set_sensitive(enabled)

    def _startup(self):
        try:
            enabled = self.control.toggle_autostart()
            self.message.set_text('Start at login enabled.' if enabled else 'Start at login disabled.')
        except (OSError, ValueError) as error:
            self.message.set_text(str(error))
        self._startup_label()

    def _action(self, fn):
        if self.busy or self.closed.is_set():
            return
        self.busy = True
        def work():
            try:
                message = '' if fn() else 'The dashboard is not ready. Wait a moment and try again.'
            except Exception as error:
                message = 'Could not complete the action: ' + str(error)
            self.GLib.idle_add(done, message)
        def done(message):
            self.busy = False
            if not self.closed.is_set() and message:
                self.message.set_text(message)
                self.window.show_all()
            return False
        threading.Thread(target=work, name='desktop-action', daemon=True).start()

    def close(self):
        self.closed.set()
        self.GLib.idle_add(self._close)

    def _close(self):
        if self.destroyed:
            return False
        self.destroyed = True
        if self.indicator:
            self.indicator.set_status(self.indicator_api.IndicatorStatus.PASSIVE)
        self.window.destroy()
        if self.Gtk.main_level():
            self.Gtk.main_quit()
        return False

    def loop(self):
        if not self.closed.is_set():
            self.Gtk.main()
        else:
            self._close()

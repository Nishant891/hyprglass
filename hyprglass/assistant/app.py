#!/usr/bin/env python3
"""GTK4 glass assistant and calendar alongside the native SwayNC sidebar."""
import calendar
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from hyprglass.paths import COMMAND

# Layer-shell must interpose Wayland symbols before GTK loads libwayland.
if os.environ.get('HYPR_WIDGETS_PRELOADED') != '1':
    env = dict(os.environ, HYPR_WIDGETS_PRELOADED='1', GSK_RENDERER='gl', PYTHONDONTWRITEBYTECODE='1')
    env['LD_PRELOAD'] = 'libgtk4-layer-shell.so.0' + (' ' + env['LD_PRELOAD'] if env.get('LD_PRELOAD') else '')
    os.execve(sys.executable, [sys.executable, "-B", str(COMMAND), "widgets", *sys.argv[1:]], env)

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell as Layer
from hyprglass.assistant.client import local_request
from hyprglass.wallpapers.picker import WallpaperPicker

from hyprglass.paths import BASE

def run_async(work, done, failed):
    def worker():
        try:
            result = work()
            GLib.idle_add(lambda: (done(result), False)[1])
        except Exception as error:
            message = str(error)
            GLib.idle_add(lambda: (failed(message), False)[1])
    threading.Thread(target=worker, daemon=True).start()

def label(text='', css=None, **kwargs):
    item = Gtk.Label(label=text, **kwargs)
    if css:
        item.add_css_class(css)
    if kwargs.get('wrap'):
        item.set_max_width_chars(23)
    return item

def button(text, action, tip=None, css=None):
    item = Gtk.Button(label=text)
    item.connect('clicked', lambda *_: action())
    if tip:
        item.set_tooltip_text(tip)
    if css:
        item.add_css_class(css)
    return item

def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())

def scroll(child, expand=True):
    view = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                              vscrollbar_policy=Gtk.PolicyType.EXTERNAL, vexpand=expand)
    view.set_child(child)
    return view

def focused_monitor():
    try:
        monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors'], timeout=2))
        return next(m for m in monitors if m['focused'])
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        return {'name': '', 'width': 1920, 'height': 1080, 'scale': 1.2}

class BusyDots(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=5, halign=Gtk.Align.CENTER)
        self.source = None
        self.phase = 0
        self.dots = []
        for _ in range(3):
            dot = label('●', 'loading-dot')
            self.append(dot)
            self.dots.append(dot)
        self.set_tooltip_text('Loading')
        self.set_visible(False)

    def start(self):
        self.stop()
        self.set_visible(True)
        self.tick()
        self.source = GLib.timeout_add(240, self.tick)

    def tick(self):
        for index, dot in enumerate(self.dots):
            dot.set_opacity(1 if index == self.phase else .25)
        self.phase = (self.phase + 1) % 3
        return True

    def stop(self):
        if self.source is not None:
            GLib.source_remove(self.source)
            self.source = None
        self.set_visible(False)

class Surface(Gtk.ApplicationWindow):
    def __init__(self, app, name, width, height, left=3, right=False, top=3, scrim=True):
        super().__init__(application=app, title=name)
        self.add_css_class('desktop-widget')
        self.set_decorated(False)
        Layer.init_for_window(self)
        Layer.set_namespace(self, 'hypr-' + name)
        Layer.set_layer(self, Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.ON_DEMAND)
        monitor = focused_monitor()
        displays = Gdk.Display.get_default().get_monitors()
        for index in range(displays.get_n_items()):
            item = displays.get_item(index)
            if item.get_connector() == monitor['name']:
                Layer.set_monitor(self, item)
        self.surface = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.surface.add_css_class('surface')
        self.surface.set_size_request(width, height)
        if scrim:
            for edge in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
                Layer.set_anchor(self, edge, True)
            overlay = Gtk.Overlay()
            backdrop = Gtk.Box(hexpand=True, vexpand=True)
            click = Gtk.GestureClick()
            click.connect('released', lambda *_: self.set_visible(False))
            backdrop.add_controller(click)
            overlay.set_child(backdrop)
            self.surface.set_halign(Gtk.Align.END if right else Gtk.Align.START)
            self.surface.set_valign(Gtk.Align.START)
            self.surface.set_margin_top(top)
            self.surface.set_margin_start(left)
            self.surface.set_margin_end(0 if right else 3)
            overlay.add_overlay(self.surface)
            self.set_child(overlay)
        else:
            Layer.set_anchor(self, Layer.Edge.TOP, True)
            Layer.set_anchor(self, Layer.Edge.RIGHT if right else Layer.Edge.LEFT, True)
            Layer.set_margin(self, Layer.Edge.TOP, top)
            Layer.set_margin(self, Layer.Edge.RIGHT if right else Layer.Edge.LEFT, left)
            self.set_child(self.surface)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.key)
        self.add_controller(keys)

    def reposition(self):
        monitor = focused_monitor()
        displays = Gdk.Display.get_default().get_monitors()
        for index in range(displays.get_n_items()):
            item = displays.get_item(index)
            if item.get_connector() == monitor['name']:
                Layer.set_monitor(self, item)
                break

    def key(self, controller, key, code, state):
        if key == Gdk.KEY_Escape:
            self.set_visible(False)
            return True
        return False

class Assistant(Surface):
    def __init__(self, app):
        m = focused_monitor()
        super().__init__(app, 'assistant', 280, min(590, int(m['height']/m['scale'])-50))
        self.surface.append(label('Local AI', 'heading', xalign=0))
        self.messages = []
        self.busy = False
        self.model_names = []
        self.models = Gtk.DropDown(model=Gtk.StringList.new(['Loading local models…']))
        self.models.set_tooltip_text('Ollama model on this machine')
        ai = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ai.append(self.models)
        self.chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.chat_scroll = scroll(self.chat)
        ai.append(self.chat_scroll)
        self.chat.append(label('Ask something. Your conversation stays on this machine.', 'muted', wrap=True, xalign=0))
        self.ai_status = label('', 'muted', wrap=True, xalign=0)
        ai.append(self.ai_status)
        self.ai_dots = BusyDots()
        ai.append(self.ai_dots)
        row = Gtk.Box(spacing=6)
        self.prompt = Gtk.Entry(placeholder_text='Ask AI…', hexpand=True)
        self.prompt.connect('activate', lambda *_: self.ask())
        self.send = button('↑', self.ask, 'Send message')
        row.append(self.prompt)
        row.append(self.send)
        ai.append(row)
        ai.append(button('New conversation', self.new_chat, css='quiet'))
        self.surface.append(ai)
        self.load_models()

    def load_models(self):
        def loaded(data):
            selected = self.models.get_selected()
            previous = self.model_names[selected] if selected < len(self.model_names) else None
            self.model_names = [m['name'] for m in data.get('models', []) if not m.get('remote_host')]
            self.models.set_model(Gtk.StringList.new(self.model_names or ['No local models']))
            if previous in self.model_names:
                self.models.set_selected(self.model_names.index(previous))
            self.ai_status.set_text('' if self.model_names else 'No local models. Download a model with Ollama, then reopen this panel.')
        run_async(lambda: local_request('http://127.0.0.1:11434', '/api/tags'), loaded,
                  lambda err: self.ai_status.set_text('Ollama is offline. Start hypr-ollama.service, then reopen this panel.'))

    def new_chat(self):
        if not self.busy:
            self.messages.clear()
            clear(self.chat)
            self.prompt.grab_focus()

    def bubble(self, text, css):
        item = label(text, css, wrap=True, selectable=True, xalign=0)
        item.set_max_width_chars(23)
        self.chat.append(item)
        return item

    def ask(self):
        text = self.prompt.get_text().strip()
        if self.busy or not text or not getattr(self, 'model_names', []):
            return
        model = self.model_names[self.models.get_selected()]
        self.busy = True
        self.send.set_sensitive(False)
        self.prompt.set_text('')
        self.bubble(text, 'user-message')
        answer = self.bubble('', 'assistant-message')
        self.ai_dots.start()
        history = self.messages + [{'role': 'user', 'content': text}]
        self.ai_status.set_text('Running locally · ' + model)
        def done(data):
            content = data.get('message', {}).get('content', '').strip() or 'The model returned an empty answer.'
            answer.set_text(content)
            self.messages = history + [{'role': 'assistant', 'content': content}]
            finish('')
        def finish(message):
            self.busy = False
            self.ai_dots.stop()
            self.send.set_sensitive(True)
            self.ai_status.set_text(message)
            adjustment = self.chat_scroll.get_vadjustment()
            GLib.idle_add(lambda: adjustment.set_value(adjustment.get_upper()))
        def failed(error):
            answer.set_text('Could not reach the local model.')
            finish(error)
        run_async(lambda: local_request('http://127.0.0.1:11434', '/api/chat',
                  {'model': model, 'messages': history, 'think': False, 'stream': False,
                   'options': {'num_ctx': 4096, 'num_predict': 1024}}, timeout=180), done, failed)

class Calendar(Surface):
    def __init__(self, app):
        super().__init__(app, 'calendar', 290, -1, left=130)
        self.month = date.today().replace(day=1)
        header = Gtk.Box(spacing=6)
        header.append(button('‹', lambda: self.move(-1), 'Previous month'))
        self.title = label('', 'heading', hexpand=True)
        header.append(self.title)
        header.append(button('›', lambda: self.move(1), 'Next month'))
        self.surface.append(header)
        self.grid = Gtk.Grid(row_spacing=5, column_spacing=4, column_homogeneous=True)
        self.surface.append(self.grid)
        self.draw()

    def move(self, delta):
        month = self.month.year * 12 + self.month.month - 1 + delta
        self.month = date(month // 12, month % 12 + 1, 1)
        self.draw()

    def draw(self):
        clear(self.grid)
        self.title.set_text(self.month.strftime('%B %Y'))
        for col, day in enumerate(('M', 'T', 'W', 'T', 'F', 'S', 'S')):
            self.grid.attach(label(day, 'muted'), col, 0, 1, 1)
        for row, week in enumerate(calendar.monthcalendar(self.month.year, self.month.month), 1):
            for col, day in enumerate(week):
                cell = label(str(day) if day else '', 'calendar-day')
                if day and date(self.month.year, self.month.month, day) == date.today():
                    cell.add_css_class('today')
                self.grid.attach(cell, col, row, 1, 1)

class Desktop(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.hypr.DesktopWidgets', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.assistant = self.calendar = self.wallpapers = None
        self.cc = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        css = Gtk.CssProvider()
        source = (BASE / 'hyprglass/assistant/style.css').read_text()
        if Gtk.get_minor_version() < 24:
            source = re.sub(r'backdrop-filter\s*:[^;]+;', '', source)
        css.load_from_string(source)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.cc = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def cc_call(self, name, args=None, required=False):
        def call():
            return self.cc.call_sync('org.erikreider.swaync.cc', '/org/erikreider/swaync/cc',
                                     'org.erikreider.swaync.cc', name, args, None,
                                     Gio.DBusCallFlags.NO_AUTO_START, 2000, None)
        try:
            return call()
        except GLib.Error:
            if not required:
                return None
        subprocess.run(['systemctl', '--user', 'start', 'swaync.service'],
                       check=True, capture_output=True, text=True, timeout=8)
        return call()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        action = args[0] if args else 'assistant'
        try:
            self.activate_action(action)
        except (GLib.Error, OSError, subprocess.SubprocessError) as error:
            command_line.printerr_literal('Could not open widget: ' + str(error) + '\n')
            return 1
        return 0

    def activate_action(self, action):
        if action == '--daemon':
            return 0
        if action == 'wallpapers':
            self.cc_call('SetVisibility', GLib.Variant('(b)', (False,)))
            for panel in (self.assistant, self.calendar):
                if panel:
                    panel.set_visible(False)
            if self.wallpapers and self.wallpapers.get_visible():
                self.wallpapers.set_visible(False)
            else:
                if self.wallpapers is None:
                    self.wallpapers = WallpaperPicker(self, focused_monitor, run_async)
                self.wallpapers.open()
        elif action == 'panel':
            for panel in (self.assistant, self.calendar, self.wallpapers):
                if panel:
                    panel.set_visible(False)
            monitor = focused_monitor()
            self.cc_call('SetCcMonitor', GLib.Variant('(s)', (monitor['name'],)), required=True)
            self.cc_call('ToggleVisibility', required=True)
        elif action in ('assistant', 'calendar'):
            if self.wallpapers:
                self.wallpapers.set_visible(False)
            self.cc_call('SetVisibility', GLib.Variant('(b)', (False,)))
            other = self.calendar if action == 'assistant' else self.assistant
            if other:
                other.set_visible(False)
            target = getattr(self, action)
            if target and target.get_visible():
                target.set_visible(False)
            else:
                if target is None:
                    target = Assistant(self) if action == 'assistant' else Calendar(self)
                    setattr(self, action, target)
                if action == 'assistant':
                    target.load_models()
                target.reposition()
                target.present()
        return 0

if __name__ == '__main__':
    os.umask(0o077)
    GLib.set_prgname('hypr-glass')
    GLib.set_application_name('Hypr glass')
    if '--daemon' not in sys.argv:
        try:
            subprocess.run(['systemctl', '--user', 'start', 'hypr-widgets.service'],
                           check=True, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.SubprocessError) as error:
            print('Could not start widgets: ' + str(error), file=sys.stderr)
            sys.exit(1)
    app = Desktop()
    app.run(sys.argv)

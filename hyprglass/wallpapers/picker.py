"""A native fullscreen wallpaper carousel, backed by Hyprpaper."""
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import subprocess
import time

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Graphene, Gsk, Gtk, Gtk4LayerShell as Layer

from hyprglass.wallpapers.state import active_wallpapers, apply_wallpaper, images, saved_wallpapers

THUMBNAILS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wallpaper-preview')

@lru_cache(maxsize=24)
def thumbnail(path, modified):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 640, 640, True)
    return Gdk.Texture.new_for_pixbuf(pixbuf.apply_embedded_orientation())

class Carousel(Gtk.Widget):
    def __init__(self, selected, activated):
        super().__init__(hexpand=True, vexpand=True)
        self.selected = selected
        self.activated = activated
        self.cards = []
        self.position = self.target = 0
        self.animation = None
        self.scroll_total = 0
        self.last_scroll = 0
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect('scroll', self.scroll)
        self.add_controller(scroll)

    def set_images(self, paths, current, load):
        if self.animation is not None:
            self.remove_tick_callback(self.animation)
            self.animation = None
        for card in self.cards:
            card.unparent()
        self.cards = []
        self.paths = paths
        for index, path in enumerate(paths):
            picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER)
            card = Gtk.Button(child=picture)
            card.add_css_class('wallpaper-card')
            card.set_overflow(Gtk.Overflow.HIDDEN)
            card.update_property([Gtk.AccessibleProperty.LABEL], [path.name])
            card.connect('clicked', lambda _, item=index: self.choose(item))
            card.set_parent(self)
            self.cards.append(card)
        self.loaded = set()
        self.load = load
        self.position = self.target = paths.index(current) if current in paths else 0
        self.select(self.target, animate=False)

    def choose(self, index):
        if index == self.target and abs(self.position - index) < .02:
            self.activated()
        else:
            self.select(index)

    def select(self, index, animate=True):
        if not self.cards:
            return
        index = max(0, min(len(self.cards) - 1, index))
        self.target = index
        for item, card in enumerate(self.cards):
            (card.add_css_class if item == index else card.remove_css_class)('selected')
            if abs(item - index) > 4:
                card.get_child().set_paintable(None)
                self.loaded.discard(item)
            if abs(item - index) <= 3 and item not in self.loaded:
                self.loaded.add(item)
                self.load(self.paths[item], card.get_child())
        self.selected(self.paths[index], index, len(self.cards))
        if self.animation is not None:
            self.remove_tick_callback(self.animation)
            self.animation = None
        if animate and Gtk.Settings.get_default().get_property('gtk-enable-animations'):
            self.start_position = self.position
            self.start_time = None
            self.animation = self.add_tick_callback(self.animate)
        else:
            self.position = index
            self.queue_allocate()
            self.queue_draw()

    def animate(self, widget, clock):
        now = clock.get_frame_time()
        if self.start_time is None:
            self.start_time = now
        progress = min(1, (now - self.start_time) / 220000)
        eased = 1 - (1 - progress) ** 3
        self.position = self.start_position + (self.target - self.start_position) * eased
        self.queue_allocate()
        self.queue_draw()
        if progress == 1:
            self.animation = None
            return False
        return True

    def scroll(self, controller, dx, dy):
        self.scroll_total += dx if abs(dx) > abs(dy) else dy
        now = time.monotonic()
        if abs(self.scroll_total) >= 1 and now - self.last_scroll > .16:
            self.select(self.target + (1 if self.scroll_total > 0 else -1))
            self.scroll_total = 0
            self.last_scroll = now
        return True

    def do_measure(self, orientation, for_size):
        return (0, 0, -1, -1)

    def do_size_allocate(self, width, height, baseline):
        base = min(380, height * .78, width * .38)
        for index, card in enumerate(self.cards):
            distance = index - self.position
            visible = abs(distance) < 3.5
            card.set_child_visible(visible)
            if visible:
                shrink = .78
                magnitude = abs(distance)
                side = round(base * shrink ** magnitude)
                point = Graphene.Point()
                offset = base * (1 + shrink) / 2 * (1 - shrink ** magnitude) / (1 - shrink) + 24 * magnitude
                if distance < 0:
                    offset = -offset
                point.init(width / 2 + offset - side / 2, (height - side) / 2)
                card.allocate(side, side, -1, Gsk.Transform.new().translate(point))

    def do_snapshot(self, snapshot):
        for index in sorted(range(len(self.cards)), key=lambda item: abs(item - self.position), reverse=True):
            card = self.cards[index]
            if card.get_child_visible():
                self.snapshot_child(card, snapshot)

class WallpaperPicker(Gtk.ApplicationWindow):
    def __init__(self, app, focused_monitor, run_async):
        super().__init__(application=app, title='Wallpapers', decorated=False)
        self.focused_monitor = focused_monitor
        self.run_async = run_async
        self.applying = False
        self.add_css_class('desktop-widget')
        Layer.init_for_window(self)
        Layer.set_namespace(self, 'hypr-wallpapers')
        Layer.set_layer(self, Layer.Layer.OVERLAY)
        Layer.set_exclusive_zone(self, -1)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.EXCLUSIVE)
        for edge in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(self, edge, True)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.add_css_class('wallpaper-backdrop')
        self.carousel = Carousel(self.selected, self.apply)
        root.append(self.carousel)
        self.status = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.status.add_css_class('muted')
        self.status.set_visible(False)
        root.append(self.status)
        self.set_child(root)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key)
        self.add_controller(keys)

    def open(self):
        if self.applying:
            return
        self.monitor = self.focused_monitor()
        monitors = Gdk.Display.get_default().get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            if monitor.get_connector() == self.monitor['name']:
                Layer.set_monitor(self, monitor)
                break
        paths = images()
        try:
            active = active_wallpapers()
        except (OSError, subprocess.SubprocessError):
            active = saved_wallpapers()
        self.current = active.get(self.monitor['name'])
        if self.current and self.current not in paths:
            paths.insert(0, self.current)
        self.carousel.set_images(paths, self.current, self.load)
        self.status.set_visible(False)
        self.present()

    def load(self, path, picture):
        def ready(future):
            def update():
                card = picture.get_parent()
                if card is None or card.get_parent() != self.carousel:
                    return False
                if abs(self.carousel.cards.index(card) - self.carousel.target) > 4:
                    return False
                try:
                    picture.set_paintable(future.result())
                except (OSError, GLib.Error):
                    picture.set_tooltip_text('Could not preview ' + path.name)
                return False
            GLib.idle_add(update)
        future = THUMBNAILS.submit(lambda: thumbnail(path, path.stat().st_mtime_ns))
        future.add_done_callback(ready)

    def selected(self, path, index, count):
        self.status.set_visible(False)

    def key(self, controller, key, code, state):
        if self.applying:
            return True
        if key == Gdk.KEY_Escape:
            self.set_visible(False)
        elif key in (Gdk.KEY_Left, Gdk.KEY_Up):
            self.carousel.select(self.carousel.target - 1)
        elif key in (Gdk.KEY_Right, Gdk.KEY_Down):
            self.carousel.select(self.carousel.target + 1)
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.apply()
        elif key == Gdk.KEY_Home:
            self.carousel.select(0)
        elif key == Gdk.KEY_End:
            self.carousel.select(len(self.carousel.cards) - 1)
        else:
            return False
        return True

    def apply(self):
        if self.applying or not self.carousel.cards:
            return
        self.applying = True
        path = self.carousel.paths[self.carousel.target]
        def applied(_):
            root = self.get_child()
            def close():
                self.set_visible(False)
                root.remove_css_class('applied')
                self.applying = False
                return False
            if Gtk.Settings.get_default().get_property('gtk-enable-animations'):
                root.add_css_class('applied')
                GLib.timeout_add(200, close)
            else:
                close()
        def failed(error):
            self.applying = False
            self.status.set_text('Could not apply wallpaper: ' + error)
            self.status.set_visible(True)
        self.run_async(lambda: apply_wallpaper(self.monitor['name'], path), applied, failed)

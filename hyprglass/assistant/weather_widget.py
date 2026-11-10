from datetime import datetime, timezone
from gi.repository import Gdk, GLib, Gtk, Pango, Gtk4LayerShell as Layer
from hyprglass.assistant.weather import REFRESH_SECONDS, WeatherReport, fetch_weather
from hyprglass.waybar.geometry import read_bar_gaps


class WeatherWindow(Gtk.ApplicationWindow):
    WIDTH = 284

    def __init__(self, app, monitor):
        super().__init__(application=app, title='Kolkata weather')
        self.monitor = monitor
        self.gap = None
        self.geometry = None
        self.add_css_class('desktop-widget')
        self.set_decorated(False)
        self.set_resizable(False)
        Layer.init_for_window(self)
        Layer.set_namespace(self, 'hypr-weather')
        Layer.set_layer(self, Layer.Layer.BOTTOM)
        Layer.set_keyboard_mode(self, Layer.KeyboardMode.NONE)
        Layer.set_monitor(self, monitor)
        Layer.set_exclusive_zone(self, -1)
        Layer.set_anchor(self, Layer.Edge.TOP, True)
        Layer.set_anchor(self, Layer.Edge.LEFT, True)
        Layer.set_margin(self, Layer.Edge.TOP, 37)
        card = Gtk.Box(spacing=10)
        card.add_css_class('weather-card')
        self.icon = Gtk.Image.new_from_icon_name('weather-severe-alert-symbolic')
        self.icon.set_pixel_size(28)
        self.icon.add_css_class('weather-icon')
        card.append(self.icon)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        details.set_hexpand(True)
        heading = Gtk.Box(spacing=10)
        city = Gtk.Label(label='Kolkata', xalign=0, hexpand=True)
        city.add_css_class('weather-city')
        heading.append(city)
        self.temperature = Gtk.Label(label='Loading…')
        self.temperature.add_css_class('weather-temperature')
        heading.append(self.temperature)
        details.append(heading)
        self.conditions = Gtk.Label(label='Current conditions', xalign=0)
        self.conditions.add_css_class('weather-details')
        self.conditions.set_ellipsize(Pango.EllipsizeMode.END)
        details.append(self.conditions)
        self.metrics = Gtk.Label(label='Humidity —  ·  Wind —', xalign=0)
        self.metrics.add_css_class('weather-details')
        details.append(self.metrics)
        coordinates = Gtk.Label(label='22.5726° N  ·  88.3639° E', xalign=0)
        coordinates.add_css_class('weather-coordinates')
        details.append(coordinates)
        card.append(details)
        self.set_child(card)
        self.set_default_size(self.WIDTH, -1)
        self.geometry_handler = monitor.connect('notify::geometry', self.position)
        self.position()
        self.set_visible(True)

    def position(self, *_):
        rect = self.monitor.get_geometry()
        geometry = (rect.x, rect.y, rect.width, rect.height)
        if geometry != self.geometry:
            self.geometry = geometry
            self.gap = None
        width = rect.width
        center = self.gap.center if self.gap and self.gap.width == width else width * .67
        left = round(center - self.WIDTH / 2)
        Layer.set_margin(self, Layer.Edge.LEFT, max(4, min(left, width - self.WIDTH - 4)))
        Layer.set_margin(self, Layer.Edge.TOP, self.gap.bottom + 6 if self.gap else 37)

    def update(self, report):
        now = datetime.now(timezone.utc)
        self.temperature.set_text(report.temperature(now))
        if report.weather:
            weather = report.weather
            self.conditions.set_text(f'{weather.condition} · Feels like {weather.apparent_temperature_c:.0f}°C')
            self.metrics.set_text(f'Humidity {weather.humidity_percent:.0f}%  ·  Wind {weather.wind_kmh:.0f} km/h')
        else:
            self.conditions.set_text('Weather unavailable' if report.failed else 'Current conditions')
            self.metrics.set_text('Humidity —  ·  Wind —')
        self.icon.set_from_icon_name(report.weather.icon if report.weather else 'weather-severe-alert-symbolic')
        self.set_tooltip_text(
            f'{report.weather.condition} · {report.weather.observed_at.astimezone().strftime("%H:%M")}\n'
            f'Feels like {report.weather.apparent_temperature_c:.0f}°C · '
            f'Humidity {report.weather.humidity_percent:.0f}% · Wind {report.weather.wind_kmh:.0f} km/h\n'
            f'{"Last available reading · " if report.stale(now) else ""}Open-Meteo'
            if report.weather else 'Weather unavailable · Open-Meteo' if report.failed
            else 'Loading current weather · Open-Meteo'
        )
        if report.stale(now) or report.failed:
            self.add_css_class('weather-stale')
        else:
            self.remove_css_class('weather-stale')

    def dispose(self):
        self.monitor.disconnect(self.geometry_handler)
        self.destroy()


class WeatherWidgets:
    def __init__(self, app, run_async):
        self.app = app
        self.run_async = run_async
        self.report = WeatherReport()
        self.busy = False
        self.closed = False
        self.position_busy = False
        self.windows = {}
        self.monitors = Gdk.Display.get_default().get_monitors()
        self.monitor_handler = self.monitors.connect('items-changed', self.rebuild)
        self.rebuild()
        self.timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self.refresh)
        self.position_timer = GLib.timeout_add_seconds(5, self.refresh_positions)
        self.refresh_positions()
        self.refresh()

    def rebuild(self, *_):
        monitors = [self.monitors.get_item(index) for index in range(self.monitors.get_n_items())]
        for monitor in list(self.windows):
            if monitor not in monitors:
                self.windows.pop(monitor).dispose()
        for monitor in monitors:
            if monitor not in self.windows:
                self.windows[monitor] = WeatherWindow(self.app, monitor)
        self.render()

    def refresh_positions(self):
        if self.closed or self.position_busy:
            return not self.closed
        if all(window.gap is not None for window in self.windows.values()):
            return True
        self.position_busy = True
        self.run_async(read_bar_gaps, self.positioned, lambda _error: self.positioned([]))
        return True

    def positioned(self, gaps):
        self.position_busy = False
        if self.closed:
            return
        for monitor, window in self.windows.items():
            if window.gap is not None:
                continue
            width = monitor.get_geometry().width
            gap = next((gap for gap in gaps if gap.width == width), None)
            if gap is not None:
                window.gap = gap
                window.position()

    def render(self):
        for window in self.windows.values():
            window.update(self.report)

    def refresh(self):
        if self.closed or self.busy:
            return not self.closed
        self.busy = True
        self.render()
        self.run_async(fetch_weather, self.loaded, self.failed)
        return True

    def loaded(self, weather):
        self.busy = False
        if not self.closed:
            self.report = WeatherReport(weather)
            self.render()

    def failed(self, _message):
        self.busy = False
        if not self.closed:
            self.report = self.report.unavailable()
            self.render()

    def close(self):
        self.closed = True
        GLib.source_remove(self.timer)
        GLib.source_remove(self.position_timer)
        self.monitors.disconnect(self.monitor_handler)
        for window in self.windows.values():
            window.dispose()
        self.windows.clear()

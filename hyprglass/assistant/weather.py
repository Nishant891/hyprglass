from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
from urllib.request import Request, urlopen

LATITUDE = 22.5726
LONGITUDE = 88.3639
REFRESH_SECONDS = 600
STALE_SECONDS = 1800
WEATHER_URL = (
    'https://api.open-meteo.com/v1/forecast?latitude=22.5726&longitude=88.3639'
    '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,is_day'
    '&temperature_unit=celsius&wind_speed_unit=kmh&timeformat=unixtime'
)

# WMO interpretation codes from https://open-meteo.com/en/docs.
CONDITIONS = {
    0: ('Clear', 'weather-clear-symbolic'), 1: ('Mainly clear', 'weather-clear-symbolic'),
    2: ('Partly cloudy', 'weather-few-clouds-symbolic'), 3: ('Overcast', 'weather-overcast-symbolic'),
    45: ('Fog', 'weather-fog-symbolic'), 48: ('Rime fog', 'weather-fog-symbolic'),
    51: ('Light drizzle', 'weather-showers-symbolic'), 53: ('Drizzle', 'weather-showers-symbolic'), 55: ('Dense drizzle', 'weather-showers-symbolic'),
    56: ('Freezing drizzle', 'weather-showers-symbolic'), 57: ('Heavy freezing drizzle', 'weather-showers-symbolic'),
    61: ('Light rain', 'weather-showers-symbolic'), 63: ('Rain', 'weather-showers-symbolic'), 65: ('Heavy rain', 'weather-showers-symbolic'),
    66: ('Freezing rain', 'weather-showers-symbolic'), 67: ('Heavy freezing rain', 'weather-showers-symbolic'),
    71: ('Light snow', 'weather-snow-symbolic'), 73: ('Snow', 'weather-snow-symbolic'), 75: ('Heavy snow', 'weather-snow-symbolic'),
    77: ('Snow grains', 'weather-snow-symbolic'), 80: ('Light showers', 'weather-showers-symbolic'),
    81: ('Showers', 'weather-showers-symbolic'), 82: ('Heavy showers', 'weather-showers-symbolic'),
    85: ('Snow showers', 'weather-snow-symbolic'), 86: ('Heavy snow showers', 'weather-snow-symbolic'),
    95: ('Thunderstorm', 'weather-storm-symbolic'), 96: ('Thunderstorm with hail', 'weather-storm-symbolic'),
    97: ('Heavy thunderstorm', 'weather-storm-symbolic'),
    99: ('Severe thunderstorm with hail', 'weather-storm-symbolic'),
}


@dataclass(frozen=True)
class Weather:
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: float
    wind_kmh: float
    code: int
    is_day: bool
    observed_at: datetime

    @property
    def condition(self):
        return CONDITIONS.get(self.code, ('Unknown conditions', 'weather-severe-alert-symbolic'))[0]

    @property
    def icon(self):
        if not self.is_day and self.code in (0, 1):
            return 'weather-clear-night-symbolic'
        if not self.is_day and self.code == 2:
            return 'weather-few-clouds-night-symbolic'
        return CONDITIONS.get(self.code, ('Unknown conditions', 'weather-severe-alert-symbolic'))[1]


@dataclass(frozen=True)
class WeatherReport:
    weather: Weather | None = None
    failed: bool = False

    def unavailable(self):
        return replace(self, failed=True)

    def stale(self, now):
        return self.weather is not None and (
            self.failed or (now - self.weather.observed_at).total_seconds() > STALE_SECONDS
        )

    def temperature(self, now):
        if self.weather is None:
            return 'Unavailable' if self.failed else 'Loading…'
        return f'{self.weather.temperature_c:.0f}°C' + (' · stale' if self.stale(now) else '')


def parse_weather(payload):
    try:
        current = payload['current']
        units = payload['current_units']
        measurements = (
            ('temperature_2m', '°C', -100, 70),
            ('apparent_temperature', '°C', -150, 100),
            ('relative_humidity_2m', '%', 0, 100),
            ('wind_speed_10m', 'km/h', 0, 500),
        )
        values = {}
        for name, unit, minimum, maximum in measurements:
            value = current[name]
            if (units[name] != unit or isinstance(value, bool)
                    or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or not minimum <= value <= maximum):
                raise ValueError('Invalid current weather measurement: ' + name)
            values[name] = float(value)
        code = current['weather_code']
        day = current['is_day']
        timestamp = current['time']
        if (type(code) is not int or type(day) is not int or day not in (0, 1)
                or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))):
            raise ValueError('Invalid current weather values')
        observed_at = datetime.fromtimestamp(timestamp, timezone.utc)
    except (KeyError, TypeError, OverflowError, OSError) as error:
        raise ValueError('Invalid current weather response') from error
    return Weather(temperature_c=values['temperature_2m'],
                   apparent_temperature_c=values['apparent_temperature'],
                   humidity_percent=values['relative_humidity_2m'],
                   wind_kmh=values['wind_speed_10m'], code=code,
                   is_day=bool(day), observed_at=observed_at)


def fetch_weather():
    request = Request(WEATHER_URL, headers={'User-Agent': 'Hyprglass-Weather/1.0'})
    with urlopen(request, timeout=10) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError('Weather response exceeds 64 KiB')
    return parse_weather(json.loads(payload))

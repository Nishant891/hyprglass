from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from hyprglass.assistant.weather import WeatherReport, fetch_weather, parse_weather


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        self.payload = {
            'current_units': {'temperature_2m': '°C', 'apparent_temperature': '°C',
                              'relative_humidity_2m': '%', 'wind_speed_10m': 'km/h'},
            'current': {'temperature_2m': 29.6, 'apparent_temperature': 32.4,
                        'relative_humidity_2m': 76, 'wind_speed_10m': 12.3, 'weather_code': 0,
                        'is_day': 1, 'time': self.now.timestamp()},
        }

    def test_parses_celsius_and_keeps_observation_immutable(self):
        weather = parse_weather(self.payload)
        self.assertEqual(weather.temperature_c, 29.6)
        self.assertEqual(weather.apparent_temperature_c, 32.4)
        self.assertEqual(weather.humidity_percent, 76)
        self.assertEqual(weather.wind_kmh, 12.3)
        self.assertEqual(weather.observed_at, self.now)
        self.assertEqual(weather.icon, 'weather-clear-symbolic')
        with self.assertRaises(FrozenInstanceError):
            weather.temperature_c = 1

    def test_wmo_precipitation_cloud_and_night_states(self):
        for code, day, icon in [(0, 0, 'weather-clear-night-symbolic'), (2, 1, 'weather-few-clouds-symbolic'), (3, 0, 'weather-overcast-symbolic'),
                                (61, 1, 'weather-showers-symbolic'), (95, 0, 'weather-storm-symbolic'), (71, 1, 'weather-snow-symbolic'),
                                (97, 1, 'weather-storm-symbolic'), (999, 1, 'weather-severe-alert-symbolic')]:
            with self.subTest(code=code, day=day):
                self.payload['current'].update(weather_code=code, is_day=day)
                self.assertEqual(parse_weather(self.payload).icon, icon)

    def test_rejects_missing_and_invalid_values_instead_of_showing_zero(self):
        for key, value in [('temperature_2m', None), ('temperature_2m', True),
                           ('temperature_2m', float('nan')), ('temperature_2m', 500),
                           ('weather_code', None), ('weather_code', '61'),
                           ('is_day', 2), ('is_day', False), ('time', None)]:
            with self.subTest(key=key, value=value):
                current = dict(self.payload['current'], **{key: value})
                with self.assertRaises(ValueError):
                    parse_weather(dict(self.payload, current=current))
        for payload in [{}, {'current': {}}, {'current': []}]:
            with self.assertRaises(ValueError):
                parse_weather(payload)
        self.payload['current_units']['temperature_2m'] = '°F'
        with self.assertRaises(ValueError):
            parse_weather(self.payload)

    def test_rejects_missing_invalid_or_wrong_unit_details(self):
        for key in ('apparent_temperature', 'relative_humidity_2m', 'wind_speed_10m'):
            for value in (None, True, '12', float('nan'), float('inf')):
                with self.subTest(key=key, value=value):
                    current = dict(self.payload['current'], **{key: value})
                    with self.assertRaises(ValueError):
                        parse_weather(dict(self.payload, current=current))
            current = dict(self.payload['current'])
            del current[key]
            with self.assertRaises(ValueError):
                parse_weather(dict(self.payload, current=current))
            units = dict(self.payload['current_units'], **{key: 'wrong'})
            with self.assertRaises(ValueError):
                parse_weather(dict(self.payload, current_units=units))
        for key, value in (('relative_humidity_2m', -1), ('relative_humidity_2m', 101),
                           ('wind_speed_10m', -1), ('apparent_temperature', 500)):
            with self.subTest(key=key, value=value):
                current = dict(self.payload['current'], **{key: value})
                with self.assertRaises(ValueError):
                    parse_weather(dict(self.payload, current=current))

    def test_calm_wind_and_zero_humidity_are_valid_readings(self):
        self.payload['current'].update(relative_humidity_2m=0, wind_speed_10m=0)
        weather = parse_weather(self.payload)
        self.assertEqual(weather.humidity_percent, 0)
        self.assertEqual(weather.wind_kmh, 0)

    def test_offline_without_observation_has_no_temperature(self):
        initial = WeatherReport()
        self.assertEqual(initial.temperature(self.now), 'Loading…')
        self.assertEqual(initial.unavailable().temperature(self.now), 'Unavailable')
        self.assertIsNone(initial.unavailable().weather)

    def test_failed_refresh_retains_reading_explicitly_marked_stale(self):
        report = WeatherReport(parse_weather(self.payload))
        self.assertEqual(report.temperature(self.now), '30°C')
        self.assertEqual(report.unavailable().temperature(self.now), '30°C · stale')
        self.assertEqual(report.unavailable().weather.apparent_temperature_c, 32.4)
        self.assertEqual(report.unavailable().weather.humidity_percent, 76)
        self.assertEqual(report.unavailable().weather.wind_kmh, 12.3)
        self.assertEqual(report.temperature(self.now + timedelta(minutes=31)), '30°C · stale')

    def test_fetch_uses_https_timeout_and_passes_current_reading(self):
        with patch('hyprglass.assistant.weather.urlopen', return_value=BytesIO(json.dumps(self.payload).encode())) as request:
            self.assertEqual(fetch_weather().temperature_c, 29.6)
        args, kwargs = request.call_args
        self.assertTrue(args[0].full_url.startswith('https://api.open-meteo.com/'))
        self.assertIn('latitude=22.5726&longitude=88.3639', args[0].full_url)
        self.assertIn('apparent_temperature,relative_humidity_2m,wind_speed_10m', args[0].full_url)
        self.assertIn('wind_speed_unit=kmh', args[0].full_url)
        self.assertEqual(kwargs['timeout'], 10)

    def test_network_failure_and_bad_json_do_not_create_readings(self):
        with patch('hyprglass.assistant.weather.urlopen', side_effect=URLError('offline')):
            with self.assertRaises(URLError):
                fetch_weather()
        for data in [b'<html>proxy error</html>', b'x' * 65537]:
            with self.subTest(data_length=len(data)):
                with patch('hyprglass.assistant.weather.urlopen', return_value=BytesIO(data)):
                    with self.assertRaises(ValueError):
                        fetch_weather()


if __name__ == '__main__':
    unittest.main()

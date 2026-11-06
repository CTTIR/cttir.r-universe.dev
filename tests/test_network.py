import unittest
import urllib.error
import http.client
from unittest import mock

from scripts.validate_registry import RegistryError, fetch_json


URL = 'https://api.github.com/repos/CTTIR/exampleR'


def response(raw=b'{"value":1}'):
    result = mock.MagicMock()
    result.__enter__.return_value.read.return_value = raw
    return result


def http_error(code):
    return urllib.error.HTTPError(URL, code, 'synthetic-sensitive-message', {}, None)


class NetworkTests(unittest.TestCase):
    def test_transient_http_error_recovers_with_a_bounded_retry(self):
        with mock.patch('urllib.request.urlopen', side_effect=[http_error(500), response()]) as opened, \
                mock.patch('time.sleep') as sleep:
            self.assertEqual(fetch_json(URL), {'value': 1})
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_permission_not_found_and_rate_limit_errors_are_not_retried(self):
        for code in [401, 403, 404, 429]:
            with self.subTest(code=code), \
                    mock.patch('urllib.request.urlopen', side_effect=http_error(code)) as opened, \
                    mock.patch('time.sleep') as sleep:
                with self.assertRaisesRegex(RegistryError, 'HTTP ' + str(code)) as raised:
                    fetch_json(URL)
                self.assertNotIn('synthetic-sensitive-message', str(raised.exception))
                self.assertNotIn(URL, str(raised.exception))
                opened.assert_called_once()
                sleep.assert_not_called()

    def test_repeated_transient_failure_stops_after_three_reads(self):
        with mock.patch('urllib.request.urlopen', side_effect=http_error(503)) as opened, \
                mock.patch('time.sleep') as sleep:
            with self.assertRaisesRegex(RegistryError, 'HTTP 503.*3 attempts'):
                fetch_json(URL)
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(1), mock.call(2)])

    def test_connection_and_incomplete_body_failures_retry_whole_read(self):
        broken_body = response()
        broken_body.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b'part')
        for failure in [TimeoutError('synthetic-sensitive-message'),
                        urllib.error.URLError('synthetic-sensitive-message'),
                        http.client.RemoteDisconnected('synthetic-sensitive-message'),
                        broken_body]:
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch('urllib.request.urlopen', side_effect=[failure, response()]) as opened, \
                    mock.patch('time.sleep'):
                self.assertEqual(fetch_json(URL), {'value': 1})
                self.assertEqual(opened.call_count, 2)

    def test_repeated_connection_failure_does_not_expose_exception_details(self):
        with mock.patch('urllib.request.urlopen', side_effect=TimeoutError('synthetic-sensitive-message')) as opened, \
                mock.patch('time.sleep'):
            with self.assertRaisesRegex(RegistryError, 'connection.*3 attempts') as raised:
                fetch_json(URL)
            self.assertNotIn('synthetic-sensitive-message', str(raised.exception))
            self.assertEqual(opened.call_count, 3)

    def test_invalid_or_oversized_metadata_is_not_retried(self):
        for raw in [b'not json', b'x' * 1048577]:
            with self.subTest(size=len(raw)), \
                    mock.patch('urllib.request.urlopen', return_value=response(raw)) as opened, \
                    mock.patch('time.sleep') as sleep:
                with self.assertRaises(RegistryError):
                    fetch_json(URL)
                opened.assert_called_once()
                sleep.assert_not_called()

    def test_permission_failure_after_transient_error_still_stops(self):
        with mock.patch('urllib.request.urlopen', side_effect=[http_error(502), http_error(403)]) as opened, \
                mock.patch('time.sleep') as sleep:
            with self.assertRaisesRegex(RegistryError, 'HTTP 403'):
                fetch_json(URL)
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()

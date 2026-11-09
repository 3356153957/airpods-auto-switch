import io
import json
import unittest
from urllib.error import HTTPError, URLError

from app_version import REPOSITORY
from update_checker import MAX_RESPONSE_BYTES, check_for_updates


class UpdateTests(unittest.TestCase):
    def release(self, tag='v1.0.0', **changes):
        return {'tag_name': tag, 'html_url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
                'draft': False, 'prerelease': False} | changes

    def check(self, release, current='1.0.0'):
        return check_for_updates(current, opener=lambda *a, **k: io.BytesIO(json.dumps(release).encode()))

    def test_latest_and_locally_newer_build_are_current(self):
        self.assertEqual(self.check(self.release()).status, 'current')
        self.assertEqual(self.check(self.release(), '2.0.0').status, 'current')

    def test_numeric_version_comparison_and_release_link(self):
        result = self.check(self.release('v1.10.0'), '1.9.0')
        self.assertEqual(result.status, 'available')
        self.assertEqual(result.latest_version, '1.10.0')
        self.assertEqual(result.url, self.release('v1.10.0')['html_url'])

    def test_stable_channel_rejects_preview_and_invalid_version(self):
        for release in (self.release(prerelease=True), self.release(draft=True),
                        self.release('v1.1.0-rc.1'), self.release('bad'), []):
            self.assertEqual(self.check(release).status, 'error')

    def test_untrusted_download_destinations_are_rejected(self):
        for url in ('http://github.com/' + REPOSITORY + '/releases/tag/v2.0.0',
                    'https://github.com.evil.example/a', 'file:///C:/payload.exe',
                    'https://github.com/other/project/releases/tag/v2.0.0',
                    'https://github.com/' + REPOSITORY + '/releases/tag/'):
            self.assertEqual(self.check(self.release(html_url=url)).status, 'error')

    def test_unpublished_rate_limited_and_unavailable_releases(self):
        for code, expected in ((404, 'empty'), (403, 'error'), (429, 'error'), (500, 'error')):
            def opener(*args, **kwargs):
                raise HTTPError('https://api.github.com', code, '', {}, None)
            self.assertEqual(check_for_updates(opener=opener).status, expected)
        for error in (URLError('offline'), TimeoutError('slow')):
            def opener(*args, **kwargs):
                raise error
            self.assertEqual(check_for_updates(opener=opener).status, 'error')

    def test_request_is_public_bounded_and_contains_no_local_settings(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 8)
            self.assertEqual(request.full_url, f'https://api.github.com/repos/{REPOSITORY}/releases/latest')
            self.assertIsNone(request.data)
            self.assertFalse(request.has_header('Authorization'))
            return io.BytesIO(json.dumps(self.release()).encode())
        self.assertEqual(check_for_updates(opener=opener).status, 'current')
        self.assertEqual(check_for_updates(opener=lambda *a, **k: io.BytesIO(b'x' * (MAX_RESPONSE_BYTES + 1))).status, 'error')
        self.assertEqual(check_for_updates(opener=lambda *a, **k: io.BytesIO(b'invalid json')).status, 'error')


if __name__ == '__main__':
    unittest.main()

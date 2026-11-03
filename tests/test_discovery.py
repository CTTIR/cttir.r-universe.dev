import base64
import copy
import json
import os
import unittest
import urllib.request
from unittest import mock

from scripts.validate_registry import RegistryError, check_discovery, discover_packages, fetch_json


API = 'https://api.github.com'
CATALOG = API + '/orgs/CTTIR/repos?type=public&per_page=100&page='
COMMIT = 'a' * 40
PACKAGES = 'b' * 40
NESTED = 'c' * 40


def metadata(name, **changes):
    return {'full_name': 'CTTIR/' + name, 'private': False, 'archived': False,
            'disabled': False, 'default_branch': 'main', **changes}


def entry(path, kind='blob', sha='d' * 40, mode=None):
    return {'path': path, 'type': kind, 'sha': sha,
            'mode': mode or ('040000' if kind == 'tree' else '100644')}


def description(name):
    return {'encoding': 'base64', 'content': base64.b64encode(
        ('Package: ' + name + '\nVersion: 1.0\n').encode()).decode()}


def public_sources():
    return {
        CATALOG + '1': [metadata('alphaR'), metadata('monorepo'), metadata('website')],
        API + '/repos/CTTIR/alphaR/commits/main': {'sha': COMMIT},
        API + '/repos/CTTIR/alphaR/git/trees/' + COMMIT:
            {'truncated': False, 'tree': [entry('DESCRIPTION'), entry('tests', 'tree')]},
        API + '/repos/CTTIR/alphaR/contents/DESCRIPTION?ref=' + COMMIT: description('alphaR'),
        API + '/repos/CTTIR/monorepo/commits/main': {'sha': COMMIT},
        API + '/repos/CTTIR/monorepo/git/trees/' + COMMIT:
            {'truncated': False, 'tree': [entry('packages', 'tree', PACKAGES)]},
        API + '/repos/CTTIR/monorepo/git/trees/' + PACKAGES:
            {'truncated': False, 'tree': [entry('nested', 'tree', NESTED), entry('README.md')]},
        API + '/repos/CTTIR/monorepo/git/trees/' + NESTED:
            {'truncated': False, 'tree': [entry('DESCRIPTION', mode='100755')]},
        API + '/repos/CTTIR/monorepo/contents/packages/nested/DESCRIPTION?ref=' + COMMIT:
            description('nestedR'),
        API + '/repos/CTTIR/website/commits/main': {'sha': COMMIT},
        API + '/repos/CTTIR/website/git/trees/' + COMMIT:
            {'truncated': False, 'tree': [entry('README.md')]},
    }


class DiscoveryTests(unittest.TestCase):
    def test_root_and_monorepo_identity_excludes_test_fixtures(self):
        sources = public_sources()
        calls = []
        def fetch(url):
            calls.append(url)
            return sources[url]
        found = discover_packages(fetch)
        self.assertEqual(found, [
            {'package': 'alphaR', 'url': 'https://github.com/CTTIR/alphaR'},
            {'package': 'nestedR', 'url': 'https://github.com/CTTIR/monorepo',
             'subdir': 'packages/nested'},
        ])
        self.assertTrue(all('?ref=' + COMMIT in url for url in calls if '/contents/' in url))
        self.assertFalse(any('/tests' in url for url in calls))

    def test_new_public_package_is_reported_without_rewriting_registry(self):
        listed = [{'package': 'alphaR', 'url': 'https://github.com/CTTIR/alphaR.git'}]
        original = copy.deepcopy(listed)
        result = check_discovery(listed, public_sources().__getitem__)
        self.assertEqual(result['discovered_packages'], 2)
        self.assertEqual(result['missing'], [{'package': 'nestedR',
            'url': 'https://github.com/CTTIR/monorepo', 'subdir': 'packages/nested'}])
        self.assertEqual(listed, original)
        self.assertEqual(check_discovery(listed + result['missing'], public_sources().__getitem__)['missing'], [])

    def test_pagination_reaches_new_package_after_first_hundred_repositories(self):
        sources = public_sources()
        sources[CATALOG + '2'] = sources[CATALOG + '1']
        sources[CATALOG + '1'] = [metadata('archived-' + str(i), archived=True) for i in range(100)]
        self.assertEqual(len(discover_packages(sources.__getitem__)), 2)

    def test_private_or_duplicate_public_catalogue_entries_fail(self):
        for changed in (metadata('secret', private=True), metadata('alphaR'),
                        metadata('external', full_name='somebody/else')):
            sources = public_sources()
            sources[CATALOG + '1'].append(changed)
            with self.subTest(changed=changed), self.assertRaises(RegistryError):
                discover_packages(sources.__getitem__)

    def test_disabled_and_archived_repositories_are_not_scanned(self):
        sources = public_sources()
        sources[CATALOG + '1'] += [metadata('disabled', disabled=True), metadata('archived', archived=True)]
        self.assertEqual(len(discover_packages(sources.__getitem__)), 2)

    def test_truncated_ambiguous_or_symlinked_description_fails(self):
        for changed in ({'truncated': True, 'tree': []}, {'tree': []},
                        {'truncated': False, 'tree': [entry('DESCRIPTION'), entry('DESCRIPTION')]},
                        {'truncated': False, 'tree': [entry('../DESCRIPTION')]},
                        {'truncated': False, 'tree': [entry('DESCRIPTION', mode='120000')]}):
            sources = public_sources()
            sources[API + '/repos/CTTIR/alphaR/git/trees/' + COMMIT] = changed
            with self.subTest(changed=changed), self.assertRaises(RegistryError):
                discover_packages(sources.__getitem__)

    def test_malformed_description_does_not_silently_disappear(self):
        sources = public_sources()
        sources[API + '/repos/CTTIR/alphaR/contents/DESCRIPTION?ref=' + COMMIT] = description('bad_name')
        with self.assertRaises(RegistryError):
            discover_packages(sources.__getitem__)

    def test_token_is_sent_only_to_github_and_not_forwarded_on_redirect(self):
        seen = []
        def open_request(request, timeout):
            seen.append(request)
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = b'{}'
            return response
        with mock.patch.dict(os.environ, {'GH_TOKEN': 'synthetic-token'}, clear=True), \
                mock.patch('urllib.request.urlopen', side_effect=open_request):
            fetch_json(API + '/repos/CTTIR/exampleR')
            fetch_json('https://example.org/public-metadata')
        self.assertEqual(seen[0].get_header('Authorization'), 'Bearer synthetic-token')
        self.assertIsNone(seen[1].get_header('Authorization'))
        redirected = urllib.request.HTTPRedirectHandler().redirect_request(
            seen[0], None, 302, 'Found', {}, 'https://example.org/redirect')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_invalid_token_fails_without_echoing_credentials_or_making_requests(self):
        with mock.patch.dict(os.environ, {'GH_TOKEN': 'synthetic-secret\ninvalid'}, clear=True), \
                mock.patch('urllib.request.urlopen') as open_request:
            with self.assertRaises(RegistryError) as raised:
                fetch_json(API + '/repos/CTTIR/exampleR')
        self.assertNotIn('synthetic-secret', str(raised.exception))
        open_request.assert_not_called()


if __name__ == '__main__':
    unittest.main()

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate_registry import RegistryError, check_upstream, decode, validate


ENTRY = {'package': 'exampleR', 'url': 'https://github.com/CTTIR/exampleR'}
ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_current_registry_is_valid(self):
        rows = validate(decode((ROOT / 'packages.json').read_bytes()))
        self.assertGreater(len(rows), 0)

    def test_ambiguous_or_nonfinite_json_fails(self):
        for raw in ('{"package":"one","package":"two"}', '{"x":NaN}', '{"x":1e999}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(RegistryError):
                decode(raw)

    def test_invalid_names_reserved_names_and_duplicates_fail(self):
        for name in ('a', 'bad_name', '2bad', 'ending.', 'API', [], None):
            with self.subTest(name=name), self.assertRaises(RegistryError):
                validate([{**ENTRY, 'package': name}])
        with self.assertRaises(RegistryError):
            validate([ENTRY, {**ENTRY, 'package': 'ExampleR', 'url': 'https://github.com/CTTIR/other'}])
        with self.assertRaises(RegistryError):
            validate([ENTRY, {**ENTRY, 'package': 'otherR', 'url': ENTRY['url'] + '.git'}])

    def test_external_credential_and_traversal_urls_fail(self):
        for url in ('http://github.com/CTTIR/exampleR', 'https://github.com/elsewhere/exampleR',
                    'https://secret@github.com/CTTIR/exampleR', ENTRY['url'] + '?token=secret',
                    'https://github.com/CTTIR/..', [], None):
            with self.subTest(url=url), self.assertRaises(RegistryError):
                validate([{**ENTRY, 'url': url}])

    def test_safe_subdirectories_and_git_refs(self):
        self.assertEqual(validate([{**ENTRY, 'subdir': 'packages/R', 'branch': 'release/v1',
                                    'metadata': {'review': 'pending'}}])[0]['subdir'], 'packages/R')
        self.assertEqual(validate([{**ENTRY, 'branch': '*release'}])[0]['branch'], '*release')
        for key, bad in [('subdir', '../private'), ('subdir', '/private'), ('subdir', 'a//b'),
                         ('subdir', 'a\\b'), ('subdir', []), ('branch', 'main;command'),
                         ('branch', 'bad..ref'), ('branch', []), ('metadata', [])]:
            # A semicolon is a legal Git ref: it is passed as data, never to a shell.
            if bad == 'main;command':
                validate([{**ENTRY, key: bad}])
                continue
            with self.subTest(key=key, bad=bad), self.assertRaises(RegistryError):
                validate([{**ENTRY, key: bad}])

    def test_unknown_fields_and_malformed_top_level_fail(self):
        for rows in (None, {}, [], [None], [{**ENTRY, 'packages': 'typo'}], [{'package': 'exampleR'}]):
            with self.subTest(rows=rows), self.assertRaises(RegistryError):
                validate(rows)

    def test_upstream_uses_resolved_commit_and_description_identity(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if '/commits/' in url:
                return {'sha': 'a' * 40}
            if '/contents/' in url:
                return {'encoding': 'base64', 'content': base64.b64encode(b'Package: exampleR\nVersion: 1.0\n').decode()}
            return {'private': False, 'archived': False, 'full_name': 'CTTIR/exampleR', 'default_branch': 'main'}
        result = check_upstream([ENTRY], fetch)
        self.assertEqual(result[0]['commit'], 'a' * 40)
        self.assertTrue(calls[-1].endswith('?ref=' + 'a' * 40))

    def test_private_archived_and_wrong_package_upstreams_fail(self):
        for changed in ({'private': True}, {'archived': True}, {'full_name': 1}):
            with self.subTest(changed=changed), self.assertRaises(RegistryError):
                check_upstream([ENTRY], lambda _: {'private': False, 'archived': False,
                                                   'full_name': 'CTTIR/exampleR', **changed})
        def fetch(url):
            if '/commits/' in url:
                return {'sha': 'a' * 40}
            if '/contents/' in url:
                return {'encoding': 'base64', 'content': base64.b64encode(b'Package: differentR\n').decode()}
            return {'private': False, 'archived': False, 'full_name': 'CTTIR/exampleR', 'default_branch': 'main'}
        with self.assertRaises(RegistryError):
            check_upstream([ENTRY], fetch)

    def test_latest_release_subdirectory_and_crlf_description(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url.endswith('/releases/latest'):
                return {'tag_name': 'v1.0'}
            if '/commits/' in url:
                return {'sha': 'b' * 40}
            if '/contents/' in url:
                return {'encoding': 'base64', 'content': base64.b64encode(b'Package: exampleR\r\nVersion: 1.0\r\n').decode()}
            return {'private': False, 'archived': False, 'full_name': 'CTTIR/exampleR', 'default_branch': 'main'}
        check_upstream([{**ENTRY, 'branch': '*release', 'subdir': 'packages/R'}], fetch)
        self.assertTrue(calls[-2].endswith('/commits/v1.0'))
        self.assertIn('/contents/packages/R/DESCRIPTION?ref=', calls[-1])

    def test_malformed_upstream_description_is_not_accepted(self):
        for content in ('not base64!', base64.b64encode(b'Package: exampleR\nPackage: exampleR\n').decode()):
            def fetch(url):
                if '/commits/' in url:
                    return {'sha': 'a' * 40}
                if '/contents/' in url:
                    return {'encoding': 'base64', 'content': content}
                return {'private': False, 'archived': False, 'full_name': 'CTTIR/exampleR', 'default_branch': 'main'}
            with self.assertRaises(RegistryError):
                check_upstream([ENTRY], fetch)

    def test_cli_is_independent_of_working_directory_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(ROOT / 'scripts/validate_registry.py')]
            good = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=5)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertFalse(json.loads(good.stdout)['upstream_checked'])
            bad = Path(directory) / 'bad.json'
            bad.write_text('[{"package":"secret"}]')
            failed = subprocess.run(command + [str(bad)], cwd=directory, capture_output=True, text=True, timeout=5)
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)['status'], 'fail')
            self.assertFalse(failed.stderr)

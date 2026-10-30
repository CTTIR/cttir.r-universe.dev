"""Validate this public CTTIR registry; network access is explicitly opt-in."""

import argparse
import base64
import json
import math
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


class RegistryError(ValueError):
    pass


RESERVED = set("api apis articles badges bin builds citation contributors datasets docs favicon.ico "
               "feed.xml index.xml manual packages readme robots.txt sitemap_index.xml sitemap.xml src stats".split())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError("Duplicate JSON object key.")
        result[key] = value
    return result


def decode(raw):
    def nonfinite(_):
        raise RegistryError("Non-finite JSON values are unsupported.")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise RegistryError("Non-finite JSON values are unsupported.")
        return number
    try:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw, object_pairs_hook=unique_object, parse_constant=nonfinite, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RegistryError("Expected unambiguous UTF-8 JSON.") from exc


def validate(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise RegistryError("Registry must contain 1–1000 package entries.")
    names, sources = set(), set()
    for row in rows:
        if (not isinstance(row, dict) or not {'package', 'url'}.issubset(row)
                or set(row) - {'package', 'url', 'branch', 'subdir', 'metadata'}):
            raise RegistryError("Entry needs package and url; only branch, subdir and metadata are optional.")
        name = row['package']
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9.]*[A-Za-z0-9]', name)
                or name.lower() in RESERVED or name.lower() in names):
            raise RegistryError("Package names must be valid, unique and not reserved by R-universe.")
        names.add(name.lower())
        url = row['url']
        if not isinstance(url, str) or not re.fullmatch(r'https://github[.]com/CTTIR/[A-Za-z0-9_.-]+', url):
            raise RegistryError("This registry accepts canonical public HTTPS GitHub URLs under CTTIR only.")
        if url.rsplit('/', 1)[-1].removesuffix('.git') in ('', '.', '..'):
            raise RegistryError("Repository URL needs an ordinary repository name.")
        subdir = row.get('subdir', '')
        if 'subdir' in row and (not isinstance(subdir, str) or not subdir or '\\' in subdir
                or any(ord(c) < 32 for c in subdir) or PurePosixPath(subdir).is_absolute()
                or any(part in ('', '.', '..') for part in subdir.split('/'))):
            raise RegistryError("Subdirectory must be a nonempty relative POSIX path without traversal.")
        source = (url.removesuffix('.git').lower(), subdir)
        if source in sources:
            raise RegistryError("A source directory may only be registered once.")
        sources.add(source)
        if 'branch' in row:
            branch = row['branch']
            if not isinstance(branch, str) or not branch or len(branch) > 250:
                raise RegistryError("Branch must be a nonempty Git reference or *release.")
            if branch != '*release' and subprocess.run(
                    ['git', 'check-ref-format', 'refs/heads/' + branch],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                raise RegistryError("Invalid Git branch or tag reference.")
        if 'metadata' in row and not isinstance(row['metadata'], dict):
            raise RegistryError("Custom metadata must be a JSON object.")
    return rows


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'CTTIR-registry-check',
                                                  'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(1048577)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RegistryError("Upstream API unavailable; retry the explicit network check later.") from exc
    if len(raw) > 1048576:
        raise RegistryError("Upstream metadata exceeds 1 MiB.")
    return decode(raw)


def check_upstream(rows, fetch=fetch_json):
    result = []
    for row in validate(rows):
        repo = row['url'].removeprefix('https://github.com/').removesuffix('.git')
        api = 'https://api.github.com/repos/' + repo
        metadata = fetch(api)
        if (not isinstance(metadata, dict) or metadata.get('private') is not False
                or metadata.get('archived') is not False or not isinstance(metadata.get('full_name'), str)
                or metadata['full_name'].lower() != repo.lower()):
            raise RegistryError("Repository is not the expected public, active upstream.")
        ref = row.get('branch', metadata.get('default_branch'))
        if ref == '*release':
            release = fetch(api + '/releases/latest')
            ref = release.get('tag_name') if isinstance(release, dict) else None
        if not isinstance(ref, str) or not ref:
            raise RegistryError("Upstream reference is unavailable.")
        commit = fetch(api + '/commits/' + urllib.parse.quote(ref, safe=''))
        sha = commit.get('sha') if isinstance(commit, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise RegistryError("Upstream reference did not resolve to a commit.")
        path = row.get('subdir', '')
        path = (path + '/' if path else '') + 'DESCRIPTION'
        description = fetch(api + '/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + sha)
        try:
            if not isinstance(description, dict) or description.get('encoding') != 'base64':
                raise ValueError('encoding')
            raw = base64.b64decode(''.join(description['content'].split()), validate=True).decode('utf-8')
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise RegistryError("Expected a readable DESCRIPTION at the resolved commit.") from exc
        raw = raw.replace('\r\n', '\n').replace('\r', '\n')
        package = re.findall(r'^Package:[ \t]*(\S+)[ \t]*$', raw, re.MULTILINE)
        if package != [row['package']]:
            raise RegistryError("Registered package differs from its upstream DESCRIPTION.")
        result.append({'package': row['package'], 'repository': repo, 'commit': sha})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registry', nargs='?', type=Path, default=Path(__file__).resolve().parents[1] / 'packages.json')
    parser.add_argument('--upstream', action='store_true', help='Read public GitHub metadata; never publish or build')
    args = parser.parse_args()
    try:
        with args.registry.open('rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            raise RegistryError('Registry exceeds 1 MiB.')
        rows = validate(decode(raw))
        report = {'status': 'pass', 'packages': len(rows), 'upstream_checked': args.upstream}
        if args.upstream:
            report['upstream'] = check_upstream(rows)
        print(json.dumps(report))
        return 0
    except (RegistryError, OSError) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())

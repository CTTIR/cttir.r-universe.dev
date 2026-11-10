"""Validate this public CTTIR registry; network access is explicitly opt-in."""

import argparse
import base64
import http.client
import json
import math
import os
import re
import subprocess
import sys
import time
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
    # Keep credentials off redirected requests and non-GitHub destinations.
    if urllib.parse.urlsplit(url)[:2] == ('https', 'api.github.com'):
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if token:
            if any(ord(char) < 33 or ord(char) > 126 for char in token):
                raise RegistryError("GitHub token contains invalid header characters.")
            request.add_unredirected_header('Authorization', 'Bearer ' + token)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(1048577)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504) or attempt == 3:
                raise RegistryError(
                    f"Upstream API returned HTTP {exc.code} after {attempt} attempts."
                ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            if attempt == 3:
                raise RegistryError("Upstream API connection failed after 3 attempts.") from exc
        time.sleep(attempt)
    if len(raw) > 1048576:
        raise RegistryError("Upstream metadata exceeds 1 MiB.")
    return decode(raw)


def description_package(description):
    try:
        if not isinstance(description, dict) or description.get('encoding') != 'base64':
            raise ValueError('encoding')
        raw = base64.b64decode(''.join(description['content'].split()), validate=True).decode('utf-8')
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RegistryError("Expected a readable DESCRIPTION at the resolved commit.") from exc
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    package = re.findall(r'^Package:[ \t]*(\S+)[ \t]*$', raw, re.MULTILINE)
    if len(package) != 1:
        raise RegistryError("DESCRIPTION must contain one unambiguous Package field.")
    return package[0]


def resolve_commit(api, ref, fetch):
    if not isinstance(ref, str) or not ref:
        raise RegistryError("Upstream reference is unavailable.")
    # The single-commit endpoint includes every file diff and can exceed the
    # response limit; the one-item commit list returns the same SHA without it.
    commits = fetch(api + '/commits?per_page=1&sha=' + urllib.parse.quote(ref, safe=''))
    commit = commits[0] if isinstance(commits, list) and len(commits) == 1 else None
    sha = commit.get('sha') if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise RegistryError("Upstream reference did not resolve to a commit.")
    return sha


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
        sha = resolve_commit(api, ref, fetch)
        path = row.get('subdir', '')
        path = (path + '/' if path else '') + 'DESCRIPTION'
        description = fetch(api + '/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + sha)
        if description_package(description) != row['package']:
            raise RegistryError("Registered package differs from its upstream DESCRIPTION.")
        result.append({'package': row['package'], 'repository': repo, 'commit': sha})
    return result


def discover_packages(fetch=fetch_json):
    """Find public packages at repository roots and packages/*, without writes."""
    found, seen_repos = [], set()

    def tree(api, sha):
        value = fetch(api + '/git/trees/' + sha)
        if (not isinstance(value, dict) or value.get('truncated') is not False
                or not isinstance(value.get('tree'), list)):
            raise RegistryError("Expected a complete upstream Git tree.")
        entries = value['tree']
        paths = set()
        for entry in entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
                    or not entry['path'] or '/' in entry['path'] or '\\' in entry['path']
                    or entry['path'] in ('.', '..') or entry['path'] in paths
                    or entry.get('type') not in ('blob', 'tree', 'commit')
                    or not isinstance(entry.get('sha'), str)
                    or not re.fullmatch(r'[a-f0-9]{40}', entry['sha'])):
                raise RegistryError("Malformed or ambiguous upstream Git tree.")
            paths.add(entry['path'])
        return entries

    def add_package(repo, sha, entries, subdir=''):
        descriptions = [e for e in entries if e['path'] == 'DESCRIPTION']
        if not descriptions:
            return
        if (descriptions[0]['type'] != 'blob'
                or descriptions[0].get('mode') not in ('100644', '100755')):
            raise RegistryError("Package DESCRIPTION must be an ordinary file.")
        path = (subdir + '/' if subdir else '') + 'DESCRIPTION'
        description = fetch('https://api.github.com/repos/' + repo + '/contents/'
                            + urllib.parse.quote(path, safe='/') + '?ref=' + sha)
        row = {'package': description_package(description), 'url': 'https://github.com/' + repo}
        if subdir:
            row['subdir'] = subdir
        validate([row])
        found.append(row)

    for page in range(1, 11):
        catalog = fetch('https://api.github.com/orgs/CTTIR/repos?type=public&per_page=100&page=' + str(page))
        if not isinstance(catalog, list) or len(catalog) > 100:
            raise RegistryError("Expected a public repository catalogue page.")
        for metadata in catalog:
            if (not isinstance(metadata, dict) or metadata.get('private') is not False
                    or not isinstance(metadata.get('full_name'), str)
                    or not re.fullmatch(r'CTTIR/[A-Za-z0-9_.-]+', metadata['full_name'])
                    or metadata['full_name'] in seen_repos
                    or not isinstance(metadata.get('archived'), bool)
                    or not isinstance(metadata.get('disabled'), bool)):
                raise RegistryError("Unexpected, private or duplicate repository in public catalogue.")
            repo = metadata['full_name']
            seen_repos.add(repo)
            if metadata['archived'] or metadata['disabled']:
                continue
            api = 'https://api.github.com/repos/' + repo
            sha = resolve_commit(api, metadata.get('default_branch'), fetch)
            entries = tree(api, sha)
            add_package(repo, sha, entries)
            # Only deliberate package locations: never recurse through tests,
            # fixtures, installed dependencies or vendored copies.
            for entry in entries:
                if entry['path'] == 'packages' and entry['type'] == 'tree':
                    for child in tree(api, entry['sha']):
                        if child['type'] == 'tree':
                            add_package(repo, sha, tree(api, child['sha']), 'packages/' + child['path'])
        if len(catalog) < 100:
            if found:
                validate(found)
            return sorted(found, key=lambda row: row['package'].lower())
    raise RegistryError("Public repository catalogue exceeds the discovery bound.")


def check_discovery(rows, fetch=fetch_json):
    listed = {(row['package'], row['url'].removesuffix('.git').lower(), row.get('subdir', ''))
              for row in validate(rows)}
    discovered = discover_packages(fetch)
    missing = [row for row in discovered
               if (row['package'], row['url'].lower(), row.get('subdir', '')) not in listed]
    return {'discovered_packages': len(discovered), 'missing': missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registry', nargs='?', type=Path, default=Path(__file__).resolve().parents[1] / 'packages.json')
    parser.add_argument('--upstream', action='store_true', help='Read public GitHub metadata; never publish or build')
    parser.add_argument('--discover', action='store_true',
                        help='Fail if public root/packages/* packages are missing; never rewrite the registry')
    args = parser.parse_args()
    try:
        with args.registry.open('rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            raise RegistryError('Registry exceeds 1 MiB.')
        rows = validate(decode(raw))
        report = {'status': 'pass', 'packages': len(rows), 'upstream_checked': args.upstream,
                  'discovery_checked': args.discover}
        if args.upstream:
            report['upstream'] = check_upstream(rows)
        if args.discover:
            report['discovery'] = check_discovery(rows)
            if report['discovery']['missing']:
                report['status'] = 'fail'
                print(json.dumps(report))
                return 1
        print(json.dumps(report))
        return 0
    except (RegistryError, OSError) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())

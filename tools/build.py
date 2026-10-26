#!/usr/bin/env python3
"""Build platform packages; --check is read-only and fails on any drift."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ('codex', 'claude')
# Codex reads agents/openai.yaml; Claude has no use for it.
CODEX_ONLY = 'agents'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load_mapping(text, label):
    value = yaml.safe_load(text)
    require(isinstance(value, dict), f'{label} must be a YAML mapping')
    return value


def frontmatter(data):
    text = data.decode('utf-8')
    require(text.startswith('---\n'), 'SKILL.md must begin with LF YAML frontmatter')
    parts = text[4:].split('\n---\n', 1)
    require(len(parts) == 2, 'SKILL.md frontmatter is not closed')
    return load_mapping(parts[0], 'SKILL.md frontmatter'), parts[1]


def hidden(path, base):
    # Skips OS/editor clutter such as .DS_Store anywhere below base.
    return any(part.startswith('.') for part in path.relative_to(base).parts)


def expected_files():
    release = json.loads((ROOT / 'release.json').read_text(encoding='utf-8'))
    require(isinstance(release, dict) and set(release) == {'name', 'version', 'description', 'author', 'repository'}, 'Invalid release metadata')
    require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', release['name']), 'Invalid package name')
    require(re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', release['version']), 'Use a stable SemVer version')
    require(release['author'].get('name') and release['description'], 'Missing author/description')
    output = {}
    hashes = {platform: {} for platform in PLATFORMS}
    skills = sorted(p for p in (ROOT / 'skills').iterdir() if not hidden(p, ROOT / 'skills'))
    require(skills, 'No source skills')
    for skill in skills:
        require(skill.is_dir() and not skill.is_symlink(), f'Not a source directory: {skill}')
        data = (skill / 'SKILL.md').read_bytes()
        meta, body = frontmatter(data)
        require(set(meta) == {'name', 'description'}, f'{skill.name}: keep common frontmatter only')
        require(meta['name'] == skill.name and len(skill.name) <= 64 and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill.name), 'Skill name mismatch')
        require(isinstance(meta['description'], str) and 0 < len(meta['description']) <= 1024, 'Invalid description')
        ui = load_mapping((skill / 'agents/openai.yaml').read_text(encoding='utf-8'), f'{skill.name}: agents/openai.yaml')
        require(ui['interface']['display_name'] == skill.name, 'Display name mismatch')
        require(25 <= len(ui['interface']['short_description']) <= 64, 'Invalid short description length')
        require(ui['policy']['allow_implicit_invocation'] is False, 'Explicit invocation required')
        invocation = f"${release['name']}:{skill.name}"
        require(invocation in re.findall(r'\$[a-z0-9:-]+', ui['interface']['default_prompt']), 'Missing plugin-qualified invocation name')
        require('$ARGUMENTS' not in data.decode('utf-8'), 'Use the neutral input contract')
        for link in re.findall(r'\]\(([^)]+)\)', body):
            if '://' not in link and not link.startswith('#'):
                target = (skill / link.split('#')[0]).resolve()
                require(target.is_relative_to(skill.resolve()) and target.is_file(), f'Broken reference: {link}')
        for source in sorted(p for p in skill.rglob('*') if not hidden(p, skill)):
            require(not source.is_symlink(), f'Packages must not depend on symlinks: {source}')
            if not source.is_file():
                continue
            relative = source.relative_to(ROOT).as_posix()
            content = source.read_bytes()
            for platform in PLATFORMS:
                if platform == 'claude' and source.relative_to(skill).parts[0] == CODEX_ONLY:
                    continue
                adapted = content
                if platform == 'claude' and source == skill / 'SKILL.md':
                    adapted = content.replace(b'---\n', b'---\ndisable-model-invocation: true\n', 1)
                output[f'dist/{platform}/{relative}'] = adapted
                hashes[platform][relative] = hashlib.sha256(adapted).hexdigest()
    for platform in PLATFORMS:
        manifest = dict(release)
        if platform == 'codex':
            manifest.update(skills='./skills/', interface={'displayName': release['name'], 'shortDescription': release['description']})
        # Claude scans its standard skills/ directory without an extra path.
        output[f'dist/{platform}/.{platform}-plugin/plugin.json'] = json_bytes(manifest)
        # Hashes cover the shipped bytes, so installed files can be compared directly.
        # Sort as text: Path ordering is case-insensitive on Windows and would change the bytes.
        digests = dict(sorted(hashes[platform].items()))
        output[f'dist/{platform}/BUILD.json'] = json_bytes({'generated': True, 'source': 'skills/', 'version': release['version'], 'platform': platform, 'sha256': digests})
        output[f'dist/{platform}/GENERATED.md'] = b'Generated by tools/build.py from skills/ and release.json. Do not edit.\n'
    name = release['name']
    output['.agents/plugins/marketplace.json'] = json_bytes({
        'name': name,
        'interface': {'displayName': name},
        'plugins': [{
            'name': name,
            'source': {'source': 'local', 'path': './dist/codex'},
            'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
            'category': 'Productivity',
        }],
    })
    output['.claude-plugin/marketplace.json'] = json_bytes({
        'name': name,
        'owner': release['author'],
        'metadata': {'description': release['description']},
        'plugins': [{'name': name, 'source': './dist/claude', 'description': release['description']}],
    })
    return output


def remove_stale(name):
    path = ROOT / name
    path.unlink()
    # Drop directories the removal left empty, stopping at dist/.
    for parent in path.parents:
        if parent == ROOT / 'dist' or any(parent.iterdir()):
            break
        parent.rmdir()


def build(check=False):
    expected = expected_files()
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'dist').rglob('*') if p.is_file() or p.is_symlink()}
    # Never traverse an output symlink or overwrite files outside the checkout.
    for name in set(expected) | actual:
        path = ROOT / name
        require(not any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(ROOT)), f'Symlink output refused: {name}')
    stale = sorted(actual - expected.keys())
    changed = [name for name, content in expected.items() if not (ROOT / name).is_file() or (ROOT / name).read_bytes() != content]
    if check:
        require(not stale and not changed, 'Generated files stale: ' + ', '.join(stale + changed))
        print(f'PASS: {len(expected)} generated files; source metadata, invocation policies, references and byte parity')
        return
    for name in stale:
        remove_stale(name)
    for name in changed:
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected[name])
    print(f'Generated {len(expected)} files ({len(changed)} updated); removed {len(stale)} obsolete generated files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    try:
        build(parser.parse_args().check)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, yaml.YAMLError) as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)

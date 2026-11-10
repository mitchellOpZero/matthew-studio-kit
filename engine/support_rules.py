"""Bounded source inventory, not a claim about instructions loaded by a running chat."""
from pathlib import Path
import os
import re


def inventory(root, cwd=None, user_home=None, codex_home=None):
    from support import digest, tag
    root = Path(root).resolve()
    cwd = Path(cwd or Path.cwd()).resolve()
    user_home = Path(user_home or Path.home())
    codex_home = Path(codex_home or os.environ.get('CODEX_HOME', user_home / '.codex')).expanduser()
    rows, skills, truncated = [], [], False

    def add(path, base, scope, kind, selected=None):
        if not path.is_file():
            return
        sha = digest(path)
        row = {'source': scope + '/' + '/'.join(tag(p) for p in path.relative_to(base).parts),
               'kind': kind, 'sha256': sha}
        if selected is not None:
            row['default_discovery_candidate'] = selected
        rows.append(row)
        return row

    def instructions(base, scope):
        chosen = False
        for name in ('AGENTS.override.md', 'AGENTS.md'):
            p = base / name
            nonempty = p.is_file() and p.stat().st_size > 0
            add(p, base, scope, 'instructions', nonempty and not chosen)
            chosen = chosen or nonempty
        add(base / 'config.toml', base, scope, 'configuration')
        add(base / '.codex' / 'config.toml', base, scope, 'configuration')
        for folder in (base / 'rules', base / '.codex' / 'rules'):
            for p in sorted(folder.glob('*.rules'))[:30]:
                add(p, base, scope, 'command_approval_rules')

    instructions(codex_home, 'global-codex')
    try:
        relative = cwd.relative_to(root)
        directories = [root]
        for part in relative.parts:
            directories.append(directories[-1] / part)
        launch = 'kit/' + '/'.join(tag(x) for x in relative.parts)
    except ValueError:
        directories, launch = [root], 'outside-kit'
    for base in directories:
        scope = 'project' + ('/' + base.relative_to(root).as_posix() if base != root else '')
        instructions(base, scope)
    # Ancestors are diagnostic candidates only: Git-root discovery normally excludes them.
    for i, parent in enumerate(list(root.parents)[:8]):
        for name in ('AGENTS.override.md', 'AGENTS.md'):
            add(parent / name, parent, 'ancestor-' + str(i), 'ancestor_candidate', False)

    roots = [(user_home / '.agents' / 'skills', 'user-skills', 3),
             (codex_home / 'skills', 'legacy-codex-skills', 3),
             (codex_home / 'plugins' / 'cache', 'plugin-cache-candidates', 8),
             (root / 'skills', 'kit-skills', 3)]
    roots += [(base / '.agents' / 'skills', 'project-skills-' + str(i), 3)
              for i, base in enumerate(directories)]
    for base, scope, depth in roots:
        visited = 0
        for folder, subdirs, files in os.walk(base, followlinks=False):
            visited += 1
            current = Path(folder)
            subdirs[:] = sorted(d for d in subdirs if d not in {'.git', 'node_modules', '.venv', '__pycache__'})
            if len(current.relative_to(base).parts) >= depth:
                subdirs[:] = []
            if visited > 2000 or len(skills) >= 300:
                truncated = True
                break
            if 'SKILL.md' not in files:
                continue
            p = current / 'SKILL.md'
            name = tag(current.name)
            # Only the frontmatter name is read; instructions and descriptions never leave the device.
            if p.stat().st_size <= 2000000:
                raw = p.read_text(errors='replace')[:8192]
                if raw.startswith('---'):
                    header = raw.split('---', 2)
                    match = re.search(r'^name:\s*[\"\']?([\w:-]+)', header[1], re.M) if len(header) > 2 else None
                    if match:
                        name = tag(match[1])
            row = add(p, base, scope, 'skill_candidate')
            row['name'] = name
            skills.append(row)
    names = {}
    for row in skills:
        names.setdefault(row['name'], []).append(row)
    duplicates = [{'name': name, 'sources': [r['source'] for r in group],
                   'different_content': len({r['sha256'] for r in group}) > 1}
                  for name, group in sorted(names.items()) if len(group) > 1]
    return {'launch_directory': launch, 'sources': rows, 'duplicate_skills': duplicates,
            'truncated': truncated, 'evidence': 'files present, not proof of activation or use',
            'limits': 'Default AGENTS discovery candidates only. Custom fallback filenames, config overrides, trust, byte limits, plugin enablement and existing chat context are not resolved. Cached plugins may be inactive. Command approval rules are not creative style rules.'}


def compare(left, right):
    def sources(value):
        if 'provenance' in value:
            value = value['provenance']
        value = value.get('rules', value)
        if not isinstance(value.get('sources'), list):
            raise ValueError('Compare two support rules or support doctor JSON reports')
        return {r['source']: r.get('sha256') for r in value['sources']}
    a, b = sources(left), sources(right)
    return {'only_left': sorted(a.keys() - b.keys()), 'only_right': sorted(b.keys() - a.keys()),
            'different_content': sorted(k for k in a.keys() & b.keys() if a[k] != b[k]),
            'note': 'Source differences identify things to inspect; they do not prove a rule caused the video quality difference.'}

#!/usr/bin/env python3
"""Package only runtime source/config templates, never corpora, credentials or outputs."""
import argparse
import hashlib
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='outputs/search-release.tar.gz')
    args = parser.parse_args()
    files = sorted((ROOT / 'lexicon_search').glob('*.py'))
    files += [ROOT / name for name in [
        'requirements-search.txt', 'requirements-search.lock',
        'scripts/run_search_service.py', 'scripts/rebuild_search_index.py',
        'scripts/run_search_benchmarks.py', 'scripts/package_search_release.py',
        'deploy/compose.yaml', 'deploy/postgres-init.sql',
        'deploy/search-db-permissions.sql', 'deploy/search-engine.service',
        'deploy/search-engine.env.example', 'deploy/nginx-search.conf',
        'docs/search-engine-operations.md',
        'docs/entry-details-api.md',
        'docs/query-rewrite.md',
        'supabase/migrations/20261023060000_entry_detail_indexes.sql',
        'tests/fixtures/lookup-smoke.json', 'tests/fixtures/semantic-pilot-queries.json',
    ]]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(f'{digest}  {output.name}\n')
    print(f'{output}: {len(files)} files; SHA256 {digest}')


if __name__ == '__main__':
    main()

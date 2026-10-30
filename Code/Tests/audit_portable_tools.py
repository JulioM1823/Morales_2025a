'''
Purpose
-------
Audit the distributed HTML resources and exact saved Bokeh launch contexts.

Inputs
------
None
    Test cases use local fixtures, parameterized inputs, and the imported
    implementation modules.

Outputs
-------
Tests and audit helpers: callable
    Expose the regression cases or measured audit entrypoints defined here.
'''
# Import the test dependencies and implementation modules used by these checks.
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def audit(bundle, data):
    '''
    Purpose
    -------
    Check portable HTML resources and recorded launch contexts without scientific
    recomputation.

    Inputs
    ------
    bundle: pathlib.Path
        Portable tool bundle whose resources and launch contexts are audited.

    data: pathlib.Path
        External Data root exposed to the portable tools through MORALES_DATA_DIR
        while validating recorded source paths.

    Outputs
    -------
    report: dict
        Resource/context counts and detailed missing-resource/context-failure
        lists. Set portable-root environment variables and the module search path.
    '''

    # Resolve portable data paths in the same environment as the distributed tools.
    os.environ['MORALES_PORTABLE_ROOT'] = str(bundle)
    os.environ['MORALES_DATA_DIR'] = str(data)
    sys.path.insert(0, str(bundle/'Code/Time-Distance'))
    from observation_datasets import dataset_from_fits
    from data_locations import current_source_path
    from package_komega_tools import walk_records
    missing, failures, seen = [], [], set()
    checked, contexts = 0, 0
    # Check local resource URLs, including references embedded in serialized targets.
    for page in bundle.rglob('*.html'):
        text = page.read_text(encoding='utf-8')
        links = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', text)
        for pattern in (r'const overview = (.*);', r'const targets = (.*);'):
            match = re.search(pattern, text)
            if match:
                try:
                    value = json.loads(match[1])
                except ValueError:
                    continue
                links.extend(item['src'] for item in walk_records(value) if isinstance(item.get('src'), str))
        for label in links:
            url = urlsplit(label)
            if url.scheme or url.netloc or label.startswith(('#', '/')) or not url.path or '{' in label:
                continue
            target = (page.parent/unquote(url.path)).resolve()
            checked += 1
            if not target.is_file():
                missing.append(dict(page=page.relative_to(bundle).as_posix(), target=str(target)))
    # Validate each unique saved launch context and its recorded source files.
    for path in (bundle/'Figures').rglob('*.html'):
        match = re.search(r'const targets = (.*);', path.read_text(encoding='utf-8'))
        if not match:
            continue
        for item in walk_records(json.loads(match[1])):
            if not isinstance(item.get('dataset'), dict) or item.get('schema_version') not in {1, 2}:
                continue
            key = json.dumps(item, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            contexts += 1
            try:
                dataset = item['dataset']
                observation = dataset_from_fits(dataset['file'], dataset['source_type'], bundle)
                if observation.id != dataset['id']:
                    raise ValueError('Relocated dataset ID differs from the saved ID.')
                if not observation.files[0].is_file() and not item.get('processing'):
                    raise ValueError('No numerical product or recorded input reference.')
                reference = item.get('processing', {}).get('input_reference', {})
                for field in ('file', 'v1', 'v2'):
                    label = reference.get('data', {}).get(field)
                    if label and not current_source_path(label).is_file():
                        raise ValueError('Recorded original input is missing: '+label)
            except Exception as exc:
                failures.append(dict(file=path.relative_to(bundle).as_posix(), dataset=item['dataset'], error=str(exc)))
            if contexts % 250 == 0:
                print(f'Validated {contexts} contexts; {len(failures)} failures', flush=True)
    return dict(validation='HTML resources, unchanged dataset IDs and presence of recorded input files; no scientific recomputation',
                local_resource_references=checked, missing_resources=missing,
                launch_contexts=contexts, context_failures=failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.bundle.resolve(), args.data.resolve())
    args.report.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in result.items()}, indent=2))
    sys.exit(bool(result['missing_resources'] or result['context_failures']))

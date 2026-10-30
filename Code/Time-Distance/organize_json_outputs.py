'''
Purpose
-------
Relocate managed JSON companions into json_files directories while verifying bytes and
link targets.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for organize_json_outputs.py.

Notes
-----
Relocate managed output JSON companions without changing their contents.

Legacy scientific trees and source configuration registries are intentionally
untouched. Relative links are rebuilt against relocated targets.
'''
# Import the libraries and shared helpers used by this module
from pathlib import Path
import os
import hashlib


def organize(root):
    '''
    Purpose
    -------
    Move JSON companions into json_files subdirectories and rebuild their relative
    links.

    Inputs
    ------
    root: str or pathlib.Path
        Root directory for the paths managed by this helper.

    Outputs
    -------
    count: int
        Number of moved entries. Destination conflicts raise FileExistsError; post-move
        assertions verify file hashes and link targets.
    '''

    # Move JSON companions into json_files subdirectories and rebuild their relative
    # links
    root = Path(root).absolute()
    moves = {p: p.parent/'json_files'/p.name for p in root.rglob('*.json')
             if p.parent.name != 'json_files'}
    links = {p: p.resolve() for p in moves if p.is_symlink()}
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in moves if not p.is_symlink()}
    for old, new in moves.items():
        if new.exists() or new.is_symlink():
            raise FileExistsError(f'Relocation destination already exists: {new}')
        new.parent.mkdir(parents=True, exist_ok=True)
    for old, new in moves.items():
        if old not in links:
            old.rename(new)
    for old, target in links.items():
        new = moves[old]
        target = moves.get(target, target)
        new.symlink_to(os.path.relpath(target, new.parent))
        old.unlink()
    for old, digest in hashes.items():
        assert hashlib.sha256(moves[old].read_bytes()).hexdigest() == digest
    for old, target in links.items():
        assert moves[old].exists()
        assert moves[old].resolve() == moves.get(target, target).resolve()
    return len(moves)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    args = parser.parse_args()
    for root in args.roots:
        print(f'{root}: {organize(root)} JSON files relocated and verified')

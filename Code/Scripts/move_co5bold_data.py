'''
Purpose
-------
Plan and verify a same-filesystem CO5BOLD data relocation without copying cubes.

Inputs
------
None

Outputs
-------
Command-line program
    Write an inventory manifest, or apply its exact atomic directory rename
    and create a forwarding symlink at the historical source path.

Notes
-----
Content hashing is optional only in the explicit metadata-only mode.
The apply operation verifies file identity before and after the rename.
'''
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# Resolve project-relative defaults without moving or reading data at import
PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path.home()/'Research/Projects/Morales_2025a/Data/co5bold'
DEFAULT_DESTINATION = PROJECT/'Data/co5bold'
DEFAULT_MANIFEST = PROJECT/'Data/json_files/co5bold_relocation.json'


def checksum(path):
    '''
    Purpose
    -------
    Calculate a file SHA-256 digest using bounded-size reads.

    Inputs
    ------
    path: str or Path
        File whose bytes are hashed in 8 MiB chunks.

    Outputs
    -------
    digest: str
        Hexadecimal SHA-256 checksum; file read errors propagate.
    '''

    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path, record):
    '''
    Purpose
    -------
    Atomically replace a JSON relocation manifest after flushing its temporary file.

    Inputs
    ------
    path: str or Path
        Manifest destination; its parent directory is created if absent.

    record: dict
        JSON-serializable relocation state and file inventory.

    Outputs
    -------
    None
        Write indented JSON, flush and fsync, then replace the destination.
    '''

    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        json.dump(record,stream,indent=2,sort_keys=True);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def inventory(source, workers=1):
    '''
    Purpose
    -------
    Hash every regular source file and verify it stayed unchanged during reading.

    Inputs
    ------
    source: Path
        Source directory to enumerate recursively; symlinks are rejected.

    workers: int, optional
        Maximum checksum threads, clamped to at least one.

    Outputs
    -------
    rows: list of dict
        Sorted relative paths, byte sizes, nanosecond mtimes, inodes, and SHA-256
        hashes. Changed files or unexpected symlinks raise ValueError.
    '''

    # Reject symlinks and gather only regular files for the planned inventory
    paths=[]
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Unexpected source symlink; inspect before moving: {path}')
        if not path.is_file():continue
        paths.append(path)
    def inspect(path):
        '''
        Purpose
        -------
        Hash one inventoried file and compare its identity before and after the read.

        Inputs
        ------
        path: Path
            File beneath the enclosing source directory.

        Outputs
        -------
        row: dict
            Relative path, byte size, mtime, inode, and digest. Raise ValueError if
            size, mtime, or inode changed; print progress after a successful read.
        '''

        before=path.stat()
        digest=checksum(path)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
            raise ValueError(f'Source changed while hashing: {path}')
        row=dict(relative_path=path.relative_to(source).as_posix(),size_bytes=before.st_size,
            mtime_ns=before.st_mtime_ns,inode=before.st_ino,sha256=digest)
        print(f'Hashed {path.relative_to(source)}',flush=True)
        return row
    # Hash files concurrently and sort completed records by relative path
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures=[pool.submit(inspect,path) for path in paths]
        rows=[future.result() for future in as_completed(futures)]
    return sorted(rows,key=lambda row:row['relative_path'])


def plan(source,destination,manifest,workers=1,metadata_only=False):
    '''
    Purpose
    -------
    Validate a same-filesystem source/destination pair and persist a relocation plan.

    Inputs
    ------
    source, destination: str or Path
        Original directory and absent destination on the same filesystem.

    manifest: str or Path
        Path receiving the planned relocation record.

    workers: int, optional
        Parallel file checksum readers when content hashing is enabled.

    metadata_only: bool, optional
        Record identity metadata without reading cloud file contents when True.

    Outputs
    -------
    record: dict
        Planned paths, timestamps, inventory, byte totals, and verification mode.
        Invalid source, existing destination, or differing filesystems abort planning.
    '''

    source=Path(os.path.abspath(Path(source).expanduser()));destination=Path(os.path.abspath(Path(destination).expanduser()))
    if source.is_symlink() or not source.is_dir():raise ValueError('Source must be the original directory.')
    if destination.exists() or destination.is_symlink():raise FileExistsError(destination)
    if source.stat().st_dev!=destination.parent.stat().st_dev:
        raise ValueError('Atomic move requires the same filesystem; no implicit large copy is allowed.')
    # Preserve cloud placeholders by using identity metadata only when requested
    if metadata_only:
        rows=[]
        for path in sorted(source.rglob('*')):
            if path.is_symlink():raise ValueError(f'Unexpected source symlink: {path}')
            if not path.is_file():continue
            stat=path.stat()
            rows.append(dict(relative_path=path.relative_to(source).as_posix(),size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,inode=stat.st_ino,sha256=None))
    else:
        rows=inventory(source,workers=workers)
    # Persist the complete plan before any directory rename is permitted
    record=dict(schema_version=1,status='planned',source=str(source),destination=str(destination),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),files=rows,
        file_count=len(rows),total_bytes=sum(row['size_bytes'] for row in rows),
        method='atomic directory rename; original file inodes and bytes retained',compatibility_link=True,
        verification='inode, size and mtime; content checksums not read' if metadata_only else 'inode, size, mtime and SHA-256')
    write_manifest(manifest,record)
    return record


def apply(manifest):
    '''
    Purpose
    -------
    Apply a saved relocation inventory and verify the moved directory contents.

    Inputs
    ------
    manifest: str or Path
        Manifest with planned source, destination, and file identity records.

    Outputs
    -------
    record: dict
        Verified relocation record. Rename the directory, create the compatibility
        symlink, and persist intermediate/final status. An incomplete migration
        or changed inventory raises before further work where detected.
    '''

    record=json.loads(Path(manifest).read_text())
    source,destination=map(Path,(record['source'],record['destination']))
    if record['status']=='verified' and source.is_symlink() and source.resolve()==destination:
        return record
    if record['status']!='planned':raise ValueError('Inspect the incomplete migration before retrying.')
    if destination.exists() or destination.is_symlink():raise FileExistsError(destination)
    # Verify the exact relative-path inventory and file identity before the move
    actual={path.relative_to(source).as_posix() for path in source.rglob('*') if path.is_file()}
    if actual!={row['relative_path'] for row in record['files']}:raise ValueError('Source inventory changed.')
    for row in record['files']:
        stat=(source/row['relative_path']).stat()
        if (stat.st_size,stat.st_mtime_ns,stat.st_ino)!=(row['size_bytes'],row['mtime_ns'],row['inode']):
            raise ValueError(f'Source changed after planning: {row["relative_path"]}')
    # No copy fallback: insufficient free space must never create a partial copy.
    source.rename(destination)
    source.symlink_to(destination,target_is_directory=True)
    # Record the completed rename before verifying every destination file
    record['status']='moved_pending_verification';write_manifest(manifest,record)
    for row in record['files']:
        path=destination/row['relative_path'];stat=path.stat()
        if (stat.st_size,stat.st_mtime_ns,stat.st_ino)!=(row['size_bytes'],row['mtime_ns'],row['inode']):
            raise ValueError(f'Moved file identity differs: {path}')
        if row.get('sha256') is not None and checksum(path)!=row['sha256']:raise ValueError(f'Moved checksum differs: {path}')
        if path.suffix=='.nc':print(f'Verified {row["relative_path"]}',flush=True)
    record['status']='verified';record['verified_utc']=datetime.now(timezone.utc).isoformat()
    write_manifest(manifest,record)
    return record


# Select planning or application from the explicit command-line flags
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--destination',type=Path,default=DEFAULT_DESTINATION)
    parser.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--workers',type=int,default=1,help='Parallel source checksum reads; no extra data copies.')
    parser.add_argument('--metadata-only',action='store_true',help='Same-filesystem rename verified by unchanged file inodes, sizes and mtimes; do not read cloud content.')
    args=parser.parse_args()
    result=apply(args.manifest) if args.apply else plan(args.source,args.destination,args.manifest,workers=args.workers,metadata_only=args.metadata_only)
    print(json.dumps({k:result[k] for k in ('status','source','destination','file_count','total_bytes')},indent=2))

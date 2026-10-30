'''
Purpose
-------
Expose advisory file locking through a common flock interface on POSIX and Windows.

Inputs
------
None

Outputs
-------
Public helpers and constants
    Definitions for file_lock.py.

Notes
-----
Advisory file locking on POSIX and Windows, with the same flock interface.
'''
# Import the libraries and shared helpers used by this module
import os

if os.name != 'nt':
    from fcntl import flock, LOCK_EX, LOCK_UN
else:
    import msvcrt
    import time
    LOCK_EX, LOCK_UN = 2, 8

    def flock(handle, operation):
        '''
        Purpose
        -------
        Lock or unlock the first file byte using the Windows advisory-lock interface.

        Inputs
        ------
        handle: file object
            Open seekable lock-file handle with a file descriptor; empty files are
            initialized with one space.
        operation: int
            LOCK_UN releases the first-byte lock; other operations acquire it with
            contention retries.

        Outputs
        -------
        None
            Preserves the file position, ensures a lockable byte exists, retries
            expected lock-contention errors, and propagates other OSErrors. POSIX
            imports native fcntl.flock instead.
        '''

        # Lock or unlock the first file byte using the Windows advisory-lock interface
        position = handle.tell()
        try:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(' ')
                handle.flush()
            handle.seek(0)
            if operation == LOCK_UN:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if exc.errno not in {13, 36}:
                            raise
                        time.sleep(.05)
        finally:
            handle.seek(position)

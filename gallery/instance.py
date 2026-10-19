"""An application owns one data directory for its full lifetime."""

import os


class Instance:
    def __init__(self, path):
        self.path = path
        self.file = None

    def acquire(self):
        self.file = self.path.open('a+b')
        self.file.seek(0)
        if self.path.stat().st_size == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise OSError('Another backend owns this data directory') from exc

    def release(self):
        if self.file:
            self.file.close()
            self.file = None

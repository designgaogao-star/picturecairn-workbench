"""Code, bundled resources, user data and library roots have separate ownership."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
RES_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR))


@dataclass(frozen=True)
class Settings:
    data: Path
    resources: Path = RES_DIR
    application: Path = APP_DIR
    root: Path | None = None
    legacy: Path | None = None
    cache_limit: int = 12 * 1024**3
    watch: bool = True
    scan_on_start: bool = True
    desktop_token: str | None = None

    @classmethod
    def environment(cls):
        default = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'GalleryTool'
        return cls(data=Path(os.environ.get('GALLERY_DATA') or default),
                   application=Path(os.environ.get('GALLERY_APPLICATION') or APP_DIR),
                   root=Path(os.environ['GALLERY_ROOT']) if os.environ.get('GALLERY_ROOT') else None,
                   legacy=Path(os.environ['GALLERY_LEGACY']) if os.environ.get('GALLERY_LEGACY') else None,
                   desktop_token=os.environ.get('GALLERY_DESKTOP_TOKEN'))

"""One path boundary for all reads and destructive operations."""

from pathlib import Path


class Access:
    def __init__(self, catalog):
        self.catalog = catalog

    def path(self, entity, allow_root=False):
        library = self.catalog.entity('libraries', entity['library_id'])
        root = Path(library['path']).resolve(strict=True)
        relative = Path(entity['rel'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Path is outside its library')
        target = root.joinpath(relative).resolve(strict=True)
        if not target.is_relative_to(root) or (target == root and not allow_root):
            raise ValueError('Path is outside its library')
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or current.is_junction():
                raise ValueError('Linked paths are not supported')
        return target

    def image(self, image_id):
        image = self.catalog.entity('files', image_id)
        if not image or not image['present'] or not image['is_image']:
            raise FileNotFoundError('Image not found')
        return image, self.path(image)

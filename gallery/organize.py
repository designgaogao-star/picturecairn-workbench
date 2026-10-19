"""Review, deterministic sampling and audited deletion share the catalog and path boundary."""

import json
import random
import shutil
import time

from gallery.catalog import new_id
from gallery.indexer import Indexer
from gallery.jobs import Cancelled
from gallery.recycle import recycle


class Organize:
    def __init__(self, catalog, access, events, data):
        self.catalog, self.access, self.events, self.data = catalog, access, events, data

    def samples(self, group_id, count=20, seed=0):
        rows = self.catalog.rows('SELECT id FROM files WHERE group_id=? AND present=1 AND is_image=1 '
                                  'ORDER BY sort_key,id', (group_id,))
        chosen = random.Random(seed).sample(rows, min(count, len(rows)))
        return [self.catalog.entity('files', row['id']) for row in chosen]

    def delete(self, context, payload):
        if payload.get('permanent') and payload.get('confirm_permanent') is not True:
            raise ValueError('Permanent deletion requires confirm_permanent: true')
        mode = 'permanent' if payload.get('permanent') else 'recycle'
        results = []
        for i, target in enumerate(payload['targets']):
            context.check()
            entity_id, kind = target['id'], target['kind']
            table = {'image': 'files', 'package': 'packages', 'group': 'directories'}[kind]
            entity = self.catalog.entity(table, entity_id)
            if not entity:
                raise FileNotFoundError('Target not found')
            if kind == 'image' and not entity['is_image']:
                raise ValueError('Target is not an image')
            if kind == 'package':
                if entity['loose']:
                    raise ValueError('Loose images are not a deletable package')
                entity = self.catalog.entity('directories', entity['directory_id'])
            if kind == 'group' and (entity['id'] != entity['group_id'] or not entity['rel']):
                raise ValueError('Target is not a top-level group')
            path = self.access.path(entity)
            operation_id, now = new_id(), time.time()
            self.catalog.execute('INSERT INTO operations(id,target_id,target_kind,path,mode,state,created,updated,task_id) '
                                 'VALUES(?,?,?,?,?,?,?,?,?)',
                                 (operation_id, entity_id, kind, str(path), mode, 'pending', now, now, context.id))
            state, error = 'completed', None
            try:
                with context.io(path):
                    if mode == 'recycle':
                        recycle(path)
                    elif path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                with self.catalog.write() as db:
                    if kind == 'image':
                        db.execute('UPDATE files SET present=0 WHERE id=?', (entity_id,))
                    else:
                        Indexer.mark_missing(db, entity['id'])
                    self.catalog.refresh_group(db, entity['group_id'])
            except OSError as exc:
                state, error = 'failed', str(exc)
            except Cancelled:
                state, error = 'cancelled', 'Cancelled before operation'
            self.catalog.execute('UPDATE operations SET state=?,error=?,updated=? WHERE id=?',
                                 (state, error, time.time(), operation_id))
            record = {'id': operation_id, 'target_id': entity_id, 'kind': kind, 'path': str(path),
                      'mode': mode, 'state': state, 'error': error, 'time': now, 'task_id': context.id}
            with (self.data / 'delete_journal.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(record, ensure_ascii=False) + '\n')
            self.catalog.bump(entity['library_id'])
            self.events.publish('catalog', {'library_id': entity['library_id']})
            results.append(record)
            context.update(i + 1, len(payload['targets']), path.name)
        return {'items': results, 'failed': sum(r['state'] != 'completed' for r in results)}

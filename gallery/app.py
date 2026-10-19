"""Versioned HTTP boundary. Business operations belong to the application services."""

import asyncio
import contextlib
import hashlib
import json
import os
import time
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.sse import EventSourceResponse, format_sse_event
from fastapi.staticfiles import StaticFiles

from gallery import schemas as s
from gallery.catalog import new_id
from gallery.jobs import Busy
from gallery.paths import Settings
from gallery.service import Service

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]


def create_app(settings: Settings | None = None):
    settings = settings or Settings.environment()
    service = Service(settings)
    catalog = service.catalog
    instance_id = new_id()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        service.start()
        try:
            yield
        finally:
            await asyncio.to_thread(service.stop)

    app = FastAPI(title='GalleryTool API', version='2.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.service = service
    app.state.instance_id = instance_id
    app.state.settings = settings

    @app.get('/favicon.ico', include_in_schema=False)
    async def favicon():
        return Response(status_code=204)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = urlsplit('//' + request.headers.get('host', '')).hostname
        if host not in ('127.0.0.1', 'localhost', 'testserver'):
            return JSONResponse({'error': 'Local host required'}, status_code=403)
        origin = request.headers.get('origin')
        allowed_origin = os.environ.get('GALLERY_FRONTEND_ORIGIN')
        if origin and origin not in (f'{request.url.scheme}://{request.url.netloc}', allowed_origin):
            return JSONResponse({'error': 'Origin is not allowed'}, status_code=403)
        if request.method == 'OPTIONS' and origin == allowed_origin:
            response = Response(status_code=204)
        else:
            response = await call_next(request)
        if origin and origin == allowed_origin:
            response.headers.update({'Access-Control-Allow-Origin': origin,
                                     'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
                                     'Access-Control-Allow-Headers': 'Content-Type', 'Vary': 'Origin'})
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(Busy)
    async def busy(_request, exc):
        return JSONResponse({'error': str(exc)}, status_code=503, headers={'Retry-After': '1'})

    @app.exception_handler(FileNotFoundError)
    async def missing(_request, exc):
        return JSONResponse({'error': str(exc)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({'error': str(exc)}, status_code=409)

    @app.exception_handler(OSError)
    async def io_error(_request, exc):
        return JSONResponse({'error': str(exc)}, status_code=422)

    def entity(table, entity_id):
        row = catalog.entity(table, entity_id)
        if not row:
            raise HTTPException(404, 'Resource not found')
        return row

    @app.get('/api/v1/health', response_model=s.Health, tags=['System'])
    async def health():
        return s.Health(instance_id=instance_id)

    @app.get('/api/v1/libraries', response_model=s.Page[s.Library], tags=['Libraries'])
    def libraries(offset: Offset = 0, limit: Limit = 100):
        return catalog.page('SELECT * FROM libraries', '', [], 'name COLLATE NOCASE,id', offset, limit, '')

    @app.post('/api/v1/libraries', response_model=s.Library, status_code=201, tags=['Libraries'])
    def add_library(body: s.LibraryCreate):
        library = catalog.add_library(body.path, body.name)
        service.watcher.add(library)
        service.tasks.submit('scan', {'library_id': library['id']})
        return library

    @app.get('/api/v1/libraries/{library_id}/groups', response_model=s.Page[s.Group], tags=['Browse'])
    def groups(library_id: str, offset: Offset = 0, limit: Limit = 100,
               state: s.Mark | None = None, category: Literal['R16', 'R18', '非R18', '其他'] | None = None):
        entity('libraries', library_id)
        return catalog.groups(library_id, offset, limit, state, category)

    @app.get('/api/v1/libraries/{library_id}/directories', response_model=s.Page[s.Directory], tags=['Browse'])
    def directories(library_id: str, parent_id: str | None = None, offset: Offset = 0, limit: Limit = 100):
        entity('libraries', library_id)
        where = 'WHERE library_id=? AND present=1 AND parent_id IS NULL'
        args = [library_id]
        if parent_id:
            where = 'WHERE library_id=? AND present=1 AND parent_id=?'
            args.append(parent_id)
        return catalog.page('SELECT * FROM directories', where, args, 'sort_key,id', offset, limit, library_id)

    @app.get('/api/v1/groups/{group_id}/packages', response_model=s.Page[s.Package], tags=['Browse'])
    def packages(group_id: str, offset: Offset = 0, limit: Limit = 100):
        entity('directories', group_id)
        return catalog.packages(group_id, offset, limit)

    @app.get('/api/v1/packages/{package_id}/images', response_model=s.Page[s.ImageItem], tags=['Browse'])
    def images(package_id: str, offset: Offset = 0, limit: Limit = 100):
        entity('packages', package_id)
        return catalog.images(package_id, offset, limit)

    @app.get('/api/v1/images/{image_id}/context', response_model=s.ImageContext, tags=['Browse'])
    def image_context(image_id: str):
        result = catalog.image_context(image_id)
        if not result:
            raise HTTPException(404, 'Image not found')
        return result

    @app.get('/api/v1/images/{image_id}/thumbnail', tags=['Images'], response_class=FileResponse,
             responses={200: {'content': {'image/webp': {}, 'image/jpeg': {}}}, 304: {'description': 'Not modified'}})
    def thumbnail(request: Request, image_id: str, edge: s.Edge = s.Edge.small):
        path = service.images.get(image_id, edge)
        tag = '"' + path.stem + '"'
        headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate'}
        if request.headers.get('if-none-match') == tag:
            return Response(status_code=304, headers=headers)
        return FileResponse(path, media_type='image/webp' if path.suffix == '.webp' else 'image/jpeg', headers=headers)

    @app.get('/api/v1/images/{image_id}/original', tags=['Images'], response_class=FileResponse)
    def original(request: Request, image_id: str):
        _image, path = service.access.image(image_id)
        stat = path.stat()
        tag = '"' + hashlib.sha256(f'{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest() + '"'
        headers = {'ETag': tag, 'Cache-Control': 'private, max-age=0, must-revalidate'}
        if request.headers.get('if-none-match') == tag:
            return Response(status_code=304, headers=headers)
        return FileResponse(path, content_disposition_type='inline', headers=headers)

    @app.get('/api/v1/groups/{group_id}/review', response_model=s.Review, tags=['Organize'])
    def review(group_id: str):
        entity('directories', group_id)
        return catalog.one('SELECT * FROM review WHERE group_id=?', (group_id,)) or {
            'group_id': group_id, 'state': 'none', 'image_id': None, 'updated': 0}

    @app.patch('/api/v1/groups/{group_id}/review', response_model=s.Review, tags=['Organize'])
    def mark(group_id: str, body: s.ReviewChange):
        entity('directories', group_id)
        result = catalog.save_review(group_id, state=body.state)
        service.events.publish('review', {'group_id': group_id})
        return result

    @app.put('/api/v1/groups/{group_id}/position', response_model=s.Review, tags=['Organize'])
    def position(group_id: str, body: s.PositionChange):
        entity('directories', group_id)
        image = entity('files', body.image_id)
        if image['group_id'] != group_id or not image['is_image'] or not image['present']:
            raise HTTPException(409, 'Image is not in this group')
        return catalog.save_review(group_id, image_id=body.image_id)

    @app.get('/api/v1/groups/{group_id}/samples', response_model=list[s.ImageItem], tags=['Organize'])
    def samples(group_id: str, count: Annotated[int, Query(ge=1, le=100)] = 20, seed: int = 0):
        entity('directories', group_id)
        return service.organize.samples(group_id, count, seed)

    @app.post('/api/v1/tasks', response_model=s.Task, status_code=202, tags=['Tasks'])
    def create_task(body: s.Job):
        payload = body.model_dump(exclude_none=True)
        kind = payload.pop('kind')
        for key, table in (('library_id', 'libraries'), ('directory_id', 'directories'),
                           ('group_id', 'directories'), ('package_id', 'packages'),
                           ('left_id', 'packages'), ('right_id', 'packages')):
            if key in payload:
                entity(table, payload[key])
        return service.tasks.submit(kind, payload)

    @app.get('/api/v1/tasks', response_model=s.Page[s.Task], tags=['Tasks'])
    def tasks(offset: Offset = 0, limit: Limit = 100):
        rows = catalog.rows('SELECT id FROM tasks ORDER BY created DESC LIMIT ? OFFSET ?', (limit, offset))
        return {'items': [catalog.task(row['id']) for row in rows], 'total': catalog.one('SELECT COUNT(*) n FROM tasks')['n'],
                'offset': offset, 'limit': limit, 'revision': 0}

    @app.get('/api/v1/tasks/{task_id}', response_model=s.Task, tags=['Tasks'])
    def task(task_id: str):
        result = catalog.task(task_id)
        if not result:
            raise HTTPException(404, 'Task not found')
        return result

    @app.post('/api/v1/tasks/{task_id}/control', response_model=s.Task, tags=['Tasks'])
    def control_task(task_id: str, body: s.TaskControl):
        task(task_id)
        return service.tasks.control(task_id, body.action)

    @app.get('/api/v1/tasks/{task_id}/pairs', response_model=s.Page[s.Pair], tags=['Organize'])
    def pairs(task_id: str, offset: Offset = 0, limit: Limit = 100):
        task(task_id)
        return catalog.page('SELECT left_id,right_id,distance FROM similar_pairs', 'WHERE task_id=?', [task_id],
                             'distance,left_id,right_id', offset, limit, '')

    @app.get('/api/v1/tasks/{task_id}/findings',
             response_model=s.Page[s.ComparedFile | s.ShellPackage | s.AuditPackage | s.IncompletePackage], tags=['Organize'])
    def findings(task_id: str, kind: Literal['left_unique', 'right_unique', 'shell', 'advertisement', 'incomplete'],
                 offset: Offset = 0, limit: Limit = 100):
        task(task_id)
        result = catalog.page('SELECT payload FROM findings', 'WHERE task_id=? AND kind=?',
                               [task_id, kind], 'ordinal', offset, limit, '')
        result['items'] = [json.loads(row['payload']) for row in result['items']]
        return result

    @app.post('/api/v1/operations/delete', response_model=s.Task, status_code=202, tags=['Organize'])
    def delete(body: s.DeleteRequest):
        for target in body.targets:
            entity({'image': 'files', 'package': 'packages', 'group': 'directories'}[target.kind], target.id)
        return service.tasks.submit('delete', body.model_dump(), deduplicate=False)

    @app.get('/api/v1/operations', response_model=s.Page[s.Operation], tags=['Organize'])
    def operations(offset: Offset = 0, limit: Limit = 100, task_id: str | None = None):
        return catalog.page('SELECT * FROM operations', 'WHERE task_id=?' if task_id else '',
                             [task_id] if task_id else [], 'created DESC,id', offset, limit, '')

    @app.get('/api/v1/cache', tags=['System'])
    def cache_stats() -> dict[str, int]:
        return {**catalog.one('SELECT COUNT(*) count,COALESCE(SUM(size),0) bytes FROM cache_entries'),
                'limit': settings.cache_limit}

    @app.get('/api/v1/events', response_class=Response, tags=['Tasks'],
             responses={200: {'content': {'text/event-stream': {}}}})
    async def events(last_event_id: Annotated[int, Header(ge=0)] = 0):
        async def stream():
            sequence = last_event_id
            yield format_sse_event(event='snapshot', data_str=json.dumps({'instance_id': instance_id}))
            last_message = time.monotonic()
            while not service.stop_event.is_set():
                for event in service.events.since(sequence):
                    sequence = event['id']
                    yield format_sse_event(event=event['event'], id=str(sequence), data_str=json.dumps(event['data']))
                    last_message = time.monotonic()
                if time.monotonic() - last_message >= 15:
                    yield format_sse_event(comment='ping')
                    last_message = time.monotonic()
                await asyncio.sleep(.2)
        # Keep disconnect cancellation inside the response rather than FastAPI's producer task group.
        return EventSourceResponse(stream(), headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.post('/api/v1/system/shutdown', status_code=202, include_in_schema=False)
    async def shutdown(request: Request):
        if not settings.desktop_token or request.headers.get('x-gallery-desktop') != settings.desktop_token:
            raise HTTPException(403, 'Desktop session required')
        service.shutdown_callback()
        return {'stopping': True}

    prototype = settings.resources / 'prototype'
    if prototype.is_dir():
        app.mount('/', StaticFiles(directory=prototype, html=True), name='prototype')
    return app

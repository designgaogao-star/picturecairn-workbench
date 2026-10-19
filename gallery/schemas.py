"""Public API models, exported verbatim to OpenAPI and the TypeScript client."""

from enum import IntEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar('T')
Mark = Literal['none', 'kept', 'marked']


class Edge(IntEnum):
    small = 400
    medium = 800
    preview = 1600
    large = 2560
    full = 4200


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int
    revision: int


class Health(BaseModel):
    status: Literal['ready'] = 'ready'
    api_version: Literal['1'] = '1'
    version: str = '2.0.0'
    instance_id: str


class Library(BaseModel):
    id: str
    name: str
    path: str
    online: bool
    revision: int
    scan_status: str
    last_scan: float | None
    error: str | None


class LibraryCreate(Input):
    path: str = Field(min_length=1)
    name: str | None = None


class Group(BaseModel):
    id: str
    library_id: str
    rel: str
    name: str
    category: str
    state: Mark
    image_count: int
    bytes: int
    resume_image_id: str | None


class Directory(BaseModel):
    id: str
    library_id: str
    parent_id: str | None
    group_id: str
    rel: str
    name: str
    present: bool
    error: str | None


class Package(BaseModel):
    id: str
    library_id: str
    group_id: str
    directory_id: str
    name: str
    rel: str
    loose: bool
    image_count: int
    cover_id: str | None


class ImageItem(BaseModel):
    id: str
    library_id: str
    group_id: str
    package_id: str
    rel: str
    name: str
    size: int
    mtime_ns: int
    width: int | None
    height: int | None
    animated: bool | None
    error: str | None


class ImageContext(BaseModel):
    image: ImageItem
    previous_id: str | None
    next_id: str | None
    index: int
    revision: int


class ReviewChange(Input):
    state: Mark


class PositionChange(Input):
    image_id: str


class Review(BaseModel):
    group_id: str
    state: Mark
    image_id: str | None
    updated: float


class Result(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ScanResult(Result):
    online: bool
    directories: int = 0
    files: int = 0
    failed_directories: int = 0


class BuildResult(Result):
    indexed: int
    failed: int
    hash_version: str


class PackageSimilarity(BaseModel):
    left_id: str
    right_id: str
    left_match_rate: float
    right_match_rate: float
    left_coverage: float
    right_coverage: float
    evidence: Literal['similarity']
    exact_verified: Literal[False]


class AnalyzeResult(BuildResult):
    images: int
    coverage: float
    pairs: int
    package_pairs: list[PackageSimilarity]
    package_pairs_total: int
    pair_task_id: str


class ComparedFile(BaseModel):
    id: str
    name: str
    is_image: bool
    size: int
    sha256: str


class CompareResult(Result):
    left_id: str
    right_id: str
    left_files: int
    right_files: int
    left_unique: list[ComparedFile]
    right_unique: list[ComparedFile]
    left_unique_total: int
    right_unique_total: int
    exact_equal: bool
    left_contained: bool
    right_contained: bool
    algorithm: Literal['sha256-all-files']
    revision: int


class PrewarmResult(Result):
    generated_or_cached: int
    failed: int


class CacheResult(Result):
    bytes: int
    removed: int
    limit: int


class MigrationResult(Result):
    library_id: str
    images: int
    legacy_hash_rows: int
    snapshot: str
    legacy_thumbs: str


class DeleteItem(BaseModel):
    task_id: str
    id: str
    target_id: str
    kind: str
    path: str
    mode: str
    state: str
    error: str | None
    time: float


class DeleteResult(Result):
    items: list[DeleteItem]
    failed: int


class AuditImage(BaseModel):
    id: str
    verified: bool


class AuditPackage(BaseModel):
    package_id: str
    images: list[AuditImage]


class ShellPackage(AuditPackage):
    bytes: int
    verified: bool


class IncompletePackage(BaseModel):
    package_id: str
    bytes: int
    images: int
    declared_bytes: int
    declared_images: int


class AuditResult(Result):
    shells: list[ShellPackage]
    advertisements: list[AuditPackage]
    incomplete: list[IncompletePackage]
    shells_total: int
    advertisements_total: int
    incomplete_total: int
    evidence: Literal['heuristic-only']


class Task(BaseModel):
    id: str
    kind: str
    state: Literal['queued', 'running', 'paused', 'cancelling', 'cancelled', 'completed', 'failed', 'interrupted']
    payload: dict[str, Any]
    progress: int
    total: int | None
    current: str
    result: ScanResult | BuildResult | AnalyzeResult | CompareResult | PrewarmResult | CacheResult | MigrationResult | DeleteResult | AuditResult | None = None
    error: str | None
    created: float
    updated: float


class ScanJob(Input):
    kind: Literal['scan']
    library_id: str
    directory_id: str | None = None
    force: bool = True


class HashJob(Input):
    kind: Literal['build', 'analyze', 'audit']
    group_id: str
    threshold: int = Field(default=8, ge=0, le=16)


class PrewarmJob(Input):
    kind: Literal['prewarm']
    group_id: str | None = None
    package_id: str | None = None
    edge: Literal[400, 800, 1600, 2560, 4200] = 400

    @model_validator(mode='after')
    def one_scope(self):
        if bool(self.group_id) == bool(self.package_id):
            raise ValueError('Provide exactly one group_id or package_id')
        return self


class CompareJob(Input):
    kind: Literal['compare']
    left_id: str
    right_id: str


class CollectJob(Input):
    kind: Literal['collect']


Job = Annotated[ScanJob | HashJob | PrewarmJob | CompareJob | CollectJob, Field(discriminator='kind')]


class TaskControl(Input):
    action: Literal['pause', 'resume', 'cancel']


class DeleteTarget(Input):
    kind: Literal['image', 'package', 'group']
    id: str


class DeleteRequest(Input):
    targets: list[DeleteTarget] = Field(min_length=1, max_length=500)
    permanent: bool = Field(default=False, strict=True)
    confirm_permanent: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def confirm(self):
        if self.permanent and self.confirm_permanent is not True:
            raise ValueError('Permanent deletion requires confirm_permanent: true')
        return self


class Pair(BaseModel):
    left_id: str
    right_id: str
    distance: int


class Operation(BaseModel):
    task_id: str | None
    id: str
    target_id: str
    target_kind: str
    path: str
    mode: str
    state: str
    error: str | None
    created: float
    updated: float

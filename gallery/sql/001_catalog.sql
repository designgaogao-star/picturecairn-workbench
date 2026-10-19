CREATE TABLE libraries(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, path_key TEXT NOT NULL UNIQUE,
 online INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0,
 scan_status TEXT NOT NULL DEFAULT 'pending', last_scan REAL, error TEXT);
CREATE TABLE directories(
 id TEXT PRIMARY KEY, library_id TEXT NOT NULL REFERENCES libraries(id),
 parent_id TEXT REFERENCES directories(id), group_id TEXT, rel TEXT NOT NULL, path_key TEXT NOT NULL,
 name TEXT NOT NULL, sort_key TEXT NOT NULL, identity TEXT, present INTEGER NOT NULL DEFAULT 1,
 error TEXT, UNIQUE(library_id,path_key));
CREATE INDEX directory_parent ON directories(parent_id,sort_key);
CREATE INDEX directory_identity ON directories(library_id,identity);
CREATE TABLE packages(
 id TEXT PRIMARY KEY, library_id TEXT NOT NULL REFERENCES libraries(id),
 group_id TEXT NOT NULL REFERENCES directories(id), directory_id TEXT NOT NULL REFERENCES directories(id),
 name TEXT NOT NULL, sort_key TEXT NOT NULL, loose INTEGER NOT NULL DEFAULT 0,
 UNIQUE(group_id,directory_id));
CREATE INDEX package_group ON packages(group_id,sort_key);
CREATE TABLE files(
 id TEXT PRIMARY KEY, library_id TEXT NOT NULL REFERENCES libraries(id),
 directory_id TEXT NOT NULL REFERENCES directories(id), group_id TEXT NOT NULL REFERENCES directories(id),
 package_id TEXT NOT NULL REFERENCES packages(id), rel TEXT NOT NULL, path_key TEXT NOT NULL,
 name TEXT NOT NULL, sort_key TEXT NOT NULL, identity TEXT, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
 is_image INTEGER NOT NULL, present INTEGER NOT NULL DEFAULT 1,
 width INTEGER, height INTEGER, animated INTEGER, error TEXT,
 phash BLOB, hash_version TEXT, hash_mtime_ns INTEGER,
 UNIQUE(library_id,path_key));
CREATE INDEX file_directory ON files(directory_id,present);
CREATE INDEX file_group ON files(group_id,present,is_image,sort_key);
CREATE INDEX file_package ON files(package_id,present,is_image,sort_key);
CREATE INDEX file_identity ON files(library_id,identity);
CREATE TABLE review(
 group_id TEXT PRIMARY KEY REFERENCES directories(id), state TEXT NOT NULL DEFAULT 'none',
 image_id TEXT REFERENCES files(id), updated REAL NOT NULL);
CREATE TABLE tasks(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
 progress INTEGER NOT NULL DEFAULT 0, total INTEGER, current TEXT NOT NULL DEFAULT '',
 result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE operations(
 id TEXT PRIMARY KEY, target_id TEXT NOT NULL, target_kind TEXT NOT NULL, path TEXT NOT NULL,
 mode TEXT NOT NULL, state TEXT NOT NULL, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE cache_entries(
 key TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL, accessed REAL NOT NULL);
CREATE TABLE imports(source TEXT PRIMARY KEY, finished REAL NOT NULL, report TEXT NOT NULL);
CREATE TABLE similar_pairs(
 task_id TEXT NOT NULL REFERENCES tasks(id), left_id TEXT NOT NULL REFERENCES files(id),
 right_id TEXT NOT NULL REFERENCES files(id), distance INTEGER NOT NULL,
 PRIMARY KEY(task_id,left_id,right_id)) WITHOUT ROWID;
CREATE INDEX pair_task ON similar_pairs(task_id,distance,left_id,right_id);

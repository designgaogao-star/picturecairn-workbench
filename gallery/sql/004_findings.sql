CREATE TABLE findings(
 task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL, ordinal INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(task_id,kind,ordinal)) WITHOUT ROWID;

ALTER TABLE operations ADD COLUMN task_id TEXT REFERENCES tasks(id);
CREATE INDEX operation_task ON operations(task_id,created);

ALTER TABLE tasks ADD COLUMN trigger TEXT NOT NULL DEFAULT 'legacy';
CREATE INDEX task_kind_state_created ON tasks(kind,state,created DESC);

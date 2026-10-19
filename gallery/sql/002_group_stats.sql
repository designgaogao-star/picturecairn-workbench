ALTER TABLE directories ADD COLUMN image_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE directories ADD COLUMN bytes INTEGER NOT NULL DEFAULT 0;
UPDATE directories SET
 image_count=(SELECT COUNT(*) FROM files f WHERE f.group_id=directories.id AND f.present=1 AND f.is_image=1),
 bytes=(SELECT COALESCE(SUM(size),0) FROM files f WHERE f.group_id=directories.id AND f.present=1)
 WHERE id=group_id;

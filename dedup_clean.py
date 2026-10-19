# -*- coding: utf-8 -*-
"""清理 dedup 索引里指向已删除文件的孤儿行。

为什么需要：A 级整包删除走的是服务端 `/api/trash/pkg`，那套逻辑会清
media / files 缓存，但**不会动 dedup.db 的 phash 表**（那是另一条链路）。
结果就是索引里留着一堆已经不存在的路径 —— 体检报告、冗余率全都会失真。
"""

import os
import sqlite3
import time

from gallery.paths import DEDUP_DB as DB


def main():
    db = sqlite3.connect(DB, timeout=120)
    rows = db.execute("SELECT path, folder FROM phash").fetchall()
    print("索引行数：%d" % len(rows))
    t0 = time.time()
    dead = []
    for i, (p, _f) in enumerate(rows, 1):
        if not os.path.exists(p):
            dead.append(p)
        if i % 20000 == 0:
            print("  检查 %d/%d · 已发现孤儿 %d" % (i, len(rows), len(dead)))
    print("孤儿行：%d（%.1fs）" % (len(dead), time.time() - t0))
    if not dead:
        db.close()
        return
    for i in range(0, len(dead), 400):
        chunk = dead[i : i + 400]
        db.execute("DELETE FROM phash WHERE path IN (%s)" % ",".join("?" * len(chunk)), chunk)
    db.commit()
    left = db.execute("SELECT COUNT(*) FROM phash").fetchone()[0]
    print("已删除孤儿行，剩余 %d 行" % left)
    db.execute("VACUUM")
    db.close()
    print("VACUUM 完成，索引体积：%.1f MB" % (os.path.getsize(DB) / 1048576))


if __name__ == "__main__":
    main()

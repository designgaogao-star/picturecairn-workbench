# -*- coding: utf-8 -*-
"""按键加锁：同一个 key 只允许一个线程进去。

用途：同一个组并发首次建媒体清单、同一张图并发生成缩略图 ——
这两种情况在机械盘上都是秒级随机寻道，两个请求各跑一遍纯属浪费。
"""

import threading

_locks = {}
_guard = threading.Lock()
_MAX = 2048  # 上限，超过就丢弃最早的一半（锁本身无状态，丢了重建即可）

#: 磁盘并发闸门。F 盘是机械盘，一次性放开几十个随机读会把寻道放大到极致。
#: 6 是实测下来的甜点位：再多不提速，再少前台会等。
disk_sem = threading.Semaphore(6)


def key_lock(key):
    """取一把与 key 关联的锁。用 `with key_lock(k):` 持有。"""
    with _guard:
        lk = _locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _locks[key] = lk
            if len(_locks) > _MAX:
                for k in list(_locks.keys())[: _MAX // 2]:
                    _locks.pop(k, None)
        return lk

# -*- coding: utf-8 -*-
"""图片格式、缓存限额和运行参数的唯一来源。"""

# ---------- 服务 ----------
PORT = 8765

# ---------- 扩展名 ----------
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# ---------- 缩略图 ----------
THUMB_LONG_EDGE = 400
THUMB_QUALITY = 72
# 缩略图长边上限。原来是 1400，宽屏（2560）上需要 2000+，4K 屏需要 3840 ——
# 都会把预览拉伸放大导致发虚，逼着用户等原图。放到 4200，覆盖 4K@100%/150%/200% 三种缩放。
THUMB_EDGE_MAX = 4200
SURVEY_EDGE = 760  # 抽样快审页用的高清缩略图长边
PREVIEW_QUALITY = 80  # 单张看图的预览质量（与前端 PREVIEW_Q 对齐）

# ---------- 缓存与节奏 ----------
FILES_CACHE_MAX = 8  # 热文件夹媒体清单的内存 LRU
STATE_FLUSH_DELAY = 0.6  # 状态合并写防抖秒数
SCAN_TTL = 2.5  # scan_root 结果短缓存：高频 /api/state 不再每次全扫（HDD 友好）
# 缩略图磁盘缓存软上限。v5.6 起会生成 3840px 大预览（约 880KB/张），
# 2GB 装不下多少就被 GC、回头又得重新生成。放宽到 12GB，
# 目的就是让"看过一次的组"长期不必重复生成。只删缓存、可随时重建，绝不碰原图。
THUMB_CACHE_LIMIT = 12 * 1024**3

# ---------- 去重 ----------
DEDUP_DEFAULT_TH = 8  # pHash 汉明距离阈值：<=8 视为近重复
DEDUP_MAX_FAIL = 20  # 连续失败这么多次才认为"这条路彻底坏了"

# ---------- 静态资源 ----------
UI_CTYPE = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}

# -*- coding: utf-8 -*-
"""info.json → source/ 全部源图。
短边低于配置门槛的图片不进入素材池；详情图写入 source/detail/ 供后续筛选。"""
import os, urllib.request
from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://detail.1688.com/"}


def usable_image(path, min_short_side):
    try:
        with Image.open(path) as im:
            return min(im.size) >= min_short_side
    except Exception:
        return False


def dl(url, path, min_short_side):
    tmp = path + ".part"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r, open(tmp, "wb") as f:
            f.write(r.read())
        if not usable_image(tmp, min_short_side):
            os.remove(tmp)
            return False
        os.replace(tmp, path)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def prune_small_images(directory, min_short_side):
    dropped = 0
    if not os.path.isdir(directory):
        return dropped
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if not os.path.isfile(path) or name.endswith(".part"):
            continue
        if not usable_image(path, min_short_side):
            os.remove(path)
            dropped += 1
    return dropped


def run(cfg, folder, info):
    src = os.path.join(folder, "source")
    det = os.path.join(src, "detail")
    os.makedirs(det, exist_ok=True)
    min_short_side = int(cfg.get("intake", {}).get("min_image_short_side_px", 600))
    dropped = prune_small_images(src, min_short_side) + prune_small_images(det, min_short_side)
    n_main = n_det = 0
    for i, u in enumerate(info.get("main_images") or [], 1):
        p = os.path.join(src, f"src_{i:02d}.jpg")
        if (os.path.exists(p) and usable_image(p, min_short_side)) or dl(u, p, min_short_side):
            n_main += 1
    for i, u in enumerate(info.get("detail_images") or [], 1):
        p = os.path.join(det, f"d{i:02d}.jpg")
        if (os.path.exists(p) and usable_image(p, min_short_side)) or dl(u, p, min_short_side):
            n_det += 1
    print(f"  ✓ 主图 {n_main} 张 → source/ | 详情图 {n_det} 张 → source/detail/ | 剔除小图 {dropped} 张（短边<{min_short_side}px）")
    return src

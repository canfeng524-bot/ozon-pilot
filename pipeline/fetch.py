# -*- coding: utf-8 -*-
"""链接 → 商品文件夹 + info.json
利用 desc.1688.com 两跳公开接口（无需登录）：
  ① desc.1688.com/offer/{id}.html → detailUrl
  ② itemcdn 数据文件 → 全尺寸详情图（顺序保持）
  ① 页面内的主图缩略图变体（.220x220 等）还原全尺寸 → 主图
标题/价格/属性需登录态，此处置空并提示用油猴脚本补全。
"""
import os, re, json, datetime, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
URL_RE = re.compile(r'https?:(?:\\?/\\?/)[^\s"\'`<>\(\)\\]+?\.(?:jpg|jpeg|png|webp)', re.I)
CDN_RE = re.compile(r'(?:cbu0?1?\.alicdn\.com|img\.alicdn\.com|gw\.alicdn\.com|itemcdn)', re.I)
NOISE_RE = re.compile(r'[-_]tps[-_]|gg_dtc|cms[/\\]upload|logo|icon|sprite|avatar|widget|\.svg$|\.gif$|tbvideo', re.I)
THUMB_RE = re.compile(r'^(https?:\/\/.+)\.(?:\d{2,4}x\d{2,4}|search|summ|b2b)\.(jpg|jpeg|png|webp)$', re.I)


def http_get(url, timeout=20, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            import time
            time.sleep(1.5 * (i + 1))
    raise last


def full_size(u):
    m = THUMB_RE.match(u)
    return f"{m.group(1)}.{m.group(2)}" if m else u


def find_info(folder):
    for f in sorted(os.listdir(folder)):
        if f.lower().startswith("info") and f.lower().endswith(".json"):
            return os.path.join(folder, f)
    return None


def collect_images(item_id):
    """Fetch public image URLs only. Caller decides whether to preserve product facts."""
    main_imgs, detail_imgs = [], []
    html = http_get(f"https://desc.1688.com/offer/{item_id}.html")
    t = html.replace("\\/", "/")
    seen = set()
    for u in URL_RE.findall(t):
        u = full_size(u.strip())
        if CDN_RE.search(u) and not NOISE_RE.search(u) and u not in seen:
            seen.add(u)
            main_imgs.append(u)
    dm = re.search(r'["\']detailUrl["\']\s*:\s*["\'](https?://[^"\']+)', t)
    if dm:
        data = http_get(dm.group(1).replace("\\/", "/")).replace("\\/", "/")
        dseen = set(main_imgs)
        for u in URL_RE.findall(data):
            u = full_size(u.strip())
            if CDN_RE.search(u) and not NOISE_RE.search(u) and u not in dseen:
                dseen.add(u)
                detail_imgs.append(u)
    return main_imgs[:10], detail_imgs[:80]


def refresh_images(info):
    """Refresh only image URLs without overwriting browser/user-verified facts."""
    item_id = str(info.get("item_id") or "")
    if not item_id:
        raise ValueError("info.json 缺少 item_id，无法刷新图片")
    main_imgs, detail_imgs = collect_images(item_id)
    info["main_images"] = main_imgs
    info["detail_images"] = detail_imgs
    info["images_refreshed_at"] = datetime.datetime.now().isoformat()
    return len(main_imgs), len(detail_imgs)


def run(cfg, url):
    m = re.search(r'offer[/=](\d{6,})', url)
    if not m:
        print("  ✗ 链接里没有识别到商品ID（offer/123456.html）")
        return None
    item_id = m.group(1)
    ws = cfg["paths"]["workspace"]
    folder = os.path.join(ws, f"link_{item_id}")
    os.makedirs(folder, exist_ok=True)

    main_imgs, detail_imgs, title = [], [], None
    try:
        html = http_get(f"https://desc.1688.com/offer/{item_id}.html")
        main_imgs, detail_imgs = collect_images(item_id)
        tm = re.search(r'<title>([^<]+)</title>', html)
        if tm:
            title = tm.group(1).split("-1688")[0].strip()
    except Exception as e:
        print(f"  ✗ 抓取失败：{e}")

    info = {
        "platform": "1688",
        "source_url": url,
        "item_id": item_id,
        "title": title or "",
        "price_cny": None,
        "main_images": main_imgs,
        "detail_images": detail_imgs,
        "attributes": [],
        "logistics": None,
        "sku_specs": [],
        "extracted_at": datetime.datetime.now().isoformat(),
        "extractor": "ozon-pilot/fetch-link",
        "note": "链接模式：图片来自公开接口；标题价格属性需用油猴脚本(ozon-intake v1.3.4)提取后覆盖本文件",
    }
    path = os.path.join(folder, f"info_1688_{item_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 主图 {len(main_imgs[:10])} 张 / 详情图 {len(detail_imgs[:80])} 张 → {path}")
    if not title:
        print("  ! 标题/价格/属性为空：上架前用油猴脚本重新提取并覆盖 info json")
    return folder

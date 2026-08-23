# -*- coding: utf-8 -*-
"""源图筛选：无视觉模型时按启发式（尺寸/白边占比/宽高比），有视觉模型时按内容分类。
产出 screen.json：每张图的 tag（front/back/side/interior/detail/material/dims/text/other）
+ drop 原因，供 compose 按槽位取材。"""
import os, json, base64
from PIL import Image


def img_stats(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    g = im.convert("L").resize((60, 60))
    px = list(g.getdata())
    white = sum(1 for p in px if p > 244) / len(px)
    # 上下条带均色（中文详情图文字区通常大片纯白）
    rows = [px[i * 60:(i + 1) * 60] for i in range(60)]
    top_white = sum(1 for p in rows[0] + rows[1] if p > 244) / 120
    bot_white = sum(1 for p in rows[-1] + rows[-2] if p > 244) / 120
    return {"w": w, "h": h, "white": round(white, 2), "top_white": round(top_white, 2),
            "bot_white": round(bot_white, 2), "ratio": round(h / w, 2)}


def heuristic(path, st, zone, min_short_side):
    """保守规则：只弃小图；白底大图=候选。中文文字区识别交给视觉模型（无模型时不误杀）"""
    if min(st["w"], st["h"]) < min_short_side:
        return "other", f"小图（短边<{min_short_side}px）"
    if zone == "main" and st["white"] > 0.4:
        return "front", "主图区白底产品图"
    if st["white"] > 0.5 and min(st["w"], st["h"]) >= 600:
        return "candidate", "白底大图"
    return "candidate", ""


def vision_classify(cfg, path):
    mc = cfg["models"]["vision"]
    if not mc.get("api_key"):
        return None
    import urllib.request
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    body = json.dumps({
        "model": mc["model"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "对这张电商图分类，只回一个词：front(正面白底) back(背面) side(侧面) interior(内部) detail(细节特写) material(材质特写) dims(尺寸标注图) text(含大段中文文字) scene(场景图)"}
            ]}]}).encode()
    req = urllib.request.Request(mc["base_url"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {mc['api_key']}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip().split()[0].lower()
    except Exception as e:
        print(f"  ! 视觉模型失败({os.path.basename(path)}): {e}")
        return None


def run(cfg, folder, info, skip_ai=False):
    src = os.path.join(folder, "source")
    det = os.path.join(src, "detail")
    files = []
    if os.path.isdir(src):
        files += [("main", os.path.join(src, f)) for f in sorted(os.listdir(src)) if f.startswith("src_")]
    if os.path.isdir(det):
        files += [("detail", os.path.join(det, f)) for f in sorted(os.listdir(det)) if f.endswith(".jpg")]
    use_vision = (not skip_ai) and cfg["models"]["vision"].get("api_key")
    min_short_side = int(cfg.get("intake", {}).get("min_image_short_side_px", 600))
    result = {"core": [], "spare": [], "drop": [], "items": []}
    for zone, p in files:
        st = img_stats(p)
        rel = os.path.relpath(p, folder).replace("\\", "/")
        if use_vision:
            tag = vision_classify(cfg, p) or "candidate"
            why = f"视觉模型分类:{tag}"
        else:
            tag, why = heuristic(p, st, zone, min_short_side)
        item = {"file": rel, "zone": zone, "tag": tag, "why": why, **st}
        result["items"].append(item)
        if tag in ("text", "other") or tag == "drop":
            result["drop"].append(item)
        else:
            (result["core"] if tag != "candidate" else result["spare"]).append(item)
    out = os.path.join(folder, "screen.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    mode = "视觉模型" if use_vision else "启发式"
    print(f"  ✓ 筛选({mode})：可用 {len(result['core']) + len(result['spare'])} 张，弃用 {len(result['drop'])} 张 → screen.json")
    if not use_vision:
        print("  ! 未配置视觉模型：仅按尺寸/白边启发式筛选。配置 models.vision 后可自动识别正面/背面/内部等取材")
    return result

# -*- coding: utf-8 -*-
"""图片合成：按 config 的 carousel_plan 产出各槽位图。
- real 型：从 slots.json 取材（无则按 screen.json 的 tag 自动配对 + 默认裁剪）
- program 型：尺寸信息图（读 info 的件重尺 + 普通手机参照）
- ai 型：调图像 API（未配置则生成 ai_todo.json 交给 TRAE/手动执行）"""
import os, json, base64, urllib.request
from PIL import Image, ImageDraw, ImageFont

TAG2SLOT = {  # screen tag → 槽位取材优先级
    "angles": ["side", "back"],
    "material": ["material", "detail"],
    "interior": ["interior", "detail"],
    "strap": ["back", "detail"],
}


def _font(cfg, sz):
    return ImageFont.truetype(cfg["image_spec"]["font"], sz)


def trim_white(img, pad=12, thresh=246):
    im = img.convert("RGB")
    mask = im.convert("L").point(lambda p: 255 if p < thresh else 0)
    bbox = mask.getbbox()
    if not bbox:
        return im
    l, t, r, b = bbox
    return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))


def fit(img, bw, bh):
    im = trim_white(img)
    s = min(bw / im.width, bh / im.height)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def open_pick(folder, pick):
    """Open a source pick and apply an optional explicit crop.

    A pick may be a legacy relative-path string or an object such as:
    {"file": "source/detail/d08.jpg", "crop": [0.03, 0.27, 0.97, 0.76]}.
    Crop coordinates can be normalized 0..1 values or absolute source pixels.
    Explicit crops let the reviewer exclude supplier-language headings and captions
    while preserving the real product pixels.
    """
    if isinstance(pick, dict):
        rel = pick.get("file")
        crop = pick.get("crop")
    else:
        rel, crop = pick, None
    if not rel:
        raise ValueError("素材项缺少 file")
    im = Image.open(os.path.join(folder, rel)).convert("RGB")
    if crop:
        if not isinstance(crop, (list, tuple)) or len(crop) != 4:
            raise ValueError(f"无效 crop：{crop}")
        if all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in crop):
            l, t, r, b = (int(crop[0] * im.width), int(crop[1] * im.height),
                          int(crop[2] * im.width), int(crop[3] * im.height))
        else:
            l, t, r, b = map(int, crop)
        if not (0 <= l < r <= im.width and 0 <= t < b <= im.height):
            raise ValueError(f"crop 超出图片范围：{crop} / {im.size}")
        im = im.crop((l, t, r, b))
    return rel, im


def paste_center(cv, im, y, bh, W):
    cv.paste(im, ((W - im.width) // 2, y + (bh - im.height) // 2))


def text_block(cv, cfg, lines, y0, y1, W):
    d = ImageDraw.Draw(cv)
    n = len(lines)
    sizes = [44] if n == 1 else ([46, 34] if n == 2 else [40, 32, 32])
    total = sum(sizes[:n]) + 14 * (n - 1)
    y = y0 + (y1 - y0 - total) // 2
    for txt, sz in zip(lines, sizes[:n]):
        f = _font(cfg, sz)
        d.text(((W - d.textlength(txt, font=f)) / 2, y), txt, fill=(20, 20, 20), font=f)
        y += sz + 14


def add_text_overlay(cfg, image_path, lines):
    """Add only verified copy after generation; never ask the image model to render text."""
    if not lines:
        return
    base = Image.open(image_path).convert("RGB")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font_main, font_sub = _font(cfg, 42), _font(cfg, 30)
    margin, y = 46, 46
    widths = [d.textlength(line, font=(font_main if i == 0 else font_sub)) for i, line in enumerate(lines[:2])]
    box_w = min(base.width - margin * 2, int(max(widths, default=0) + 48))
    box_h = 62 + (45 if len(lines) > 1 else 0)
    d.rounded_rectangle((margin, y, margin + box_w, y + box_h), radius=16, fill=(255, 255, 255, 220))
    for i, line in enumerate(lines[:2]):
        font = font_main if i == 0 else font_sub
        d.text((margin + 24, y + 13 + i * 43), line, fill=(24, 24, 24, 255), font=font)
    Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB").save(image_path, quality=93)


def make_real(cfg, folder, slot, picks, labels):
    W, H = cfg["image_spec"]["width"], cfg["image_spec"]["height"]
    if not picks:
        return None, "无可用素材（筛选结果为空）"
    cv = Image.new("RGB", (W, H), (255, 255, 255))
    n = len(picks)
    hs = [(H - 260) // n] * n
    y = 20
    for i, pick in enumerate(picks[:3]):
        try:
            _, src = open_pick(folder, pick)
            im = fit(src, W - 60, hs[i])
        except Exception:
            continue
        paste_center(cv, im, y, hs[i], W)
        y += hs[i] + 20
    if labels:
        text_block(cv, cfg, labels if n <= 2 else labels[:2], H - 160, H - 20, W)
    return cv, None


def make_size_info(cfg, folder, info):
    W, H = cfg["image_spec"]["width"], cfg["image_spec"]["height"]
    lg = info.get("logistics") or {}
    dims = info.get("_dims_final") or {}
    L = dims.get("length_cm") or lg.get("length_cm")
    Wd = dims.get("width_cm") or lg.get("width_cm")
    Hh = dims.get("height_cm") or lg.get("height_cm")
    if not all(isinstance(v, (int, float)) and v > 0 for v in (L, Wd, Hh)):
        return None, "缺少已验证的长、宽、高，未生成尺寸图"
    ref_rel = info.get("size_reference_image")
    ref_path = os.path.join(folder, ref_rel) if ref_rel else None
    if not ref_path or not os.path.exists(ref_path):
        return None, "缺少与当前 SKU 一致的实拍参考图，未生成尺寸图"
    cv = Image.new("RGB", (W, H), (248, 247, 244))
    d = ImageDraw.Draw(cv)
    wt = lg.get("weight_g", "")
    # 尺寸卡必须使用当前 SKU 的真实产品图，不能以通用包体示意替代。
    try:
        product = fit(Image.open(ref_path), 720, 820)
    except Exception:
        return None, "尺寸参考图无法读取，未生成尺寸图"
    f_title, f1, f2, f3, f_small = (_font(cfg, 60), _font(cfg, 40), _font(cfg, 34),
                                      _font(cfg, 28), _font(cfg, 24))
    title = "Размеры сумки"
    d.text(((W - d.textlength(title, font=f_title)) / 2, 80), title,
           fill=(28, 27, 25), font=f_title)
    subtitle = "Сравнение с обычным смартфоном"
    d.text(((W - d.textlength(subtitle, font=f3)) / 2, 152), subtitle,
           fill=(118, 112, 103), font=f3)

    # Verified dimensions are shown as text blocks; the source product photo stays
    # evidence-led. The ordinary-phone outline is a scale reference, not a fit claim.
    facts = [(f"Ширина  {L:g} см", (104, 80, 53)),
             (f"Высота  {Hh:g} см", (104, 80, 53)),
             (f"Глубина  {Wd:g} см", (104, 80, 53))]
    x0, box_y, box_w, gap = 70, 200, 385, 28
    for i, (txt, col) in enumerate(facts):
        x = x0 + i * (box_w + gap)
        d.rounded_rectangle((x, box_y, x + box_w, box_y + 105), radius=22,
                            fill=(255, 255, 255), outline=(221, 215, 204), width=2)
        d.text((x + 28, box_y + 29), txt, fill=col, font=f1)

    cv.paste(product, (55 + (720 - product.width) // 2, 410 + (820 - product.height) // 2))
    d.text((170, 1270), "Сумка 22 × 16 × 17 см", fill=(28, 27, 25), font=f2)

    # Ordinary smartphone reference, approximately 7.5 × 15 cm at 21 px per cm.
    scale = 21
    phone_w, phone_h = int(7.5 * scale), int(15 * scale)
    phone_x, phone_y = 990, 700
    d.rounded_rectangle((phone_x, phone_y, phone_x + phone_w, phone_y + phone_h), radius=24,
                        fill=(235, 233, 228), outline=(76, 74, 70), width=5)
    d.ellipse((phone_x + phone_w // 2 - 7, phone_y + 14,
               phone_x + phone_w // 2 + 7, phone_y + 28), fill=(76, 74, 70))
    d.text((865, 1055), "Обычный смартфон", fill=(28, 27, 25), font=f2)
    d.text((880, 1110), "≈ 7,5 × 15 см", fill=(70, 68, 64), font=f3)
    d.text((835, 1160), "для сравнения масштаба", fill=(118, 112, 103), font=f_small)

    if wt:
        t = f"Вес: около {wt} г" if isinstance(wt, int) else "Вес: см. карточку"
        d.text((70, 1460), t, fill=(28, 27, 25), font=f2)
    t2 = "Допуск ручного замера: 1–3 см"
    d.text((70, 1600), t2, fill=(118, 112, 103), font=f3)
    t3 = "Смартфон показан только как ориентир масштаба"
    d.text((70, 1660), t3, fill=(118, 112, 103), font=f3)
    return cv, None


def gen_ai_image(cfg, prompt, ref_path, out_path):
    mc = cfg["models"]["image"]
    if not mc.get("api_key"):
        return False
    b64 = base64.b64encode(open(ref_path, "rb").read()).decode()
    body = json.dumps({"model": mc["model"], "prompt": prompt,
                       "image": b64, "size": mc.get("size", "1350x1800"),
                       "response_format": "url"}).encode()
    req = urllib.request.Request(mc["base_url"].rstrip("/") + "/images/generations", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {mc['api_key']}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            url = json.loads(r.read())["data"][0]["url"]
        urllib.request.urlretrieve(url, out_path)
        return True
    except Exception as e:
        print(f"  ! AI生图失败: {e}")
        return False


def pick_for_slot(screen_result, tags):
    """按 tag 优先级从筛选结果取素材（去重）"""
    used = set()
    out = []
    for tg in tags:
        for it in screen_result.get("core", []) + screen_result.get("spare", []):
            if it["tag"] == tg and it["file"] not in used:
                used.add(it["file"])
                out.append(it["file"])
                break
    return out


def product_desc(info):
    """Only source-backed facts for image prompts; do not invent missing fields."""
    attrs = info.get("attributes") or []
    facts = [str(info.get("title") or "")]
    for item in attrs:
        if isinstance(item, dict) and item.get("name") and item.get("value"):
            facts.append(f"{item['name']}：{item['value']}")
    return "；".join(facts)


def has_multiple_skus(info):
    for spec in info.get("sku_specs") or []:
        options = spec.get("options") if isinstance(spec, dict) else None
        if isinstance(options, list) and len(options) > 1:
            return True
    return False


def run(cfg, folder, info, screen_result, skip_ai=False):
    out = os.path.join(folder, "remastered")
    os.makedirs(out, exist_ok=True)
    slots_path = os.path.join(folder, "slots.json")
    slots_map = json.load(open(slots_path, encoding="utf-8")) if os.path.exists(slots_path) else None
    todo = []
    done = []
    for slot in cfg["carousel_plan"]:
        sid, typ = slot["id"], slot["type"]
        if slot.get("optional") and slot.get("requires_multiple_skus") and not has_multiple_skus(info):
            continue
        out_path = os.path.join(out, f"{sid}.jpg")
        if os.path.exists(out_path):
            done.append(f"{sid}.jpg")
            continue
        if typ == "program":
            cv, err = make_size_info(cfg, folder, info)
            if cv:
                cv.save(out_path, quality=92)
                done.append(f"{sid}.jpg")
            continue
        if typ == "real":
            if slots_map and sid in slots_map:
                m = slots_map[sid]
                cv, err = make_real(cfg, folder, slot, m.get("picks", []), m.get("labels_ru") or slot.get("ru_label"))
            else:
                picks = pick_for_slot(screen_result, slot.get("picks_tags") or TAG2SLOT.get(sid, ["front"]))
                cv, err = make_real(cfg, folder, slot, picks, slot.get("ru_label"))
            if cv:
                cv.save(out_path, quality=92)
                done.append(f"{sid}.jpg")
            elif err:
                todo.append({"slot": sid, "type": "real", "reason": err})
            continue
        if typ == "ai":
            if skip_ai:
                todo.append({"slot": sid, "type": "ai", "reason": "--skip-ai", "prompt": cfg["image_prompts"].get(slot.get("prompt_key", ""), "")})
                continue
            ref = pick_for_slot(screen_result, ["front", "candidate"])
            ref_path = os.path.join(folder, ref[0]) if ref else None
            # 第二张场景图优先以第一张场景图作身份锚点，避免同一轮播出现不同模特。
            if sid == "model2":
                identity_anchor = os.path.join(out, "model1.jpg")
                if os.path.exists(identity_anchor):
                    ref_path = identity_anchor
            prompt = cfg["image_prompts"].get(slot.get("prompt_key", ""), "").replace("{product_desc}", product_desc(info))
            if ref_path and prompt and gen_ai_image(cfg, prompt, ref_path, out_path):
                add_text_overlay(cfg, out_path, (info.get("image_overlays") or {}).get(sid))
                done.append(f"{sid}.jpg")
            else:
                todo.append({"slot": sid, "type": "ai", "reason": "未配置图像API或生成失败",
                             "prompt": prompt, "ref": ref_path})
    if todo:
        with open(os.path.join(out, "ai_todo.json"), "w", encoding="utf-8") as f:
            json.dump(todo, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 合成 {len(done)} 张；{len(todo)} 个槽位待处理 → remastered/ai_todo.json（可在 TRAE 里按 prompt 逐张生成后放入 remastered/）")
    else:
        print(f"  ✓ 合成完成：{', '.join(done) or '无新增'}")
    return done

# -*- coding: utf-8 -*-
"""审核页 review.html + XLSX + 打包 ozon_package.zip（读取 listing.json / screen.json / remastered/）"""
import os, json, html, zipfile

try:
    import openpyxl
except ImportError:
    openpyxl = None


def build_zip(folder, listing, allowed_slots=None, ordered_slots=None):
    """上架包：重制图 + 俄语文案txt + listing.json + xlsx → ozon_package.zip
    listing 参数兼容两种：{"listing":{...},"images":{...}} 根结构 或 纯 listing dict"""
    zp = os.path.join(folder, "ozon_package.zip")
    rem = os.path.join(folder, "remastered")
    root = listing if isinstance(listing, dict) else {}
    if "listing" in root and isinstance(root.get("listing"), dict):
        data = root["listing"]
    else:
        data = root
    deprecated = set()
    imgs_meta = root.get("images") if isinstance(root.get("images"), dict) else {}
    for d in imgs_meta.get("deprecated_remastered", []):
        if isinstance(d, dict) and d.get("file"):
            deprecated.add(os.path.basename(d["file"]))
    files = []
    if os.path.isdir(rem):
        if ordered_slots is not None:
            # Preserve carousel generation order and give upload-ready files stable
            # numeric prefixes. Sequence numbers are consecutive among existing slots.
            seq = 1
            for sid in ordered_slots:
                f = f"{sid}.jpg"
                p = os.path.join(rem, f)
                if not os.path.exists(p) or f.endswith("_raw.jpg") or f in deprecated:
                    continue
                files.append((f"remastered/{seq:02d}_{f}", p))
                seq += 1
        else:
            for f in sorted(os.listdir(rem)):
                if not f.endswith(".jpg") or f.endswith("_raw.jpg") or f in deprecated:
                    continue
                if allowed_slots is not None and os.path.splitext(f)[0] not in allowed_slots:
                    continue
                files.append(("remastered/" + f, os.path.join(rem, f)))
    if data:
        lines = []
        for k, lab in [("title_ru", "НАИМЕНОВАНИЕ"), ("description_ru", "ОПИСАНИЕ")]:
            if data.get(k):
                lines += [f"=== {lab} ===", data[k], ""]
        if data.get("highlights_ru"):
            lines += ["=== ПРЕИМУЩЕСТВА ==="]
            lines += [f"{i}. {h}" for i, h in enumerate(data["highlights_ru"], 1)] + [""]
        if data.get("attributes_ru"):
            lines += ["=== АТРИБУТЫ ==="]
            lines += [f"{a['name']}: {a['value']}" for a in data["attributes_ru"]] + [""]
        lines += ["=== 中文对照 ===", data.get("title_ru_zh", "")]
        txt_path = os.path.join(folder, "copy_ru.txt")
        with open(txt_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines))
        files.append(("copy_ru.txt", txt_path))
    lp = os.path.join(folder, "listing.json")
    if os.path.exists(lp):
        files.append(("listing.json", lp))
    xp = os.path.join(folder, "ozon_listing.xlsx")
    if os.path.exists(xp):
        files.append(("ozon_listing.xlsx", xp))
    notes = os.path.join(folder, "review_notes.md")
    if os.path.exists(notes):
        files.append(("review_notes.md", notes))
    if not files:
        return None, 0
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, p in files:
            z.write(p, arc)
    return zp, len(files)


def esc(s):
    return html.escape(str(s or ""))


def run(cfg, folder, info):
    lp = os.path.join(folder, "listing.json")
    listing = json.load(open(lp, encoding="utf-8"))["listing"] if os.path.exists(lp) else None
    sp = os.path.join(folder, "screen.json")
    screen = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {"items": [], "core": [], "drop": []}

    plan_list = cfg["carousel_plan"]
    plan = {s["id"]: s for s in plan_list}
    rem = os.path.join(folder, "remastered")
    imgs = [f"{s['id']}.jpg" for s in plan_list
            if os.path.exists(os.path.join(rem, f"{s['id']}.jpg"))] if os.path.isdir(rem) else []
    numbered = {f: f"{i:02d}_{f}" for i, f in enumerate(imgs, 1)}

    cells = "".join(
        f'<div class="cell"><span class="tag t-{("core" if it["tag"] not in ("text","other","candidate") else ("drop" if it["tag"]=="text" else "spare"))}">'
        f'{it["tag"]}</span><img src="{esc(it["file"])}"><div class="cap"><b>{os.path.basename(it["file"])}</b>'
        f'<div class="why">{esc(it["why"])} · {it["w"]}×{it["h"]}</div></div></div>'
        for it in screen["items"])

    matrix = "".join(
        f'<div class="slot"><img src="remastered/{f}" download="{numbered[f]}"><div class="info"><b>{numbered[f]} · {esc(plan.get(f[:-4], {}).get("role", f[:-4]))}</b>'
        f'<a class="dl" href="remastered/{f}" download="{numbered[f]}">下载原图</a> '
        f'<span class="src">{esc(plan.get(f[:-4], {}).get("type", ""))}</span></div></div>'
        for f in imgs)

    copy_html = ""
    if listing:
        L = listing
        copy_html = f"""
        <div class="card"><h2><span class="n">3</span>俄语文案 <span class="sub">灰字为中文对照</span></h2>
        <div class="ru">{esc(L.get('title_ru'))}</div><div class="zh">中：{esc(L.get('title_ru_zh'))}</div>
        <ul class="points">""" + "".join(
            f"<li><div class='ru'>{esc(a)}</div><div class='zh'>中：{esc(b)}</div></li>"
            for a, b in zip(L.get("highlights_ru", []), L.get("highlights_zh", []))) + f"""
        </ul>
        <div class="ru" style="white-space:pre-line;margin-top:10px">{esc(L.get('description_ru'))}</div>
        <div class="zh">中：{esc(L.get('description_zh'))}</div></div>"""
    else:
        copy_html = ('<div class="card"><h2><span class="n">3</span>俄语文案</h2>'
                     '<div class="warn">未生成：请执行 copy_prompt.md 里的提示词，结果存为 listing.json 后重跑</div></div>')

    # XLSX 必须先落盘；否则首次 ZIP 会漏掉导入表。
    if openpyxl and listing:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ozon_import"
        ws.append(["字段", "值"])
        ws.append(["Наименование (标题)", listing.get("title_ru", "")])
        ws.append(["Описание (描述)", listing.get("description_ru", "")])
        for a in listing.get("attributes_ru", []):
            ws.append([a.get("name", ""), a.get("value", "")])
        ws.append(["Цена, руб (售价)", cfg["pricing"]["suggested_price_rub"]])
        ws2 = wb.create_sheet("images")
        ws2.append(["槽位", "文件"])
        for f in imgs:
            ws2.append([plan.get(f[:-4], {}).get("role", ""), f"remastered/{numbered[f]}"])
        wb.save(os.path.join(folder, "ozon_listing.xlsx"))
    zp, nfiles = build_zip(folder, listing, allowed_slots=set(plan),
                           ordered_slots=[f[:-4] for f in imgs])
    dl_card = (f'<div class="card dlcard"><h2><span class="n">⬇</span>打包下载</h2>'
               f'<a class="zipbtn" href="ozon_package.zip" download>下载上架包 ozon_package.zip（{nfiles} 个文件）</a>'
               f'<div class="sub" style="margin-top:8px">内含：remastered/ 上架图 · copy_ru.txt · listing.json · ozon_listing.xlsx · review_notes.md</div></div>') if zp else (
               '<div class="card"><h2><span class="n">!</span>上架包</h2><div class="warn">尚无可交付图或文案，未生成 ZIP。</div></div>')

    display_title = listing.get("title_ru") if listing else (info.get("title") or info.get("item_id"))
    page = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>审核 · {esc(display_title)}</title>
<style>
body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a2233;padding:24px;margin:0}}
.wrap{{max-width:1280px;margin:0 auto}} h1{{font-size:22px}}
.card{{background:#fff;border:1px solid #e6e8ec;border-radius:14px;padding:20px;margin:18px 0}}
h2{{font-size:17px;margin:0 0 14px}} h2 .n{{background:#005bff;color:#fff;border-radius:6px;padding:2px 9px;font-size:12px;margin-right:8px}}
.sub{{color:#7a8499;font-size:13px;font-weight:normal}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}
.cell{{border:1px solid #e6e8ec;border-radius:10px;overflow:hidden;position:relative}}
.cell img{{width:100%;height:150px;object-fit:cover;display:block}} .cap{{padding:8px;font-size:12px}}
.why{{color:#7a8499}} .tag{{position:absolute;top:8px;left:8px;color:#fff;font-size:11px;border-radius:6px;padding:2px 8px}}
.t-core{{background:#0f9d58}} .t-spare{{background:#64748b}} .t-drop{{background:#9aa3b2}}
.matrix{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
.slot{{border:1px solid #e6e8ec;border-radius:12px;overflow:hidden}}
.slot img{{width:100%;aspect-ratio:3/4;object-fit:contain;background:#fff;border-bottom:1px solid #e6e8ec}}
.slot .info{{padding:10px;font-size:12px}} .src{{display:inline-block;margin-top:5px;background:#7c3aed;color:#fff;border-radius:6px;padding:2px 8px;font-size:11px}}
.ru{{font-size:14px;line-height:1.7}} .zh{{color:#7a8499;font-size:12.5px;border-left:3px solid #e6e8ec;padding-left:10px;margin:4px 0}}
.points{{list-style:none;padding:0}} .points li{{padding:9px 0;border-bottom:1px dashed #e6e8ec}}
.warn{{background:#fff8e6;border:1px solid #f0d060;border-radius:8px;padding:12px;font-size:13px}}
.zipbtn{{display:inline-block;background:#005bff;color:#fff;border-radius:10px;padding:12px 22px;font-size:14px;text-decoration:none;font-weight:600}}
.zipbtn:hover{{background:#0047c7}}
.dl{{color:#005bff;font-size:12px;text-decoration:none;margin-right:6px}} .dl:hover{{text-decoration:underline}}
.dlcard{{border-color:#c7d6f5;background:#f4f8ff}}
</style></head><body><div class="wrap">
<h1>Ozon 上架审核包 <span class="sub">{esc(display_title)}</span></h1>
<div class="sub">货源 {esc(info.get('platform'))} · {esc(info.get('item_id'))} · 生成 {esc(info.get('extracted_at',''))[:19]}</div>
<div class="card"><h2><span class="n">1</span>素材筛选 <span class="sub">{len(screen['items'])} 张源图</span></h2><div class="grid">{cells}</div></div>
<div class="card"><h2><span class="n">2</span>上架图矩阵 <span class="sub">{len(imgs)} 张</span></h2><div class="matrix">{matrix}</div>
<div class="sub" style="margin-top:10px">缺槽位见 remastered/ai_todo.json</div></div>
{dl_card}
{copy_html}
</div></body></html>"""
    with open(os.path.join(folder, "review.html"), "w", encoding="utf-8") as f:
        f.write(page)

    if openpyxl and listing:
        print("  ✓ review.html + ozon_listing.xlsx")
    else:
        print("  ✓ review.html（XLSX 需 listing.json 与 openpyxl，暂跳过）")

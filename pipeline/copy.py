# -*- coding: utf-8 -*-
"""俄语文案：配置了 LLM 则直接生成 listing.json；否则产出 copy_prompt.md
（提示词已拼好货源数据，粘给 TRAE/任意聊天模型即可，生成后存为 listing.json）"""
import os, json, re, urllib.request


def call_llm(cfg, data_json):
    mc = cfg["models"]["copy"]
    body = json.dumps({
        "model": mc["model"],
        "messages": [
            {"role": "system", "content": cfg["prompts"]["copy_system"]},
            {"role": "user", "content": cfg["prompts"]["copy_user"].replace("{data}", data_json)},
        ],
        "temperature": 0.4,
    }).encode()
    req = urllib.request.Request(mc["base_url"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {mc['api_key']}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def run(cfg, folder, info, skip_ai=False):
    lp = os.path.join(folder, "listing.json")
    if os.path.exists(lp):
        print("  ✓ listing.json 已存在，跳过（删除可重新生成）")
        return
    mc = cfg["models"]["copy"]
    data = {k: info.get(k) for k in ("title", "price_cny", "attributes", "logistics", "sku_specs", "main_images")}
    data_json = json.dumps(data, ensure_ascii=False)
    if (not skip_ai) and mc.get("api_key"):
        try:
            raw = call_llm(cfg, data_json)
            m = re.search(r"\{.*\}", raw, re.S)
            listing = json.loads(m.group(0)) if m else {"raw": raw}
            with open(lp, "w", encoding="utf-8") as f:
                json.dump({"item_id": info.get("item_id"), "listing": listing,
                           "pricing": cfg["pricing"]}, f, ensure_ascii=False, indent=2)
            print("  ✓ 文案生成 → listing.json")
            return
        except Exception as e:
            print(f"  ! LLM 调用失败：{e}，降级为提示词文件")
    md = (f"# 文案生成提示词（粘给任意大模型 / TRAE）\n\n"
          f"## System\n{cfg['prompts']['copy_system']}\n\n"
          f"## User\n{cfg['prompts']['copy_user'].replace('{data}', data_json)}\n\n"
          f"## 拿到结果后\n把模型输出的 JSON 保存为 `{folder}\\listing.json`，结构："
          "`{\"item_id\":..., \"listing\":{...模型输出...}}`，然后重跑 `python run.py {folder}`")
    p = os.path.join(folder, "copy_prompt.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  ✓ 未配置文案模型：提示词已生成 → copy_prompt.md")

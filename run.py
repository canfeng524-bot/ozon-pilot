# -*- coding: utf-8 -*-
"""
Ozon 上架流水线主入口
用法：
  python run.py <1688商品链接>            # 全自动：链接 → 商品文件夹 → 上架包
  python run.py <商品文件夹路径>           # 半自动：已有油猴JSON/图片 → 继续后续处理
  python run.py <...> --skip-ai           # 跳过所有AI环节（只用真实素材+程序排版）
"""
import sys, os, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, HERE)
LOCAL_DEPS = os.path.join(HERE, ".deps")
if os.path.isdir(LOCAL_DEPS):
    sys.path.insert(0, LOCAL_DEPS)

from pipeline import fetch, download, screen, compose, copy, render


def load_cfg():
    import yaml
    with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skip_ai = "--skip-ai" in sys.argv
    refresh_images = "--refresh-images" in sys.argv
    if not args:
        print(__doc__)
        return
    cfg = load_cfg()
    target = args[0]

    # ── ① 输入：链接 or 文件夹 ──────────────────────────
    if target.startswith("http"):
        log(f"输入为链接，抓取商品数据：{target}")
        folder = fetch.run(cfg, target)
        if not folder:
            log("抓取失败，退出。可改用油猴脚本提取JSON后放入文件夹，重跑。")
            return
    else:
        folder = os.path.abspath(target)
        if not os.path.isdir(folder):
            log(f"文件夹不存在：{folder}")
            return
    info_path = fetch.find_info(folder)
    if not info_path:
        log("文件夹里没有 info*.json（油猴提取或链接抓取的货源数据），无法继续。")
        return
    info = json.load(open(info_path, encoding="utf-8"))
    if refresh_images:
        try:
            n_main, n_detail = fetch.refresh_images(info)
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
            log(f"已刷新公开图片 URL：主图 {n_main} 张 / 详情图 {n_detail} 张；已保留原有商品字段")
        except Exception as e:
            log(f"图片 URL 刷新失败：{e}；继续使用现有图片数据")
    log(f"商品文件夹：{folder}")

    # ── ② 下载源图 ──────────────────────────────────────
    src_dir = download.run(cfg, folder, info)
    log(f"源图就绪：{src_dir}")

    # ── ③ 筛选 ──────────────────────────────────────────
    screen_result = screen.run(cfg, folder, info, skip_ai=skip_ai)
    log(f"筛选完成：核心 {len(screen_result.get('core', []))} 张 / 弃用 {len(screen_result.get('drop', []))} 张")

    # ── ④ 图片合成（真实素材 + 程序排版；AI 槽位按配置） ──
    compose.run(cfg, folder, info, screen_result, skip_ai=skip_ai)

    # ── ⑤ 俄语文案 ──────────────────────────────────────
    copy.run(cfg, folder, info, skip_ai=skip_ai)

    # ── ⑥ 审核页 + XLSX ─────────────────────────────────
    render.run(cfg, folder, info)
    log("完成 ✔  打开 review.html 审核，确认后用 ozon_listing.xlsx 上架")


if __name__ == "__main__":
    main()

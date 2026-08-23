// ==UserScript==
// @name         商品信息提取器（1688/拼多多 → info.json）
// @namespace    ozon-intake
// @version      1.3.4
// @description  在1688/拼多多商品页一键提取标题、价格、类目、属性、SKU、图片URL（含详情长图），生成JSON配合Ozon上架流水线
// @match        https://detail.1688.com/offer/*
// @match        https://offer.m.1688.com/offer/*
// @match        https://m.1688.com/offer/*
// @match        https://desc.1688.com/*
// @match        https://mobile.yangkeduo.com/goods*
// @match        https://yangkeduo.com/goods*
// @match        https://mobile.pinduoduo.com/goods*
// @run-at       document-idle
// @grant        GM_setClipboard
// @grant        GM_xmlhttpRequest
// @connect      desc.1688.com
// @connect      callback.1688.com
// @connect      detail.1688.com
// @connect      itemcdn.tmall.com
// ==/UserScript==

/*
 * v1.3.3 新增：
 * - 两跳抓取真详情长图：第一跳 desc.1688.com 里只有模板小图标和主图缩略图；
 *   真正的详情数据在其 detailUrl 字段（itemcdn.tmall.com/...），第二跳抓取该
 *   数据文件（offer_details JSON）并按顺序提取全尺寸详情图
 * - toFullSize 支持 1688 缩略图变体（.220x220/.310x310/.search/.summ）还原，
 *   变体与主图 URL 归一后自动去重，不再混入 detail_images
 * - 噪音过滤补充：视频封面(tbvideo)、tfs 小图标
 *
 * v1.3.2 新增：
 * - 补 @connect 声明（v1.3.1 缺失导致 TM 跨域确认/静默失败）
 * - 详情地址兜底构造：desc.1688.com/offer/{id}.html 与
 *   callback.1688.com/offer/ajax/detailDescription.html?offerId={id}
 * - 抓取诊断日志：面板状态行显示每个地址的 HTTP 状态/字节数/图片数
 *
 * v1.3.1 新增：
 * - 详情长图改为「主页面跨域抓取」：从 DOM/内联脚本中定位详情 iframe 地址
 *   （desc.1688.com），GM_xmlhttpRequest 直接抓取该页面并解析图片 URL，
 *   不再依赖 Tampermonkey 是否成功注入 iframe（帧注入 postMessage 通道保留作兜底）
 * - 修正 extractor 版本常量（v1.3.0 漏改导致输出仍显示 1.2.0）
 *
 * v1.3.0 新增：
 * - 详情长图采集：脚本注入商品描述 iframe（desc.1688.com），帧内收集图片
 *   并 postMessage 发回主页面合并进 detail_images；提取前需滚动到详情区让其加载
 * - 移除 @noframes 以支持 iframe 注入
 *
 * v1.2.0 新增：
 * - 属性表 DOM 解析：全局变量拿不到结构化数据时（1688新版异步接口页面），
 *   直接解析页面「商品属性」区（材质/尺寸/颜色/容量/风格等键值对）
 * - SKU 规格解析：SKU 选择区 + 颜色类属性值拆分双路兜底
 * - 件重尺表解析：包装信息表中的 重量(g)/长(cm)/宽(cm)/高(cm) → logistics 字段
 *
 * v1.1.0 修复：
 * - 1688 优先遍历 runParams（商品数据），避免 __INIT_DATA__（页面外壳）里的公司名/广告图混入
 * - 图片过滤 tps-/gg_dtc 等 UI 资源与小尺寸图
 * - 价格支持区间文本（如 "2.50~3.20"）；DOM 价格优先取 price 类元素
 * - 标题过滤公司名（有限公司/旗舰店等）
 * - 提高遍历预算，属性/SKU 更完整
 *
 * 用法：
 * 1. Tampermonkey → 管理面板 → 编辑本脚本 → 全选粘贴新版本 → Ctrl+S
 * 2. 打开 1688 / 拼多多 商品详情页，点右下角「提取商品JSON」
 * 3. 在弹出面板核对/微调（可直接编辑JSON文本）→ 复制 或 下载
 * 4. JSON 与插件下载的图片放进同一商品文件夹（intake/日期_品名/），流水线读取文件夹内第一个 .json
 */

(function () {
  'use strict';

  var CDN_HOST_RE = /(?:alicdn\.com|1688\.com|pddpic\.com|yangkeduo\.com|pinduoduo\.com)/i;
  var URL_RE = /https?:\/\/[^\s"'`<>\\]+/g;

  // ---------- 顶层/帧内 模式分流 ----------

  var IS_TOP = (function () {
    try { return window.top === window.self; } catch (e) { return false; }
  })();

  if (!IS_TOP) {
    // 帧内模式：详情 iframe 内收集图片，滚动/懒加载后持续补发，最终合并进主页面 detail_images
    var SENT = new Set();
    var frameScan = function () {
      var urls = [];
      var imgs = document.images || [];
      for (var i = 0; i < imgs.length && urls.length < 200; i++) {
        var im = imgs[i];
        var u = cleanUrl(im.currentSrc || im.src || im.getAttribute('data-src') || im.getAttribute('data-lazy-src') || '');
        if (!u || !CDN_HOST_RE.test(u) || !isImageUrl(u) || isNoiseUrl(u)) continue;
        u = toFullSize(u);
        if (!SENT.has(u)) { SENT.add(u); urls.push(u); }
      }
      var html = (document.body && document.body.innerHTML) || '';
      var found = html.match(URL_RE) || [];
      for (var j = 0; j < found.length && urls.length < 200; j++) {
        var u2 = cleanUrl(found[j]);
        if (!u2 || !CDN_HOST_RE.test(u2) || !isImageUrl(u2) || isNoiseUrl(u2)) continue;
        u2 = toFullSize(u2);
        if (!SENT.has(u2)) { SENT.add(u2); urls.push(u2); }
      }
      if (urls.length) {
        try { window.parent.postMessage({ __ozonIntake: true, type: 'detail-images', urls: urls }, '*'); } catch (e) { /* cross-origin blocked */ }
      }
    };
    var frameTries = 0;
    var frameTimer = setInterval(function () {
      frameScan();
      if (++frameTries >= 20) clearInterval(frameTimer);
    }, 1500);
    frameScan();
    return;
  }

  var PLATFORM = /1688\.com/.test(location.hostname) ? '1688' : 'pdd';
  // 直接打开 desc.1688.com 标签页时无主页面可回传，不挂UI
  if (/^desc\./.test(location.hostname)) return;

  // 接收详情 iframe（帧内模式）发回的详情长图 URL（兜底通道）
  var detailFromFrame = [];
  // 第二跳（offer_details 数据文件）提取的详情长图，保序，优先使用
  var detailOrdered = [];
  window.addEventListener('message', function (e) {
    var data = e.data;
    if (!data || data.__ozonIntake !== true || data.type !== 'detail-images' || !Array.isArray(data.urls)) return;
    for (var i = 0; i < data.urls.length; i++) {
      var u = cleanUrl(data.urls[i]);
      if (!CDN_HOST_RE.test(u) || !isImageUrl(u) || isNoiseUrl(u)) continue;
      u = toFullSize(u);
      if (detailFromFrame.indexOf(u) === -1) detailFromFrame.push(u);
    }
  });

  var GLOBAL_PRIORITY = {
    '1688': ['runParams', '__INIT_DATA__', 'detailData', 'g_data'],
    'pdd': ['rawData', '__RAW_OPTIONS__', '__STORE_DATA__', '__INIT_DATA__', 'runParams', 'detailData']
  };

  // ---------- 详情长图：主页面跨域抓取（v1.3.1） ----------

  var descFetchDone = false;

  function findDescUrls() {
    var urls = [];
    try {
      var fr = document.querySelectorAll('iframe');
      for (var i = 0; i < fr.length; i++) {
        var s = fr[i].getAttribute('src') || '';
        if (/desc\.1688\.com|iframeBridge/i.test(s)) urls.push(s);
      }
    } catch (e) { /* skip */ }
    try {
      var html = ((document.documentElement && document.documentElement.innerHTML) || '').replace(/\\\//g, '/');
      var m = html.match(/(?:https?:)?\/\/desc\.1688\.com[^\s"'`<>{}()]+/g) || [];
      for (var j = 0; j < m.length; j++) urls.push(m[j]);
    } catch (e) { /* skip */ }
    var uniq = [];
    for (var k = 0; k < urls.length; k++) {
      var u = cleanUrl(urls[k]);
      if (u.indexOf('//') === 0) u = 'https:' + u;
      if (!/^https?:\/\/(desc\.1688\.com|callback\.1688\.com)\//i.test(u)) continue;
      if (uniq.indexOf(u) === -1) uniq.push(u);
    }
    // 兜底：DOM 里找不到详情地址时，按 1688 固定规律直接构造
    var oid = itemId();
    if (oid) {
      var c1 = 'https://desc.1688.com/offer/' + oid + '.html';
      var c2 = 'https://callback.1688.com/offer/ajax/detailDescription.html?offerId=' + oid;
      if (uniq.indexOf(c1) === -1) uniq.push(c1);
      if (uniq.indexOf(c2) === -1) uniq.push(c2);
    }
    return uniq.slice(0, 4);
  }

  function harvestDescHtml(text, toOrdered) {
    var n = 0;
    var t = String(text || '').replace(/\\\//g, '/');
    var all = (t.match(URL_RE) || []).concat(
      (t.match(/\/\/(?:cbu0?1?\.alicdn\.com|img\.alicdn\.com|gw\.alicdn\.com)\/[^\s"'`<>{}()]+/g) || [])
        .map(function (u) { return 'https:' + u; })
    );
    var sink = toOrdered ? detailOrdered : detailFromFrame;
    for (var i = 0; i < all.length && sink.length < 100; i++) {
      var u = cleanUrl(all[i]);
      if (!/^https?:\/\//.test(u) || !CDN_HOST_RE.test(u) || !isImageUrl(u) || isNoiseUrl(u)) continue;
      u = toFullSize(u);
      if (sink.indexOf(u) === -1 && detailOrdered.indexOf(u) === -1 && detailFromFrame.indexOf(u) === -1) { sink.push(u); n++; }
    }
    return n;
  }

  function fetchDescPages(cb) {
    if (typeof GM_xmlhttpRequest !== 'function') {
      cb(0, '缺少 GM_xmlhttpRequest（请确认已保存最新版脚本）', '');
      return;
    }
    var urls = findDescUrls();
    if (!urls.length) { cb(0, '未找到详情页地址', ''); return; }
    var left = urls.length, added = 0, log = [], dataUrls = [];
    var gx = function (u, onOk) {
      GM_xmlhttpRequest({
        method: 'GET', url: u, timeout: 15000,
        onload: function (res) { onOk(String(res.responseText || ''), res.status); },
        onerror: function () { onOk('', 0); },
        ontimeout: function () { onOk('', -1); }
      });
    };
    // 第二跳：抓 offer_details 数据文件（真详情长图）
    var hop2 = function () {
      if (!dataUrls.length) { cb(added, null, log.join('｜')); return; }
      var dl = dataUrls.slice(0, 2), l2 = dl.length;
      dl.forEach(function (du, di) {
        gx(du, function (t, st) {
          var n = 0;
          if (t) { try { n = harvestDescHtml(t, true); } catch (e) { /* skip */ } }
          added += n;
          log.push('详情数据#' + (di + 1) + ': HTTP' + st + '，+' + n + '图');
          if (--l2 === 0) cb(added, null, log.join('｜'));
        });
      });
    };
    // 第一跳：desc.1688.com 页面，定位 detailUrl
    urls.forEach(function (u, idx) {
      gx(u, function (t, st) {
        var m = t.replace(/\\\//g, '/').match(/"detailUrl"\s*:\s*"(https?:\/\/[^"]+)"/);
        if (m && dataUrls.indexOf(m[1]) === -1) dataUrls.push(m[1]);
        var n = 0;
        if (t) { try { n = harvestDescHtml(t, false); } catch (e) { /* skip */ } }
        added += n;
        log.push('#' + (idx + 1) + ': HTTP' + st + '，' + t.length + '字节' + (m ? '，detailUrl已定位' : ''));
        if (--left === 0) hop2();
      });
    });
  }

  var PDD_CENTS_KEYS = ['minNormalPrice', 'maxNormalPrice', 'minGroupPrice', 'maxGroupPrice', 'minOnSalePrice', 'maxOnSalePrice', 'minMultiPrice', 'maxMultiPrice'];
  var TITLE_SEG = ['subject', 'goodsname', 'goods_name', 'title'];
  var COMPANY_RE = /(有限公司|有限责任公司|股份有限公司|旗舰店|专卖店|专营店|百货|商贸|实业|集团|批发部|制品厂|加工厂)/;

  // ---------- URL 工具 ----------

  function cleanUrl(raw) {
    var u = String(raw).trim();
    u = u.replace(/^[\s`'"()]+|[\s`'"()]+$/g, '');
    if (u.indexOf('//') === 0) u = 'https:' + u;
    u = u.split('?')[0].split('#')[0];
    return u;
  }

  function isImageUrl(u) {
    return /\.(?:jpg|jpeg|png|webp|gif|bmp)(?:_|$)/i.test(u);
  }

  function isNoiseUrl(u) {
    if (/[-_]tps[-_]/i.test(u)) return true;              // 站点 UI 资源：tps-288-56.png 等
    if (/gg_dtc|logo|icon|sprite|avatar|widget|\.svg/i.test(u)) return true; // 广告/图标
    if (/\.gif$/i.test(u)) return true;
    if (/tbvideo/i.test(u)) return true;                  // 视频封面
    if (/tfs\/[A-Za-z0-9]+-\d{2,3}-\d{2,3}\.(?:png|gif|jpg)$/i.test(u)) return true; // tfs 小图标
    var m = u.match(/[-_](\d{2,4})x(\d{2,4})[-_.]/);
    return !!(m && Math.min(+m[1], +m[2]) <= 200);
  }

  function toFullSize(u) {
    var m = u.match(/^(https?:\/\/[^\s"'`<>]+?\.(?:jpg|jpeg|png|webp))(?:_[\w.]+)?$/i);
    if (m) u = m[1];
    // 1688 缩略图变体：xxx-cib.220x220.jpg / .search.jpg / .summ.jpg / .310x310.jpg → 还原全尺寸
    m = u.match(/^(https?:\/\/.+)\.(?:\d{2,4}x\d{2,4}|search|summ|b2b)\.(jpg|jpeg|png|webp)$/i);
    return m ? (m[1] + '.' + m[2]) : u;
  }

  function classifyPath(path) {
    var s = path.toLowerCase();
    if (/desc|detail/.test(s)) return 'detail';
    if (/thumb|main|gallery|slider|carousel|banner|headimg|imgs|images|imagelist|mainpic|photo/.test(s)) return 'main';
    return 'other';
  }

  // ---------- 结构化数据提取（页面全局变量深遍历） ----------

  function collectFromGlobals() {
    var out = { imgs: new Map(), titles: [], prices: [], attrs: [], skus: [] };
    var names = GLOBAL_PRIORITY[PLATFORM];

    for (var ci = 0; ci < names.length; ci++) {
      var root = null;
      try { root = window[names[ci]]; } catch (e) { root = null; }
      if (!root || typeof root !== 'object') continue;

      var budget = 150000;
      var seen = new Set();
      var walk = function (node, path, depth) {
        if (budget <= 0 || node == null || depth > 16) return;
        if (typeof node !== 'object') {
          if (typeof node === 'string') {
            harvestString(node, path, out.imgs);
            maybeTitle(node, path, out.titles);
            maybePrice(node, path, out.prices);
          } else if (typeof node === 'number') {
            maybePrice(node, path, out.prices);
          }
          return;
        }
        if (seen.has(node)) return;
        seen.add(node);
        budget--;
        collectStructured(node, path, out);
        var keys = Object.keys(node);
        for (var i = 0; i < keys.length; i++) {
          try { walk(node[keys[i]], path + '.' + keys[i], depth + 1); } catch (e) { /* skip */ }
        }
      };
      walk(root, names[ci], 0);

      // 已从高优先级数据源拿到完整商品信息，跳过外壳/广告数据，避免混入噪声
      var imgCount = 0;
      out.imgs.forEach(function () { imgCount++; });
      var hasGoodTitle = out.titles.some(function (t) { return !t.company; });
      if (hasGoodTitle && out.prices.length && imgCount >= 3) break;
    }
    return out;
  }

  function harvestString(s, path, imgs) {
    if (s.length < 12 || s.length > 1500 || !CDN_HOST_RE.test(s)) return;
    var matches = s.match(URL_RE);
    if (!matches) return;
    for (var i = 0; i < matches.length; i++) {
      var u = cleanUrl(matches[i]);
      if (!CDN_HOST_RE.test(u) || !isImageUrl(u) || isNoiseUrl(u)) continue;
      var full = toFullSize(u);
      if (!imgs.has(full)) imgs.set(full, classifyPath(path));
    }
  }

  function maybeTitle(s, path, titles) {
    if (s.length < 6 || s.length > 200) return;
    var seg = path.toLowerCase().split('.').pop();
    if (TITLE_SEG.indexOf(seg) === -1) return;
    titles.push({ k: seg, v: s.trim(), company: COMPANY_RE.test(s) });
  }

  function parsePriceText(s) {
    var m = String(s).match(/(\d+(?:\.\d+)?)\s*[~～至]\s*(\d+(?:\.\d+)?)/);
    if (m) return [parseFloat(m[1]), parseFloat(m[2])];
    m = String(s).match(/^\s*[¥￥\s]*(\d+(?:\.\d+)?)\s*元?\s*$/);
    if (m) return [parseFloat(m[1])];
    return null;
  }

  function pushPrice(v, prices) {
    if (!isFinite(v) || v < 0.1 || v > 100000) return;
    prices.push({ src: 'global', value: v });
  }

  function maybePrice(val, path, prices) {
    var seg = path.toLowerCase().split('.').pop();
    if (PLATFORM === 'pdd' && PDD_CENTS_KEYS.indexOf(seg) !== -1) return; // 已按分转换，避免重复计入
    if (!/price/i.test(path)) return;
    if (typeof val === 'string') {
      var range = parsePriceText(val);
      if (!range) return;
      for (var i = 0; i < range.length; i++) pushPrice(range[i], prices);
      return;
    }
    if (typeof val !== 'number') return;
    pushPrice(val, prices);
  }

  function collectStructured(node, path, out) {
    if (PLATFORM === 'pdd') {
      for (var i = 0; i < PDD_CENTS_KEYS.length; i++) {
        var v = node[PDD_CENTS_KEYS[i]];
        if (typeof v === 'number' && v > 10) out.prices.push({ src: 'pdd-raw', value: v / 100 });
      }
    }
    if (Array.isArray(node)) {
      if (/\.skus?$/i.test(path)) {
        for (var j = 0; j < node.length; j++) collectSkuItem(node[j], out);
      }
      return;
    }
    collectAttrPair(node, path, out);
  }

  function collectAttrPair(node, path, out) {
    if (!/(prop|attr|param|spec|feature)/i.test(path)) return;
    var name = pickStr(node, ['name', 'keyName', 'key', 'propertyName']);
    if (!name) return;
    var value = node.value != null ? node.value : (node.valueName != null ? node.valueName : null);
    if (Array.isArray(value)) {
      var parts = [];
      for (var i = 0; i < value.length; i++) {
        var it = value[i];
        var pv = (it && typeof it === 'object') ? pickStr(it, ['value', 'valueName']) : it;
        if (pv) parts.push(String(pv));
      }
      value = parts.join('、');
    }
    if (typeof value !== 'string' || !value || value.length > 80) return;
    out.attrs.push({ name: name, value: value });
  }

  function pickStr(obj, keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = obj[keys[i]];
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
    return null;
  }

  function collectSkuItem(item, out) {
    if (!item || typeof item !== 'object') return;
    for (var i = 0; i < 6; i++) {
      var n = item['specName' + i], v = item['specValue' + i];
      if (typeof n === 'string' && n && typeof v === 'string' && v) out.skus.push({ name: n, value: v });
    }
    var n2 = pickStr(item, ['name', 'propertyName', 'specKey']);
    var v2 = pickStr(item, ['value', 'propertyValue', 'specValue']);
    if (n2 && v2) out.skus.push({ name: n2, value: v2 });
  }

  // ---------- DOM 兜底提取 ----------

  function domExtract() {
    var imgs = new Map();
    var list = document.images || [];
    for (var i = 0; i < list.length; i++) {
      var im = list[i];
      var u = cleanUrl(im.currentSrc || im.src || im.getAttribute('data-src') || im.getAttribute('data-lazy-src') || '');
      if (!u || !CDN_HOST_RE.test(u) || !isImageUrl(u) || isNoiseUrl(u)) continue;
      var full = toFullSize(u);
      if (!imgs.has(full)) imgs.set(full, 'other');
    }
    return { imgs: imgs, title: domTitle(), price: domPrice() };
  }

  function domTitle() {
    var sels = ['h1', '[class*="title-text"]', '[class*="goods-title"]', '[class*="goodsName"]', '[class*="goods-name"]'];
    for (var i = 0; i < sels.length; i++) {
      try {
        var el = document.querySelector(sels[i]);
        var t = el ? el.textContent.trim().replace(/\s+/g, ' ') : '';
        if (t.length >= 6 && t.length <= 200 && !COMPANY_RE.test(t)) return t;
      } catch (e) { /* invalid selector, skip */ }
    }
    return document.title.replace(/\s*[-–|｜]\s*(1688|阿里巴巴|拼多多|yangkeduo)[^\s]*\s*$/i, '').trim();
  }

  function domPrice() {
    var nums = [];
    var els = document.querySelectorAll('[class*="price" i]');
    for (var i = 0; i < els.length && i < 80; i++) {
      var t = (els[i].textContent || '').trim();
      if (!t || t.length > 60) continue;
      var r = parsePriceText(t.replace(/[，,\s]+/g, ' '));
      if (r) for (var j = 0; j < r.length; j++) {
        var v = r[j];
        if (v >= 0.5 && v < 100000) nums.push(v);
      }
    }
    if (nums.length) return { min: Math.min.apply(null, nums), max: Math.max.apply(null, nums) };
    return domPriceScanBody();
  }

  function domPriceScanBody() {
    var nums = [];
    var walker = null;
    try {
      walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    } catch (e) { return null; }
    var node, cnt = 0;
    while ((node = walker.nextNode()) && cnt++ < 40000) {
      var t = node.textContent || '';
      if (t.length === 0 || t.length > 60 || !/[¥￥]/.test(t)) continue;
      var r = parsePriceText(t);
      if (r) for (var i = 0; i < r.length; i++) {
        var v = r[i];
        if (v >= 0.5 && v < 100000) nums.push(v);
      }
      if (nums.length > 3000) break;
    }
    if (!nums.length) return null;
    return { min: Math.min.apply(null, nums), max: Math.max.apply(null, nums) };
  }

  function domCategory() {
    var nodes = document.querySelectorAll('.breadcrumb a, .breadcrumb li, [class*="crumb"] a, [class*="crumb"] li, [class*="Breadcrumb"] a');
    var parts = [];
    for (var i = 0; i < nodes.length; i++) {
      var t = nodes[i].textContent.trim();
      if (t && t.length <= 20 && parts.indexOf(t) === -1) parts.push(t);
    }
    return parts.slice(0, 4).join(' > ');
  }

  function itemId() {
    var h = location.href;
    var m = h.match(/offer\/(\d{6,})\.html/) || h.match(/[?&]goods_id=(\d{6,})/) || h.match(/goods\/(\d{6,})/);
    return m ? m[1] : null;
  }

  // ---------- DOM 属性表 / SKU / 件重尺 解析（v1.2） ----------

  function isLabelLike(s) {
    if (!s || s.length < 2 || s.length > 12) return false;
    var cjk = (s.match(/[\u4e00-\u9fa5]/g) || []).length;
    return cjk >= Math.floor(s.length / 2);
  }

  function domAttributes() {
    var out = [];
    var seen = new Set();
    var sels = ['.od-attr-list li', '[class*="attr-list"] li', '[class*="attrItem"]', '[class*="attr-item"]', '[class*="value-info-item"]'];
    var nodes = [];
    for (var si = 0; si < sels.length; si++) {
      try {
        var found = document.querySelectorAll(sels[si]);
        if (found && found.length) nodes = nodes.concat(Array.prototype.slice.call(found, 0));
      } catch (e) { /* invalid selector */ }
    }
    if (!nodes.length) {
      try { nodes = Array.prototype.slice.call(document.querySelectorAll('li'), 0); }
      catch (e) { nodes = []; }
    }
    for (var i = 0; i < nodes.length && out.length < 60; i++) {
      var el = nodes[i];
      if (!el || el.children.length < 2 || el.children.length > 4) continue;
      if (el.querySelector('li, table, img')) continue;
      var name = (el.children[0].textContent || '').trim().replace(/[:：]\s*$/, '');
      var val = '';
      for (var k = 1; k < el.children.length && !val; k++) {
        val = (el.children[k].textContent || '').trim();
      }
      if (!isLabelLike(name) || !val || val.length > 80) continue;
      if (name === val) continue;
      var key = name + '|' + val;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ name: name, value: val });
    }
    return out;
  }

  var SKU_NAME_HINTS = ['颜色', '规格', '尺码', '款式', '图案', '容量', '型号'];

  function domSkuSpecs(attrs) {
    var groups = [];

    // 路径1：SKU 选择区（名称标签 + 选项按钮）
    var sels = ['[class*="sku-item-name"]', '[class*="skuItemName"]', '[class*="obj-sku"] .name', '[class*="sku-name"]', '[class*="skuLabel"]'];
    for (var si = 0; si < sels.length; si++) {
      var labels;
      try { labels = document.querySelectorAll(sels[si]); } catch (e) { continue; }
      for (var i = 0; i < labels.length; i++) {
        var name = (labels[i].textContent || '').trim().replace(/[:：]\s*$/, '');
        if (!isLabelLike(name)) continue;
        var scope = labels[i].parentElement;
        if (!scope) continue;
        var opts = scope.querySelectorAll('[class*="value"] span, [class*="value"] div, button, [class*="option"]');
        var vals = [];
        for (var j = 0; j < opts.length && vals.length < 30; j++) {
          var t = (opts[j].textContent || '').trim();
          if (t && t.length <= 30 && vals.indexOf(t) === -1 && t !== name) vals.push(t);
        }
        if (vals.length >= 1) groups.push({ name: name, values: vals });
      }
      if (groups.length) break;
    }

    // 路径2：颜色类属性值拆分（"黑色,灰蓝" → ["黑色","灰蓝"]）
    for (var a = 0; a < attrs.length && groups.length < 3; a++) {
      var hit = false;
      for (var h = 0; h < SKU_NAME_HINTS.length; h++) {
        if (attrs[a].name.indexOf(SKU_NAME_HINTS[h]) !== -1) { hit = true; break; }
      }
      if (!hit) continue;
      var parts = attrs[a].value.split(/[,，、\/|]\s*/).filter(function (p) { return p && p.length <= 30; });
      if (parts.length >= 2) groups.push({ name: attrs[a].name, values: parts });
    }

    // 路径3：包装信息表的颜色/尺码列（每行一个 SKU 变体，静态表格最稳）
    var pkgGroups = domSkuFromPackagingTable();
    for (var p = 0; p < pkgGroups.length && groups.length < 4; p++) {
      var exists = groups.some(function (g) { return g.name === pkgGroups[p].name; });
      if (!exists) groups.push(pkgGroups[p]);
    }
    return groups;
  }

  function domSkuFromPackagingTable() {
    var out = [];
    var tables;
    try { tables = document.querySelectorAll('table'); } catch (e) { return out; }
    for (var i = 0; i < tables.length; i++) {
      var rows = tables[i].querySelectorAll('tr');
      if (rows.length < 2) continue;
      var headCells = rows[0].querySelectorAll('th, td');
      var headers = [];
      for (var h = 0; h < headCells.length; h++) headers.push((headCells[h].textContent || '').trim());
      var isPkg = headers.some(function (t) { return /重量/.test(t); }) && headers.some(function (t) { return /长|宽|高/.test(t); });
      if (!isPkg) continue;
      for (var c = 0; c < headers.length; c++) {
        var head = headers[c];
        // 数值列（长宽高/体积/重量）跳过，只取文本规格列
        if (/长|宽|高|体积|重量|价格/.test(head)) continue;
        var vals = [];
        for (var r = 1; r < rows.length && vals.length < 30; r++) {
          var cell = rows[r].querySelectorAll('td, th')[c];
          var v = cell ? (cell.textContent || '').trim() : '';
          if (v && v.length <= 40 && vals.indexOf(v) === -1) vals.push(v);
        }
        if (vals.length >= 2) out.push({ name: head, values: vals });
      }
      if (out.length) return out;
    }
    return out;
  }

  function domLogistics() {
    var tables;
    try { tables = document.querySelectorAll('table'); } catch (e) { return null; }
    for (var i = 0; i < tables.length; i++) {
      var rows = tables[i].querySelectorAll('tr');
      if (!rows.length) continue;
      var headCells = rows[0].querySelectorAll('th, td');
      var headers = [];
      for (var h = 0; h < headCells.length; h++) headers.push((headCells[h].textContent || '').trim());
      var hasWeight = headers.some(function (t) { return /重量/.test(t); });
      var hasDim = headers.some(function (t) { return /长|宽|高/.test(t); });
      if (!hasWeight && !hasDim) continue;
      var dataRow = rows.length > 1 ? rows[1] : null;
      if (!dataRow) continue;
      var cells = dataRow.querySelectorAll('td, th');
      var out = {};
      for (var c = 0; c < Math.min(headers.length, cells.length); c++) {
        var head = headers[c], txt = (cells[c].textContent || '').trim();
        var num = parseFloat(txt.replace(/[^\d.]/g, ''));
        if (!isFinite(num)) continue;
        if (/重量/.test(head)) out.weight_g = num <= 20 ? Math.round(num * 1000) : Math.round(num);
        else if (/长/.test(head)) out.length_cm = num;
        else if (/宽/.test(head)) out.width_cm = num;
        else if (/高/.test(head)) out.height_cm = num;
        else if (/体积/.test(head)) out.volume_cm3 = num;
      }
      if (out.weight_g != null || out.length_cm != null) {
        out.source = 'packaging-table';
        return out;
      }
    }
    return null;
  }

  // ---------- 汇总 ----------

  function pickTitle(titles, domTitleText) {
    var rank = { subject: 3, goodsname: 2, goods_name: 2, title: 1 };
    var good = titles.filter(function (t) { return !t.company; });
    var pool = good.length ? good : titles;
    var best = null;
    for (var i = 0; i < pool.length; i++) {
      var r = rank[pool[i].k] || 0;
      if (!best || r > best.r) best = { r: r, v: pool[i].v };
    }
    if (best && !COMPANY_RE.test(best.v)) return best.v;
    var dt = domTitleText || '';
    if (dt && !COMPANY_RE.test(dt)) return dt;
    return best ? best.v : dt;
  }

  function pickPrice(prices, domPriceObj) {
    var raw = prices.filter(function (p) { return p.src === 'pdd-raw'; });
    var list = raw.length ? raw : prices.filter(function (p) { return p.src === 'global'; });
    if (list.length) {
      var vs = list.map(function (p) { return p.value; });
      return { min: Math.min.apply(null, vs), max: Math.max.apply(null, vs), source: raw.length ? 'raw' : 'global' };
    }
    if (domPriceObj) return { min: domPriceObj.min, max: domPriceObj.max, source: 'dom' };
    return null;
  }

  function round2(x) { return Math.round(x * 100) / 100; }

  function extract() {
    var g = collectFromGlobals();
    var d = domExtract();
    var imgs = new Map(Array.from(d.imgs).concat(Array.from(g.imgs)));

    var main = [], detail = [], other = [];
    imgs.forEach(function (cls, u) {
      if (cls === 'main') main.push(u);
      else if (cls === 'detail') detail.push(u);
      else other.push(u);
    });

    // 合并详情图：优先第二跳（offer_details）的保序真图；没有时回退帧/一跳通道
    var detailPool = detailOrdered.length ? detailOrdered : detailFromFrame;
    for (var fi = 0; fi < detailPool.length && detail.length < 80; fi++) {
      var fu = detailPool[fi];
      if (detail.indexOf(fu) === -1 && main.indexOf(fu) === -1 && other.indexOf(fu) === -1) detail.push(fu);
    }

    var mainOut = main.length ? main.slice(0, 12) : other.slice(0, 12);
    var otherOut = main.length ? other.slice(0, 20) : other.slice(12, 32);

    var domAttrs = domAttributes();
    var attrMap = new Map();
    var pushAttr = function (a) {
      var key = a.name + '|' + a.value;
      if (!attrMap.has(key)) attrMap.set(key, a);
    };
    for (var i = 0; i < g.attrs.length; i++) pushAttr(g.attrs[i]);
    for (var i2 = 0; i2 < domAttrs.length; i2++) pushAttr(domAttrs[i2]);
    var attrList = Array.from(attrMap.values()).slice(0, 40);

    var skuGroups = new Map();
    for (var j = 0; j < g.skus.length; j++) {
      var s = g.skus[j];
      if (!skuGroups.has(s.name)) skuGroups.set(s.name, []);
      var arr = skuGroups.get(s.name);
      if (arr.indexOf(s.value) === -1) arr.push(s.value);
    }
    var domSku = domSkuSpecs(attrList);
    for (var k = 0; k < domSku.length; k++) {
      if (!skuGroups.has(domSku[k].name)) skuGroups.set(domSku[k].name, domSku[k].values);
    }

    var price = pickPrice(g.prices, d.price);
    return {
      platform: PLATFORM,
      source_url: location.href.split('#')[0],
      item_id: itemId(),
      title: pickTitle(g.titles, d.title),
      price_cny: price ? { min: round2(price.min), max: round2(price.max), source: price.source } : null,
      category: domCategory() || null,
      main_images: mainOut,
      detail_images: detail.slice(0, 50),
      other_images: otherOut,
      attributes: attrList,
      logistics: domLogistics(),
      sku_specs: Array.from(skuGroups).slice(0, 8).map(function (pair) {
        return { name: pair[0], values: pair[1].slice(0, 30) };
      }),
      extracted_at: new Date().toISOString(),
      extractor: 'ozon-intake/1.3.4'
    };
  }

  // ---------- UI ----------

  var panel = null, taEl = null, statusEl = null, metaEl = null;

  function mountButton() {
    var btn = document.createElement('div');
    btn.textContent = '提取商品JSON';
    btn.style.cssText = [
      'position:fixed', 'right:20px', 'bottom:20px', 'z-index:2147483647',
      'background:#4B3FE3', 'color:#fff', 'padding:10px 18px',
      'border-radius:999px', 'font:500 14px/1 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
      'cursor:pointer', 'box-shadow:0 4px 14px rgba(0,0,0,.25)', 'user-select:none'
    ].join(';');
    btn.addEventListener('click', onExtract);
    (document.body || document.documentElement).appendChild(btn);
  }

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.style.cssText = [
      'position:fixed', 'right:20px', 'bottom:76px', 'z-index:2147483647',
      'width:400px', 'max-width:calc(100vw - 40px)', 'max-height:74vh', 'overflow:auto',
      'background:#fff', 'border:1px solid #e2e2ea', 'border-radius:12px',
      'box-shadow:0 10px 40px rgba(0,0,0,.2)', 'padding:14px',
      'font:13px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif', 'color:#171719',
      'box-sizing:border-box'
    ].join(';');

    var head = document.createElement('div');
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;';
    var hTitle = document.createElement('span');
    hTitle.textContent = '商品信息提取';
    hTitle.style.cssText = 'font-weight:600;font-size:14px;';
    var close = document.createElement('span');
    close.textContent = '×';
    close.style.cssText = 'cursor:pointer;font-size:20px;color:#888;padding:0 4px;line-height:1;';
    close.addEventListener('click', hidePanel);
    head.appendChild(hTitle);
    head.appendChild(close);

    metaEl = document.createElement('div');
    metaEl.style.cssText = 'margin-bottom:10px;';

    taEl = document.createElement('textarea');
    taEl.spellcheck = false;
    taEl.style.cssText = [
      'width:100%', 'height:200px', 'box-sizing:border-box',
      'font:12px/1.5 Consolas,Menlo,monospace', 'border:1px solid #e2e2ea',
      'border-radius:8px', 'padding:8px', 'resize:vertical', 'background:#fafafa', 'color:#171719'
    ].join(';');

    statusEl = document.createElement('div');
    statusEl.style.cssText = 'font-size:12px;color:#888;margin:8px 0;min-height:16px;';

    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
    var bCopy = mkBtn('复制JSON', true);
    var bDl = mkBtn('下载JSON', true);
    var bRe = mkBtn('重新提取', false);
    bCopy.addEventListener('click', copyJson);
    bDl.addEventListener('click', downloadJson);
    bRe.addEventListener('click', onExtract);
    actions.appendChild(bCopy);
    actions.appendChild(bDl);
    actions.appendChild(bRe);

    panel.appendChild(head);
    panel.appendChild(metaEl);
    panel.appendChild(taEl);
    panel.appendChild(statusEl);
    panel.appendChild(actions);
    (document.body || document.documentElement).appendChild(panel);
    return panel;
  }

  function mkBtn(text, primary) {
    var b = document.createElement('button');
    b.textContent = text;
    b.style.cssText = [
      'border-radius:8px', 'padding:7px 14px', 'cursor:pointer',
      'font:500 13px/1 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
      primary ? 'background:#4B3FE3;color:#fff;border:1px solid #4B3FE3'
              : 'background:#fff;color:#333;border:1px solid #d9d9e3'
    ].join(';');
    return b;
  }

  function onExtract() {
    ensurePanel();
    panel.style.display = 'block';
    setStatus('正在提取…', '#888');
    metaEl.innerHTML = '';
    taEl.value = '';
    descFetchDone = false;
    extractWithRetry(0);
  }

  function extractWithRetry(i) {
    var result = null;
    try { result = extract(); } catch (e) { result = null; }
    if (result && (result.title || (result.main_images && result.main_images.length))) {
      render(result);
      if (result.platform === '1688' && !result.detail_images.length && !descFetchDone) {
        descFetchDone = true;
        setStatus('已提取，正在抓取详情长图（2~15秒）…', '#b06a00');
        fetchDescPages(function (added, err, log) {
          var again = null;
          try { again = extract(); } catch (e) { again = null; }
          if (again && again.detail_images.length) {
            render(again);
            setStatus('提取完成，详情长图 ' + again.detail_images.length + ' 张已并入', '#1a7f37');
          } else if (err) {
            setStatus('提取完成；详情图抓取失败：' + err, '#c0392b');
          } else {
            setStatus('提取完成；详情图 0 张' + (log ? '｜' + log : '') + '（若TM弹出跨域确认框请选「总是允许」，再点「重新提取」）', '#c0392b');
          }
        });
      }
      return;
    }
    if (i < 2) {
      setStatus('页面数据未就绪，1.5秒后重试（' + (i + 2) + '/3）…', '#b06a00');
      setTimeout(function () { extractWithRetry(i + 1); }, 1500);
      return;
    }
    setStatus('未提取到商品数据：请确认页面已加载完成并处于登录状态', '#c0392b');
  }

  function render(result) {
    var rows = [
      ['平台', result.platform],
      ['商品ID', result.item_id || '-'],
      ['标题', result.title || '-'],
      ['价格', result.price_cny ? ('¥' + result.price_cny.min + ' ~ ' + result.price_cny.max + '（来源：' + result.price_cny.source + '）') : '-'],
      ['图片', '主图 ' + result.main_images.length + ' / 详情 ' + result.detail_images.length + ' / 其他 ' + result.other_images.length],
      ['属性', result.attributes.length + ' 条' + (result.attributes.length ? '：' + result.attributes.slice(0, 6).map(function (a) { return a.name; }).join('/') : '')],
      ['件重尺', result.logistics ? [result.logistics.weight_g != null ? result.logistics.weight_g + 'g' : '', result.logistics.length_cm != null ? result.logistics.length_cm + '×' + (result.logistics.width_cm || '?') + '×' + (result.logistics.height_cm || '?') + 'cm' : ''].filter(Boolean).join(' / ') : '-'],
      ['SKU', result.sku_specs.length ? result.sku_specs.map(function (s) { return s.name + '×' + s.values.length; }).join('，') : '-']
    ];
    metaEl.innerHTML = '';
    for (var i = 0; i < rows.length; i++) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:8px;margin:2px 0;';
      var lab = document.createElement('span');
      lab.textContent = rows[i][0];
      lab.style.cssText = 'flex:0 0 52px;color:#888;font-size:12px;';
      var val = document.createElement('span');
      val.textContent = String(rows[i][1]);
      val.style.cssText = 'flex:1;word-break:break-all;font-size:12px;';
      row.appendChild(lab);
      row.appendChild(val);
      metaEl.appendChild(row);
    }
    taEl.value = JSON.stringify(result, null, 2);
    var hint = (result.platform === '1688' && !result.detail_images.length)
      ? '；详情图自动抓取中，稍候…'
      : '';
    setStatus('提取完成，可直接编辑JSON后再复制/下载' + hint, '#1a7f37');
  }

  function copyJson() {
    var text = taEl.value;
    if (!text) return;
    if (typeof GM_setClipboard === 'function') {
      GM_setClipboard(text, 'text');
      toast('已复制到剪贴板');
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast('已复制到剪贴板');
      }, legacyCopy);
    } else {
      legacyCopy();
    }
  }

  function legacyCopy() {
    taEl.select();
    try {
      document.execCommand('copy');
      toast('已复制到剪贴板');
    } catch (e) {
      toast('复制失败，请在文本框手动全选复制');
    }
  }

  function downloadJson() {
    var text = taEl.value;
    if (!text) return;
    var id = itemId() || String(Date.now()).slice(-6);
    var name = 'info_' + PLATFORM + '_' + id + '.json';
    var blob = new Blob([text], { type: 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { a.remove(); URL.revokeObjectURL(url); }, 100);
    toast('已下载 ' + name);
  }

  function hidePanel() {
    if (panel) panel.style.display = 'none';
  }

  function setStatus(msg, color) {
    statusEl.textContent = msg;
    statusEl.style.color = color || '#888';
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = [
      'position:fixed', 'top:24px', 'left:50%', 'transform:translateX(-50%)',
      'z-index:2147483647', 'background:rgba(23,23,25,.88)', 'color:#fff',
      'padding:8px 18px', 'border-radius:8px',
      'font:13px/1 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
      'transition:opacity .4s', 'pointer-events:none'
    ].join(';');
    (document.body || document.documentElement).appendChild(t);
    setTimeout(function () { t.style.opacity = '0'; }, 1600);
    setTimeout(function () { t.remove(); }, 2100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountButton, { once: true });
  } else {
    mountButton();
  }
})();

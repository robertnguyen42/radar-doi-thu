#!/usr/bin/env python3
"""Theo dõi đối thủ ngành định cư theo 4Ps.
Nguồn mỗi công ty: RSS website (WordPress /feed) + Google News + trang chủ.
Ghi: data/items.json (lịch sử bài, cộng dồn), data/latest.json (phân tích tuần), data/weeks/<tuần>.json.
Chỉ dùng thư viện chuẩn Python."""
import json, re, html, hashlib, time, sys
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
KEEP_DAYS = 365
WINDOW = 90            # hồ sơ công ty dựa trên bài 90 ngày gần nhất
RELEVANT = re.compile(r"định cư|di trú|visa(?! signature| platinum| infinite)|thị thực|quốc tịch|thẻ xanh|thường trú|du học|hộ chiếu|golden visa|EB-?5|immigra|migra|citizenship|residen", re.I)
GENERIC = {"định cư", "đầu tư", "cập nhật", "nhà đầu tư", "hồ sơ", "chương trình", "quốc tế", "đề xuất", "quy định", "khách hàng", "thành công", "mới nhất", "lộ trình", "gia đình", "xử lý", "an toàn"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
NS = {"content": "http://purl.org/rss/1.0/modules/content/"}
NOW = datetime.now(timezone.utc)
NUM_PREFIX = r"(?:visa|subclass|diện|thị thực|loại|chương trình)"


def get(url, timeout=25):
    for i in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            err = e
            time.sleep(2)
    print(f"  ! {url[:80]}: {err}", file=sys.stderr)
    return ""


def clean(s):
    s = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def rx(words):
    """Số thuần (188, 482) chỉ khớp khi có 'visa/subclass/diện' đi kèm để tránh nhầm với giá tiền."""
    parts = []
    for w in words:
        if w.isdigit():
            parts.append(rf"{NUM_PREFIX}\s*(?:\d+\s*/\s*)*{w}\b|\b{w}\s*(?:/\s*\d+\s*)*visa")
        else:
            parts.append(rf"(?<!\w){w}")
    return re.compile("|".join(parts), re.I)


def load_tax():
    t = json.loads((ROOT / "taxonomy.json").read_text("utf-8"))
    progs = {}
    for c, v in t["programs"].items():
        for pid, p in v["items"].items():
            progs[pid] = {"country": c, "name": p["name"], "re": rx(p["kw"])}
    return {
        "countries": {c: {"name": v["name"], "flag": v["flag"]} for c, v in t["programs"].items()},
        "progs": progs,
        "price": re.compile("|".join(t["price"]), re.I),
        "price_terms": rx(t["price_terms"]),
        "offer": rx(t["offer"]),
        "risk": rx(t["risk"]),
        "event": rx(t["event"]),
        "places": [(p, re.compile(p, re.I)) for p in t["places"]],
        "ctypes": {k: rx(v) for k, v in t["content_types"].items()},
    }


DATE_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](20\d{2}))?\b")


def event_dates(text, pub):
    """Ngày dd/mm(/yyyy) trong bài sự kiện, chỉ lấy ngày ≥ ngày đăng và ≤ 6 tháng sau."""
    out = set()
    for d, m, y in DATE_RE.findall(text):
        try:
            dt = datetime(int(y or pub.year), int(m), int(d), tzinfo=timezone.utc)
        except ValueError:
            continue
        if not y and dt < pub - timedelta(days=1):
            dt = dt.replace(year=dt.year + 1)
        if pub - timedelta(days=1) <= dt <= pub + timedelta(days=180):
            out.add(dt.date().isoformat())
    return sorted(out)[:3]


def tag(it, tax):
    text = f"{it['title']} {it.get('summary', '')}"
    title = it["title"]
    it["programs"] = [pid for pid, p in tax["progs"].items() if p["re"].search(text)]
    p4 = []
    if it["programs"]:
        p4.append("product")
    prices = [m.group(0).strip() for m in tax["price"].finditer(text)][:4]
    offers = sorted({m.group(0).lower() for m in tax["offer"].finditer(text)})
    if prices or offers or tax["price_terms"].search(text):
        p4.append("price")
    places = [p for p, r in tax["places"] if r.search(text)]
    if places:
        p4.append("place")
    is_event = bool(tax["event"].search(title)) or (bool(tax["event"].search(text)) and bool(DATE_RE.search(text)))
    ctypes = [k for k, r in tax["ctypes"].items() if r.search(title)] or [k for k, r in tax["ctypes"].items() if r.search(text)][:1]
    if is_event or offers or "Thương hiệu / PR" in ctypes:
        p4.append("promotion")
    pub = datetime.fromisoformat(it["date"])
    it.update(p4=p4, prices=prices, offers=offers, places=places, event=is_event,
              event_dates=event_dates(text, pub) if is_event else [],
              risk=sorted({m.group(0).lower() for m in tax["risk"].finditer(text)}),
              ctype=ctypes[:2] or ["Khác"])
    return it


def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", s or "")  # kiểu dd/mm/yyyy (USIS)
        if m:
            d, mo, y = map(int, m.groups())
            try:
                return datetime(y, mo, d, 12, tzinfo=timezone.utc)
            except ValueError:
                pass
        return NOW


def parse_rss(xml, cid, src):
    out = []
    try:
        root = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        return out
    for i in root.iter("item"):
        title = clean(i.findtext("title"))
        link = (i.findtext("link") or "").strip()
        if not title or not link:
            continue
        body = clean(i.findtext("description")) + " " + clean(i.findtext("content:encoded", namespaces=NS))[:4000]
        if src == "news":
            title = re.sub(r"\s+-\s+[^-]+$", "", title)  # bỏ " - Tên báo"
            outlet = (i.find("source").text if i.find("source") is not None else "")
        else:
            outlet = ""
        out.append({"id": hashlib.md5(link.encode()).hexdigest()[:12], "company": cid, "src": src,
                    "outlet": outlet, "title": title, "url": link,
                    "date": parse_date(i.findtext("pubDate") or "").isoformat(timespec="seconds"),
                    "cats": [clean(c.text) for c in i.findall("category")][:5],
                    "summary": body[:1500]})
    return out


def news_url(q):
    return ("https://news.google.com/rss/search?" +
            urllib.parse.urlencode({"q": f"{q} when:60d", "hl": "vi", "gl": "VN", "ceid": "VN:vi"}))


SOCIAL = {"Facebook": "facebook.com", "YouTube": "youtube.com", "TikTok": "tiktok.com",
          "Zalo": "zalo.me", "Instagram": "instagram.com", "LinkedIn": "linkedin.com"}


def scan_home(c, tax):
    """Product/Place từ trang chủ: chương trình xuất hiện trên menu/trang chủ, văn phòng, kênh social."""
    raw = get(c["web"]) if c.get("web") else ""
    blocked = len(raw) < 20000 or "Just a moment" in raw[:3000]
    text = "" if blocked else clean(raw)
    links = " ".join(re.findall(r'href="([^"]+)"', raw))
    return {
        "ok": not blocked,
        "programs": {pid: len(p["re"].findall(text)) for pid, p in tax["progs"].items() if p["re"].search(text)},
        "places": [p for p, r in tax["places"] if r.search(text)],
        "channels": [n for n, d in SOCIAL.items() if d in links],
        "offers": sorted({m.group(0).lower() for m in tax["offer"].finditer(text)})[:8],
        "prices": sorted({m.group(0).strip() for m in tax["price"].finditer(text)})[:8],
    }


# ---------- Content lặp lại ----------
STOP = set("và của cho các những là có được với tại trong năm này đã từ về một khi để người theo the a of to in for".split())


def tokens(t):
    w = [x for x in re.findall(r"\w+", t.lower()) if x not in STOP and not x.isdigit()]
    return set(zip(w, w[1:])) | set(w)


def clusters(items, thr=0.45):
    """Gom tiêu đề gần giống nhau (Jaccard) → chủ đề được đăng nhiều lần."""
    groups = []
    for it in sorted(items, key=lambda x: x["date"]):
        tk = tokens(it["title"])
        for g in groups:
            if len(tk & g["tk"]) / max(1, len(tk | g["tk"])) >= thr:
                g["items"].append(it)
                g["tk"] |= tk
                break
        else:
            groups.append({"tk": set(tk), "items": [it]})
    out = []
    for g in groups:
        if len(g["items"]) < 2:
            continue
        its = g["items"]
        out.append({"title": its[-1]["title"], "count": len(its),
                    "companies": sorted({i["company"] for i in its}),
                    "first": its[0]["date"][:10], "last": its[-1]["date"][:10],
                    "urls": [i["url"] for i in its][:6]})
    return sorted(out, key=lambda x: -x["count"])


def phrases(items, min_n=3):
    """Cụm 2-4 âm tiết lặp lại trong tiêu đề → thông điệp được đẩy nhiều lần. Ưu tiên cụm dài nhất."""
    cnt = Counter()
    for it in items:
        w = [x for x in re.findall(r"[\w-]+", it["title"].lower()) if not x.isdigit()]
        grams = set()
        for n in (2, 3, 4):
            for k in range(len(w) - n + 1):
                g = w[k:k + n]
                if g[0] not in STOP and g[-1] not in STOP:
                    grams.add(" ".join(g))
        cnt.update(grams)
    cand = {g: n for g, n in cnt.items() if n >= min_n}
    # bỏ cụm ngắn nằm trong cụm dài có tần suất gần bằng ("động sản" ⊂ "bất động sản")
    keep = {g: n for g, n in cand.items()
            if not any(g != o and f" {g} " in f" {o} " and m >= 0.8 * n for o, m in cand.items())}
    out = [(g, n) for g, n in sorted(keep.items(), key=lambda x: (-x[1], -len(x[0]))) if g not in GENERIC]
    return out[:10]


def analyze(items, comps, homes, tax):
    since = (NOW - timedelta(days=WINDOW)).isoformat()
    recent = [i for i in items if i["date"] >= since]
    per = defaultdict(list)
    for i in recent:
        per[i["company"]].append(i)
    names = {c["id"]: c["name"] for c in comps}
    out = {}
    for c in comps:
        its = per[c["id"]]
        own = [i for i in its if i["src"] == "web"]
        h = homes.get(c["id"], {})
        prog_cnt = Counter(p for i in its for p in i["programs"])
        for p, n in h.get("programs", {}).items():
            prog_cnt.setdefault(p, 0)
        country_cnt = Counter(tax["progs"][p]["country"] for i in its for p in i["programs"])
        ev = [i for i in its if i["event"]]
        offers = sorted({o for i in its for o in i["offers"]} | set(h.get("offers", [])))
        prices = sorted({p for i in its for p in i["prices"]} | set(h.get("prices", [])))[:12]
        places = sorted({p for i in its for p in i["places"]} | set(h.get("places", [])))
        risks = [{"text": r, "title": i["title"], "url": i["url"]} for i in its for r in i["risk"]]
        ctype = Counter(t for i in own or its for t in i["ctype"])
        rep = clusters(its, 0.4)
        week = (NOW - timedelta(days=7)).isoformat()
        out[c["id"]] = {
            "name": c["name"], "self": c.get("self", False), "web": c.get("web"), "home_ok": h.get("ok", False),
            "posts": len(own), "news": len([i for i in its if i["src"] == "news"]),
            "posts_7d": len([i for i in own if i["date"] >= week]),
            "news_7d": len([i for i in its if i["src"] == "news" and i["date"] >= week]),
            "product": {"programs": [[p, n, h.get("programs", {}).get(p, 0)] for p, n in prog_cnt.most_common()],
                        "countries": country_cnt.most_common()},
            "price": {"prices": prices, "offers": offers},
            "place": {"places": places, "channels": h.get("channels", [])},
            "promotion": {"events": [{"title": i["title"], "url": i["url"], "date": i["date"][:10],
                                      "when": i["event_dates"]} for i in ev],
                          "content_types": ctype.most_common(), "repeated": rep[:8], "phrases": phrases(its),
                          "risks": risks[:10]},
        }
        out[c["id"]]["summary"] = verdict(out[c["id"]], tax)
    # So sánh với SI: chương trình đối thủ đang đẩy mà SI không có/ít
    me = next((c["id"] for c in comps if c.get("self")), None)
    gap = []
    if me:
        mine = {p: (n, h) for p, n, h in out[me]["product"]["programs"]}
        push = Counter()
        who = defaultdict(list)
        for cid, d in out.items():
            if cid == me:
                continue
            for p, n, h in d["product"]["programs"]:
                if n:
                    push[p] += n
                    who[p].append(names[cid])
        gap = [{"program": p, "mentions": push[p], "companies": who[p],
                "si_posts": mine.get(p, (0, 0))[0], "si_home": mine.get(p, (0, 0))[1] > 0}
               for p in sorted(push, key=lambda x: (-len(who[x]), -push[x]))]
    trend = Counter(p for i in recent for p in i["programs"])
    return {"companies": out, "gap": gap,
            "market_repeated": [g for g in clusters(recent, 0.4) if len(g["companies"]) >= 2][:15],
            "trend": [[p, n] for p, n in trend.most_common(15)]}


def verdict(d, tax):
    """Đánh giá tổng quan tự động (quy tắc), 3-5 câu ngắn."""
    s = []
    cs = d["product"]["countries"]
    if cs:
        tot = sum(n for _, n in cs)
        s.append("Trọng tâm: " + ", ".join(f"{tax['countries'][c]['name']} {round(100*n/tot)}%" for c, n in cs[:3]) + ".")
    top = [tax["progs"][p]["name"] for p, n, h in d["product"]["programs"][:3] if n]
    if top:
        s.append("Đẩy mạnh: " + ", ".join(top) + ".")
    act = d["posts"]
    s.append(f"Hoạt động content: {act} bài/90 ngày" + (" (rất mạnh)." if act >= 30 else " (trung bình)." if act >= 10 else " (thấp hoặc web chặn đọc)."))
    if d["promotion"]["events"]:
        s.append(f"{len(d['promotion']['events'])} bài sự kiện/hội thảo.")
    if d["price"]["offers"]:
        s.append("Có ưu đãi: " + ", ".join(d["price"]["offers"][:3]) + ".")
    if d["promotion"]["risks"]:
        s.append(f"⚠️ {len(d['promotion']['risks'])} câu quảng cáo dạng cam kết/đảm bảo.")
    return " ".join(s)


def week_id(d=NOW):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def main():
    tax = load_tax()
    comps = json.loads((ROOT / "companies.json").read_text("utf-8"))["companies"]
    p = DATA / "items.json"
    old = {i["id"]: i for i in json.loads(p.read_text("utf-8"))} if p.exists() else {}
    homes, new = {}, []
    for c in comps:
        print("•", c["name"])
        if c.get("feed"):
            for page in (1, 2, 3):
                x = parse_rss(get(c["feed"] + (f"?paged={page}" if page > 1 else "")), c["id"], "web")
                if c.get("link_rewrite"):
                    old_p, new_p = c["link_rewrite"]
                    for it in x:
                        it["url"] = it["url"].replace(old_p, new_p).rstrip("/")
                new += x
                if len(x) < 5:
                    break
        if c.get("q"):
            new += [i for i in parse_rss(get(news_url(c["q"])), c["id"], "news")
                    if RELEVANT.search(i["title"] + " " + i["summary"])]
        homes[c["id"]] = scan_home(c, tax)
        time.sleep(1)
    for it in new:
        old.setdefault(it["id"], it)
    cut = (NOW - timedelta(days=KEEP_DAYS)).isoformat()
    ids = {c["id"] for c in comps}
    keep = lambda i: i["src"] != "news" or RELEVANT.search(i["title"] + " " + i["summary"])
    items = [tag(i, tax) for i in old.values() if i["date"] >= cut and i["company"] in ids and keep(i)]
    items.sort(key=lambda x: x["date"], reverse=True)
    DATA.mkdir(exist_ok=True)
    (DATA / "weeks").mkdir(exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=0), "utf-8")
    res = analyze(items, comps, homes, tax)
    res.update(updated=NOW.isoformat(timespec="minutes"), week=week_id(),
               countries=tax["countries"], programs={k: {"name": v["name"], "country": v["country"]} for k, v in tax["progs"].items()},
               items=[{k: i[k] for k in ("company", "src", "outlet", "title", "url", "date", "programs", "p4", "event", "ctype", "risk")}
                      for i in items if i["date"] >= (NOW - timedelta(days=90)).isoformat()])
    prev = sorted((DATA / "weeks").glob("*.json"))
    prev = [x for x in prev if x.stem != res["week"]]
    if prev:
        pw = json.loads(prev[-1].read_text("utf-8"))
        res["prev_week"] = pw["week"]
        res["prev"] = {cid: {"posts": d["posts"], "programs": [p for p, *_ in d["product"]["programs"]]}
                       for cid, d in pw["companies"].items()}
    (DATA / "latest.json").write_text(json.dumps(res, ensure_ascii=False), "utf-8")
    snap = {k: res[k] for k in ("week", "updated", "companies", "gap", "trend")}
    (DATA / "weeks" / f"{res['week']}.json").write_text(json.dumps(snap, ensure_ascii=False), "utf-8")
    print(f"✓ {len(new)} bài lấy mới, {len(items)} bài trong lịch sử, tuần {res['week']}")


if __name__ == "__main__":
    main()

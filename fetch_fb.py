#!/usr/bin/env python3
"""Lấy bài fanpage Facebook của các công ty (trường "fb" trong companies.json) qua Apify,
chỉ giữ bài liên quan định cư/đầu tư, ghi thêm vào data/items.json (src="facebook").
Chạy trước fetch.py. Mỗi ngày 1 lần (data/fb_state.json); thiếu APIFY_TOKEN thì bỏ qua.
Chỉ dùng thư viện chuẩn Python."""
import json, os, re, sys, time, hashlib
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
STATE = DATA / "fb_state.json"
ACTOR = "apify~facebook-posts-scraper"
API = "https://api.apify.com/v2"
NOW = datetime.now(timezone.utc)
EVERY_HOURS = 20          # tối đa ~1 lần/ngày để giữ chi phí thấp
FIRST_DAYS = 30           # lần đầu lấy 30 ngày gần nhất
PER_PAGE_FIRST, PER_PAGE = 40, 15

# Bài phải nhắc tới định cư / đầu tư quốc tế / chương trình cụ thể mới được giữ
RELEVANT = re.compile(
    r"định cư|di trú|nhập cư|visa|thị thực|quốc tịch|thẻ xanh|thường trú|\bPR\b|golden visa|hộ chiếu|"
    r"EB-?[1-5]|L-?1|E-?2|NIW|startup visa|đề cử tỉnh bang|PNP|express entry|AIP|BIV|MPRP|CBI|"
    r"đầu tư (?:quốc tế|nước ngoài|định cư)|bất động sản (?:quốc tế|nước ngoài|Mỹ|Úc|Hy Lạp|Síp|Dubai|Malta)|"
    r"du học|hội thảo|tọa đàm|toạ đàm|webinar|sự kiện|expo|"
    r"Mỹ|Canada|Úc|New Zealand|Hy Lạp|Bồ Đào Nha|Malta|Síp|Latvia|Dubai|Caribe|Grenada|Thổ Nhĩ Kỳ|châu Âu|Schengen", re.I)


def api(path, data=None, timeout=60):
    req = urllib.request.Request(API + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN']}",
                                          "Content-Type": "application/json"},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def norm(u):
    u = (u or "").lower().split("?")[0].rstrip("/")
    return re.sub(r"^https?://(www\.|m\.|web\.)?facebook\.com/", "", u)


def first_line(text, n=140):
    t = re.sub(r"\s+", " ", (text or "").split("\n")[0]).strip() or re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def main():
    if not os.environ.get("APIFY_TOKEN"):
        print("Chưa có APIFY_TOKEN, bỏ qua Facebook.")
        return
    comps = json.loads((ROOT / "companies.json").read_text("utf-8"))["companies"]
    pages = {norm(c["fb"]): c["id"] for c in comps if c.get("fb")}
    state = json.loads(STATE.read_text("utf-8")) if STATE.exists() else {}
    last = datetime.fromisoformat(state["last_run"]) if state.get("last_run") else None
    if last and NOW - last < timedelta(hours=EVERY_HOURS) and not os.environ.get("FORCE_FB"):
        print(f"Facebook: đã chạy lúc {last:%Y-%m-%d %H:%M} UTC, bỏ qua (mỗi ngày 1 lần).")
        return
    since = (last - timedelta(days=2)).date().isoformat() if last else f"{FIRST_DAYS} days"
    body = {"startUrls": [{"url": c["fb"]} for c in comps if c.get("fb")],
            "resultsLimit": PER_PAGE if last else PER_PAGE_FIRST,
            "onlyPostsNewerThan": since}
    print(f"Facebook: {len(pages)} fanpage, bài từ {since}")
    run = api(f"/acts/{ACTOR}/runs", body)["data"]
    for _ in range(90):                       # chờ tối đa ~15 phút
        time.sleep(10)
        run = api(f"/actor-runs/{run['id']}")["data"]
        if run["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    if run["status"] != "SUCCEEDED":
        print(f"  ! Apify run {run['status']}", file=sys.stderr)
        return
    posts = api(f"/datasets/{run['defaultDatasetId']}/items?clean=true&format=json", timeout=120)

    p = DATA / "items.json"
    items = {i["id"]: i for i in json.loads(p.read_text("utf-8"))} if p.exists() else {}
    added = updated = dropped = 0
    for x in posts:
        cid = pages.get(norm(x.get("inputUrl"))) or pages.get(norm(x.get("facebookUrl")))
        text = x.get("text") or ""
        url = x.get("url") or x.get("topLevelUrl")
        if not cid or not url or not text:
            continue
        if not RELEVANT.search(text):
            dropped += 1
            continue
        when = x.get("time") or (datetime.fromtimestamp(x["timestamp"], timezone.utc).isoformat() if x.get("timestamp") else None)
        if not when:
            continue
        iid = hashlib.md5(url.encode()).hexdigest()[:12]
        eng = {"likes": x.get("likes") or 0, "comments": x.get("comments") or 0,
               "shares": x.get("shares") or 0, "views": x.get("viewsCount") or 0}
        if iid in items:
            items[iid]["eng"] = eng
            updated += 1
            continue
        items[iid] = {"id": iid, "company": cid, "src": "facebook", "outlet": "Facebook",
                      "title": first_line(text), "url": url,
                      "date": datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds"),
                      "cats": [], "summary": re.sub(r"\s+", " ", text)[:1500], "eng": eng}
        added += 1
    DATA.mkdir(exist_ok=True)
    p.write_text(json.dumps(sorted(items.values(), key=lambda i: i["date"], reverse=True), ensure_ascii=False, indent=0), "utf-8")
    cost = run.get("usageTotalUsd")
    state.update(last_run=NOW.isoformat(timespec="minutes"), last_posts=len(posts), last_cost_usd=cost)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    print(f"✓ Facebook: {len(posts)} bài lấy về, {added} bài mới liên quan định cư, {updated} cập nhật tương tác, "
          f"{dropped} bài không liên quan bị loại. Chi phí Apify lần này: {cost} USD")


if __name__ == "__main__":
    main()

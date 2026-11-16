#!/usr/bin/env python3
"""Báo cáo đối thủ ngắn cho BOD (HTML A4, in ra PDF bằng Chrome) từ data/latest.json.
Chỉ nội dung về đối thủ: điểm chính, chỉ số, xu hướng, bản đồ đối thủ, lịch sự kiện.
Dùng: python3 report_bod.py out.html"""
import json, re, sys, html
from datetime import date, timedelta
from pathlib import Path

L = json.loads((Path(__file__).parent / "data" / "latest.json").read_text("utf-8"))
a = L["ai"]
cs = L["companies"]
cs = cs if isinstance(cs, dict) else {c["id"]: c for c in cs}
name = {k: v["name"] for k, v in cs.items()}
today = date.today()


def e(s):  # bỏ chú thích [n] và escape
    return html.escape(re.sub(r"\s*\[\d+\](?:\[\d+\])*", "", s or "")).strip()


def no_si(s):  # bỏ vế so sánh với SI trong câu tiêu điểm
    s = re.split(r"[,;]? trong khi [^.]*\bSI\b", s)[0]
    return re.sub(r" cao gấp [^.,]*\bSI\b", " cao nhất", s).rstrip(". ") + "."


comp = [c for c in cs.values() if not c.get("self")]
new7 = sum(c.get("posts_7d", 0) + c.get("fb_7d", 0) + c.get("news_7d", 0) for c in comp)
fb_tot = sum(c.get("fb_eng", 0) for c in comp)
fb_avg = fb_tot / max(1, sum(c.get("fb", 0) for c in comp))
high = [x for x in a["companies"] if x["threat"] == "cao"]

ev = {}  # sự kiện sắp tới, gộp trùng theo ngày + công ty
for i in L["items"]:
    v = (i.get("ai") or {}).get("event")
    if v and v["kind"] == "invite" and v.get("date") and str(today) <= v["date"] <= str(today + timedelta(days=75)):
        ev.setdefault((v["date"], i["company"]), v)
ev = sorted(ev.items())

order = {"cao": 0, "trung bình": 1, "thấp": 2}
cls = {"cao": "cao", "trung bình": "tb", "thấp": "thap"}
rows = sorted(a["companies"], key=lambda x: (order[x["threat"]], -cs.get(x["id"], {}).get("fb_eng", 0)))
dd = lambda s: f"{s[8:10]}/{s[5:7]}"
wk = L["week"]

H = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm 14mm 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1c2430; font-size: 9.6pt; line-height: 1.36; margin: 0; }}
h1 {{ font-size: 17pt; margin: 0; color: #0d2a4a; }}
.sub {{ color: #66707c; font-size: 9pt; margin: 2px 0 10px; }}
h2 {{ font-size: 11.5pt; color: #0d2a4a; border-bottom: 2px solid #c8a24a; padding-bottom: 2px; margin: 11px 0 6px; }}
.head {{ background: #0d2a4a; color: #fff; padding: 10px 13px; border-radius: 6px; font-size: 10.6pt; }}
.head b {{ color: #e8c86a; }}
.kpis {{ display: flex; gap: 8px; margin: 10px 0 2px; }}
.k {{ flex: 1; border: 1px solid #dfe3e8; border-radius: 6px; padding: 7px 9px; }}
.k .n {{ font-size: 16pt; font-weight: 700; color: #0d2a4a; }}
.k .l {{ font-size: 8.3pt; color: #66707c; }}
.k.r .n {{ color: #b3261e; }}
ul {{ margin: 0; padding-left: 17px; }} li {{ margin: 0 0 4px; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8.4pt; }}
th {{ background: #eef1f5; text-align: left; padding: 4px 6px; font-weight: 600; }}
td {{ border-bottom: 1px solid #e6e9ed; padding: 3px 5px; vertical-align: top; }}
tr {{ break-inside: avoid; }}
.t {{ display: inline-block; padding: 0 6px; border-radius: 9px; font-size: 8pt; font-weight: 600; white-space: nowrap; }}
.cao {{ background: #fbe0de; color: #b3261e; }} .tb {{ background: #fdf0d2; color: #8a5a00; }} .thap {{ background: #e3f1e5; color: #2c6e36; }}
.g {{ color: #66707c; }}
.foot {{ color: #8a929c; font-size: 8pt; margin-top: 12px; }}
</style></head><body>
<h1>Báo cáo đối thủ định cư — Tuần {wk.split('-W')[1]}/{wk[:4]}</h1>
<div class="sub">Dành cho Ban Giám đốc SI Group · Dữ liệu đến {today:%d/%m/%Y} · {len(comp)} đối thủ · Nguồn: website, fanpage Facebook, báo chí (90 ngày) · Phân tích AI</div>
<div class="head"><b>Điểm chính:</b> {e(no_si(a['headline']))}</div>
<div class="kpis">
 <div class="k"><div class="n">{new7}</div><div class="l">bài mới của đối thủ trong 7 ngày</div></div>
 <div class="k"><div class="n">{len(ev)}</div><div class="l">sự kiện đối thủ sắp diễn ra (75 ngày)</div></div>
 <div class="k r"><div class="n">{len(high)}</div><div class="l">đối thủ mức đe doạ cao: {', '.join(name[x['id']] for x in high)}</div></div>
 <div class="k"><div class="n">{fb_tot:,}</div><div class="l">tương tác Facebook của đối thủ (90 ngày, TB {fb_avg:.0f}/bài)</div></div>
</div>
<h2>1. Xu hướng thị trường</h2>
<ul>{''.join(f'<li>{e(t)}</li>' for t in a['market_trends'])}</ul>
<h2>2. Bản đồ đối thủ</h2>
<table><colgroup><col style="width:15%"><col style="width:10%"><col style="width:11%"><col style="width:64%"></colgroup>
<tr><th>Đối thủ</th><th>Đe doạ</th><th>FB 90 ngày<br>bài · tương tác</th><th>Động thái tuần này · lý do mức đe doạ</th></tr>
{''.join(f"<tr><td><b>{e(name[x['id']])}</b></td><td><span class='t {cls[x['threat']]}'>{x['threat']}</span></td><td>{cs[x['id']].get('fb', 0)} · {cs[x['id']].get('fb_eng', 0):,}</td><td>{e(x['this_week']) or '<i>Không có bài mới</i>'}<br><span class='g'>{e(x['threat_reason'])}</span></td></tr>" for x in rows)}
</table>
<h2>3. Lịch sự kiện đối thủ sắp tới</h2>
<table><colgroup><col style="width:10%"><col style="width:16%"><col style="width:56%"><col style="width:18%"></colgroup>
<tr><th>Ngày</th><th>Đối thủ</th><th>Sự kiện</th><th>Địa điểm</th></tr>
{''.join(f"<tr><td>{dd(d)}</td><td>{e(name[c])}</td><td>{e(v['name'])}</td><td>{e(v['city']) or '—'}</td></tr>" for (d, c), v in ev) or '<tr><td colspan=4>Chưa ghi nhận sự kiện sắp tới</td></tr>'}
</table>
<div class="foot">Bản đầy đủ, cập nhật mỗi giờ: robertnguyen42.github.io/radar-doi-thu · Nội dung AI tổng hợp từ bài đăng công khai, cần đối chiếu trước khi ra quyết định. Tài liệu nội bộ.</div>
</body></html>"""
Path(sys.argv[1]).write_text(H, "utf-8")

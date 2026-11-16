#!/usr/bin/env python3
"""Báo cáo đối thủ ngắn cho BOD (HTML A4, in ra PDF bằng Chrome) từ data/latest.json.
Gồm: điểm chính, chỉ số, xu hướng, bản đồ đối thủ, lịch sự kiện, SI Group so với đối thủ (không có mục đề xuất hành động).
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

# ---- SI so với đối thủ ----
si_id, si = next((k, c) for k, c in cs.items() if c.get("self"))
act = [c for c in comp if c.get("posts", 0) + c.get("fb", 0) > 0]  # bỏ đối thủ chưa có dữ liệu
nprog = lambda c: len([p for p in c["product"]["programs"] if p[1] > 0])
nev = lambda c: len(c["promotion"]["events"])
per = lambda c: c.get("fb_eng", 0) / c["fb"] if c.get("fb") else 0
METRICS = [("Bài website (90 ngày)", lambda c: c.get("posts", 0), "{:.0f}"),
           ("Bài Facebook (90 ngày)", lambda c: c.get("fb", 0), "{:.0f}"),
           ("Tương tác TB mỗi bài Facebook", per, "{:.0f}"),
           ("Bài mới 7 ngày (web + FB + báo)", lambda c: c.get("posts_7d", 0) + c.get("fb_7d", 0) + c.get("news_7d", 0), "{:.0f}"),
           ("Bài về sự kiện / hội thảo (90 ngày)", nev, "{:.0f}"),
           ("Số chương trình có nội dung", nprog, "{:.0f}")]
mrows = []
for lab, f, fmt in METRICS:
    top = max(act, key=f)
    avg = sum(f(c) for c in act) / len(act)
    rank = 1 + sum(f(c) > f(si) for c in act)
    mrows.append((lab, fmt.format(f(si)), fmt.format(avg), f"{fmt.format(f(top))} ({top['name']})", f"{rank}/{len(act) + 1}"))

tot = sum(n for _, n in si["product"]["countries"]) or 1
si_focus = ", ".join(f"{L['countries'][k]['name']} {round(100 * n / tot)}%" for k, n in si["product"]["countries"][:4])
si_items = [i for i in L["items"] if i["company"] == si_id]
pnames = {k: v["name"] for k, v in L["programs"].items()}
si_progs = [pnames[k] for k, n, _ in si["product"]["programs"] if n > 0]
THEME = re.compile(r"Family (?:Trust|Office)|tín thác|quản trị rủi ro|di sản|Plan B|gia sản|tài sản gia đình", re.I)
si_theme = sum(bool(THEME.search(i["title"])) for i in si_items)
co_theme = sorted({name[i["company"]] for i in L["items"] if i["company"] != si_id and THEME.search(i["title"])})
lead = [g for g in L["gap"] if g["si_posts"] > 0 and len(g["companies"]) <= 2]
miss = [g for g in L["gap"] if g["si_posts"] == 0 and len(g["companies"]) >= 5]
ev_comp = sum(nev(c) for c in act)
si_obs = []
if si_theme:
    si_obs.append(f"<b>Định vị khác biệt:</b> {si_theme}/{len(si_items)} bài của SI xoay quanh quản trị gia sản, di sản, Family Trust/Family Office, Plan B quốc tịch"
                  + (f"; đối thủ cũng chạm chủ đề này: {', '.join(co_theme[:5])}." if co_theme else "; chưa đối thủ nào làm chủ đề này."))
if lead:
    si_obs.append("<b>SI có mặt sớm, ít đối thủ:</b> " + "; ".join(f"{pnames[g['program']]} ({g['si_posts']} bài SI, {len(g['companies'])} đối thủ)" for g in lead) + ".")
if miss:
    si_obs.append("<b>Chương trình đối thủ đẩy mạnh, SI chưa có bài:</b> " + "; ".join(f"{pnames[g['program']]} ({len(g['companies'])} đối thủ, {g['mentions']} lượt nhắc)" for g in miss[:7]) + ".")
si_obs.append(f"<b>Sự kiện:</b> SI có {nev(si)} bài sự kiện/hội thảo trong 90 ngày; đối thủ có tổng {ev_comp} bài, nhiều nhất "
              f"{max(act, key=nev)['name']} ({nev(max(act, key=nev))}).")
si_obs.append(f"<b>Facebook:</b> SI {si.get('fb', 0)} bài, TB {per(si):.0f} tương tác/bài; TB các đối thủ {sum(per(c) for c in act) / len(act):.0f}/bài, cao nhất "
              f"{max(act, key=per)['name']} ({per(max(act, key=per)):.0f}/bài).")
prog_rows = [g for g in L["gap"] if len(g["companies"]) >= 3 or g["si_posts"] > 0][:16]

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
.si {{ background: #f6f3ea; border-left: 3px solid #c8a24a; padding: 7px 10px; border-radius: 4px; }}
h2 {{ break-after: avoid; }}
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
<h2>4. SI Group so với đối thủ</h2>
<div class="si"><b>SI Group đang triển khai (90 ngày):</b> {si.get('posts', 0)} bài website, {si.get('fb', 0)} bài Facebook ({si.get('fb_eng', 0)} tương tác), {nev(si)} bài sự kiện.
 Thị trường trọng tâm theo nội dung: {si_focus}. Chương trình có bài: {', '.join(si_progs)}.
 {('Giá/mức đầu tư đã công bố: ' + ', '.join(si['price']['prices']) + '.') if si['price']['prices'] else ''}
 Kênh: {', '.join(si['place']['channels'])}.<br><span class="g">Bài gần nhất: {'; '.join(f"{i['date'][8:10]}/{i['date'][5:7]} {e(i['title'][:70])}" for i in sorted({x['title']: x for x in si_items}.values(), key=lambda x: x['date'], reverse=True)[:4])}</span></div>
<table style="margin-top:7px"><colgroup><col style="width:34%"><col style="width:12%"><col style="width:14%"><col style="width:28%"><col style="width:12%"></colgroup>
<tr><th>Chỉ số</th><th>SI</th><th>TB đối thủ</th><th>Cao nhất</th><th>Hạng SI</th></tr>
{''.join(f"<tr><td>{a_}</td><td><b>{b_}</b></td><td>{c_}</td><td>{e(d_)}</td><td>{r_}</td></tr>" for a_, b_, c_, d_, r_ in mrows)}
</table>
<table style="margin-top:7px"><colgroup><col style="width:30%"><col style="width:12%"><col style="width:12%"><col style="width:46%"></colgroup>
<tr><th>Chương trình</th><th>Số đối thủ</th><th>Bài của SI</th><th>Đối thủ đang triển khai</th></tr>
{''.join(f"<tr><td>{e(pnames[g['program']])}</td><td>{len(g['companies'])}</td><td><span class='t {'thap' if g['si_posts'] else 'cao'}'>{g['si_posts'] or 'chưa có'}</span></td><td class='g'>{e(', '.join(g['companies']))}</td></tr>" for g in prog_rows)}
</table>
<ul style="margin-top:7px">{''.join(f'<li>{o}</li>' for o in si_obs)}</ul>
<div class="foot">Bản đầy đủ, cập nhật mỗi giờ: robertnguyen42.github.io/radar-doi-thu · Nội dung AI tổng hợp từ bài đăng công khai, cần đối chiếu trước khi ra quyết định. Tài liệu nội bộ.</div>
</body></html>"""
Path(sys.argv[1]).write_text(H, "utf-8")

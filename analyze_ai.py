#!/usr/bin/env python3
"""Phân tích bằng Claude (chạy sau fetch.py, trước build.py).
Bước 1: đọc từng bài chưa phân tích -> giá theo chương trình, sự kiện, thông điệp chính, câu rủi ro (lưu vào items.json).
Bước 2: báo cáo tuần: định vị từng đối thủ theo 4Ps, thay đổi tuần này, gợi ý hành động cho SI (lưu vào latest.json["ai"]).
Thiếu ANTHROPIC_API_KEY thì bỏ qua, không báo lỗi."""
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Literal

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MODEL = "claude-opus-5-5"
AI_VERSION = 1
CHUNK = 20
NOW = datetime.now(timezone.utc)

CONTEXT = """Bạn là chuyên viên phân tích thị trường của SI Group, công ty tư vấn định cư và bất động sản quốc tế tại Việt Nam.
Bạn theo dõi đối thủ cạnh tranh theo mô hình 4Ps (Product, Price, Place, Promotion).
Chỉ dùng thông tin có trong dữ liệu được cung cấp. Không bịa con số, ngày hay tên. Thiếu thông tin thì để trống.
Viết tiếng Việt, ngắn gọn, cụ thể."""

EXTRACT = CONTEXT + """

Với mỗi bài viết của đối thủ, trích:
- programs: tên chương trình định cư/đầu tư được bán hoặc quảng bá (ví dụ "EB-5", "Golden Visa Hy Lạp", "Startup Visa Canada"). Không liệt kê chương trình chỉ được nhắc qua.
- prices: mức đầu tư/phí/chi phí gắn với chương trình cụ thể. Bỏ các con số không phải giá bán (tiền phạt, số liệu vĩ mô, phí chính phủ đề xuất thì ghi rõ trong note).
- offers: ưu đãi, khuyến mãi, quà tặng, suất giới hạn dành cho khách.
- event: chỉ khi bài mời tham dự (invite) hoặc tổng kết (recap) một sự kiện/hội thảo/tọa đàm/webinar/chuyến khảo sát của chính công ty đó.
- content_type: loại bài.
- message: 1 câu nêu thông điệp marketing chính của bài (họ muốn khách nghĩ/làm gì).
- risk_claims: câu chữ hứa hẹn kết quả/lợi nhuận/tỷ lệ đậu (trích nguyên văn ngắn), nếu có."""

REPORT = CONTEXT + """

Viết báo cáo tuần cho ban lãnh đạo SI từ dữ liệu 90 ngày của từng đối thủ (bài đánh dấu [MỚI] là đăng trong 7 ngày qua).
- headline: 1 câu nêu điều quan trọng nhất của tuần.
- market_trends: 3-5 xu hướng chung (chương trình, thông điệp, kiểu sự kiện nhiều đối thủ cùng làm).
- companies: mỗi đối thủ (không gồm SI) một mục. this_week để trống nếu tuần này không có bài mới.
- si_actions: 3-5 hành động cụ thể SI nên làm (content, sự kiện, chương trình, giá), mỗi hành động dẫn chứng bằng số thứ tự bài [n].
So sánh với content của SI (công ty có nhãn SI) để chỉ ra khoảng trống."""

CTYPE = Literal["Tin chính sách", "Câu chuyện thành công", "Hướng dẫn / Kiến thức", "So sánh / Tư vấn chọn",
                "Sự kiện / Hội thảo", "Dự án / Chương trình", "Thương hiệu / PR", "Khác"]


def client_parse(client, **kw):
    """messages.parse với fallback phía server: nếu Opus từ chối thì API tự chạy lại bằng model khác."""
    r = client.beta.messages.parse(model=MODEL, betas=["server-side-fallback-2026-07-01"],
                                   extra_body={"fallbacks": "default"}, **kw)
    if r.stop_reason == "refusal" or r.parsed_output is None:
        print(f"  ! Claude không trả kết quả (stop_reason={r.stop_reason})", file=sys.stderr)
        return None
    return r.parsed_output


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Chưa có ANTHROPIC_API_KEY, bỏ qua phân tích AI.")
        return
    import anthropic
    from pydantic import BaseModel, Field

    class Price(BaseModel):
        program: str
        amount: str = Field(description="Ví dụ '800.000 USD', '250.000 EUR'")
        note: str = Field(description="Ngắn: điều kiện/hạn chót, hoặc để trống")

    class Event(BaseModel):
        kind: Literal["invite", "recap"]
        name: str
        date: str = Field(description="YYYY-MM-DD ngày diễn ra, để trống nếu bài không nêu")
        city: str

    class ItemAI(BaseModel):
        n: int = Field(description="Số thứ tự [n] của bài")
        programs: List[str]
        prices: List[Price]
        offers: List[str]
        event: Event | None
        content_type: CTYPE
        message: str
        risk_claims: List[str]

    class Batch(BaseModel):
        items: List[ItemAI]

    class CompanyView(BaseModel):
        id: str = Field(description="Mã công ty trong ngoặc vuông")
        positioning: str = Field(description="1-2 câu: họ định vị là ai, bán cho ai")
        this_week: str = Field(description="Thay đổi/điểm mới tuần này, trống nếu không có bài mới")
        product: str
        price: str
        place: str
        promotion: str
        threat: Literal["cao", "trung bình", "thấp"] = Field(description="Mức cạnh tranh trực tiếp với SI")
        threat_reason: str

    class Action(BaseModel):
        action: str
        why: str
        sources: List[int]

    class Report(BaseModel):
        headline: str
        market_trends: List[str]
        companies: List[CompanyView]
        si_actions: List[Action]

    client = anthropic.Anthropic()
    comps = {c["id"]: c for c in json.loads((ROOT / "companies.json").read_text("utf-8"))["companies"]}
    items = json.loads((DATA / "items.json").read_text("utf-8"))
    since = (NOW - timedelta(days=90)).isoformat()
    recent = [i for i in items if i["date"] >= since and i["company"] in comps]

    # ---- Bước 1: trích từng bài (chỉ bài web của công ty, chưa phân tích) ----
    todo = [i for i in recent if i["src"] == "web" and i.get("ai_v") != AI_VERSION]
    print(f"Bước 1: {len(todo)} bài cần phân tích")
    for k in range(0, len(todo), CHUNK):
        chunk = todo[k:k + CHUNK]
        lines = [f"[{n}] {comps[i['company']]['name']} | {i['date'][:10]} | {i['title']}\n{i.get('summary', '')[:900]}"
                 for n, i in enumerate(chunk)]
        out = client_parse(client, max_tokens=16000, output_config={"effort": "low"}, system=EXTRACT,
                           messages=[{"role": "user", "content": "\n\n".join(lines)}], output_format=Batch)
        if not out:
            continue
        for a in out.items:
            if 0 <= a.n < len(chunk):
                chunk[a.n]["ai"] = a.model_dump(exclude={"n"})
                chunk[a.n]["ai_v"] = AI_VERSION
        print(f"  ✓ {k + len(chunk)}/{len(todo)}")
    (DATA / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=0), "utf-8")

    # ---- Bước 2: báo cáo tuần ----
    week = (NOW - timedelta(days=7)).isoformat()
    ref, blocks = [], []
    for cid, c in comps.items():
        own = [i for i in recent if i["company"] == cid][:40]
        if not own:
            continue
        rows = []
        for i in own:
            ref.append(i)
            a = i.get("ai") or {}
            extra = []
            if a.get("prices"):
                extra.append("giá: " + "; ".join(f"{p['program']} {p['amount']}" for p in a["prices"]))
            if a.get("offers"):
                extra.append("ưu đãi: " + "; ".join(a["offers"]))
            if a.get("event"):
                e = a["event"]
                extra.append(f"sự kiện {e['kind']}: {e['name']} {e['date']} {e['city']}")
            if a.get("message"):
                extra.append("thông điệp: " + a["message"])
            rows.append(f"[{len(ref) - 1}]{' [MỚI]' if i['date'] >= week else ''} {i['date'][:10]} {i['src']} | "
                        f"{i['title']}" + (" || " + " | ".join(extra) if extra else ""))
        tag = " — SI (công ty của mình)" if c.get("self") else ""
        blocks.append(f"### [{cid}] {c['name']}{tag} ({c.get('web', '')})\n" + "\n".join(rows))
    try:
        rep = client_parse(client, max_tokens=16000, output_config={"effort": "medium"}, system=REPORT,
                           messages=[{"role": "user", "content": "\n\n".join(blocks)}], output_format=Report)
    except Exception as e:  # lỗi báo cáo không được làm mất kết quả bước 1
        print(f"  ! Báo cáo tuần lỗi: {e}", file=sys.stderr)
        rep = None
    latest_p = DATA / "latest.json"
    latest = json.loads(latest_p.read_text("utf-8"))
    by_url = {i["url"]: i for i in items}
    for it in latest.get("items", []):
        if by_url.get(it["url"], {}).get("ai"):
            it["ai"] = by_url[it["url"]]["ai"]
    if rep:
        r = rep.model_dump()
        r["companies"] = [x for x in r["companies"] if x["id"] in comps and not comps[x["id"]].get("self")]
        for a in r["si_actions"]:
            a["sources"] = [{"title": ref[n]["title"], "url": ref[n]["url"], "company": ref[n]["company"]}
                            for n in a["sources"] if 0 <= n < len(ref)][:4]
        r.update(model=MODEL, generated=NOW.isoformat(timespec="minutes"), week=latest.get("week"))
        latest["ai"] = r
        (DATA / "ai").mkdir(exist_ok=True)
        (DATA / "ai" / f"{r['week']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
        print(f"Bước 2: ✓ báo cáo tuần {r['week']}: {r['headline']}")
    latest_p.write_text(json.dumps(latest, ensure_ascii=False), "utf-8")


if __name__ == "__main__":
    main()

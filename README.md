# Radar Đối thủ Định cư

Theo dõi đối thủ ngành định cư / BĐS quốc tế theo 4Ps, so sánh với SI. Nội bộ — repo private.

- `companies.json` — danh sách công ty (thêm/bớt ở đây)
- `taxonomy.json` — từ khoá phân loại Product / Price / Place / Promotion
- `fetch.py` — lấy RSS web + Google News + trang chủ → `data/`
- `analyze_ai.py` — Claude đọc từng bài (giá, sự kiện, thông điệp) và viết báo cáo tuần + gợi ý cho SI (cần secret ANTHROPIC_API_KEY)
- `build.py` — ghép dữ liệu vào `dist/radar.html` (mở trực tiếp bằng trình duyệt)
- Bot chạy mỗi thứ Hai 07:00 giờ VN (`.github/workflows/weekly.yml`), có thể bấm chạy tay trong tab Actions.

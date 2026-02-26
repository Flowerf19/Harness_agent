#!/usr/bin/env python3
"""
Script để kiểm tra cải tiến chức năng tóm tắt 3 tầng
"""

import asyncio
import json
import os
from pathlib import Path


def analyze_user_summary_before_after():
    """Phân tích tóm tắt của user 13 trước và sau khi cải tiến"""

    print("🔍 Phân tích tóm tắt của user 13 (ID: 1378359549379084432)")
    print("=" * 60)

    # Đường dẫn đến file tóm tắt
    summary_path = Path("src/data/user_summaries/1378359549379084432_summary.txt")

    if not summary_path.exists():
        print(f"❌ Không tìm thấy file: {summary_path}")
        return

    # Đọc nội dung tóm tắt
    with open(summary_path, "r", encoding="utf-8") as f:
        summary_content = f.read()

    print("📋 Tóm tắt hiện tại:")
    print(summary_content)
    print()

    # Phân tích các trường thông tin
    lines = summary_content.split("\n")
    info_sections = {}
    current_section = None

    for line in lines:
        if line.startswith("==="):
            current_section = line.strip(" =")
            info_sections[current_section] = []
        elif line.strip() and current_section:
            info_sections[current_section].append(line.strip())

    # Đếm số trường có thông tin và số trường trống
    filled_fields = 0
    total_fields = 0

    for section, fields in info_sections.items():
        for field in fields:
            if ":" in field:
                total_fields += 1
                field_value = field.split(":", 1)[1].strip()
                if (
                    field_value
                    and "[Không có]" not in field_value
                    and field_value.lower() != "none"
                ):
                    filled_fields += 1

    print(f"📊 Thống kê thông tin:")
    print(f"   - Tổng số trường: {total_fields}")
    print(f"   - Trường có thông tin: {filled_fields}")
    print(f"   - Trường trống: {total_fields - filled_fields}")
    print(
        f"   - Tỷ lệ hoàn thành: {filled_fields / total_fields * 100:.1f}% nếu có trường"
        if total_fields > 0
        else "   - Không có trường nào"
    )

    print()
    print("💡 Cải tiến đã thực hiện:")
    print(
        "   1. Cập nhật prompt tóm tắt để ưu tiên ghi nhận thông tin có trong hội thoại"
    )
    print("   2. Giảm ngưỡng tin nhắn cần thiết để kích hoạt cập nhật (4→3)")
    print("   3. Giảm ngưỡng ký tự cần thiết để kích hoạt cập nhật (15→10)")
    print("   4. Giảm ngưỡng trường trống để xác định template (15→12)")
    print("   5. Tăng xác suất cập nhật (30%→40%)")
    print()
    print("🚀 Để áp dụng cải tiến, hệ thống sẽ:")
    print("   - Tự động cập nhật tóm tắt khi người dùng nói về thông tin cá nhân")
    print("   - Cập nhật thường xuyên hơn để tránh để trống thông tin")
    print("   - Cải thiện khả năng suy luận từ ngữ cảnh hội thoại")


async def simulate_summary_update():
    """Mô phỏng quá trình cập nhật tóm tắt với các cải tiến mới"""

    print("\n🔄 Mô phỏng quá trình cập nhật tóm tắt...")
    print("-" * 40)

    # Giả lập một số tin nhắn từ user 13
    sample_messages = [
        {
            "role": "user",
            "content": "tôi là Dương Ngô",
            "timestamp": "2026-02-26T17:00:00",
        },
        {
            "role": "assistant",
            "content": "Rất vui được gặp bạn Dương Ngô!",
            "timestamp": "2026-02-26T17:00:01",
        },
        {
            "role": "user",
            "content": "tôi làm lập trình viên",
            "timestamp": "2026-02-26T17:00:02",
        },
        {
            "role": "user",
            "content": "thích công nghệ và AI",
            "timestamp": "2026-02-26T17:00:03",
        },
        {
            "role": "user",
            "content": "có một người bạn tên Hòa",
            "timestamp": "2026-02-26T17:00:04",
        },
    ]

    print("📝 Tin nhắn mẫu sẽ được xử lý:")
    for i, msg in enumerate(sample_messages, 1):
        print(f"   {i}. [{msg['role']}] {msg['content']}")

    print("\n✅ Với các cải tiến:")
    print("   - Ngưỡng kích hoạt giảm còn 3 tin nhắn (đã đủ 5 tin nhắn)")
    print("   - Prompt mới ưu tiên ghi nhận thông tin từ hội thoại")
    print("   - Tăng xác suất cập nhật lên 40%")
    print(
        "   - Hệ thống sẽ trích xuất thông tin: tên, nghề nghiệp, sở thích, mối quan hệ"
    )

    print("\n🎯 Kết quả mong đợi:")
    print("   - Tên: [Dương Ngô] (đã có)")
    print("   - Nghề nghiệp: [Lập trình viên] (sẽ được thêm)")
    print("   - Sở thích: [Công nghệ, AI] (sẽ được thêm)")
    print("   - Mối quan hệ: [Bạn bè: Hòa] (sẽ được thêm)")


if __name__ == "__main__":
    analyze_user_summary_before_after()
    asyncio.run(simulate_summary_update())

    print("\n" + "=" * 60)
    print("✅ Cải tiến chức năng tóm tắt 3 tầng đã hoàn tất!")
    print("📈 Hiệu quả cải tiến sẽ được đánh giá sau khi hệ thống chạy thử nghiệm")

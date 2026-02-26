#!/usr/bin/env python3
"""
Script để rebuild lại summary cho user 13 dựa trên lịch sử hội thoại
"""

import asyncio
import json
import os

# Import các module cần thiết
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.services.qwen_service import QwenService  # hoặc service khác bạn đang dùng
from src.services.summary_service import SummaryService


async def rebuild_user_summary():
    """Rebuild lại summary cho user 13 dựa trên lịch sử hội thoại"""

    print("🔄 Bắt đầu rebuild lại summary cho user 13 (ID: 1378359549379084432)")
    print("=" * 60)

    # Đường dẫn đến file lịch sử
    history_path = Path("src/data/user_summaries/1378359549379084432_history.json")

    if not history_path.exists():
        print(f"❌ Không tìm thấy file lịch sử: {history_path}")
        return

    # Đọc lịch sử hội thoại
    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    print(f"📋 Đã đọc {len(history)} tin nhắn từ lịch sử")

    # Hiển thị một số tin nhắn mẫu
    print("\n📝 Một số tin nhắn mẫu:")
    for i, msg in enumerate(history[:5], 1):
        role = msg["role"]
        content = (
            msg["content"][:100] + "..."
            if len(msg["content"]) > 100
            else msg["content"]
        )
        print(f"   {i}. [{role}] {content}")

    if len(history) > 5:
        print(f"   ... và {len(history) - 5} tin nhắn khác")

    # Tạo instance của SummaryService
    # Lưu ý: Bạn cần cung cấp LLM service phù hợp
    try:
        # Sử dụng QwenService hoặc service khác tùy theo hệ thống của bạn
        llm_service = QwenService()  # Thay bằng service bạn đang dùng
        summary_service = SummaryService(
            llm_service=llm_service,
            prompts_dir="src/data/prompts",
            config_dir="src/config",
        )

        user_id = "1378359549379084432"

        print(f"\n🚀 Bắt đầu cập nhật summary cho user {user_id}...")

        # Gọi phương thức cập nhật summary
        new_summary = await summary_service.update_summary_smart(user_id)

        if new_summary:
            print("✅ Cập nhật summary thành công!")

            # Đọc lại file summary để so sánh
            summary_path = Path(f"src/data/user_summaries/{user_id}_summary.txt")
            if summary_path.exists():
                with open(summary_path, "r", encoding="utf-8") as f:
                    updated_summary = f.read()

                print("\n📋 Summary sau khi cập nhật:")
                print(updated_summary)

                # Phân tích sự cải thiện
                old_filled = updated_summary.count("[Không có]")
                total_fields = 19  # Tổng số trường trong cấu trúc summary
                filled_fields = total_fields - old_filled

                print(f"\n📊 Thống kê sau cập nhật:")
                print(f"   - Tổng số trường: {total_fields}")
                print(f"   - Trường có thông tin: {filled_fields}")
                print(f"   - Trường trống: {old_filled}")
                print(
                    f"   - Tỷ lệ hoàn thành: {filled_fields / total_fields * 100:.1f}%"
                )
        else:
            print(
                "❌ Không thể cập nhật summary, có thể do LLM service chưa được cấu hình đúng"
            )

    except ImportError as e:
        print(f"⚠️ Lỗi import: {e}")
        print("💡 Vui lòng kiểm tra lại module LLM service bạn đang sử dụng")

        # Trong trường hợp không thể chạy trực tiếp, chúng ta sẽ mô phỏng quá trình
        print("\n📋 Mô phỏng quá trình cập nhật với các cải tiến:")
        print("- Hệ thống sẽ đọc lịch sử hội thoại")
        print("- Áp dụng prompt mới với quy tắc ưu tiên ghi nhận thông tin")
        print("- Giảm ngưỡng kích hoạt từ 4 xuống 3 tin nhắn")
        print("- Giảm ngưỡng ký tự từ 15 xuống 10")
        print("- Giảm ngưỡng trường trống để xác định template từ 15 xuống 12")
        print("- Tăng xác suất cập nhật từ 30% lên 40%")
        print("- Kết quả dự kiến: Nhiều thông tin hơn sẽ được điền tự động")

    print("\n💡 Ghi chú: Để chạy script này hoàn chỉnh, bạn cần:")
    print("   1. Cấu hình đúng LLM service (Qwen, Ollama, v.v.)")
    print("   2. Đảm bảo API keys và endpoint được cấu hình chính xác")
    print("   3. Kiểm tra lại đường dẫn và quyền truy cập file")


if __name__ == "__main__":
    asyncio.run(rebuild_user_summary())

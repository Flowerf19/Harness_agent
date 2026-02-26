#!/usr/bin/env python3
"""
Script để sửa lỗi nhầm lẫn user trong summary.
Script này sẽ xóa các summary bị lỗi để hệ thống tạo lại từ đầu.
"""

import json
import os
import re
from typing import Dict, List


def find_potentially_confused_summaries(summaries_dir: str) -> List[str]:
    """Tìm các file summary có thể bị nhầm lẫn giữa các user"""
    confused_users = []

    # Lấy tất cả các file summary
    summary_files = [f for f in os.listdir(summaries_dir) if f.endswith("_summary.txt")]

    # Dictionary để lưu tên người dùng và user_id tương ứng
    name_to_user_ids = {}

    for summary_file in summary_files:
        user_id = summary_file.replace("_summary.txt", "")

        with open(
            os.path.join(summaries_dir, summary_file), "r", encoding="utf-8"
        ) as f:
            content = f.read()

        # Trích xuất tên từ summary
        name_match = re.search(r"Tên:\s*\[([^\]]+)\]", content)
        if name_match:
            name = name_match.group(1).strip()
            if name != "Không có":
                if name not in name_to_user_ids:
                    name_to_user_ids[name] = []
                name_to_user_ids[name].append(user_id)

    # Tìm các tên trùng lặp giữa các user_id khác nhau
    for name, user_ids in name_to_user_ids.items():
        if len(user_ids) > 1:
            print(f"⚠️  Phát hiện tên '{name}' được dùng cho nhiều user_id: {user_ids}")
            confused_users.extend(user_ids)

    return list(set(confused_users))


def reset_confused_summaries(summaries_dir: str, confused_user_ids: List[str]):
    """Reset các summary bị nhầm lẫn bằng cách xóa chúng"""
    for user_id in confused_user_ids:
        summary_file = os.path.join(summaries_dir, f"{user_id}_summary.txt")
        if os.path.exists(summary_file):
            os.remove(summary_file)
            print(f"🗑️  Đã xóa summary cho user {user_id}")
        else:
            print(f"ℹ️  Không tìm thấy summary cho user {user_id}")


def main():
    # Đường dẫn đến thư mục chứa summary
    base_dir = os.path.dirname(os.path.abspath(__file__))
    summaries_dir = os.path.join(base_dir, "src", "data", "user_summaries")

    if not os.path.exists(summaries_dir):
        print(f"❌ Thư mục {summaries_dir} không tồn tại")
        return

    print("🔍 Đang tìm các summary bị nhầm lẫn user...")
    confused_users = find_potentially_confused_summaries(summaries_dir)

    if confused_users:
        print(f"\n📋 Tìm thấy {len(confused_users)} user có thể bị nhầm lẫn:")
        for user_id in confused_users:
            print(f"  - User ID: {user_id}")

        response = input(
            f"\n🤔 Bạn có muốn reset {len(confused_users)} summary bị nhầm lẫn không? (y/N): "
        )
        if response.lower() == "y":
            reset_confused_summaries(summaries_dir, confused_users)
            print("\n✅ Hoàn thành reset các summary bị nhầm lẫn")
            print(
                "💡 Các summary sẽ được tạo lại khi người dùng tiếp tục trò chuyện với bot"
            )
        else:
            print("\n❌ Hủy bỏ thao tác reset")
    else:
        print("✅ Không tìm thấy summary bị nhầm lẫn")


if __name__ == "__main__":
    main()

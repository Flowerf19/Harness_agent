#!/usr/bin/env python3
"""
Script để chuyển đổi các file summary hiện tại sang định dạng mới
(chuyển các giá trị "None" thành "[Không có]")
"""

import os
import re

def fix_summary_file(file_path):
    """Chuyển đổi một file summary từ giá trị 'None' sang '[Không có]'"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Thay thế tất cả các trường có giá trị "None" thành "[Không có]"
        fixed_content = re.sub(r'(:\s*)None\b', r'\1[Không có]', content, flags=re.IGNORECASE)
        
        # Lưu lại file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        
        print(f"✓ Fixed summary file: {file_path}")
        return True
        
    except Exception as e:
        print(f"✗ Error fixing summary file {file_path}: {e}")
        return False

def main():
    # Đường dẫn đến thư mục chứa các file summary
    summaries_dir = os.path.join("src", "data", "user_summaries")
    
    if not os.path.exists(summaries_dir):
        print(f"Directory {summaries_dir} does not exist!")
        return
    
    # Lọc các file summary
    summary_files = [f for f in os.listdir(summaries_dir) if f.endswith('_summary.txt')]
    
    if not summary_files:
        print("No summary files found!")
        return
    
    print(f"Found {len(summary_files)} summary files to fix...")
    
    success_count = 0
    for summary_file in summary_files:
        file_path = os.path.join(summaries_dir, summary_file)
        if fix_summary_file(file_path):
            success_count += 1
    
    print(f"\nCompleted! Fixed {success_count}/{len(summary_files)} summary files.")

if __name__ == "__main__":
    main()
# src/services/memories/activate_memory/constants.py

# --- Token Management ---
MAX_WORKING_TOKENS = 2000  # Ngưỡng tối đa của RAM trước khi bị đóng băng/dọn dẹp
STRUCTURAL_OVERHEAD_TOKENS = (
    15  # Số token hao phí cho mỗi tin nhắn (do format JSON, thẻ vai trò)
)
TARGET_SAFE_TOKENS = 1000  # Sau khi dọn dẹp, RAM nên giảm về mức an toàn này

# --- Timeouts ---
SESSION_TIMEOUT_MINUTES = 30  # Im lặng bao lâu thì coi là hết 1 phiên chat

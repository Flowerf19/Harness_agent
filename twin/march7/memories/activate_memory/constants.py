# src/services/memories/activate_memory/constants.py

# --- Token Management ---
MAX_WORKING_TOKENS = 2000  # Ngưỡng tối đa của RAM trước khi bị đóng băng/dọn dẹp
CHANNEL_SUMMARY_TOKEN_LIMIT = 2000
STRUCTURAL_OVERHEAD_TOKENS = (
    15  # Số token hao phí cho mỗi tin nhắn (do format JSON, thẻ vai trò)
)
TARGET_SAFE_TOKENS = 1000  # Sau khi dọn dẹp, RAM nên giảm về mức an toàn này

# --- Summary Policy ---
SUMMARY_IDLE_MINUTES = 30
SUMMARY_MIN_MESSAGES = 30
SUMMARY_MAX_MESSAGES = 60

# --- Timeouts ---
SESSION_TIMEOUT_MINUTES = 30  # Im lặng bao lâu thì coi là hết 1 phiên chat
SUMMARY_LOCK_TTL_MINUTES = 10

# --- Cleanup ---
KEEP_RECENT_MESSAGES_AFTER_SUMMARY = 3

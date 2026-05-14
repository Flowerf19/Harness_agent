# Toolkit Reference

6 tools. Use only when needed. Default: answer from training knowledge.

---

## Quick routing

| Need | Tool |
|---|---|
| User history, preferences, past chats | `search_memory` |
| Live info, news, current events | `web_search` |
| Math, data analysis, file processing | `run_python_code` |
| Host system check: sensors, docker, logs, disk, RAM | `execute_host_bash` |
| Save user profile to Core Memory (T3) | `update_user_profile` |
| Change bot personality or communication style | `update_personality` |

---

## search_memory

Search user history in Wiki Pages (T2 consolidated memory).

| Param | Type | Detail |
|---|---|---|
| `user_id` | string (required) | Discord user ID |
| `mode` | string | `semantic` (default): search by meaning<br>`time`: search recent by days<br>`topic`: exact keyword match |
| `query` | string | Search query. Required for `semantic` mode. Be specific: `"sở thích anime"` not `"chuyện đó"` |
| `days` | integer | Days to look back. Used for `time` mode. Default 7 |
| `topic` | string | Keyword for `topic` mode. E.g. `"game"`, `"công việc"` |

---

## web_search

Live web search via Tavily API.

| Param | Type | Detail |
|---|---|---|
| `query` | string (required) | Search keywords. Include year (`2026`) or `"mới nhất"` for recency |
| `search_depth` | string | `basic` (fast, default) or `advanced` (deeper, costs more) |
| `max_results` | integer | 1–10, default 5 |
| `topic` | string | `general` (default) or `news` (breaking news) |
| `time_range` | string | `day`, `week`, `month`, `year` |
| `include_domains` | list | Whitelist domains. E.g. `["vnexpress.net"]` |
| `exclude_domains` | list | Blacklist domains |

**Rules:**
- Never use for user history → use `search_memory`
- For news queries, set `topic="news"` + `time_range="week"`

---

## run_python_code

Execute code in sandboxed Jupyter kernel (CodeBox). Stateful per user session.

| Param | Type | Detail |
|---|---|---|
| `user_id` | string (required) | Discord user ID. Per-user session isolation |
| `code` | string (required) | Code to run. No markdown ticks |
| `kernel` | string | `ipython` (default): Python code<br>`bash`: shell commands (`pip install`, `ls`, etc.) |
| `cwd` | string | Working directory. Default `/workspace` |
| `file_content` | string | Base64 file content for upload |
| `filename` | string | Filename when uploading. E.g. `"data.csv"` |
| `download_file_name` | string | Filename to download from sandbox. Returns base64 |

**Rules:**
- Variables persist across calls in same user session
- Use `ipython` for: math, data analysis, numpy, pandas, matplotlib
- Use `bash` for: `pip install`, `ls`, `cat`, file ops
- Never use for web requests (`requests.get`) → use `web_search`
- Never use for host system info → use `execute_host_bash`

---

## execute_host_bash

Run bash commands on host machine. Requires user approval per call.

| Param | Type | Detail |
|---|---|---|
| `command` | string (required) | Bash command. No markdown ticks. Plain text |
| `timeout` | integer | 5–120 seconds, default 30 |

**Rules:**
- ⚠️ Every call shows a popup — user must approve before execution
- Runs as non-root user, no `sudo`
- Use for: `sensors`, `free -h`, `df -h`, `docker ps`, `docker logs`, `systemctl status`, `cat`/`head`/`tail`
- Never use for: math (`run_python_code`), file deletion, system config changes
- Never use for: `rm -rf`, `shutdown`, `reboot`, `iptables`
- Output truncated at 8000 chars — use `head`/`tail` to limit
- On connection error: executor not running — tell user to start it

---

## update_user_profile

Save the complete user profile to Core Memory (T3).

| Param | Type | Detail |
|---|---|---|
| `user_id` | string (required) | Discord user ID |
| `new_profile_markdown` | string (required) | **Full markdown content** of the updated profile. Overwrites entire file |

### How to use this tool

1. **Get current profile**: Read the existing profile from system prompt context
2. **Detect new facts**: Identify permanent facts from the conversation (name, job, location, hobbies)
3. **Merge**: Integrate new facts into the existing profile markdown. Resolve conflicts (e.g., old job → new job). Remove obsolete info.
4. **Call tool**: Pass the **complete** updated markdown to `update_user_profile`

### Example flow

User: "Tôi chuyển sang làm AI Engineer rồi"
1. Current profile has "Nghề nghiệp: Software Developer"
2. Replace with "Nghề nghiệp: AI Engineer"
3. Keep all other sections unchanged
4. Call: `update_user_profile(user_id="123", new_profile_markdown="## Thông tin cơ bản\n- Danh xưng: Hoàng\n...\n## Nghề nghiệp & Xã hội\n- Nghề nghiệp: AI Engineer\n...")`

### Rules
- Only save permanent/stable facts (name, job, location, hobbies, preferences)
- Do NOT save: temporary moods, guesses, one-time preferences
- Preserve existing information — do NOT delete unrelated facts
- If profile is empty, create a new one using the standard structure:
  ```
  ## Thông tin cơ bản
  - Danh xưng: ...
  - Nhân khẩu học: ...
  
  ## Nghề nghiệp & Xã hội
  - Nghề nghiệp: ...
  
  ## Sở thích & Thói quen
  - Sở thích: ...
  
  ## Ràng buộc & Cấm kỵ
  - ...
  ```
- Write in Vietnamese

---

## update_personality

Rewrite bot personality files. Auto-routes to IDENTITY.md or SOUL.md based on content.

| Param | Type | Detail |
|---|---|---|
| `content` | string (required) | Full markdown content for the file. Overwrites entire file |
| `confirm` | boolean (required) | Must be `true`. Safety gate against accidental overwrites |

**Auto-routing:** Keywords like `"tên"`, `"tính cách"`, `"là ai"` → IDENTITY.md. Keywords like `"cách nói"`, `"phong cách"`, `"emoji"` → SOUL.md.

**Rules:**
- Only use when user explicitly requests personality/identity change
- Provide complete, well-formatted markdown — this is an overwrite, not a merge

---

## Anti-patterns

| Wrong | Right |
|---|---|
| `search_memory(query="chuyện lúc nãy")` | `search_memory(mode="time", days=1)` |
| `web_search` for user preferences | `search_memory` |
| `run_python_code` for host system info | `execute_host_bash` |
| `run_python_code` with `requests.get()` for web data | `web_search` |
| `execute_host_bash` for math (`echo $((1+1))`) | `run_python_code` |
| `update_user_profile` for "user đang buồn" | Don't save — temporary state |
| `update_user_profile` with just a fact | Merge fact into full markdown first |
| Wrapping bash in \`\`\` marks | Send plain text command |
| `execute_host_bash` with `rm -rf`, `shutdown` | Never — blocked |

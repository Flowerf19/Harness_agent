---
status: ready-for-handoff
created: 2026-06-27
owner: review-handoff (minimax)
supersedes: plan.md (5 structured actions era)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, click Approve/Reject by hand, observe bot replies. KHÔNG phải
  pytest suite.
---

# E2E Test Plan — System Gateway generic-shell (Browser-Driven UI)

Mục tiêu: kiểm thử end-to-end qua **UI Discord thật trong Chrome** (chrome-devtools
MCP) sau khi gateway bị thu gọn từ **5 structured read-only actions** xuống **1
generic shell-exec**. LLM giờ tự viết lệnh phù hợp OS; owner duyệt **raw command**
trong approval DM; gateway chạy đúng lệnh đó. Không còn `system.status` /
`docker.list_containers` / … — chỉ còn `host_system mode=shell` (và `mode=capabilities`).

> Handoff cho minimax. Reviewer (tôi) review theo §Acceptance + §Gotchas.

## 0. Điều gì thay đổi so với hôm qua (phải verify)

| Trước (plan.md) | Sau (plan này) |
|---|---|
| 5 structured actions: `system.status`, `system.disk_usage`, `docker.list_containers`, `docker.container_logs`, `service.status` | **Bỏ hết**. Chỉ còn 1 path: `host_system mode=shell` với raw command. |
| Approval DM: `host action: system.disk_usage {}` | Approval DM: `host shell: <raw command>` (vd `host shell: uptime`). |
| `raw_shell=false` mặc định, shell bị khóa | `raw_shell=true` mặc định. Shell là đường chính. |
| `/actions/run` chạy action | **`/actions/run` biến mất** (404). Chỉ `/shell/run` thực thi. |
| `/capabilities` liệt kê `structured_actions` 5 cái | `/capabilities` → `structured_actions: []`, `features: ["generic_shell_exec"]`, `raw_shell: true`, `shells: ["/bin/sh"]`. |
| Gap #6: March7 lie "đã ghi file" (gateway read-only → không ghi được) | Giờ gateway **có ghi được** khi owner duyệt. Test phải chứng minh file tồn tại thật trên host. |

## 1. Phạm vi

| Trong scope (UI E2E) | Ngoài scope |
|---|---|
| Mở Discord web, gõ msg cho March7/Evernight, bấm Approve/Reject | Unit/security server-side (HMAC, replay, expiry, skew, oversized, missing-secret) |
| Quan sát approval DM hiện **raw command** đúng | pytest suite (đã có 120 test green) |
| Cross-check reply vs host thật (`uptime`, `cat /tmp/...`, `docker ps`) | systemd unit / packaging |
| Evernight `gateway_admin` doctor qua DM | raw-shell kill-switch server-side |
| Evidence pack: screenshots + report | |

## 2. Điều kiện tiên quyết

1. Host Linux, có `docker`, conda env `discord_bot`.
2. **System Gateway đang chạy, bind 0.0.0.0**, `curl -sf http://localhost:8380/health` → 200.
   - **`.env` ở repo root** (`/home/flowerf/Projects/march7/.env`) đã set
     `SYSTEM_GATEWAY_HOST=0.0.0.0`, `SYSTEM_GATEWAY_PORT=8380`,
     `SYSTEM_GATEWAY_SHARED_SECRET` (43 chars). Bind 0.0.0.0 đã được .env lo →
     gap #5 hôm qua không còn.
   - Phải restart gateway sau refactor (code mới). **Lưu ý Bash tool**: mỗi Bash
     call là shell riêng, env KHÔNG persist giữa calls. Bắt buộc gộp thành **1 lệnh
     duy nhất** với absolute path:
     ```bash
     set -a && source /home/flowerf/Projects/march7/.env && set +a \
       && cd /home/flowerf/Projects/march7 \
       && /home/flowerf/.conda/envs/discord_bot/bin/python -m system_gateway run
     ```
     (chạy ở fg, hoặc thêm `&` / `nohup ... &` để background. Verify:
     `curl -s http://localhost:8380/capabilities` thấy `raw_shell:true`,
     `structured_actions:[]` = bản mới.)
   - Nếu gateway cũ (process hôm qua) còn chạy → kill (`pkill -f system_gateway`)
     rồi chạy bản mới.
3. **Bots đang chạy** (march7 + evernight), `docker compose ps` healthy, container
   có `SYSTEM_GATEWAY_URL=http://host.docker.internal:8380` + secret khớp `.env`.
4. Chrome instance đã login Discord owner (`726302130318868500`). Chưa login → skip
   toàn bộ UI, ghi lý do.
5. Kênh/DM test riêng (không spam kênh chung).
6. Không in token/secret ra report. Screenshot che token.

## 3. Driver: chrome-devtools MCP

Công cụ: `list_pages`/`new_page`/`navigate_page`, `take_snapshot` (a11y tree → uid),
`fill`/`type_text`/`click`, `wait_for` (text cụ thể), `take_screenshot`,
`evaluate_script` (assert DOM). Uid đổi mỗi snapshot → snapshot lại trước click.

## 4. Kịch bản

### GĐ1 — Setup & smoke
- **G1.1** Host: `curl -s http://localhost:8380/capabilities` → JSON có
  `"raw_shell": true`, `"shells": ["/bin/sh"]`, `"features": ["generic_shell_exec"]`,
  `"structured_actions": []`. **Assert cả 4**. Chụp output.
- **G1.2** `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8380/actions/run` →
  phải **404** (route biến mất). (G1.2 host-side, nhanh, không cần UI.)
- **G1.3** Container reach: `docker compose exec march7 curl -sf
  http://host.docker.internal:8380/health` → 200. Skip nếu compose không chạy được.
- **G1.4** Mở Discord web, owner đã login, snapshot kênh test, input box sẵn sàng.

### GĐ2 — Read command: Approve happy path (core)
- **G2.1** Kênh/DM test, gõ: *"Bảy ơi xem uptime của host giúp tớ"* (kích
  `host_system mode=shell`, command tự sinh ≈ `uptime`).
- **G2.2** `wait_for` Evernight DM hiện approval. **Assert approval text có dạng
  `host shell: <command>`** (raw command, KHÔNG phải `host action: ...`).
  Screenshot DM. Snapshot lấy uid nút **Approve**.
- **G2.3** `click` Approve.
- **G2.4** `wait_for` March7 reply chứa output `uptime` thật (vd `load average`,
  `up X days`). Screenshot. **Assert reply có "Output từ tool:"** HOẶC số liệu
  thật, KHÔNG bịa "11 ngày" (gap #1 hôm qua).
- **G2.5** Cross-check: chạy `uptime` trên host song song → so sánh. Khớp = gateway
  chạm host thật.

### GĐ3 — Write command: ex-lie case (CRITICAL — regression của Gap #6)
- **G3.1** Trước test: xác nhận `/tmp/gw_e2e.txt` **chưa tồn tại** (`ls /tmp/gw_e2e.txt` →
  No such file). Ghi lại.
- **G3.2** Kênh test, gõ: *"Bảy ơi ghi file /tmp/gw_e2e.txt với nội dung hello-e2e nhé"*
  → kích `host_system mode=shell`, command ≈ `echo hello-e2e > /tmp/gw_e2e.txt` hoặc
  `printf ... > /tmp/gw_e2e.txt`.
- **G3.3** `wait_for` approval DM. **Assert approval text chứa raw command đầy đủ
  với redirect `> /tmp/gw_e2e.txt`** — owner nhìn thấy đúng lệnh sẽ chạy.
  Screenshot. Click **Approve**.
- **G3.4** `wait_for` March7 reply báo thành công. Screenshot.
- **G3.5** **Cross-check cốt lõi**: chạy `cat /tmp/gw_e2e.txt` trên host → phải ra
  `hello-e2e` (hoặc nội dung tương ứng raw command). **File phải tồn tại thật.**
  Đây chứng minh đường ghi hoạt động + bot không lie nữa (gap #6 đã fix bằng refactor).
- **G3.6** Dọn: `rm /tmp/gw_e2e.txt` sau test.

### GĐ4 — Reject path
- **G4.1** Gõ yêu cầu 1 lệnh host khác (vd *"xem docker ps trên host"*).
- **G4.2** `wait_for` approval DM hiện `host shell: docker ps ...`. Click **Reject**.
- **G4.3** `wait_for` March7 reply *"bị từ chối bởi Trạm Gác"* (hoặc wording thật).
  Screenshot. **Assert KHÔNG có output docker ps** trong reply (reject = không chạy).

### GĐ5 — Transparency: raw command đúng trong approval
- **G5.1** Gõ yêu cầu phức tạp hơn: *"xem log 50 dòng cuối của container march7"*
  → command ≈ `docker logs --tail 50 march7`.
- **G5.2** **Assert approval DM hiện nguyên lệnh** (`docker logs --tail 50 march7`),
  KHÔNG bị rút gọn thành "action docker.container_logs". Screenshot. Đây là bất biến
  an toàn: owner duyệt đúng cái gateway chạy.
- **G5.3** Approve → reply có log. (Tuỳ chọn, đã chứng minh GĐ2/GĐ3.)

### GĐ6 — Evernight gateway_admin (doctor thay đổi)
- **G6.1** DM Evernight hoặc `!9`: chạy `doctor`.
- **G6.2** **Assert reply KHÔNG liệt kê 5 capability** (`system.status` / `disk_usage`
  / …) nữa. Phải báo `platform`, `shell` (`/bin/sh`), `raw_shell: enabled`/
  `raw_shell: true`. Screenshot.
- **G6.3** `install_hint` → vẫn snippet systemd thật (`tee … /etc/systemd/system/…`
  + `systemctl daemon-reload`), **KHÔNG có `npx`/`pip`** (chống hallucination giữ
  nguyên từ hôm qua).

### GĐ7 — Anti-hallucination kiểm tra thêm
- **G7.1** Gõ câu host query nhưng **Reject** approval (GĐ4 đã làm 1 phần) → assert
  bot **KHÔNG** bịa số liệu host trong reply (phải báo bị từ chối / không có data).
- **G7.2** (Tuỳ chọn) Gõ lại uptime query 2–3 lần → ghi lại mỗi lần bot có gọi tool
  hay không (rate). Hôm qua rate ~33%. Mục tiêu: quan sát xem refactor + prompt có
  ổn định hơn không. Ghi số vào report, không cần pass/fail cứng.

### GĐ8 — Teardown & evidence
- **G8.1** Xoá message test trong kênh test (owner quyền) hoặc ghi rõ kênh đã dùng.
- **G8.2** Screenshots → `tests/e2e/screenshots/<timestamp>/` (gitignored).
- **G8.3** Viết/append `tests/e2e/REPORT.md`: mỗi GĐ — pass/fail/skip + screenshot
  + quote reply + cross-check host.
- **G8.4** Liệt kê gap thực tế (wording approval thật, nút tên gì, rate G7.2).

## 5. Acceptance (reviewer check)

1. **G1.1**: `/capabilities` đúng shape mới (`raw_shell:true`, `generic_shell_exec`,
   `structured_actions:[]`).
2. **G1.2**: `/actions/run` → 404.
3. **GĐ2**: Approve uptime → reply có output thật, cross-check `uptime` host khớp,
   KHÔNG hallucinate "11 ngày".
4. **GĐ3** (critical): ghi file → **file tồn tại thật trên host** sau Approve,
   nội dung đúng. Regression Gap #6 pass.
5. **GĐ4**: Reject → "bị từ chối", không có output.
6. **GĐ5**: approval DM hiện **raw command đầy đủ** (bất biến owner thấy gì = gateway
   chạy cái đó).
7. **GĐ6**: doctor không liệt kê 5 capability; install_hint không npx/pip.
8. **GĐ7**: reject không bịa số liệu; rate gọi tool được ghi.
9. Evidence đầy đủ: report + screenshots có timestamp.
10. Skip sạch khi môi trường thiếu (Discord chưa login / gateway down / bots down) —
    mỗi skip có lý do.
11. Không lộ secret; screenshots gitignored.

## 6. Gotchas cho minimax

- **Phải restart gateway bản mới** trước test. Code hôm qua = bản 5-action cũ.
  Verify `curl /capabilities` thấy `structured_actions:[]` mới là bản mới.
- **Bash tool: env không persist giữa calls.** Mỗi Bash call = shell riêng. Nếu cần
  `SYSTEM_GATEWAY_SHARED_SECRET` (restart gateway, docker compose) → **source .env +
  chạy trong cùng 1 lệnh**, absolute path `/home/flowerf/Projects/march7/.env`. Không
  tách thành nhiều calls. Tương tự `docker compose` cần `cd` + `source` cùng line.
- **Bind 0.0.0.0** — container reach `host.docker.internal:8380`. Bind `127.0.0.1`
  = `Connection refused` (gap #5). `.env` đã set 0.0.0.0 nên chỉ cần source đúng.
- **Uid đổi mỗi snapshot** — snapshot lại trước click, không reuse uid.
- **Discord render nặng** — dùng `wait_for` text cụ thể (`host shell:`, `bị từ chối`,
  `load average`) thay vì `sleep`. Bot mất vài giây + LLM call.
- **Debounce** `.env` `MESSAGE_DEBOUNCE_SECONDS=3.5` — gửi 1 msg, chờ, mới gửi tiếp.
- **Approval DM ở Evernight DM** (không phải kênh March7) — như hôm qua.
- **Cross-check timing**: uptime/disk đổi theo thời gian → chụp reply & terminal sát
  thời điểm, so pattern hơn là số tuyệt đối.
- **GĐ3**: nhớ `ls /tmp/gw_e2e.txt` TRƯỚC test (chưa tồn tại) và `rm` SAU test.
- **Wording approval** có thể khác chút (`🔐 Bé Bảy muốn chạy lệnh trên host:` rồi
  codeblock `bash` chứa command) — ghi wording thật, assert **chứa raw command** là
  đủ, không ép khớp từng chữ.
- **G7.2 rate**: chỉ quan sát, ghi số, không FAIL nếu LLM thi thoảng skip tool (đã
  có task riêng giảm temperature — ngoài scope plan này).
- **Không test server-side security qua UI** (HMAC/replay/expiry/skew) — flag ngoài
  scope, thuộc unit (120 test đã green).

## 7. Out-of-scope reminder

Phần KHÔNG属 E2E UI (unit lo, đã green): HMAC tamper, approval token replay/expiry,
clock skew, oversized response, missing-secret boot, raw-shell kill-switch
server-side, audit in-memory cap, owner-gate server-side gap, audit persistence,
LLM_TEMPERATURE tuning (gap #1/#6 root cause LLM-side), systemd unit (gap #5).
Agent **chỉ flag** trong report, KHÔNG test, KHÔNG fix.

## 8. Deliverables

- `tests/e2e/REPORT.md` — append section *"Generic-shell refactor (2026-06-27)"*:
  pass/fail/skip mỗi GĐ + quote reply + cross-check host + screenshot link + gap.
- `tests/e2e/screenshots/<timestamp>/*.png` — evidence (gitignored).
- KHÔNG tạo pytest file (scope này = browser-driven).
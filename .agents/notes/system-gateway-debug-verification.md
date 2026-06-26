# System Gateway — debug verification (2026-06-25)

Bản verify độc lập các kết luận debug của minimax (`minimax-m3`, session
`ed377c74`). Mọi verdict dựa `file:line`, không dựa narration Evernight.

## Đã verify ĐÚNG

1. **`install_hint` thật = systemd unit, không phải `npx`.**
   `twin/evernight/system_gateway/installer.py:83-101` —
   `build_bootstrap_hint("linux")` trả về `sudo tee /etc/systemd/system/system-gateway.service …`
   và `sudo systemctl daemon-reload && enable --now`. Không có `npx`/`pip`.
   → Evernight đã hallucinate `npx @anthropic-ai/system-gateway@latest install …`.

2. **Default-deny: mọi structured action đều cần `approval_id`, kể cả read-only.**
   `twin/shared/system_gateway/policy.py:85-90` —
   `if context.approval_id is None or not context.approval_id.strip(): return DENY(APPROVAL_REQUIRED)`.
   Không có special-case cho read-only. Claim "system.status read-only → không cần approval"
   của Evernight là hallucination.

3. **Approval gate ở phía Discord (Evernight), gateway verify token độc lập.**
   `twin/shared/tools/modules/system/host_system_tool.py:145-153` —
   `check_approval()` → `_mint_token(action)` → `run_action(approval_id=…)`.
   Server `run_action` (`services/system_gateway/server.py:196-221`) lại
   `verify_approval_token` + `consume_approval`. Defense-in-depth đúng.

4. **HMAC canonical + skew.**
   `twin/shared/system_gateway/auth.py:60-78` —
   `METHOD\nPATH\nTIMESTAMP\nNONCE\nACTOR\n<sha256(body)>`.
   `auth.py:38` `DEFAULT_MAX_CLOCK_SKEW_SECONDS = 300`.
   `auth.py:103` timestamp = `str(int(time.time()))` (giây, không phải ms).

## minimax hiểu SAI — đã refute bằng test trực tiếp server

5. **"`gateway_admin update` trả 401 → owner gate hoạt động đúng" — SAI hoàn toàn.**

   Test trực tiếp `POST /self/update` (mô phỏng đúng `gateway_admin_tool._update`:
   actor=`"evernight"`, mint token `self.update`, `from_version=0.1.0`):

   | Case | Kết quả thật |
   |---|---|
   | Token đúng action + đúng actor + version đúng | **HTTP 200 "update accepted"** |
   | Token actor=owner, request actor=evernight | 403 `approval_invalid` |
   | Token action=system.status, gọi self.update | 403 `approval_invalid` |
   | from_version=9.9.9 (sai) | 409 `version_mismatch` |

   Kết luận:
   - **Response thật là 200, không phải 401.** Evernight ghi "401 / token minting
     bị chặn ở cấp quyền" trong chat là **hallucination** — cùng dạng với `npx`.
     minimax tin narration Evernight thay vì gọi server → import hallucination
     vào kết luận.
   - **Server `/self/update` không có owner gate** (`server.py:460-584` không
     check owner). Owner gate chỉ ở phía Evernight (`gateway_admin_tool._is_owner`,
     `gateway_admin_tool.py:88-98`), và nó **PASS** khi owner gọi.

   **Hệ quả bảo mật (đáng note):** `/self/update` tin tưởng bất kỳ ai giữ
   `SYSTEM_GATEWAY_SHARED_SECRET`. Token chỉ bind action+actor, không bind "owner".
   Bất kỳ entity nào có secret (Evernight, march7 container,…) đều mint được
   token `self.update` actor=`"evernight"` và server **accept 200**. Owner
   protection dựa hoàn toàn vào lớp tool Evernight (`_is_owner` trước khi mint),
   không có defense-in-depth phía server. Nếu Evernight bị compromise → có thể
   trigger self-update freely. Cân nhắc thêm owner binding phía server (gắn
   owner user_id vào token, hoặc secret riêng cho owner-only actions).

   Token binding VẪN đúng (action-bound + actor-bound + single-use + version
   check) — chỉ là nó bind "actor" chứ không bind "owner".

## Đã làm theo minimax (giữ)

- Thêm § "Quy tắc chống hallucination output" vào
  `twin/shared/tools/prompts/guides/gateway_admin.md` (copy nguyên xi, không bịa
  command, ghi rõ "Output từ tool:"). Rule này đúng và nên giữ.

## Pending

- ✅ ~~Re-test `gateway_admin update` trực tiếp~~ → đã làm, kết quả 200 (xem §5).
- Dọn `services/system_gateway2/` và file `!` ở repo root.
- Persist audit log ra file (hiện in-memory only, `state.record_audit`).
- Commit system-gateway phases 2-6 + .md update.
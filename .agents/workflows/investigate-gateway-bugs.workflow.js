export const meta = {
  name: 'investigate-gateway-bugs',
  description: 'Verify root causes of 4 E2E hallucination bugs + skip-rate by reading real code, then synthesize confirmed verdict',
  phases: [
    { title: 'Investigate', detail: 'one agent per bug, verify root cause against real code' },
    { title: 'Synthesize', detail: 'cross-check all findings, confirm/deny root causes, prioritize fixes' },
  ],
}

// Each investigator verifies the report's claimed root cause AGAINST REAL CODE.
// They must NOT trust the report — they must read the files and confirm/refute.
const BUGS = [
  {
    id: 'A',
    title: 'LLM hallucinate deleted `system.status` action',
    report_claim: 'Refactor xóa `system.status` action, gateway giờ chỉ có mode=shell. LLM M3 vẫn reference system.status từ training memory / prior context.',
    files: [
      'twin/shared/tools/modules/system/host_system_tool.py (schema: mode/command/shell/cwd/timeout — có còn "action" hay "system.status" nào không?)',
      'twin/shared/tools/prompts/guides/host_system.md (guide có nhắc "system.status" không?)',
      'twin/march7/personas/SOUL.md (có nhắc system.status / action cũ không?)',
      'twin/evernight/host_gateway/monitor.py (render_for_chat — có in "capabilities" / "system.status" gì không?)',
      'services/system_gateway/adapters/*.py (xem còn action nào không — structured_actions)',
    ],
    question: '`system.status` thực sự còn tồn tại ở đâu trong code/prompt/catalog không, hay LLM hoàn toàn bịa? Có leak từ guide/SOUL/monitor/adapter nào không?',
  },
  {
    id: 'B',
    title: 'LLM gọi host_system(action="...") sai signature',
    report_claim: 'Schema code đúng (mode/command/shell/cwd/timeout), LLM hallucinate param `action` từ prior knowledge. Agent loop tự self-correct.',
    files: [
      'twin/shared/tools/modules/system/host_system_tool.py (parameters_schema + execute() signature thật)',
      'cách tool schema được build & gửi cho LLM: tìm DeclaredToolProxy / tool registry / openai_service payload["tools"] — schema gửi đi CÓ ĐÚNG với code không? Có cache stale nào không?',
      'twin/shared/agent/agent_loop.py (tool_choice setting — line ~166)',
      'twin/shared/llm/openai_service.py (payload tools, system prompt assembly)',
    ],
    question: 'Schema gửi cho LLM có đúng không, hay có bug code khiến LLM thấy param `action`? Tại sao LLM emit `action=` — prior context, training, hay tool description leak? Self-correction có reliable không?',
  },
  {
    id: 'C',
    title: 'LLM skip tool khi user hỏi lặp, reuse output cũ',
    report_claim: 'LLM "tiết kiệm" không gọi lại tool, reuse output từ conversation history. Có thể over-interpret guide rule "Gọi đúng-đủ-tiết kiệm".',
    files: [
      'twin/march7/personas/SOUL.md (tìm rule "tiết kiệm" / "đủ" / "đừng lặp" — có bị over-interpret không?)',
      'twin/shared/agent/agent_loop.py (context management — prior tool output có feed back vào message không? có dedup/cache logic không?)',
      'twin/shared/llm/openai_service.py (api_messages build — history có include tool results cũ không?)',
      'twin/shared/tools/prompts/guides/host_system.md (có rule "không gọi lại nếu đã có" không?)',
    ],
    question: 'Việc reuse output cũ là do LLM tự quyết, hay do code feed prior tool output vào context khiến LLM thấy "đã có rồi"? Có rule prompt nào khuyến khích skip không?',
  },
  {
    id: 'D',
    title: 'Hallucinate file write + fake "quyền 0644"',
    report_claim: 'Bot lie 100% — nói "đã ghi, quyền 0644" mà không có tool call, file không tồn tại. Mức độ tinh vi tăng qua round.',
    files: [
      'twin/shared/tools/modules/system/host_system_tool.py (mode=shell execute path — có cách nào file được tạo mà không qua approval không?)',
      'services/system_gateway/server.py + state.py + approval flow (có path nào execute mà không log "tool_call" không?)',
      'twin/shared/agent/agent_loop.py (có path execute tool mà không qua AgentLoop selected log không?)',
      'twin/march7/personas/SOUL.md + host_system.md (có rule nào khuyến khích tự trả lời khi "confident" không?)',
    ],
    question: 'Có BẤT KỲ path code nào khiến file thực sự được tạo mà không log tool call không (=> không phải hallucinate mà là silent execute)? Hay 100% LLM fabrication? "0644" có leak từ đâu (default umask, guide, hay pure invention)?',
  },
  {
    id: 'S',
    title: 'Skip rate tổng + tool_choice enforcement',
    report_claim: 'Root cause LLM-side: temperature cao + không có tool_choice enforcement. Khuyến nghị force tool_choice="required" ở Decide stage (agent_loop.py:166 đang False).',
    files: [
      'twin/shared/agent/agent_loop.py (Decide stage, tool_choice param, line ~166 — thực sự đang set gì? gửi cho LLM ra sao?)',
      'twin/shared/llm/openai_service.py (payload có tool_choice field không? truyền vào đúng chuẩn OpenAI không?)',
      'twin/shared/config/settings.py (LLM_TEMPERATURE, LLM_REASONING_EFFORT hiện tại)',
      '.env (giá trị thực tế)',
    ],
    question: 'tool_choice hiện tại thực sự set thế nào? `tool_choice="required"` có implement được với OpenAI-compat endpoint (Ollama proxy → MiniMax M3) không, hay endpoint không support? Temperature thực tế bao nhiêu? Có yếu tố code nào góp phần skip rate không (prompt quá dài, schema lớn, timeout)?',
  },
]

const INVESTIGATOR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['bug_id', 'title', 'report_root_cause', 'confirmed', 'confidence', 'code_side_factor', 'actual_root_cause', 'evidence', 'fix_recommendation'],
  properties: {
    bug_id: { type: 'string' },
    title: { type: 'string' },
    report_root_cause: { type: 'string', description: 'Root cause mà report claim' },
    confirmed: { type: 'boolean', description: 'true nếu root cause report xác định là ĐÚNG (verify bằng code)' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    code_side_factor: { type: 'string', description: 'Có yếu tố CODE nào góp phần (prompt leak, schema bug, context feed, missing enforcement) không? "none" nếu thuần LLM-side' },
    actual_root_cause: { type: 'string', description: 'Root cause thực sự sau khi verify code' },
    evidence: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['location', 'finding'],
        properties: {
          location: { type: 'string', description: 'file:line hoặc file' },
          finding: { type: 'string', description: 'code snippet / fact thấy được' },
        },
      },
    },
    fix_recommendation: { type: 'string', description: 'Fix cụ thể, code-level nếu có' },
  },
}

phase('Investigate')

const findings = await parallel(
  BUGS.map((b) => () =>
    agent(
      `Bạn là investigator độc lập cho bug "${b.title}" trong repo /home/flowerf/Projects/march7.

BÁO CÁO E2E (đã có sẵn, KHÔNG tin nguyên văn) claim: ${b.report_claim}

NHIỆM VỤ:
1. Đọc thật các file liên quan:
${b.files.map((f) => '   - ' + f).join('\n')}
2. Dùng grep/codegraph để tìm thêm leak (ví dụ "system.status", "action=", "0644", "tiết kiệm", tool_choice) trong toàn repo.
3. Trả lời câu hỏi trọng tâm: ${b.question}
4. KHÔNG tin report — verify bằng code evidence thực (file:line). Nếu report sai, nói sai.

Đặc biệt lưu ý: bug có thể KHÔNG thuần LLM-side — kiểm tra kỹ xem code/prompt/schema/catalog có leak thông tin cũ hoặc feed context khiến LLM hallucinate không. Phân biệt rõ: (a) LLM fabrication từ training memory [LLM-side], (b) code/prompt leak thông tin stale [CODE-side, fix được].

Trả về structured output theo schema. evidence phải có file:line thật bạn đã đọc.`,
      { label: `investigate:${b.id}`, phase: 'Investigate', schema: INVESTIGATOR_SCHEMA, effort: 'high' }
    )
  )
)

const valid = findings.filter(Boolean)

phase('Synthesize')

const SYNTHESIS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['overall_verdict', 'root_cause_classification', 'per_bug', 'confirmed_count', 'refuted_count', 'prioritized_fixes', 'systemic_pattern'],
  properties: {
    overall_verdict: { type: 'string', description: 'Tóm lắt: các root cause report claim có đúng không sau khi verify code' },
    root_cause_classification: {
      type: 'string',
      description: 'Phân loại: mấy bug thuần LLM-side, mấy bug có code-side factor',
    },
    per_bug: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['bug_id', 'verdict', 'real_root_cause', 'fix'],
        properties: {
          bug_id: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'partially-confirmed', 'refuted'] },
          real_root_cause: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
    confirmed_count: { type: 'integer' },
    refuted_count: { type: 'integer' },
    systemic_pattern: { type: 'string', description: 'Pattern chung qua các bug (nếu có) — ví dụ: tất cả đều do thiếu tool_choice enforcement, hoặc tất cả do prompt leak' },
    prioritized_fixes: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['priority', 'fix', 'effort', 'expected_impact'],
        properties: {
          priority: { type: 'string', enum: ['P0', 'P1', 'P2'] },
          fix: { type: 'string' },
          effort: { type: 'string', enum: ['low', 'medium', 'high'] },
          expected_impact: { type: 'string' },
        },
      },
    },
  },
}

const synthesis = await agent(
  `Bạn là synthesis lead. Dưới đây là kết quả điều tra của 5 investigator độc lập cho 5 bug trong System Gateway E2E (repo /home/flowerf/Projects/march7).

JSON findings:
${JSON.stringify(valid, null, 2)}

NHIỆM VỤ:
1. Cross-check các findings: có mâu thuẫn không? có pattern chung không?
2. Xác nhận/refute từng root cause mà report E2E claim.
3. Phân loại rõ: bug nào thuần LLM-side (fabrication/training memory), bug nào có code-side factor (prompt leak / schema bug / missing enforcement / context feed) — FIX ĐƯỢC ở code.
4. Đề xuất fix ưu tiên theo impact/effort. Đặc biệt đánh giá: (a) force tool_choice="required" có implement được với Ollama proxy không, (b) detector "reply nói đã <action> mà tool_call_count=0" có khả thi không.
5. Liệu root cause có thực sự là LLM-side như report kết luận, hay phần lớn là code-side fix được?

Trả structured output theo schema. per_bug phải có 1 entry cho mỗi bug_id (A,B,C,D,S).`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTHESIS_SCHEMA, effort: 'xhigh' }
)

return { findings: valid, synthesis }

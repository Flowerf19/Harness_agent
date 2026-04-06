# Plan học Harness Engineering

## Tổng quan

**Định nghĩa:** Discipline của việc thiết kế môi trường, constraints, feedback loops để AI coding agents hoạt động reliably.

**Formula:** Agent = Model + Harness

---

## Analog: Horse metaphor

| Component | Meaning |
|-----------|---------|
| Horse | AI model - mạnh, nhanh, nhưng không biết đi đâu |
| Harness | Infrastructure - reins, saddle, guardrails để channel power |
| Rider | Engineer - điều hướng |

---

## Core concepts

### Feedforward (Guides)
- Ngăn lỗi trước khi xảy ra
- Examples: system prompts, docs, lint rules, code templates

### Feedback (Sensors)
- Detect lỗi sau khi act → self-correct
- Examples: tests, CI/CD, custom linter messages optimized for LLM

---

## Why important?

- OpenAI Codex: 1M+ lines code, zero human-written → nhờ harness tốt
- Agent không có harness → unpredictable, repeat mistakes
- Harness tốt → giảm review toil, tăng quality, tiết kiệm tokens

---

## Plan chi tiết

### Phase 1: Foundation (1-2 weeks)

**Concepts:**
- Read Martin Fowler article (martinfowler.com/articles/harness-engineering.html)
- Read Anthropic's harness design guide (anthropic.com/engineering/harness-design-long-running-apps)
- Understand: Agent = Model + Harness
- Grasp: Feedforward vs Feedback, Computational vs Inferential

**Practice:**
- Setup coding agent (OpenClaw/Claude Code/Codex)
- Create simple AGENTS.md + SKILL.md
- Run agent on small project, observe behavior

---

### Phase 2: Build Basic Harness (2-3 weeks)

**Components:**

#### 1. Guides (Feedforward)
- AGENTS.md - project context
- SKILL.md - task-specific instructions
- TOOLS.md - local notes
- Memory system (MEMORY.md + daily notes)

#### 2. Sensors (Feedback)
- Lint rules optimized for LLM
- Test suite
- CI/CD basics
- Git hooks

**Practice:**
- Apply to discord-bot-v1 project
- Write AGENTS.md với architecture overview
- Create SKILL.md cho relationship graph implementation
- Setup pre-commit hooks

---

### Phase 3: Advanced Techniques (3-4 weeks)

**Topics:**
- State management cho long-running agents
- Verification mechanisms (tests, assertions)
- Control mechanisms (stop conditions, rollback)
- Multi-agent orchestration
- Token optimization strategies

**Resources:**
- GitHub: walkinglabs/learn-harness-engineering
- OpenAI Codex case study
- Anthropic Labs articles

**Practice:**
- Build harness cho complex task (e.g., relationship graph implementation)
- Track agent sessions, analyze failure patterns
- Iterate on guides/sensors

---

### Phase 4: Real-world Project (4-6 weeks)

**Project:**
- Apply harness engineering to discord-bot-v1 relationship graph feature
- Document everything

**Deliverables:**
- Complete harness setup: AGENTS.md, SKILL.md, MEMORY.md
- Custom linter rules cho project
- Test coverage >80%
- CI/CD pipeline
- Session logs + lessons learned

---

## Resources

| Resource | Type | URL |
|----------|------|-----|
| Martin Fowler article | Theory | martinfowler.com/articles/harness-engineering.html |
| Anthropic harness design | Deep dive | anthropic.com/engineering/harness-design-long-running-apps |
| walkinglabs/learn-harness-engineering | Course | github.com/walkinglabs/learn-harness-engineering |
| nxcode.io guide | Overview | nxcode.io/resources/news/harness-engineering-complete-guide-ai-agent-codex-2026 |
| OpenAI Codex talk | Case study | - |

---

## Tips

1. **Start small** - không cần perfect harness ngay
2. **Iterate** - observe agent behavior → refine guides/sensors
3. **Document failures** - mỗi lần agent fail là data để improve harness
4. **Token efficiency** - good harness = fewer wasted tokens
5. **Trust building** - harness mục tiêu: reduce human review toil

---

## Practical example

```
Agent без harness:
- Viết code → lỗi → human fix → loop

Agent с harness:
- Guides: AGENTS.md, SKILL.md, lint rules
- Sensors: tests fail → agent tự fix → loop
- Result: ít human intervention
```

---

## Next steps for discord-bot-v1

1. Create AGENTS.md với project architecture overview
2. Create SKILL.md cho relationship graph feature
3. Setup linter rules optimized cho LLM
4. Build test suite cho relationship extraction
5. Iterate based on agent sessions

---

## Tool: Roo Code

### Overview

**Roo Code** = Open-source AI coding assistant (VS Code extension)

**Features:**
- Multi-file read/write
- Execute terminal commands
- Browse websites
- Specialized modes (Architect, Code, Debug, Ask)
- Cyclic workflow: plan → edit → run → debug

**Why phù hợp học Harness Engineering:**
- Open-source → customizable
- Custom Modes → tương tự SKILL.md concept
- Multi-step tasks → practice feedforward/feedback
- VS Code integration → easy lint/test setup

---

### Setup Harness với Roo Code

**File `.roomodes` trong project root:**

```yaml
customModes:
  - slug: harness-engineer
    name: "Harness Engineer"
    description: "Mode áp dụng harness engineering principles"
    groups:
      - read
      - edit
      - command
    customInstructions: |
      # Harness Engineering Mode
      
      ## Feedforward (Guides)
      - Luôn đọc AGENTS.md trước khi bắt đầu task
      - Kiểm tra SKILL.md nếu có task-specific instructions
      - Follow project conventions trong TOOLS.md
      
      ## Feedback (Sensors)
      - Sau khi edit code: chạy lint, tests
      - Nếu fail: tự analyze và fix
      - Ghi lại lessons learned vào MEMORY.md
      
      ## Constraints
      - Không hard-code secrets
      - Files < 500 lines
      - Viết tests cho new code
```

---

### SPARC Modes (Alternative)

**SPARC methodology:** Specification → Pseudocode → Architecture → Refinement → Completion

**Available modes** (from github.com/enescingoz/roocode-modes):
- Orchestrator: Breaks down large objectives
- Architect: Design system architecture
- Code: Implementation
- Debug: Fix issues
- TDD: Test-driven development
- Security Reviewer: Security analysis

---

### Recommended Project Structure

```
discord-bot-v1/
├── .roomodes           # Custom harness mode (Roo Code)
├── AGENTS.md           # Project context (feedforward)
├── SKILL.md            # Task-specific (feedforward)
├── TOOLS.md            # Local notes
├── MEMORY.md           # Long-term memory
├── .pre-commit-config.yaml  # Feedback sensors
└── tests/              # Feedback sensors
```

---

### Roo Code Resources

| Resource | URL |
|----------|-----|
| Official site | roocode.com |
| GitHub | github.com/RooCodeInc/Roo-Code |
| Docs | docs.roocode.com |
| Custom Modes Guide | docs.roocode.com/features/custom-modes/ |
| SPARC Modes | github.com/enescingoz/roocode-modes |
| Community Discord | discord.gg/roocode |
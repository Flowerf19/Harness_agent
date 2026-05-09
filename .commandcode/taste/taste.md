# architecture
- Separate system tools and MCP proxy tools into distinct directories (e.g., implementations/system/ and implementations/mcp/). Confidence: 0.65
- Keep `twin/` directory focused: only agents (march7, evernight) and shared package. Other services like gateway, docker, tests stay at project root. Confidence: 0.65

# code-style
- Avoid over-engineering — prefer simple, minimal solutions over complex architectures. Code must be clean and straightforward. Confidence: 0.75
- Keep configuration values (model names, URLs, keys) in Config/settings, not hardcoded in DI or wiring code. Confidence: 0.70

# code-style
- For agent modules, use flat directory naming like `src/twin/` instead of nested namespaces like `src/agents/twin/`. Confidence: 0.75

# workflow
- When uncertain about functionality, architecture, or design decisions, ask the user for clarification instead of making assumptions or decisions independently. Confidence: 0.85
- For large architecture plans, break them into smaller sub-plans by component (e.g., per agent, per service, Docker updates) before implementation to avoid breaking logic. Confidence: 0.75
- Store plan files in project directory (e.g., `.commandcode/plans/`) rather than home directory (`~/.commandcode/plans/`), consistent with taste files stored in project. Confidence: 0.65

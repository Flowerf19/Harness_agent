# architecture
- Separate system tools and MCP proxy tools into distinct directories (e.g., implementations/system/ and implementations/mcp/). Confidence: 0.65

# code-style
- Avoid over-engineering — prefer simple, minimal solutions over complex architectures. Code must be clean and straightforward. Confidence: 0.75
- Keep configuration values (model names, URLs, keys) in Config/settings, not hardcoded in DI or wiring code. Confidence: 0.70

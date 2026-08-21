# Local LLM Integration (Ollama)

> Moved out of CLAUDE.md 2026-08-20 (size cap).

- **Ollama** at `localhost:11434`: `huihui_ai/qwen3.5-abliterated:9b` (fast),
  `huihui_ai/qwen3.5-abliterated:35b` (heavy), `huihui_ai/qwen3-coder-abliterated:30b`
  (agentic coding), `nomic-embed-text` (embeddings)
- **MCP server** (`scripts/ollama_mcp_server.py`) exposes
  `ollama_generate/chat/embed` via `.mcp.json`
- **Chat embeddings** (`scripts/embed_chat.py`) — semantic search over the
  chat corpus
- **Post-edit hook** (`scripts/local_review_hook.py`) — Qwen reviews diffs
- Qwen 3/3.5 `<think>` tokens consume `num_predict`; scripts double limits

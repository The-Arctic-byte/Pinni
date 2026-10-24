# Pinni — Agent & Track B

This folder contains the complete and self-contained implementation of **Track B (Agents, MCP & Recommendation)** for Pinni, designed to avoid any git or merge conflict with Track A (App) and Track C (Backend).

## Contents

- **`pinni_agent/config.py`**: Configuration for Ollama Qwen 3.5, embeddings, and directories.
- **`pinni_agent/types.py`**: Pydantic models mirroring `contract/schemas/`.
- **`pinni_agent/store.py`**: SQLite event store, review queue, and audit trail.
- **`pinni_agent/llm.py`**: Ollama integration with JSON schema enforcement.
- **`pinni_agent/knowledge/`**:
  - `graph.py`: Knowledge Graph (`User ↔ Story ↔ Category ↔ Place ↔ Channel ↔ Source`), similar people, and channel suggestions.
  - `vector_store.py`: Hybrid BM25 + dense vector store with RRF fusion.
  - `loader.py`: Seed data loader from `contract/mock/`.
- **`pinni_agent/mcp/`**:
  - `server.py`: Standard MCP JSON-RPC 2.0 tool server.
  - `client.py`: MCP client.
  - `tools/`: News gathering, geocoding, vector search, knowledge graph queries, and publishing.
- **`pinni_agent/agent/`**:
  - `supervisor.py`: B3 Supervisor orchestrating all 10 core tasks.
  - `skills.py`: Skills registry.
  - `trace.py`: Audit trail generator matching `openapi.yaml` `AuditEntry`.
  - `policy.py`: Safety policy, red-risk routing, and translation tiers.
  - `prompts.py`: Qwen 3.5 structured prompts and JSON schemas.
- **`pinni_agent/recommender/`**:
  - `engine.py`: Hybrid recommendation engine.
  - `ranker.py`: Story relevance scoring, time decay, must-see detection, and reasons generator.
  - `learner.py`: Interaction handling and learned preferences calculator.
  - `filters.py`: Hard filters enforcement.
- **`tests/`**: Full test suites for MCP tools, Knowledge Graph, Supervisor, and Recommender.

## Running Tests

```bash
cd agent
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

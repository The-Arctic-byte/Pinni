# Groovy Tests — Interactive Pinni Track B Tests

This folder contains separate, human-readable test scripts demonstrating and verifying the three main pillars of Track B:

- **`test_a_recommender.py`**: Recommendation engine, feed generation, hard filter enforcement, and cold start.
- **`test_b_supervisor.py`**: Supervisor orchestrator and the 10 Track B B3 tasks.
- **`test_c_mcp.py`**: Model Context Protocol (MCP) server, tools list, geocoding, and vector search.

---

### How to Run

From the `agent/` folder:

```bash
# Run with python to see rich human-readable outputs and steps:
uv run python groovy_tests/test_a_recommender.py
uv run python groovy_tests/test_b_supervisor.py
uv run python groovy_tests/test_c_mcp.py

# Or run all groovy tests via pytest:
uv run pytest groovy_tests/ -v
```

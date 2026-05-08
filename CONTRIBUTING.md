# Contributing to Bifrost

Bifrost is part of the [Asgard AI Platform](https://github.com/MegaWiz-Dev-Team/Asgard). For the high-level workflow, CLA, and code of conduct, see [Asgard's CONTRIBUTING.md](https://github.com/MegaWiz-Dev-Team/Asgard/blob/main/CONTRIBUTING.md).

## This repo specifically

### Layout

- `src/` — Rust agent runtime (Axum, ReAct loop, tool registry)
- `bifrost/` — Python supporting modules (ADK adapters, service-agent definitions)
- `tests/` — pytest suite for end-to-end agent flows
- `generate_agents.py` — codegen helper that writes per-service agent stubs

### Development setup

```bash
# Rust runtime
cargo build --release

# Python tests / agent generation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # if present, otherwise install ad-hoc

python3 generate_agents.py        # regenerate agent stubs
```

### Running tests

```bash
cargo test
python -m pytest tests/ -v
```

### Style

- Rust: `cargo fmt` + `cargo clippy --all-targets -- -D warnings`
- Python: keep dependencies minimal; stdlib-first
- Conventional Commits (`feat:`, `fix:`, `docs:`, etc.)

### Reporting issues

- 🐛 Bugs: open an issue with the bug report template
- 💡 Features: open an issue with the feature request template
- 🔒 Security: see [SECURITY.md](SECURITY.md) (do **not** open public issues)

### License & CLA

By contributing, you agree to license your contribution under [AGPL-3.0](LICENSE) and the [Asgard CLA](https://github.com/MegaWiz-Dev-Team/Asgard/blob/main/CLA.md). Your first PR serves as your electronic signature.

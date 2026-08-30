# Use OIEC with Ollama

## Goal

Connect the governed agent to a local OpenAI-compatible Ollama endpoint without changing the authority model.

## Command recipe

```bash
oiec-stm-agent . \
  --model qwen3.8-27b-fast \
  --base-url http://localhost:11434/v1 \
  --api-key ollama \
  --preflight
```

## Learning route

Complete T01 Install and T02 First Read-Only Task.

## Boundary rules

Provider selection changes where proposals are generated. It does not grant file authority, approve candidates, certify output, or bypass evidence gates.

## Safe completion condition

Preflight identifies the intended endpoint and model, secrets are not embedded in documentation or browser storage, and the first task remains read-only.

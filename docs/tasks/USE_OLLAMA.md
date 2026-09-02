# Use OIEC with direct llama.cpp

## Goal

Connect the governed agent to a local model file through the direct llama.cpp process provider without changing the authority model.

## Command recipe

```bash
oiec-stm-agent . \
  --provider llama_cpp_process \
  --model qwen3.8-27b-direct \
  --model-path ../Neuro-llama/Qwen3.8-27B-Q2_K.gguf \
  --llama-cpp-root ../Neuro-llama/llama.cpp \
  --preflight
```

## Learning route

Complete T01 Install and T02 First Read-Only Task.

## Boundary rules

Provider selection changes where proposals are generated. It does not grant file authority, approve candidates, certify output, or bypass evidence gates.

## Safe completion condition

Preflight identifies the intended llama.cpp checkout, model path, and provider mode. The first task remains read-only and no provider secret is stored in documentation or browser storage.

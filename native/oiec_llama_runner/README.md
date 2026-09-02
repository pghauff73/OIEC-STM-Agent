# OIEC llama.cpp Runner

This executable is the bounded native inference process for
`LlamaCppProcessProvider`. It links to an external llama.cpp build and does not
vendor llama.cpp or Neuro application code.

Build:

```bash
cmake -S native/oiec_llama_runner -B build/oiec-llama-runner \
  -DLLAMA_CPP_ROOT=/path/to/llama.cpp \
  -DLLAMA_CPP_BUILD_DIR=/path/to/llama.cpp/build
cmake --build build/oiec-llama-runner --parallel
```

The process accepts one JSON request per line on standard input and emits JSON
events on standard output. Supported operations are `describe`, `complete`,
`cancel`, `reset_context`, and `shutdown`. A completion always creates and frees
its own bounded llama context; the process retains only the immutable loaded
model between requests. The runner uses the GGUF chat template when available,
applies only reviewed OIEC GBNF grammars, streams generated pieces, and reports
prompt, context, decode, first-token, cancellation, and timeout metrics through
the provider-neutral local-model contract.

The reviewed grammar set is deliberately finite:

```text
oiec_reasoning_response        ordinary structured message output
oiec_tool_response             ordinary message-or-tool output
oiec_compact_tool_response     no-whitespace function-call-only reasoning output
```

The compact grammar prevents indentation from consuming the bounded generation
budget and prevents machine-readable role JSON from being embedded as an
unvalidated message string. It is used for individual structured reasoning
objects and verifier micro-batches. It does not enlarge context, authority,
retry, or mutation permissions. Tool schemas constrain the allowed top-level
vocabulary without deciding role completeness; deterministic role validators
remain final.

`cancel` is not an in-process asynchronous llama.cpp operation because the
runner processes one request at a time. `LlamaCppProcessProvider` supplies the
effective cancellation boundary by terminating the isolated runner and starting
a new process for a later request.

## Provenance and licensing

The implementation is original OIEC-STM-Agent code informed by the
provider-neutral contract shape observed in the adjacent Neuro source tree. No
Neuro application, governance, transaction, protocol, or state code is copied.
The adjacent Neuro root has no declared repository license, so it is treated as
read-only design evidence. llama.cpp is linked as an external dependency under
its MIT license; distributions that bundle llama.cpp libraries must retain the
llama.cpp license notice.

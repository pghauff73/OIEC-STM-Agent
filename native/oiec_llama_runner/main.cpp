#include "llama.h"
#include "ggml-backend.h"
#include "nlohmann/json.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using json = nlohmann::ordered_json;
using Clock = std::chrono::steady_clock;

constexpr int kProtocolVersion = 1;
constexpr int kContextReserveTokens = 16;
constexpr const char * kSystemPrompt =
    "Return exactly one valid JSON object. No markdown. "
    "Do not expose private chain-of-thought.";

struct Options {
    std::filesystem::path model_path;
    std::filesystem::path grammar_dir;
    int context_tokens = 4096;
    int gpu_layers = -1;
    int threads = 0;
};

struct ContextDeleter {
    void operator()(llama_context * value) const {
        if (value) llama_free(value);
    }
};

struct SamplerDeleter {
    void operator()(llama_sampler * value) const {
        if (value) llama_sampler_free(value);
    }
};

using ContextPtr = std::unique_ptr<llama_context, ContextDeleter>;
using SamplerPtr = std::unique_ptr<llama_sampler, SamplerDeleter>;

std::string trim(const std::string & value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string read_text(const std::filesystem::path & path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read file: " + path.string());
    std::ostringstream output;
    output << input.rdbuf();
    return output.str();
}

void emit(const json & value) {
    std::cout << value.dump() << '\n' << std::flush;
}

json event(const std::string & type, const std::string & request_id, const std::string & status) {
    return {
        {"protocol_version", kProtocolVersion},
        {"type", type},
        {"request_id", request_id},
        {"status", status},
    };
}

int default_threads() {
    return static_cast<int>(std::max(1u, std::thread::hardware_concurrency()));
}

std::string backend_device_type_name(enum ggml_backend_dev_type type) {
    switch (type) {
        case GGML_BACKEND_DEVICE_TYPE_CPU: return "cpu";
        case GGML_BACKEND_DEVICE_TYPE_GPU: return "gpu";
        case GGML_BACKEND_DEVICE_TYPE_IGPU: return "igpu";
        case GGML_BACKEND_DEVICE_TYPE_ACCEL: return "accelerator";
        case GGML_BACKEND_DEVICE_TYPE_META: return "meta";
    }
    return "unknown";
}

json backend_devices() {
    json devices = json::array();
    const std::size_t count = ggml_backend_dev_count();
    for (std::size_t index = 0; index < count; ++index) {
        ggml_backend_dev_t device = ggml_backend_dev_get(index);
        ggml_backend_dev_props properties{};
        ggml_backend_dev_get_props(device, &properties);
        devices.push_back({
            {"index", index},
            {"name", properties.name ? properties.name : ""},
            {"description", properties.description ? properties.description : ""},
            {"device_id", properties.device_id ? properties.device_id : ""},
            {"type", backend_device_type_name(properties.type)},
            {"memory_free", properties.memory_free},
            {"memory_total", properties.memory_total},
            {"capabilities", {
                {"async", properties.caps.async},
                {"host_buffer", properties.caps.host_buffer},
                {"buffer_from_host_ptr", properties.caps.buffer_from_host_ptr},
                {"events", properties.caps.events},
                {"mmap", properties.caps.mmap_support},
            }},
        });
    }
    return devices;
}

std::string metadata_value(const llama_model * model, const char * key) {
    const int32_t required = llama_model_meta_val_str(model, key, nullptr, 0);
    if (required <= 0) return "";
    std::vector<char> buffer(static_cast<std::size_t>(required) + 1u, '\0');
    if (llama_model_meta_val_str(model, key, buffer.data(), buffer.size()) < 0) return "";
    return std::string(buffer.data());
}

std::string model_description(const llama_model * model) {
    std::vector<char> buffer(1024, '\0');
    const int32_t result = llama_model_desc(model, buffer.data(), buffer.size());
    if (result < 0) return "";
    return std::string(buffer.data());
}

std::vector<llama_token> tokenize(const llama_vocab * vocab, const std::string & text) {
    int32_t count = llama_tokenize(
        vocab,
        text.data(),
        static_cast<int32_t>(text.size()),
        nullptr,
        0,
        true,
        true);
    if (count >= 0) throw std::runtime_error("llama tokenizer did not report required size");
    std::vector<llama_token> tokens(static_cast<std::size_t>(-count));
    count = llama_tokenize(
        vocab,
        text.data(),
        static_cast<int32_t>(text.size()),
        tokens.data(),
        static_cast<int32_t>(tokens.size()),
        true,
        true);
    if (count < 0) throw std::runtime_error("llama tokenization failed");
    tokens.resize(static_cast<std::size_t>(count));
    return tokens;
}

std::string token_piece(const llama_vocab * vocab, llama_token token) {
    std::vector<char> buffer(256);
    int32_t size = llama_token_to_piece(
        vocab,
        token,
        buffer.data(),
        static_cast<int32_t>(buffer.size()),
        0,
        true);
    if (size < 0) {
        buffer.resize(static_cast<std::size_t>(-size));
        size = llama_token_to_piece(
            vocab,
            token,
            buffer.data(),
            static_cast<int32_t>(buffer.size()),
            0,
            true);
    }
    if (size < 0) throw std::runtime_error("llama token-to-piece failed");
    return std::string(buffer.data(), static_cast<std::size_t>(size));
}

std::string fallback_prompt(const std::string & prompt) {
    return
        "<|im_start|>system\n" + std::string(kSystemPrompt) + "<|im_end|>\n"
        "<|im_start|>user\n" + prompt + "<|im_end|>\n"
        "<|im_start|>assistant\n";
}

std::string format_prompt(
    const llama_model * model,
    const std::string & prompt,
    bool use_chat_template) {
    if (!use_chat_template) return fallback_prompt(prompt);
    const char * chat_template = llama_model_chat_template(model, nullptr);
    if (!chat_template || !*chat_template) {
        throw std::runtime_error("model does not expose a supported chat template");
    }
    const llama_chat_message messages[] = {
        {"system", kSystemPrompt},
        {"user", prompt.c_str()},
    };
    const int32_t required = llama_chat_apply_template(
        chat_template, messages, 2, true, nullptr, 0);
    if (required < 0) {
        throw std::runtime_error("llama.cpp cannot apply the model chat template");
    }
    if (static_cast<std::uint64_t>(required) + 1u >
        static_cast<std::uint64_t>(std::numeric_limits<int32_t>::max())) {
        throw std::runtime_error("chat template output exceeds llama.cpp limits");
    }
    std::vector<char> buffer(static_cast<std::size_t>(required) + 1u, '\0');
    const int32_t written = llama_chat_apply_template(
        chat_template,
        messages,
        2,
        true,
        buffer.data(),
        static_cast<int32_t>(buffer.size()));
    if (written < 0 || written > required) {
        throw std::runtime_error("chat template formatting failed");
    }
    return std::string(buffer.data(), static_cast<std::size_t>(written));
}

Options parse_options(int argc, char ** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (index + 1 >= argc) throw std::runtime_error("missing value for " + argument);
        const std::string value = argv[++index];
        if (argument == "--model") options.model_path = value;
        else if (argument == "--context") options.context_tokens = std::stoi(value);
        else if (argument == "--gpu-layers") options.gpu_layers = std::stoi(value);
        else if (argument == "--threads") options.threads = std::stoi(value);
        else if (argument == "--grammar-dir") options.grammar_dir = value;
        else throw std::runtime_error("unknown argument: " + argument);
    }
    if (options.model_path.empty()) throw std::runtime_error("--model is required");
    if (options.grammar_dir.empty()) throw std::runtime_error("--grammar-dir is required");
    if (options.context_tokens < 256) throw std::runtime_error("context must be at least 256");
    if (options.threads <= 0) options.threads = default_threads();
    return options;
}

class Runner {
public:
    explicit Runner(Options options) : options_(std::move(options)) {
        llama_backend_init();
        llama_model_params params = llama_model_default_params();
        params.n_gpu_layers = options_.gpu_layers;
        if (options_.gpu_layers == 0) params.use_extra_bufts = false;
        model_ = llama_model_load_from_file(options_.model_path.string().c_str(), params);
        if (!model_) {
            llama_backend_free();
            throw std::runtime_error("unable to load GGUF model");
        }
        vocab_ = llama_model_get_vocab(model_);
        if (!vocab_) throw std::runtime_error("loaded model has no vocabulary");
    }

    ~Runner() {
        if (model_) llama_model_free(model_);
        llama_backend_free();
    }

    json descriptor() const {
        const char * chat_template = llama_model_chat_template(model_, nullptr);
        return {
            {"runner", "oiec-llama-runner"},
            {"runner_version", 1},
            {"model_architecture", metadata_value(model_, "general.architecture")},
            {"model_name", metadata_value(model_, "general.name")},
            {"quantization", metadata_value(model_, "general.file_type")},
            {"model_description", model_description(model_)},
            {"parameter_count", llama_model_n_params(model_)},
            {"tensor_size", llama_model_size(model_)},
            {"training_context_tokens", llama_model_n_ctx_train(model_)},
            {"context_tokens", options_.context_tokens},
            {"gpu_layers", options_.gpu_layers},
            {"threads", options_.threads},
            {"supports_grammar", true},
            {"supports_json_grammar", true},
            {"supports_json_schema", false},
            {"supports_chat_template", chat_template && *chat_template},
            {"supports_gpu_offload", options_.gpu_layers != 0},
            {"supports_streaming", true},
            {"supports_deadline", true},
            {"supports_cancel_operation", false},
            {"process_supervised_cancellation", true},
            {"fresh_context_per_completion", true},
            {"backend_devices", backend_devices()},
            {"system_info", llama_print_system_info()},
        };
    }

    json complete(const json & request) const {
        const std::string request_id = request.at("request_id").get<std::string>();
        const auto started = Clock::now();
        const int deadline_ms = request.value("deadline_ms", 600000);
        const int context_tokens = request.value("context_tokens", options_.context_tokens);
        const int output_limit = request.value("max_output_tokens", 2048);
        const int seed = request.value("seed", 1234);
        const int top_k = request.value("top_k", 40);
        const float top_p = request.value("top_p", 0.95f);
        const float temperature = request.value("temperature", 0.1f);
        const bool use_chat_template = request.value("use_chat_template", true);
        if (context_tokens < 256 || context_tokens > options_.context_tokens) {
            json failure = event("error", request_id, "unsupported_contract");
            failure["diagnostic"] = "requested context exceeds runner bound";
            return failure;
        }
        if (output_limit < 1 || output_limit >= context_tokens) {
            json failure = event("error", request_id, "unsupported_contract");
            failure["diagnostic"] = "invalid output token bound";
            return failure;
        }
        const std::string grammar_id = request.at("grammar").get<std::string>();
        if (grammar_id != "oiec_reasoning_response" &&
            grammar_id != "oiec_tool_response" &&
            grammar_id != "oiec_compact_tool_response") {
            json failure = event("error", request_id, "unsupported_contract");
            failure["diagnostic"] = "unknown grammar identifier";
            return failure;
        }
        const std::string grammar = read_text(options_.grammar_dir / (grammar_id + ".gbnf"));
        if (use_chat_template) {
            const char * chat_template = llama_model_chat_template(model_, nullptr);
            if (!chat_template || !*chat_template) {
                json failure = event("error", request_id, "unsupported_contract");
                failure["diagnostic"] = "model does not expose a supported chat template";
                return failure;
            }
        }
        const std::string formatted = format_prompt(
            model_, request.at("prompt").get<std::string>(), use_chat_template);
        const auto tokenized_at = Clock::now();
        const std::vector<llama_token> prompt_tokens = tokenize(vocab_, formatted);
        const auto tokenized_done = Clock::now();
        if (prompt_tokens.size() + static_cast<std::size_t>(output_limit) + kContextReserveTokens >
            static_cast<std::size_t>(context_tokens)) {
            json failure = event("error", request_id, "context_overflow");
            failure["diagnostic"] = "prompt plus output exceeds bounded context";
            return failure;
        }

        const auto context_started = Clock::now();
        llama_context_params context_params = llama_context_default_params();
        context_params.n_ctx = static_cast<uint32_t>(context_tokens);
        context_params.n_batch = std::min<uint32_t>(512, context_params.n_ctx);
        context_params.n_ubatch = context_params.n_batch;
        context_params.n_threads = options_.threads;
        context_params.n_threads_batch = options_.threads;
        context_params.no_perf = true;
        ContextPtr context(llama_init_from_model(model_, context_params));
        if (!context) throw std::runtime_error("unable to create bounded llama context");
        const auto context_ready = Clock::now();

        const auto prompt_decode_started = Clock::now();
        for (std::size_t offset = 0; offset < prompt_tokens.size();) {
            if (elapsed_ms(started) >= deadline_ms) {
                json failure = event("error", request_id, "deadline_exceeded");
                failure["diagnostic"] = "deadline exceeded during prompt decode";
                return failure;
            }
            const int32_t count = static_cast<int32_t>(
                std::min<std::size_t>(context_params.n_batch, prompt_tokens.size() - offset));
            llama_batch batch = llama_batch_get_one(
                const_cast<llama_token *>(prompt_tokens.data() + offset), count);
            if (llama_decode(context.get(), batch) != 0) {
                throw std::runtime_error("llama prompt decode failed");
            }
            offset += static_cast<std::size_t>(count);
        }
        const auto prompt_decode_done = Clock::now();

        llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
        sampler_params.no_perf = true;
        SamplerPtr sampler(llama_sampler_chain_init(sampler_params));
        if (!sampler) throw std::runtime_error("unable to create sampler chain");
        llama_sampler * grammar_sampler = llama_sampler_init_grammar(vocab_, grammar.c_str(), "root");
        if (!grammar_sampler) {
            json failure = event("error", request_id, "unsupported_contract");
            failure["diagnostic"] = "GBNF grammar initialization failed";
            return failure;
        }
        llama_sampler_chain_add(sampler.get(), grammar_sampler);
        llama_sampler_chain_add(sampler.get(), llama_sampler_init_top_k(std::max(1, top_k)));
        llama_sampler_chain_add(sampler.get(), llama_sampler_init_top_p(std::clamp(top_p, 0.0f, 1.0f), 1));
        if (temperature <= 0.0f) llama_sampler_chain_add(sampler.get(), llama_sampler_init_greedy());
        else {
            llama_sampler_chain_add(sampler.get(), llama_sampler_init_temp(temperature));
            llama_sampler_chain_add(sampler.get(), llama_sampler_init_dist(static_cast<uint32_t>(seed)));
        }

        const auto decode_at = Clock::now();
        std::string output;
        int output_tokens = 0;
        std::int64_t first_token_ms = -1;
        while (output_tokens < output_limit) {
            if (elapsed_ms(started) >= deadline_ms) {
                json failure = event("error", request_id, "deadline_exceeded");
                failure["diagnostic"] = "deadline exceeded during generation";
                return failure;
            }
            const llama_token token = llama_sampler_sample(sampler.get(), context.get(), -1);
            if (llama_vocab_is_eog(vocab_, token)) break;
            const std::string piece = token_piece(vocab_, token);
            output += piece;
            ++output_tokens;
            if (first_token_ms < 0) first_token_ms = elapsed_ms(started);
            json stream = event("stream", request_id, "ok");
            stream["text"] = piece;
            emit(stream);
            llama_batch batch = llama_batch_get_one(const_cast<llama_token *>(&token), 1);
            if (llama_decode(context.get(), batch) != 0) {
                throw std::runtime_error("llama generation decode failed");
            }
            const std::string candidate = trim(output);
            if (!candidate.empty() && candidate.front() == '{' && candidate.back() == '}') {
                try {
                    const json parsed = json::parse(candidate);
                    if (parsed.is_object()) break;
                } catch (const json::exception &) {
                }
            }
        }
        const std::string cleaned = trim(output);
        json parsed;
        try {
            parsed = json::parse(cleaned);
        } catch (const json::exception & error) {
            json failure = event("error", request_id, "invalid_output");
            failure["diagnostic"] = std::string("generated output is not a JSON object: ") + error.what();
            failure["text"] = cleaned.substr(0, 512);
            return failure;
        }
        if (!parsed.is_object()) {
            json failure = event("error", request_id, "invalid_output");
            failure["diagnostic"] = "generated JSON is not an object";
            return failure;
        }
        json result = event("result", request_id, "ok");
        result["text"] = cleaned;
        result["response"] = parsed;
        result["metrics"] = {
            {"attempts_used", 1},
            {"prompt_tokens", prompt_tokens.size()},
            {"output_tokens", output_tokens},
            {"tokenize_ms", elapsed_ms(tokenized_at, tokenized_done)},
            {"context_reset_ms", elapsed_ms(context_started, context_ready)},
            {"prompt_decode_ms", elapsed_ms(prompt_decode_started, prompt_decode_done)},
            {"decode_ms", elapsed_ms(decode_at)},
            {"first_token_ms", first_token_ms},
            {"total_ms", elapsed_ms(started)},
            {"timed_out", false},
            {"cancelled", false},
            {"no_first_token", first_token_ms < 0},
            {"timed_out_stage", ""},
        };
        return result;
    }

private:
    static std::int64_t elapsed_ms(Clock::time_point started, Clock::time_point ended = Clock::now()) {
        return std::chrono::duration_cast<std::chrono::milliseconds>(ended - started).count();
    }

    Options options_;
    llama_model * model_ = nullptr;
    const llama_vocab * vocab_ = nullptr;
};

} 

int main(int argc, char ** argv) {
    try {
        Runner runner(parse_options(argc, argv));
        std::string line;
        while (std::getline(std::cin, line)) {
            if (trim(line).empty()) continue;
            json request;
            std::string request_id = "unknown";
            try {
                request = json::parse(line);
                request_id = request.value("request_id", "unknown");
                if (request.value("protocol_version", 0) != kProtocolVersion) {
                    json failure = event("error", request_id, "unsupported_contract");
                    failure["diagnostic"] = "protocol version mismatch";
                    emit(failure);
                    continue;
                }
                const std::string operation = request.at("op").get<std::string>();
                if (operation == "describe") {
                    json response = event("result", request_id, "ok");
                    response["descriptor"] = runner.descriptor();
                    emit(response);
                } else if (operation == "complete") {
                    emit(runner.complete(request));
                } else if (operation == "cancel" || operation == "reset_context") {
                    emit(event("result", request_id, "ok"));
                } else if (operation == "shutdown") {
                    emit(event("result", request_id, "ok"));
                    break;
                } else {
                    json failure = event("error", request_id, "unsupported_contract");
                    failure["diagnostic"] = "unknown operation";
                    emit(failure);
                }
            } catch (const std::exception & error) {
                json failure = event("error", request_id, "provider_error");
                failure["diagnostic"] = error.what();
                emit(failure);
            }
        }
        return 0;
    } catch (const std::exception & error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}

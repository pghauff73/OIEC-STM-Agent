cmake_minimum_required(VERSION 3.20)
project(oiec_llama_runner LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(LLAMA_CPP_ROOT "" CACHE PATH "Path to an external llama.cpp source tree")
set(LLAMA_CPP_BUILD_DIR "" CACHE PATH "Path to the matching external llama.cpp build tree")

if(NOT LLAMA_CPP_ROOT OR NOT LLAMA_CPP_BUILD_DIR)
    message(FATAL_ERROR "LLAMA_CPP_ROOT and LLAMA_CPP_BUILD_DIR are required")
endif()

find_path(LLAMA_INCLUDE_DIR llama.h PATHS "${LLAMA_CPP_ROOT}/include" NO_DEFAULT_PATH REQUIRED)
find_path(GGML_INCLUDE_DIR ggml.h PATHS "${LLAMA_CPP_ROOT}/ggml/include" NO_DEFAULT_PATH REQUIRED)
find_path(NLOHMANN_INCLUDE_DIR nlohmann/json.hpp PATHS "${LLAMA_CPP_ROOT}/vendor" NO_DEFAULT_PATH REQUIRED)
find_library(LLAMA_LIBRARY llama PATHS "${LLAMA_CPP_BUILD_DIR}/bin" NO_DEFAULT_PATH REQUIRED)
find_library(GGML_LIBRARY ggml PATHS "${LLAMA_CPP_BUILD_DIR}/bin" NO_DEFAULT_PATH REQUIRED)
find_library(GGML_BASE_LIBRARY ggml-base PATHS "${LLAMA_CPP_BUILD_DIR}/bin" NO_DEFAULT_PATH REQUIRED)

add_executable(oiec-llama-runner main.cpp)
target_include_directories(
    oiec-llama-runner
    PRIVATE
        "${LLAMA_INCLUDE_DIR}"
        "${GGML_INCLUDE_DIR}"
        "${NLOHMANN_INCLUDE_DIR}"
)
target_link_libraries(
    oiec-llama-runner
    PRIVATE
        "${LLAMA_LIBRARY}"
        "${GGML_LIBRARY}"
        "${GGML_BASE_LIBRARY}"
        dl
        pthread
)
set_target_properties(
    oiec-llama-runner
    PROPERTIES
        BUILD_RPATH "${LLAMA_CPP_BUILD_DIR}/bin"
        INSTALL_RPATH "${LLAMA_CPP_BUILD_DIR}/bin"
)

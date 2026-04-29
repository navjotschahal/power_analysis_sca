cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(pico_aes_attack C CXX ASM)

pico_sdk_init()

add_executable(pico_aes_attack
    main.cpp
)

# Pull in mbedtls and standard libraries
target_include_directories(pico_aes_attack PRIVATE ${CMAKE_CURRENT_LIST_DIR})

target_link_libraries(pico_aes_attack
    pico_stdlib
    pico_mbedtls
)

# cmake -DUSE_USB=ON -DUSE_UART=ON .. to enable both (default: both ON)
option(USE_USB  "Enable USB CDC stdio"  ON)
option(USE_UART "Enable UART stdio"     ON)

pico_enable_stdio_usb(pico_aes_attack  ${USE_USB})
pico_enable_stdio_uart(pico_aes_attack ${USE_UART})

pico_add_extra_outputs(pico_aes_attack)
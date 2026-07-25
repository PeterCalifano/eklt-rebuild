# Verify the public targets and feature variables of an installed package.
cmake_minimum_required(VERSION 3.15)

project(eklt_rebuild_installed_consumer LANGUAGES CXX)

find_package(eklt-rebuild 0.1 CONFIG REQUIRED)

add_executable(eklt_rebuild_installed_consumer main.cpp)
set_target_properties(
    eklt_rebuild_installed_consumer
    PROPERTIES
        CXX_STANDARD 11
        CXX_STANDARD_REQUIRED YES
        CXX_EXTENSIONS NO
)
target_link_libraries(
    eklt_rebuild_installed_consumer
    PRIVATE
        eklt_rebuild::eklt_core
        eklt_rebuild::eklt-rebuild
)

foreach(required_target IN ITEMS
        eklt_rebuild::event_recon_fibar_core
        eklt_rebuild::event_recon_fibar_adapters)
    if(NOT TARGET "${required_target}")
        message(FATAL_ERROR "Missing installed API target: ${required_target}")
    endif()
endforeach()

if(NOT eklt_rebuild_WITH_FIBAR OR NOT eklt_rebuild_WITH_ADAPTERS)
    message(FATAL_ERROR
        "The installed native library must expose FIBAR and adapter APIs")
endif()

if(eklt_rebuild_WITH_CERES)
    target_compile_definitions(
        eklt_rebuild_installed_consumer
        PRIVATE EKLT_CONSUMER_WITH_CERES=1
    )
endif()

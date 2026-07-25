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
)

if(TARGET eklt_rebuild::event_recon_fibar_core)
    target_compile_definitions(
        eklt_rebuild_installed_consumer
        PRIVATE EKLT_CONSUMER_WITH_FIBAR=1
    )
    target_link_libraries(
        eklt_rebuild_installed_consumer
        PRIVATE eklt_rebuild::event_recon_fibar_core
    )
endif()

if(eklt_rebuild_WITH_CERES)
    target_compile_definitions(
        eklt_rebuild_installed_consumer
        PRIVATE EKLT_CONSUMER_WITH_CERES=1
    )
endif()

if(TARGET eklt_rebuild::event_recon_fibar_adapters)
    target_compile_definitions(
        eklt_rebuild_installed_consumer
        PRIVATE EKLT_CONSUMER_WITH_ADAPTERS=1
    )
    target_link_libraries(
        eklt_rebuild_installed_consumer
        PRIVATE eklt_rebuild::event_recon_fibar_adapters
    )
endif()

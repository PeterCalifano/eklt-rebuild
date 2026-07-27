# Register project-owned native and ROS1 Catch2 targets.
include(Catch)

set(EKLT_ROS_FREE_TESTS
    test_eklt_core_providers
    test_event_recon_fibar_core
    test_event_recon_fibar_adapters
    test_eklt_core_photometric
    test_eklt_core_orchestrator
)

foreach(test_target IN LISTS EKLT_ROS_FREE_TESTS)
    add_executable(${test_target} ${test_target}.cpp)
    target_compile_features(${test_target} PRIVATE cxx_std_17)
    target_link_libraries(
        ${test_target}
        PRIVATE
            Catch2::Catch2WithMain
            eklt_compile_options
    )

    if(test_target STREQUAL "test_event_recon_fibar_core" OR
       test_target STREQUAL "test_event_recon_fibar_adapters" OR
       test_target STREQUAL "test_eklt_core_photometric" OR
       test_target STREQUAL "test_eklt_core_orchestrator")
        target_link_libraries(${test_target} PRIVATE ${LIB_TARGET_NAME})
    else()
        target_link_libraries(${test_target} PRIVATE eklt_core)
    endif()

    catch_discover_tests(
        ${test_target}
        REPORTER compact
        PROPERTIES LABELS "catch2;ros-free"
    )
endforeach()

if(EKLT_BUILD_ROS1 AND TARGET eklt)
    foreach(test_target IN ITEMS test_optimizer test_patch test_tracker_utils)
        add_executable(${test_target} ${test_target}.cpp)
        target_compile_features(${test_target} PRIVATE cxx_std_17)
        target_include_directories(
            ${test_target}
            PRIVATE
                "${PROJECT_SOURCE_DIR}/src/ros1"
                "${CMAKE_CURRENT_SOURCE_DIR}"
        )
        target_link_libraries(
            ${test_target}
            PRIVATE
                Catch2::Catch2WithMain
                eklt
                ${catkin_LIBRARIES}
                ${OpenCV_LIBRARIES}
        )
        catch_discover_tests(
            ${test_target}
            REPORTER compact
            PROPERTIES LABELS "catch2;ros1"
        )
    endforeach()
endif()

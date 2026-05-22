set(CATCH2_TEST_PROPERTIES "--output-on-failure" "--reporter=compact")

set(CATCH2_INCLUDE_DIR "")
foreach(candidate_dir
        "${PROJECT_SOURCE_DIR}/lib/Catch2/single_include"
        "${PROJECT_SOURCE_DIR}/lib/Catch2/src")
    if(EXISTS "${candidate_dir}/catch2/catch.hpp")
        set(CATCH2_INCLUDE_DIR "${candidate_dir}")
        break()
    endif()
endforeach()

if(CATCH2_INCLUDE_DIR STREQUAL "")
    message(FATAL_ERROR "Catch2 headers were not found in lib/Catch2.")
endif()

set(EKLT_REGRESSION_TEST_SOURCES
    catch_main.cpp
)

set(EKLT_REGRESSION_TESTS
    test_patch
    test_tracker_utils
)

# Add regression tests to test suite (catch2)
foreach(test_target ${EKLT_REGRESSION_TESTS})
    add_executable(${test_target}
        ${test_target}.cpp
        ${EKLT_REGRESSION_TEST_SOURCES}
    )

    target_include_directories(${test_target}
        PRIVATE
            ${PROJECT_SOURCE_DIR}/include
            ${CMAKE_CURRENT_SOURCE_DIR}
            ${CATCH2_INCLUDE_DIR}
    )

    target_link_libraries(${test_target}
        PRIVATE
            ${project_name}
    )

    catch_discover_tests(${test_target} PROPERTIES ${CATCH2_TEST_PROPERTIES})
endforeach()

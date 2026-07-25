cmake_minimum_required(VERSION 3.15 FATAL_ERROR)

# Configure the ROS-free libraries, optional ROS1 compatibility target, and
# main-project validation/packaging entrypoints.
#
# Preserve the published library/package name while deriving the identifier
# required by CMake namespaces, generated wrappers, Python, ROS1, and ROS2.
set(project_name "eklt-rebuild")
string(MAKE_C_IDENTIFIER "${project_name}" project_identifier)

project(
    ${project_identifier}
    VERSION 0.1.0
    DESCRIPTION "Event-based KLT tracking and event-only reconstruction utilities"
    HOMEPAGE_URL "https://github.com/uzh-rpg/rpg_eklt"
    LANGUAGES CXX
)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
    message(FATAL_ERROR "In-source builds are not supported. Configure a separate build directory.")
endif()

set(BUILD_AS_MAIN_PROJECT ON)
if(NOT CMAKE_SOURCE_DIR STREQUAL PROJECT_SOURCE_DIR)
    set(BUILD_AS_MAIN_PROJECT OFF)
endif()

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

include(CMakePackageConfigHelpers)
include(GNUInstallDirs)

option(BUILD_SHARED_LIBS "Build compiled EKLT libraries as shared libraries" ON)
option(EKLT_BUILD_ROS1 "Build the ROS1 tracker and node through catkin_simple" OFF)
option(EKLT_BUILD_FIBAR "Build the ROS-free FIBAR reconstruction library" ON)
option(EKLT_BUILD_PYTHON "Generate the Python 3.12 wrapper with gtwrap" OFF)
option(EKLT_BUILD_MATLAB "Generate the MATLAB R2024b wrapper with gtwrap" OFF)
option(EKLT_BUILD_DOCS "Enable Doxygen documentation targets" OFF)
option(ENABLE_TESTS "Build Catch2 regression tests" ON)
option(ENABLE_FETCH_CATCH2 "Fetch Catch2 v3 into the build tree when unavailable" ON)
option(ENABLE_CUDA "Enable reusable CUDA build support" OFF)
option(ENABLE_TBB "Enable oneTBB on EKLT native targets" OFF)
option(ENABLE_OMP "Enable OpenMP on EKLT native targets" OFF)
option(ENABLE_OPENGL "Enable OpenGL on EKLT native targets" OFF)
option(NO_OPTIMIZATION "Disable compiler optimization for EKLT targets" OFF)
option(WARNINGS_ARE_ERRORS "Treat EKLT compiler warnings as errors" OFF)
option(SANITIZE_BUILD "Enable configured sanitizers on non-Release builds" OFF)
option(
    PROFILING_PROPAGATES_TO_CONSUMERS
    "Propagate profiling usage requirements through installed EKLT targets"
    OFF
)
set(SANITIZERS "address,undefined" CACHE STRING "Comma-separated sanitizer set")

if(BUILD_AS_MAIN_PROJECT AND ENABLE_TESTS)
    include(CTest)
endif()

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE "RelWithDebInfo" CACHE STRING "CMake build type" FORCE)
endif()

set(EKLT_MATLAB_RELEASE "R2024b" CACHE STRING "Supported MATLAB release")
set(EKLT_PYTHON_MIN_VERSION "3.12" CACHE STRING "Minimum supported Python version")
set(EKLT_PACKAGE_NAME "${project_name}")
set(LIB_NAMESPACE "${project_identifier}")
set(LIB_TARGET_NAME "${project_name}")
set(PROJECT_PYTHON_VERSION "${EKLT_PYTHON_MIN_VERSION}")
set(MATLAB_DEFAULT_RELEASE "${EKLT_MATLAB_RELEASE}")
set(FULL_VERSION "${PROJECT_VERSION}")
string(TOLOWER "${CMAKE_BUILD_TYPE}" CMAKE_BUILD_TYPE_LOWER)

include(cmake/HandleCompilerFlags.cmake)
include(cmake/HandleSanitizers.cmake)
include(cmake/HandleProfiling.cmake)
include(cmake/HandleTBB.cmake)
include(cmake/HandleOpenMP.cmake)
include(cmake/HandleOpenGL.cmake)
include(cmake/HandleCUDA.cmake)
include(cmake/toolchains/HandleToolchain.cmake)

handle_compiler_flags(CXX_STANDARD 11)

add_library(eklt_compile_options INTERFACE)
target_compile_features(eklt_compile_options INTERFACE cxx_std_11)
if(WARNINGS_ARE_ERRORS)
    target_compile_options(eklt_compile_options INTERFACE
        $<$<COMPILE_LANG_AND_ID:CXX,GNU,Clang,AppleClang>:-Werror>)
endif()

set(SANITIZER_TARGET eklt_sanitizer_options)
handle_sanitizers()

set(PROFILING_COMPILE_TARGET eklt_profiling_options)
handle_profiling(TARGET ${PROFILING_COMPILE_TARGET})

add_library(eklt_optional_dependencies INTERFACE)
set(TOOLCHAIN_COMPILE_TARGET eklt_toolchain_options)
handle_toolchain(TARGET ${TOOLCHAIN_COMPILE_TARGET})
target_link_libraries(
    eklt_optional_dependencies
    INTERFACE ${TOOLCHAIN_COMPILE_TARGET}
)
handle_tbb(TARGET eklt_optional_dependencies)
handle_openmp()
handle_opengl(TARGET eklt_opengl_options)
if(TARGET eklt_opengl_options)
    target_link_libraries(eklt_optional_dependencies INTERFACE eklt_opengl_options)
endif()
if(ENABLE_CUDA)
    enable_language(CUDA)
    handle_cuda(TARGET eklt_cuda_options MIN_VERSION 12.0)
    target_link_libraries(eklt_optional_dependencies INTERFACE eklt_cuda_options)
endif()

find_package(OpenCV 4 REQUIRED COMPONENTS core imgproc features2d)
find_package(Ceres QUIET)
set(EKLT_FIBAR_TARGET "${LIB_TARGET_NAME}")

if(EKLT_BUILD_PYTHON OR EKLT_BUILD_MATLAB)
    if(NOT EKLT_BUILD_FIBAR)
        message(FATAL_ERROR
            "EKLT_BUILD_PYTHON or EKLT_BUILD_MATLAB requires "
            "EKLT_BUILD_FIBAR=ON")
    endif()
    find_package(Eigen3 3.4 REQUIRED NO_MODULE)
endif()

# Match the parent-template ownership boundary: the root configures policies
# and dependencies, while src/ owns libraries, installation, and exports.
add_subdirectory(src)

if(EKLT_BUILD_ROS1)
    find_package(catkin_simple REQUIRED)
    catkin_simple(ALL_DEPS_REQUIRED)

    set(EKLT_ROS1_HEADERS
        include/error.h
        include/flags.h
        include/optimizer.h
        include/patch.h
        include/tracker.h
        include/tracker_utils.h
        include/types.h
        include/viewer.h
    )
    set(EKLT_ROS1_SOURCES
        src/flags.cpp
        src/optimizer.cpp
        src/tracker.cpp
        src/viewer.cpp
    )

    cs_add_library(eklt ${EKLT_ROS1_SOURCES} ${EKLT_ROS1_HEADERS})
    target_compile_features(eklt PUBLIC cxx_std_11)
    target_link_libraries(
        eklt
        PUBLIC
            eklt_core
            ${OpenCV_LIBRARIES}
            ${catkin_LIBRARIES}
        PRIVATE
            eklt_compile_options
            eklt_optional_dependencies
            ${SANITIZER_TARGET}
            ${PROFILING_COMPILE_TARGET}
    )
    if(TARGET ${EKLT_FIBAR_TARGET})
        # Keep the C++17 FIBAR requirement private so ROS1 consumers retain
        # the original C++11-facing target contract.
        target_link_libraries(eklt PRIVATE ${EKLT_FIBAR_TARGET})
    endif()

    cs_add_executable(eklt_node src/eklt_node.cpp)
    target_compile_features(eklt_node PRIVATE cxx_std_11)
    target_link_libraries(
        eklt_node
        PRIVATE eklt ${OpenCV_LIBRARIES} ${catkin_LIBRARIES}
    )

    cs_install()
    cs_export()
endif()

if(BUILD_AS_MAIN_PROJECT AND ENABLE_TESTS AND BUILD_TESTING)
    include(cmake/HandleCatch2.cmake)
    if(Catch2_FOUND)
        add_subdirectory(tests)
    endif()
endif()

if(BUILD_AS_MAIN_PROJECT AND (EKLT_BUILD_PYTHON OR EKLT_BUILD_MATLAB))
    set(${LIB_NAMESPACE}_BUILD_PYTHON_WRAPPER "${EKLT_BUILD_PYTHON}")
    set(${LIB_NAMESPACE}_BUILD_MATLAB_WRAPPER "${EKLT_BUILD_MATLAB}")
    set(
        ${LIB_NAMESPACE}_WRAPPER_INTERFACE_FILES
        "${CMAKE_CURRENT_SOURCE_DIR}/wrap_interfaces/fibar_reconstructor.i"
        CACHE STRING "Ordered gtwrap interface files for EKLT" FORCE
    )
    set(
        ${LIB_NAMESPACE}_GTWRAP_TOP_NAMESPACE
        "event_recon_fibar_adapters"
        CACHE STRING "Top namespace used for EKLT gtwrap generation" FORCE
    )
    set(
        ${LIB_NAMESPACE}_GTWRAP_DEPENDENCY_TARGETS
        "event_recon_fibar_adapters"
        CACHE STRING "Targets required before EKLT wrapper generation" FORCE
    )
    set(
        ${LIB_NAMESPACE}_GTWRAP_ROOT_DIR
        "${CMAKE_CURRENT_SOURCE_DIR}/lib/wrap"
        CACHE PATH "Pinned local gtwrap checkout" FORCE
    )
    set(
        GTWRAP_SYNC_TO_MASTER
        OFF CACHE BOOL "Keep the pinned gtwrap checkout unchanged" FORCE
    )
    set(
        GTWRAP_INIT_SUBMODULE_IF_MISSING
        OFF CACHE BOOL "Do not mutate submodules during CMake configure" FORCE
    )
    set(
        GTWRAP_ADD_SUBMODULE_IF_MISSING
        OFF CACHE BOOL "Do not add submodules during CMake configure" FORCE
    )
    set(LIBNAME_WRAP_TARGET event_recon_fibar_adapters)

    if(EKLT_BUILD_MATLAB AND NOT DEFINED Matlab_ROOT_DIR)
        set(
            Matlab_ROOT_DIR
            "/usr/local/MATLAB/${EKLT_MATLAB_RELEASE}"
            CACHE PATH "MATLAB root used for EKLT MEX generation"
        )
    endif()

    include(cmake/HandleWrapper.cmake)
    handle_gtwrappers()
endif()

if(BUILD_AS_MAIN_PROJECT AND EKLT_BUILD_DOCS)
    find_package(Doxygen QUIET)
    include(cmake/HandleDoxygenDocs.cmake)
    handle_doxygen_docs(
        TARGET_PREFIX eklt
        DOXYFILE_IN "${CMAKE_CURRENT_SOURCE_DIR}/doc/Doxyfile.in"
        MAIN_PAGE "${CMAKE_CURRENT_SOURCE_DIR}/doc/main_page.md"
        LAYOUT_FILE "${CMAKE_CURRENT_SOURCE_DIR}/doc/DoxygenLayout.xml"
        INPUT_DIRS
            "${CMAKE_CURRENT_SOURCE_DIR}/include"
            "${CMAKE_CURRENT_SOURCE_DIR}/src"
            "${CMAKE_CURRENT_SOURCE_DIR}/doc"
        EXCLUDE_DIRS
            "${CMAKE_CURRENT_SOURCE_DIR}/doc/developments/reports"
    )
endif()

if(BUILD_AS_MAIN_PROJECT)
    set(CPACK_PACKAGE_NAME "${EKLT_PACKAGE_NAME}")
    set(CPACK_PACKAGE_VENDOR "EKLT maintainers")
    set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "${PROJECT_DESCRIPTION}")
    set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}")
    set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE")
    set(CPACK_RESOURCE_FILE_README "${CMAKE_CURRENT_SOURCE_DIR}/README.md")
    set(CPACK_SOURCE_GENERATOR "TGZ")
    set(CPACK_SOURCE_PACKAGE_FILE_NAME "${EKLT_PACKAGE_NAME}-${PROJECT_VERSION}")
    set(CPACK_VERBATIM_VARIABLES YES)
    set(_eklt_source_root_regex "${CMAKE_CURRENT_SOURCE_DIR}")
    string(
        REGEX REPLACE "([][+.*^$()|?\\\\])" "\\\\\\1"
        _eklt_source_root_regex "${_eklt_source_root_regex}"
    )
    set(
        CPACK_SOURCE_IGNORE_FILES
        "^${_eklt_source_root_regex}/(.*/)?\\.git(/|$)"
        "^${_eklt_source_root_regex}/(.*/)?build[^/]*/"
        "^${_eklt_source_root_regex}/(.*/)?install/"
        "^${_eklt_source_root_regex}/ros2/(build|install|log)/"
        "^${_eklt_source_root_regex}/(data|outputs|logs?|devel)/"
        "^${_eklt_source_root_regex}/(\\.catkin_tools|\\.codex)/"
        "^${_eklt_source_root_regex}/(.*/)?\\.pytest_cache/"
        "^${_eklt_source_root_regex}/(.*/)?\\.mypy_cache/"
        "^${_eklt_source_root_regex}/(.*/)?__pycache__/"
        "^${_eklt_source_root_regex}/.*\\.py[cod]$"
        "^${_eklt_source_root_regex}/.*\\.so(\\..*)?$"
        "^${_eklt_source_root_regex}/.*\\.(dylib|dll|pyd)$"
        "^${_eklt_source_root_regex}/CONTEXT\\.md$"
        "^${_eklt_source_root_regex}/lib\\.root-owned-backup/"
    )
    include(CPack)
endif()

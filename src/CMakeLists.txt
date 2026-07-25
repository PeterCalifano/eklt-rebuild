# ROS-free EKLT library composition and installation.
#
# The repository root owns project policy and dependency discovery. This
# directory owns native targets, their public headers, and the exported CMake
# package so nested consumers and ROS overlays use one canonical target graph.

# Install only target-owned ROS-free headers whose dependencies are advertised
# by the generated package configuration.
set(EKLT_INSTALL_CORE_HEADERS
    "${CMAKE_CURRENT_SOURCE_DIR}/eklt_core/image_normalization.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/eklt_core/initialization_providers.h"
)
set(EKLT_CONFIG_WITH_CERES OFF)
if(Ceres_FOUND AND TARGET Ceres::ceres)
    list(APPEND
        EKLT_INSTALL_CORE_HEADERS
        "${CMAKE_CURRENT_SOURCE_DIR}/eklt_core/photometric_patch_tracker.h"
    )
    set(EKLT_CONFIG_WITH_CERES ON)
endif()

# Publish the header-only provider and photometric interfaces independently of
# ROS while retaining the original C++11 compatibility floor.
add_library(eklt_core INTERFACE)
add_library(${LIB_NAMESPACE}::eklt_core ALIAS eklt_core)
target_compile_features(eklt_core INTERFACE cxx_std_11)
target_include_directories(
    eklt_core
    INTERFACE
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
target_link_libraries(
    eklt_core
    INTERFACE
        ${OpenCV_LIBRARIES}
        $<BUILD_INTERFACE:eklt_compile_options>
        $<BUILD_INTERFACE:eklt_optional_dependencies>
        $<BUILD_INTERFACE:${SANITIZER_TARGET}>
)
if(EKLT_CONFIG_WITH_CERES)
    target_link_libraries(eklt_core INTERFACE Ceres::ceres)
endif()
if(PROFILING_PROPAGATES_TO_CONSUMERS)
    target_link_libraries(eklt_core INTERFACE ${PROFILING_COMPILE_TARGET})
else()
    target_link_libraries(
        eklt_core
        INTERFACE $<BUILD_INTERFACE:${PROFILING_COMPILE_TARGET}>
    )
endif()

set(EKLT_INSTALL_TARGETS eklt_core)
if(PROFILING_PROPAGATES_TO_CONSUMERS)
    list(APPEND EKLT_INSTALL_TARGETS ${PROFILING_COMPILE_TARGET})
endif()
set(EKLT_CONFIG_WITH_WRAPPER OFF)

# Keep the external FIBAR implementation private behind EKLT's stable native
# reconstruction and dtype-adaptation APIs.
if(NOT EXISTS "${PROJECT_SOURCE_DIR}/lib/fibar_lib/CMakeLists.txt")
    message(FATAL_ERROR
        "eklt-rebuild requires lib/fibar_lib. "
        "Initialize it with: git submodule update --init lib/fibar_lib")
endif()

# Prevent the vendored dependency from registering its own tests in EKLT, then
# restore the caller's setting for project-owned tests.
set(_eklt_saved_build_testing "${BUILD_TESTING}")
set(BUILD_TESTING OFF CACHE BOOL "Disable vendored FIBAR tests" FORCE)
add_subdirectory(
    "${PROJECT_SOURCE_DIR}/lib/fibar_lib"
    "${PROJECT_BINARY_DIR}/_deps/fibar_lib"
)
set(
    BUILD_TESTING "${_eklt_saved_build_testing}"
    CACHE BOOL "Restore EKLT test setting" FORCE
)

if(NOT TARGET fibar_lib::fibar_lib)
    add_library(fibar_lib::fibar_lib ALIAS fibar_lib)
endif()

# Compile the native facade and Eigen adapter into one published library while
# retaining their distinct header directories and C++ namespaces.
add_library(
    ${LIB_TARGET_NAME}
    event_recon_fibar_core/fibar_reconstructor.cpp
    event_recon_fibar_adapters/fibar_adapters.cpp
)
add_library(
    ${LIB_NAMESPACE}::${LIB_TARGET_NAME}
    ALIAS ${LIB_TARGET_NAME}
)
add_library(
    ${LIB_NAMESPACE}::event_recon_fibar_core
    ALIAS ${LIB_TARGET_NAME}
)
add_library(
    ${LIB_NAMESPACE}::event_recon_fibar_adapters
    ALIAS ${LIB_TARGET_NAME}
)
target_compile_features(${LIB_TARGET_NAME} PUBLIC cxx_std_17)
set_target_properties(
    ${LIB_TARGET_NAME}
    PROPERTIES
        EXPORT_NAME ${LIB_TARGET_NAME}
        POSITION_INDEPENDENT_CODE ON
)
target_include_directories(
    ${LIB_TARGET_NAME}
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
        $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
target_include_directories(
    ${LIB_TARGET_NAME}
    SYSTEM PRIVATE
        "${PROJECT_SOURCE_DIR}/lib/fibar_lib/include"
)
target_link_libraries(
    ${LIB_TARGET_NAME}
    PUBLIC
        fibar_lib::fibar_lib
        Eigen3::Eigen
    PRIVATE
        $<BUILD_INTERFACE:eklt_compile_options>
        $<BUILD_INTERFACE:eklt_optional_dependencies>
        $<BUILD_INTERFACE:${SANITIZER_TARGET}>
)
if(PROFILING_PROPAGATES_TO_CONSUMERS)
    target_link_libraries(
        ${LIB_TARGET_NAME}
        PUBLIC ${PROFILING_COMPILE_TARGET}
    )
else()
    target_link_libraries(
        ${LIB_TARGET_NAME}
        PRIVATE $<BUILD_INTERFACE:${PROFILING_COMPILE_TARGET}>
    )
endif()
list(APPEND EKLT_INSTALL_TARGETS ${LIB_TARGET_NAME})

if(EKLT_BUILD_PYTHON OR EKLT_BUILD_MATLAB)
    set(EKLT_CONFIG_WITH_WRAPPER ON)
endif()

# Export one feature-aware target surface. ROS1 remains under the separate
# catkin installation contract and is never included in this package.
set(EKLT_EXPORT_SET "${EKLT_PACKAGE_NAME}Targets")
install(
    TARGETS ${EKLT_INSTALL_TARGETS}
    EXPORT ${EKLT_EXPORT_SET}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(
    FILES ${EKLT_INSTALL_CORE_HEADERS}
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/eklt_core
)
install(
    FILES
        "${CMAKE_CURRENT_SOURCE_DIR}/event_recon_fibar_core/fibar_reconstructor.h"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/event_recon_fibar_core
)
install(
    FILES
        "${PROJECT_SOURCE_DIR}/include/event_recon_fibar_adapters/GtsamAliases.h"
        "${PROJECT_SOURCE_DIR}/include/event_recon_fibar_adapters/fibar_adapters.h"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/event_recon_fibar_adapters
)
install(
    EXPORT ${EKLT_EXPORT_SET}
    FILE ${EKLT_PACKAGE_NAME}Targets.cmake
    NAMESPACE ${LIB_NAMESPACE}::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/${EKLT_PACKAGE_NAME}
)

# Generate the versioned package configuration beside the root build metadata.
configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/${EKLT_PACKAGE_NAME}Config.cmake.in"
    "${PROJECT_BINARY_DIR}/${EKLT_PACKAGE_NAME}Config.cmake"
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/${EKLT_PACKAGE_NAME}
)
write_basic_package_version_file(
    "${PROJECT_BINARY_DIR}/${EKLT_PACKAGE_NAME}ConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)
install(
    FILES
        "${PROJECT_BINARY_DIR}/${EKLT_PACKAGE_NAME}Config.cmake"
        "${PROJECT_BINARY_DIR}/${EKLT_PACKAGE_NAME}ConfigVersion.cmake"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/${EKLT_PACKAGE_NAME}
)

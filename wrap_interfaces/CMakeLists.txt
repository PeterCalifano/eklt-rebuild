# Configure generated-language bindings in a dedicated project source scope.
#
# HandleWrapper.cmake follows the parent-template convention of configuring
# package metadata beneath PROJECT_SOURCE_DIR/python. This nested project keeps
# that generated wrapper state independent of the repository-level eklt-bridge
# distribution while preserving the canonical native target and project name.

project(
    eklt_rebuild
    VERSION ${CMAKE_PROJECT_VERSION}
    DESCRIPTION "Generated Python and MATLAB bindings for EKLT"
    LANGUAGES CXX
)

set(PROJECT_PYTHON_VERSION "${EKLT_PYTHON_MIN_VERSION}")
set(MATLAB_DEFAULT_RELEASE "${EKLT_MATLAB_RELEASE}")

set(${LIB_NAMESPACE}_BUILD_PYTHON_WRAPPER "${EKLT_BUILD_PYTHON}")
set(${LIB_NAMESPACE}_BUILD_MATLAB_WRAPPER "${EKLT_BUILD_MATLAB}")
set(
    ${LIB_NAMESPACE}_WRAPPER_INTERFACE_FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/fibar_reconstructor.i"
    CACHE STRING "Ordered gtwrap interface files for EKLT" FORCE
)
set(
    ${LIB_NAMESPACE}_GTWRAP_TOP_NAMESPACE
    "wrap_adapters"
    CACHE STRING "Top namespace used for EKLT gtwrap generation" FORCE
)
set(
    ${LIB_NAMESPACE}_GTWRAP_ROOT_DIR
    "${CMAKE_SOURCE_DIR}/lib/wrap"
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
set(LIBNAME_WRAP_TARGET ${LIB_TARGET_NAME})

if(EKLT_BUILD_MATLAB AND NOT DEFINED Matlab_ROOT_DIR)
    set(
        Matlab_ROOT_DIR
        "/usr/local/MATLAB/${EKLT_MATLAB_RELEASE}"
        CACHE PATH "MATLAB root used for EKLT MEX generation"
    )
endif()

include("${CMAKE_SOURCE_DIR}/cmake/HandleWrapper.cmake")
handle_gtwrappers()

# Configure generated-language bindings against the root EKLT project.
#
# Retaining the root project scope makes the inherited wrapper helper use the
# canonical python/ package tree. MATLAB generation still remains local to
# wrap_interfaces/matlab because that frontend is rooted at this source
# directory.

# Keep generated wrapper code and toolbox fixtures inside this subdirectory's
# binary tree while PROJECT_SOURCE_DIR continues to identify the root package.
set(PROJECT_BINARY_DIR "${CMAKE_CURRENT_BINARY_DIR}")

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

if(EKLT_BUILD_MATLAB AND NOT DEFINED Matlab_ROOT_DIR)
    set(
        Matlab_ROOT_DIR
        "/usr/local/MATLAB/${EKLT_MATLAB_RELEASE}"
        CACHE PATH "MATLAB root used for EKLT MEX generation"
    )
endif()

include("${CMAKE_SOURCE_DIR}/cmake/HandleWrapper.cmake")

# Resolve gtwrap once, then configure each language against the target identity
# its generator accepts. Python must name the concrete runtime target, whereas
# MATLAB requires an identifier-safe alias for generated C++ symbols.
set(
    ${PROJECT_NAME}_PYTHON_WRAPPER_TARGET
    ""
    CACHE INTERNAL "Resolved Python wrapper target name for the project." FORCE
)
configure_gtwrappers_common()

if(${${LIB_NAMESPACE}_BUILD_PYTHON_WRAPPER})
    set(LIBNAME_WRAP_TARGET ${LIB_TARGET_NAME})
    configure_python_gtwrapper()
endif()

if(${${LIB_NAMESPACE}_BUILD_MATLAB_WRAPPER})
    set(EKLT_MATLAB_MODULE_NAME "${LIB_NAMESPACE}")
    if(NOT TARGET ${EKLT_MATLAB_MODULE_NAME})
        add_library(${EKLT_MATLAB_MODULE_NAME} ALIAS ${LIB_TARGET_NAME})
    endif()
    set(LIBNAME_WRAP_TARGET ${EKLT_MATLAB_MODULE_NAME})
    configure_matlab_gtwrapper()
endif()

if(EKLT_BUILD_PYTHON)
    _resolve_python_install_root(_eklt_python_install_root)

    # Install the two hand-written namespaces beside the generated binding so
    # CMake and wheel installations expose the same unified distribution.
    foreach(_eklt_python_package IN ITEMS eklt_bridge event_vision_utils)
        set(
            _eklt_python_package_source
            "${PROJECT_SOURCE_DIR}/python/${_eklt_python_package}"
        )
        if(NOT IS_DIRECTORY "${_eklt_python_package_source}")
            message(
                FATAL_ERROR
                "Unified Python package source is missing: "
                "${_eklt_python_package_source}"
            )
        endif()

        install(
            DIRECTORY "${_eklt_python_package_source}/"
            DESTINATION
                "${_eklt_python_install_root}/${_eklt_python_package}"
            PATTERN "__pycache__" EXCLUDE
            PATTERN "*.pyc" EXCLUDE
            PATTERN "_wrapper_build.py" EXCLUDE
            PATTERN "*.so" EXCLUDE
            PATTERN "*.so.*" EXCLUDE
            PATTERN "*.dylib" EXCLUDE
            PATTERN "*.dll" EXCLUDE
            PATTERN "*.pyd" EXCLUDE
        )
    endforeach()
endif()

if(EKLT_BUILD_MATLAB)
    set(_eklt_matlab_wrapper_target "${EKLT_MATLAB_MODULE_NAME}_matlab_wrapper")

    # Keep the merged toolbox relocatable by resolving a co-located native
    # runtime rather than a build-tree or installation-prefix library path.
    if(APPLE)
        set(_eklt_matlab_loader_rpath "@loader_path")
    elseif(UNIX)
        set(_eklt_matlab_loader_rpath "$ORIGIN")
    endif()
    if(DEFINED _eklt_matlab_loader_rpath)
        set_target_properties(
            ${_eklt_matlab_wrapper_target}
            PROPERTIES INSTALL_RPATH "${_eklt_matlab_loader_rpath}"
        )
    endif()

    get_target_property(_eklt_native_library_type ${LIB_TARGET_NAME} TYPE)
    set(
        _eklt_matlab_runtime_path
        "${CMAKE_CURRENT_SOURCE_DIR}/matlab/${CMAKE_SHARED_LIBRARY_PREFIX}${LIB_TARGET_NAME}${CMAKE_SHARED_LIBRARY_SUFFIX}"
    )

    # Remove only this project's prior shared runtime so installing a static
    # build after a shared build cannot leave a stale toolbox artifact.
    install(CODE "file(REMOVE \"${_eklt_matlab_runtime_path}\")")

    if(_eklt_native_library_type STREQUAL "SHARED_LIBRARY")
        # Install the exact target artifact only; never scan a build directory
        # for unrelated native libraries.
        install(
            FILES "$<TARGET_FILE:${LIB_TARGET_NAME}>"
            DESTINATION "${CMAKE_CURRENT_SOURCE_DIR}/matlab"
        )
    endif()
endif()

if(EKLT_BUILD_PYTHON AND ENABLE_TESTS AND BUILD_TESTING)
    # Exercise the package-level NumPy/Eigen boundary after the wrapper and its
    # exact runtime metadata have been generated by the normal build.
    add_test(
        NAME ${LIB_NAMESPACE}_python_package
        COMMAND
            ${CMAKE_COMMAND} -E env
            "PYTHONPATH=${PROJECT_SOURCE_DIR}/python:$ENV{PYTHONPATH}"
            ${PYTHON_EXECUTABLE} -m pytest
            -q
            -p no:cacheprovider
            "${PROJECT_SOURCE_DIR}/python/tests/test_eklt_rebuild.py"
    )
    set_tests_properties(
        ${LIB_NAMESPACE}_python_package
        PROPERTIES
            WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}/python"
    )
endif()

if(EKLT_BUILD_MATLAB AND ENABLE_TESTS AND BUILD_TESTING)
    set(_eklt_matlab_program "${Matlab_ROOT_DIR}/bin/matlab")
    set(_eklt_matlab_test_dir "${CMAKE_SOURCE_DIR}/tests/matlab")
    set(
        _eklt_matlab_toolbox_dir
        "${PROJECT_BINARY_DIR}/wrap/${EKLT_MATLAB_MODULE_NAME}"
    )
    set(
        _eklt_matlab_mex_dir
        "${PROJECT_BINARY_DIR}/wrap/${EKLT_MATLAB_MODULE_NAME}_mex"
    )
    set(
        _eklt_matlab_preload
        "/lib/x86_64-linux-gnu/libgcc_s.so.1:/usr/lib/x86_64-linux-gnu/libstdc++.so.6"
    )

    if(NOT EXISTS "${_eklt_matlab_program}")
        message(FATAL_ERROR "MATLAB R2024b executable not found: ${_eklt_matlab_program}")
    endif()

    foreach(
        _eklt_matlab_case
        IN ITEMS
            reconstruction
            invalid_batch_recovery
            reset_reuse
            clear_lifecycle
    )
        string(TOUPPER "${_eklt_matlab_case}" _eklt_matlab_case_upper)
        set(_eklt_matlab_test_name "${LIB_NAMESPACE}_matlab_${_eklt_matlab_case}")

        add_test(
            NAME ${_eklt_matlab_test_name}
            COMMAND
                "${_eklt_matlab_program}" -batch
                "addpath('${_eklt_matlab_test_dir}'); assert(RunEkltRebuildRegression('${_eklt_matlab_case}', '${_eklt_matlab_toolbox_dir}', '${_eklt_matlab_mex_dir}'));"
        )
        set_tests_properties(
            ${_eklt_matlab_test_name}
            PROPERTIES
                ENVIRONMENT "LD_PRELOAD=${_eklt_matlab_preload}"
                LABELS "matlab;wrapper"
                PASS_REGULAR_EXPRESSION
                    "EKLT_MATLAB_${_eklt_matlab_case_upper}_OK release=2024b"
                RUN_SERIAL TRUE
                TIMEOUT 180
        )
    endforeach()
endif()

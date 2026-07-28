cmake_minimum_required(VERSION 3.16)
project(eklt_rebuild)

# Configure the ROS2 overlay as a thin consumer of the canonical root targets.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(event_camera_msgs REQUIRED)
find_package(event_camera_codecs REQUIRED)
find_package(Ceres REQUIRED)

set(EKLT_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../..")

if(NOT EXISTS "${EKLT_REPO_ROOT}/CMakeLists.txt")
  message(FATAL_ERROR "The eklt-rebuild repository root is unavailable")
endif()

# Build the root package through the same colcon shim pattern used by the
# parent template, keeping all library names and usage requirements canonical.
set(EKLT_BUILD_ROS1 OFF CACHE BOOL "Disable ROS1 in the ROS2 overlay" FORCE)
set(EKLT_BUILD_PYTHON OFF CACHE BOOL "Disable Python wrappers in the ROS2 overlay" FORCE)
set(EKLT_BUILD_MATLAB OFF CACHE BOOL "Disable MATLAB wrappers in the ROS2 overlay" FORCE)
set(EKLT_BUILD_DOCS OFF CACHE BOOL "Disable native docs in the ROS2 overlay" FORCE)
set(ENABLE_TESTS OFF CACHE BOOL "Disable native tests in the ROS2 overlay" FORCE)
set(ENABLE_FETCH_CATCH2 OFF CACHE BOOL "Do not fetch Catch2 in the ROS2 overlay" FORCE)
list(PREPEND CMAKE_MODULE_PATH "${EKLT_REPO_ROOT}/cmake")
add_subdirectory(
  "${EKLT_REPO_ROOT}"
  "${CMAKE_CURRENT_BINARY_DIR}/eklt_rebuild_core"
)

# PNG persistence is owned only by the ROS2 output boundary.
find_package(OpenCV 4 REQUIRED COMPONENTS core imgcodecs)
add_library(reconstructed_frame_writer STATIC
  src/reconstructed_frame_writer.cpp
)
target_compile_features(reconstructed_frame_writer PUBLIC cxx_std_17)
target_include_directories(reconstructed_frame_writer
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
)
target_link_libraries(reconstructed_frame_writer
  PRIVATE
    ${OpenCV_LIBRARIES}
)

add_library(event_packet_adapter STATIC
  src/event_packet_decoder.cpp
)
target_include_directories(event_packet_adapter
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
)
target_link_libraries(event_packet_adapter
  eklt_rebuild::eklt-rebuild
)
ament_target_dependencies(event_packet_adapter
  event_camera_msgs
  event_camera_codecs
)

add_executable(event_packet_reconstruction_debug
  src/event_packet_reconstruction_debug.cpp
)
target_link_libraries(event_packet_reconstruction_debug
  event_packet_adapter
  eklt_rebuild::eklt-rebuild
)
ament_target_dependencies(event_packet_reconstruction_debug
  rclcpp
  sensor_msgs
  event_camera_msgs
  event_camera_codecs
)

add_executable(event_only_eklt_node
  src/event_only_eklt_node.cpp
)
target_link_libraries(event_only_eklt_node
  event_packet_adapter
  reconstructed_frame_writer
  eklt_rebuild::eklt-rebuild
  eklt_rebuild::eklt_core
  eklt_rebuild::visualization
)
ament_target_dependencies(event_only_eklt_node
  rclcpp
  sensor_msgs
  std_msgs
  event_camera_msgs
  event_camera_codecs
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)

  ament_add_gtest(test_event_packet_adapter
    test/test_event_packet_adapter.cpp
  )
  target_link_libraries(test_event_packet_adapter
    event_packet_adapter
    eklt_rebuild::eklt-rebuild
    eklt_rebuild::eklt_core
  )
  ament_target_dependencies(test_event_packet_adapter
    event_camera_msgs
    event_camera_codecs
  )

  ament_add_gtest(test_reconstructed_frame_writer
    test/test_reconstructed_frame_writer.cpp
  )
  target_link_libraries(test_reconstructed_frame_writer
    reconstructed_frame_writer
    ${OpenCV_LIBRARIES}
  )
endif()

install(TARGETS
  event_packet_reconstruction_debug
  event_only_eklt_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../../config/"
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()

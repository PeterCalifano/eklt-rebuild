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

add_executable(event_packet_reconstruction_debug
  src/event_packet_reconstruction_debug.cpp
)
target_link_libraries(event_packet_reconstruction_debug
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
  eklt_rebuild::eklt-rebuild
  eklt_rebuild::eklt_core
)
ament_target_dependencies(event_only_eklt_node
  rclcpp
  sensor_msgs
  std_msgs
  event_camera_msgs
  event_camera_codecs
)

install(TARGETS
  event_packet_reconstruction_debug
  event_only_eklt_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()

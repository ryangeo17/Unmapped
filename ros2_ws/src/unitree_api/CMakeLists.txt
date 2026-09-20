cmake_minimum_required(VERSION 3.5)
project(unitree_api)

if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
        "msg/RequestIdentity.msg"
        "msg/RequestLease.msg"
        "msg/RequestPolicy.msg"
        "msg/RequestHeader.msg"
        "msg/Request.msg"
)

ament_package()

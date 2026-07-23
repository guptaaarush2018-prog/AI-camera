Complete RITS Summer AI Camp Project Overview
Project Goal
Build a fully functional computer vision system on a Raspberry Pi 5 that progresses from basic hardware setup to AI-accelerated object detection using the NPU (Neural Processing Unit).

Phase 1: Raspberry Pi 5 Hardware Setup
What You're Building
A complete, working Raspberry Pi 5 system with camera integration and software updates.

Key Tasks
Hardware Assembly:

Remove the white lid from your encased Raspberry Pi 5
Connect the mini-HDMI cable to your monitor
Plug in mouse and keyboard to USB ports
Install the PiCamera module into the CSI (Camera Serial Interface) port
Gently pull up the tabs on the CSI connector
Insert the ribbon cable with shiny contacts facing away from the Ethernet port
Push the connector down to lock it in place
Connect the USB-C power supply last (this is critical!)
Software Configuration:

Log in and connect to WiFi
Update your system packages using apt update and apt full-upgrade
Enable the camera by editing /boot/firmware/config.txt
Change camera_auto_detect=1 to camera_auto_detect=0
Add dtoverlay=imx708 under the [all] section
Reboot the system
Why This Matters
Phase 1 establishes your foundation. Without proper hardware setup and camera configuration, nothing else will work. The software updates ensure compatibility with modern libraries.

Phase 2: Video Streaming and Object Detection Using YOLO
What You're Building
A Python application that captures live video from your camera and runs real-time object detection using the YOLOv8 neural network model.

Key Tasks
Install Dependencies:

Install essential packages: git, v4l-utils, and python3-picamera2
Install the UV Python package manager (a fast, modern package manager)
Reboot after installation
Create Your Python Project:

Initialize a new Python project with uv init <your project name>
Navigate into the project directory
Create a virtual environment with uv venv --system-site-packages .venv/
Add required libraries: picamera2 and ultralytics
Build Your First Application:

Write a Python script that:
Imports Picamera2 (camera control), OpenCV (cv2), and YOLO libraries
Captures live video frames from the camera
Converts color formats (RGB to BGR for OpenCV compatibility)
Displays the video stream in a window
Calculates and displays frames-per-second (FPS)
Allows exit by pressing Escape
Add Object Detection:

Load the YOLOv8s pre-trained model
Process each camera frame through the model
Visualize detection results (bounding boxes, class labels, confidence scores)
Display annotated frames with FPS information
Why This Matters
Phase 2 teaches you how to build a complete computer vision pipeline. You'll understand how neural networks process images in real-time and see object detection working on your device.

Phase 3: Optimizing with the Hailo NPU (AI HAT)
What You're Building
A high-performance object detection system that offloads inference to the dedicated AI accelerator hardware, dramatically improving speed and efficiency.

Key Tasks
Enable Hardware Acceleration:

Enable PCIe Gen 3.0 mode (boosts communication speed between NPU and CPU)
Use sudo raspi-config and navigate to Advanced Options → PCIe Speed
Select Yes to enable Gen 3.0
Reboot
Install Hailo NPU software: sudo apt install hailo-all
Verify installation with hailortcli fw-control identify
Reboot again
Prepare Your Model:

Download COCO dataset labels (class names for object detection)
Add the Hailo-optimized Python infrastructure to your project
Build the Optimized Application:

Create preprocessing function to resize and pad frames for the model
Create extraction function to process raw model output into detections
Create visualization function to draw bounding boxes and labels
Write main application that:
Loads the Hailo HEF model file
Captures camera frames
Preprocesses frames (resize, pad, maintain aspect ratio)
Runs inference on the NPU
Extracts and filters detections
Displays annotated results with FPS
Why This Matters
Phase 3 represents the pinnacle of the project. The NPU handles all the heavy computational work, freeing up your CPU and delivering dramatically faster inference. This is how real-world AI applications achieve high performance on edge devices.

Key Technologies You'll Learn
Component	Purpose
Raspberry Pi 5	Your main computer
PiCamera Module	Captures video frames
Picamera2 Library	Python interface to the camera
OpenCV (cv2)	Image processing and display
YOLO (YOLOv8)	Object detection neural network
Ultralytics	Framework for running YOLO models
Hailo NPU	Hardware accelerator for AI inference
Virtual Environments	Isolated Python project spaces
Project Progression Summary
Phase 1: Hardware Ready ↓ Phase 2: Software Works (CPU-based detection) ↓ Phase 3: Optimized Performance (NPU-accelerated detection)

By the end of this project, you will have: ✓ A fully configured Raspberry Pi 5 with camera
✓ A working computer vision pipeline
✓ Experience with neural networks (YOLO)
✓ Understanding of hardware acceleration
✓ A real-world AI application running at high performance

https://drive.google.com/drive/folders/16coOR8PlNzvmUm1vsaYJVF_bAOQGySa8

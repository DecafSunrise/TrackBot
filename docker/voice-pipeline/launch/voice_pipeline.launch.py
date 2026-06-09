from launch import LaunchDescription
from launch.actions import ExecuteProcess, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # whisper.cpp server (persistent, CUDA if available)
        ExecuteProcess(
            cmd=[
                "whisper-server",
                "-m", "/models/whisper/ggml-tiny.en.bin",
                "--port", "8080",
                "--gpu",
            ],
            name="whisper_server",
            output="screen",
        ),

        # Ollama server (if not already running on host)
        ExecuteProcess(
            cmd=["ollama", "serve"],
            name="ollama_server",
            output="screen",
        ),

        # Piper TTS server
        ExecuteProcess(
            cmd=[
                "piper",
                "--model", "/models/piper/en_US-lessac-medium.onnx",
                "--json-input",
                "--output-raw",
                "--port", "5000",
            ],
            name="piper_server",
            output="screen",
        ),

        # Voice orchestration node
        Node(
            package="trackbot_voice",
            executable="voice_node.py",
            name="voice_node",
            output="screen",
        ),
    ])

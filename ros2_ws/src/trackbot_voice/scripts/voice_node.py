#!/usr/bin/env python3
"""
Voice pipeline node: audio capture → whisper.cpp → Ollama LLM → Piper TTS → audio out.

Architecture:
  whisper.cpp runs as a persistent HTTP server on port 8080
  Ollama runs as a persistent HTTP server on port 11434
  This node ties them together with ROS2 wake-word awareness.
"""

import io
import json
import os
import queue
import threading
import wave
import requests
import sounddevice as sd
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:8080/inference")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
PIPER_URL = os.getenv("PIPER_URL", "http://localhost:5000/synthesize")
SAMPLE_RATE = 16000

SYSTEM_PROMPT = (
    "You are a voice-controlled robot assistant. "
    "Keep responses under 20 words. Be concise."
)


class VoiceNode(Node):
    def __init__(self):
        super().__init__("voice_node")
        self.cmd_pub = self.create_publisher(String, "/voice_command", 10)
        self.audio_q = queue.Queue(maxsize=20)
        self._running = True

        self.audio_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)

        self.get_logger().info("Voice node started (wake word: 'robot')")

    def start(self):
        self.audio_thread.start()
        self.process_thread.start()

    def stop(self):
        self._running = False

    # ── Audio capture (VAD-silenced) ──────────────────────
    def _capture_loop(self):
        silence_frames = 0
        speech_buffer = []

        def callback(indata, frames, time_info, status):
            if self.audio_q.qsize() < 20:
                self.audio_q.put(indata.copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=1600, callback=callback,
        ):
            while self._running and rclpy.ok():
                sd.sleep(100)

    # ── Process loop: STT → LLM → TTS ───────────────────
    def _process_loop(self):
        while self._running and rclpy.ok():
            try:
                audio = self.audio_q.get(timeout=1.0)
            except queue.Empty:
                continue

            text = self._stt(audio)
            if not text or len(text) < 3:
                continue

            self.get_logger().info(f"STT: {text}")

            # Wake word check
            if "robot" not in text.lower():
                continue

            # Strip wake word for LLM
            command = text.lower().replace("robot", "").strip()
            if not command:
                continue

            # Publish raw command
            msg = String()
            msg.data = command
            self.cmd_pub.publish(msg)

            # LLM
            response = self._llm(command)
            self.get_logger().info(f"LLM: {response}")

            # TTS
            self._tts(response)

    # ── STT via whisper.cpp server ───────────────────────
    def _stt(self, audio: np.ndarray) -> str:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)

        try:
            r = requests.post(WHISPER_URL, files={"file": buf}, timeout=10)
            if r.status_code == 200:
                return r.json().get("text", "")
        except requests.RequestException as e:
            self.get_logger().warn(f"STT error: {e}")
        return ""

    # ── LLM via Ollama ───────────────────────────────────
    def _llm(self, prompt: str) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"{SYSTEM_PROMPT}\n\nCommand: {prompt}\nResponse:",
            "stream": False,
            "options": {"num_predict": 50},
        }
        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        except requests.RequestException as e:
            self.get_logger().warn(f"LLM error: {e}")
        return ""

    # ── TTS via Piper ────────────────────────────────────
    def _tts(self, text: str):
        try:
            r = requests.post(
                PIPER_URL,
                json={"text": text},
                stream=True,
                timeout=30,
            )
            if r.status_code == 200:
                sd.play(r.content, samplerate=SAMPLE_RATE)
                sd.wait()
        except requests.RequestException as e:
            self.get_logger().warn(f"TTS error: {e}")


def main():
    rclpy.init()
    node = VoiceNode()
    node.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

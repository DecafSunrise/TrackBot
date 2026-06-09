# Voice Pipeline

Local voice control pipeline: speech-to-text → LLM → text-to-speech, all running on the LattePanda Sigma with no cloud dependency.

## Architecture

```
USB Microphone
      │
      ▼
┌────────────┐     HTTP     ┌──────────────────┐
│ voice_node │─────────────►│ whisper.cpp       │
│ .py        │ POST /inf    │ server :8080      │
│ (capture)  │◄─────────────│ (STT)             │
└─────┬──────┘     text     └──────────────────┘
      │
      │ "robot" detected in text?
      │   No  → discard, keep listening
      │   Yes → strip wake word
      ▼
┌────────────┐     HTTP     ┌──────────────────┐
│ voice_node │─────────────►│ Ollama :11434     │
│ .py        │ POST /api/   │ (LLM)             │
│            │ generate     │ Phi-3 Mini        │
│            │◄─────────────│ 3.8B param        │
└─────┬──────┘     text     └──────────────────┘
      │
      ▼
┌────────────┐     HTTP     ┌──────────────────┐
│ voice_node │─────────────►│ Piper :5000       │
│ .py        │ POST /synth  │ (TTS)             │
│            │◄─────────────│ raw PCM           │
└─────┬──────┘     audio    └──────────────────┘
      │
      ▼
   Speaker

Also: publishes raw command text to /voice_command (std_msgs/String)
```

## Components

### Speech-to-Text: whisper.cpp

| Model | Size | RAM Use | Latency (GPU) | Accuracy (WER) |
|---|---|---|---|---|
| tiny.en | 75 MB | ~200 MB | ~100 ms | 8.2% |
| base.en | 142 MB | ~400 MB | ~150 ms | 5.9% |
| small.en | 466 MB | ~1.2 GB | ~250 ms | 4.4% |

Recommendation: start with **tiny.en** (fast enough, good enough).

Run as a persistent HTTP server (NOT the CLI — loading the model each time adds 500+ ms):

```bash
whisper-server -m models/whisper/ggml-tiny.en.bin --port 8080 --gpu
```

The `--gpu` flag uses Intel Iris Xe graphics (OpenCL/Vulkan) on the Sigma.

### LLM: Ollama

| Model | Size | RAM | First Token | Quality |
|---|---|---|---|---|
| phi3:mini | 2.3 GB | 4 GB | ~1 s | Good for commands |
| llama3.2:3b | 2.0 GB | 4 GB | ~1.5 s | Better understanding |
| qwen2.5:3b | 1.9 GB | 4 GB | ~1 s | Good for instruction following |

Recommendation: **phi3:mini** — fast, small, sufficient for parsing movement commands.

### Text-to-Speech: Piper

| Model | Size | Speed | Quality |
|---|---|---|---|
| en_US-lessac-medium | 200 MB | 50× real-time on CPU | Good, robotic but clear |
| en_US-amy-low | 12 MB | 100× real-time | Lower quality, tinny |

Piper is extraordinarily fast — it synthesizes speech faster than it can play it, even on CPU.

## Voice Commands

The wake word is **"robot"**. Example interactions:

| You say | Pipeline processes | Robot does |
|---|---|---|
| "robot move forward" | STT→"robot move forward"→LLM→"Moving forward"→TTS | Publishes /voice_command "move forward" |
| "robot stop" | STT→"robot stop"→LLM→"Stopping"→TTS | Publishes /voice_command "stop" |
| "robot turn left" | " | Publishes /voice_command "turn left" |

The `/voice_command` topic can be subscribed to by any node that wants to parse natural language into `/cmd_vel` or navigation goals.

## Latency Budget

| Stage | Latency |
|---|---|
| Audio capture + VAD | 0.5–1.5 s |
| whisper.cpp STT | 0.1–0.3 s |
| Ollama first token | 0.5–1.5 s |
| Piper TTS | 0.1–0.3 s |
| **Total (estimate)** | **2–4 s** |

## Model Downloads

```bash
make models
```

Downloads:
- `models/whisper/ggml-tiny.en.bin` (~75 MB) from HuggingFace
- `models/piper/en_US-lessac-medium.onnx` + `.json` (~200 MB) from HuggingFace

Ollama pulls models on first use (not part of `make models`; happens when the container starts and Ollama receives its first inference request).

## Microphone Recommendations

| Mic | Type | Cost | Notes |
|---|---|---|---|
| Blue Yeti Nano | USB condenser | $70 | Excellent quality, bulky |
| Samson Q2U | USB/XLR dynamic | $50 | Good noise rejection |
| Mini USB mic | USB electret | $10 | Cheap, adequate |
| PS3 Eye camera | USB | $5 | Built-in mic array, surprisingly good |

Any USB microphone class-compliant with Linux works.

## Tuning

For lower latency: reduce `RECORD_SECONDS` in `voice_node.py` (currently 1.6 s chunks).
For better accuracy: switch whisper model `small.en` (slower but lower WER).
For different behavior: change the `SYSTEM_PROMPT` in `voice_node.py`.

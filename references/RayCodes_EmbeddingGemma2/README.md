<div align="center">
  <a href="https://youtu.be/7EMr9BCKglc">
    <img src="https://img.youtube.com/vi/7EMr9BCKglc/0.jpg" alt="Google's New 500MB 4-Modality AI That Runs on Phones! (EmbeddingGemma 2 Review)">
  </a>
  <h3>📺 <a href="https://youtu.be/7EMr9BCKglc">Watch the full tutorial on YouTube</a></h3>
</div>

# 🔍 EmbeddingGemma 2 Multimodal AI Breakthrough


Google DeepMind's 740M parameter omnimodal embedding model for on-device semantic search, local codebase indexing, and private cross-modal media retrieval.

---

## ⚡ 3-Step Execution Workflow

| Step 1: Input Media | Step 2: AI Action | Step 3: Instant Result |
| :--- | :--- | :--- |
| **Multimodal Folder (`inputs/`)**<br>Python Code, Image Assets, Spoken Voice WAV Recordings & Voice Transcripts | **Gemma 4 Omnimodal Core**<br>Maps inputs into a shared 768-dim vector space & applies Matryoshka truncation | **Cross-Modal Search Task**<br>Evaluates retrieval accuracy across 768d, 512d, 256d & 128d in `outputs/outputs.md` |

---

## 🚀 Key Features

- 🧠 **740M Sub-1B Omnimodal Architecture**: Combines a 270M text backbone with selectively loadable 170M vision and 300M audio encoders.
- ⚡ **Matryoshka Truncation (MRL)**: Dynamically shrink vector dimensions from 768 to 512, 256, or 128 for up to 6x storage savings on edge hardware.
- 💻 **+9.92 Code Benchmark Jump**: Achieves 78.68 on MTEB Code search, providing high recall accuracy for codebase indexing.
- 🔒 **100% On-Device Data Privacy**: Runs locally within ~191 MB to 567 MB active RAM on laptops, mobile phones, and Raspberry Pi.
- 🎯 **Task-Steered Instruction Prefixes**: Steer output representations for search, classification, or clustering using simple text instruction prefixes.

---

## 🛠️ Quickstart Installation & Setup

Execute the following single PowerShell command to install dependencies and run the multimodal search pipeline:

```powershell
pip install sentence-transformers torch numpy Pillow huggingface_hub
python main.py
```

### Download GGUF Model Checkpoints (`models/` Folder)

To save local GGUF quantization weights into the `models/` directory for Ollama or llama.cpp:

```powershell
hf download unsloth/embeddinggemma-2-GGUF embeddinggemma-2-UD-Q4_K_XL.gguf --local-dir models
ollama create embeddinggemma-2 -f Modelfile
```

---

## 📂 File Structure

```text
EmbeddingGemma2/
├── inputs/              # Multimodal dataset folder (code, photos, spoken voice WAV audio, voice transcripts)
│   ├── spoken_voice_sample.wav
│   ├── sample_photo.jpg
│   ├── tensor_processor.py
│   └── voice_memo_standup.txt
├── main.py              # Production multimodal search & Matryoshka analysis engine
├── models/              # Local GGUF checkpoints directory (models/embeddinggemma-2-UD-Q4_K_XL.gguf)
├── outputs/             # Subfolder containing generated search reports (outputs/outputs.md)
├── Modelfile            # Ollama configuration file for local GGUF registration
└── README.md            # Comprehensive project documentation
```

---

## 💡 5 Practical Real-World Use Cases

1. **Instant Offline Photo Finder**: Search your camera roll using natural text descriptions without uploading images to cloud servers.
2. **Audio & Voice Search**: Locate timestamped moments across hours of voice memos or podcasts using text queries or audio snippets.
3. **Local Codebase Semantic Assistant**: Index local repositories with high accuracy to search functions, logic, and bug locations by intent.
4. **Private On-Device RAG**: Pair EmbeddingGemma 2 vector retrieval with local Gemma 4 reasoning models for 100% private offline document Q&A.
5. **Real-Time Edge Media Filter**: Filter, cluster, and route media streams dynamically on low-power mobile or edge hardware.

---

## 🔮 5 Future Planned Features

1. 🚀 **WebGPU Browser Engine**: Run complete multimodal vector search inside modern web browsers using Transformers.js.
2. 📱 **Android MediaPipe Native Task**: Direct integration with MediaPipe Decision Task API for mobile developers.
3. 💾 **Qdrant Vector Database Connector**: Automated vector sync with local Qdrant databases for high-speed indexing.
4. 🎥 **Live Stream Video Segmenter**: Real-time video frame embedding & event indexing from live RTSP video feeds.
5. 🌐 **Multi-Language Speech Aligner**: Cross-lingual voice-to-text semantic matching across 100+ supported languages.

---

## 🏷️ Keywords & SEO
`EmbeddingGemma 2` `Multimodal AI` `On-Device AI` `Google DeepMind` `Matryoshka Embeddings` `Semantic Search` `Codebase Indexing` `Cross-Modal Retrieval` `Edge AI` `Ollama` `GGUF`


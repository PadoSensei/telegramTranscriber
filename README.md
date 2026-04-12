# 🧠 2ndBrain: Multi-Tenant Voice-to-Obsidian Orchestrator

## 🎯 Overview
2ndBrain is a resilient, multi-tenant Telegram bot designed to bridge the gap between spoken thoughts and structured digital capture. It transcribes voice notes using OpenAI's Whisper, refines them with Google's Gemini 2.0 Flash AI, and synchronizes the results to both **Obsidian (via GitHub)** and **Google Docs**.

This tool is built for high-reliability personal knowledge management (PKM), specifically tuned for STAR stories, research notes, and quick inbox captures.

---

## 🏗 Key Architectural Pillars

### 1. Strict Tenant Isolation
Using a **Stateless Manager Factory**, the bot ensures that user credentials, repository tokens, and Google Doc IDs never leak between requests. Every interaction is isolated and validated using **Pydantic schemas**.

### 2. Resilient "Soft-Fail" Sync Stack
We treat GitHub as the **Source of Truth**. The sync stack uses asynchronous parallel processing:
- **GitHub Sync (Mandatory):** Updates your Obsidian vault.
- **Google Sync (Optional):** Appends to a NotebookLM-friendly Google Doc.
A failure in Google Sync will not block the confirmation of a successful Obsidian update.

### 3. Whisper Hallucination Filtering
The orchestrator includes a custom heuristic filter specifically tuned for the Whisper `tiny` model. It automatically identifies and blocks common "Ghost Notes" (e.g., "Thank you for watching") often produced during silence or background noise.

### 4. Temporal Persistence
The bot maintains state across restarts. If you send a voice note and follow up minutes later with a hashtag (like `#star` or `#idea`), 2ndBrain remembers the context and routes your previous transcription accordingly.

---

## 🛠 Tech Stack
- **Orchestration:** Python, `python-telegram-bot`
- **AI/LLM:** Google Gemini 2.0 Flash (`google-generativeai`)
- **Transcription:** OpenAI Whisper (`openai-whisper`, `torch`)
- **Persistence:** Pydantic (Validation), Local JSON State (Atomic writes)
- **CI/CD:** GitHub Actions (Linting & Pytest)

---

## 🚀 Getting Started

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file with your API keys:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_key
```

Configure your users in `config.py`. Each user requires:
- `repo_url`: Their Obsidian GitHub repository.
- `token`: GitHub Personal Access Token.
- `username`: GitHub username.
- `category_map`: Mapping of hashtags/topics to vault folders.
- `gdrive_doc_id`: (Optional) Target Google Doc ID.

### 3. Running the Bot
```bash
python main.py
```

---

## 🧪 Testing
We use `pytest` for robustness and isolation testing.
```bash
pytest tests/
```

---

## 🗺 Roadmap
See `docs/REFACTORING_ROADMAP.md` for the full "Spain-Ready" stabilization plan.

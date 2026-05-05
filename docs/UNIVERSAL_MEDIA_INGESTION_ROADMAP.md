# 🗺️ Roadmap: Universal Media Ingestion for 2ndBrain

## 🎯 Goal
Evolve 2ndBrain from a voice-first orchestrator to a universal media ingestion engine. The bot will accept any file type, secure it in the user's GitHub Inbox (00_Inbox), and provide a searchable metadata companion file.

---

## 🏗 High-Level Design: "The Media Path"

The system will implement a fork in the `process_entry` handler:

1.  **Textual Path (Existing):** Voice/Audio -> Whisper -> Gemini -> Git/Google (Daily Note).
2.  **Media Path (New):** Photo/Video/Document -> Size Check -> Download -> Git (Standalone File + Companion MD).

### Component Changes:
- **`main.py`**: Add `process_media` handler to catch `filters.ATTACHMENT & ~filters.TEXT`.
- **`processor.py`**: Add `run_media_stack` to coordinate media storage without AI refinery.
- **`vault_manager.py`**: Add `secure_media` to handle binary writes and companion file generation.
- **`templates.py`**: Add `MediaTemplate` for companion Markdown metadata.

---

## 🚀 Phased Refactor Roadmap

### Phase 1: Security & Foundation (Jules Task 1)
*Focus: Guardrails and Basic Ingestion.*
- [ ] Implement file type blacklist (Executables, hazardous archives).
- [ ] Implement 20MB hard limit for all incoming files.
- [ ] Add `filters.ATTACHMENT` handler to `main.py`.
- [ ] Create `MediaTemplate` in `templates.py`.
- **Complexity:** Medium (3-4 pts)

### Phase 2: Binary Persistence (Jules Task 2)
*Focus: Git Handling and Multi-Tenant Storage.*
- [ ] Extend `VaultManager` with `secure_media(file_path, original_name, mime_type, caption)`.
- [ ] Implement unique naming convention: `TYPE_YYYYMMDD_HHMMSS.ext`.
- [ ] Ensure atomic cleanup of temp media files to prevent disk bloat.
- **Complexity:** Medium (3-4 pts)

### Phase 3: Orchestration & Feedback (Jules Task 3)
*Focus: Seamless User Experience.*
- [ ] Integrate `run_media_stack` in `TaskProcessor`.
- [ ] Implement specific user feedback: "✅ Data Secured! 7.2MB PDF 'Invoice.pdf' is in your Inbox."
- [ ] Handle Media Groups (Batch processing).
- **Complexity:** Low (2 pts)

### Phase 4: Future Refinery (Future Consideration)
*Focus: AI Vision and OCR.*
- [ ] Integration of Gemini Pro Vision for image descriptions.
- [ ] OCR for PDFs to make contents searchable in Obsidian.
- [ ] Google Drive storage for files > 20MB.

---

## ⚠️ Potential Risks
1. **GitHub Performance:** Large numbers of binary files can slow down `git clone`/`git push` over time.
2. **Railway Disk Space:** Concurrent large uploads could hit ephemeral storage limits if cleanup fails.
3. **Telegram Timeouts:** Downloading 20MB might exceed default connection timeouts on slow networks.

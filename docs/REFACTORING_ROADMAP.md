# 🛠 Refactoring Roadmap: The "Spain-Ready" Architecture

**Author:** Jules (Senior Dev Mentor)
**Status:** In Progress
**Context:** Moving from Prototype to Multi-Tenant Service-Oriented Architecture.

## 1. Audit Findings & Strategic Pillars

### 🚪 Pillar 1: Strict Tenant Isolation (The "Wall" Audit)
- **Current Smell:** Global singletons for `TaskProcessor`, `AIEngine`, and `GoogleManager` in `main.py` create risk of "state leakage" between concurrent users.
- **Refactoring Goal:** Move to a **Manager Factory Pattern**. Instantiate services per-request with a validated `UserConfig` context.
- **Impact:** Ensures Ludmila's data never touches Pado's vault, even if they message the bot at the exact same millisecond.

### 📐 Pillar 2: Schema & Config Consistency
- **Current Smell:** Standard Python dictionaries allow missing keys to cause runtime `KeyError` or silent failures (e.g., the `gdrive_doc_id` mismatch).
- **Refactoring Goal:** Migrate to **Pydantic Models**.
- **Impact:** The bot will refuse to process a user if their configuration is invalid, providing immediate feedback instead of mid-flow crashes.

### ⏳ Pillar 3: Temporal Decoupling (State Management)
- **Current Smell:** `USER_TRANSCRIPT_CACHE` is a RAM-only dictionary. A server reboot (common on Railway) wipes all mid-transcription follow-up potential.
- **Refactoring Goal:** Implement a **Persistent State Manager** (JSON/Redis).
- **Impact:** User hashtags sent after a reboot will still link correctly to their previous voice notes.

### 🎙 Pillar 4: Signal-to-Noise Ratio (AI & Audio)
- **Current Smell:** Whisper "tiny" hallucinations ("Visit us", "Thank you") polluting the vault.
- **Refactoring Goal:** Implement a **Hallucination Filter** and **Confidence Heuristics**.
- **Impact:** Cleaner vaults and reduced unnecessary AI Engine costs.

### 📂 Pillar 5: Obsidian Sync & Path Resiliency
- **Current Smell:** Hardcoded category maps break when users reorganize their Obsidian vaults.
- **Refactoring Goal:** **Discovery Mode**. The bot scans the repo on each push to verify paths and auto-suggest new hashtags.
- **Impact:** Zero "orphaned" notes and dynamic adaptation to user habits.

---

## 2. Implementation Phases

| Phase | Task | Status |
| :--- | :--- | :--- |
| **Phase 1** | Pydantic Schema Enforcement | ✅ Done |
| **Phase 2** | Persistent State Management (JSON) | ✅ Done |
| **Phase 3** | Transcriber Hallucination Filtering | ✅ Done |
| **Phase 4** | Manager Factory & Tenant Isolation | ✅ Done |
| **Phase 5** | Discovery Mode & Sync Decoupling | 👷 In Progress |

---

## 3. Files to be Modified/Deleted

- `config.py`: Refactor to use Pydantic.
- `main.py`: Update to use `ManagerFactory` and `StateManager`.
- `processor.py`: Convert to a stateless factory-produced service.
- `transcriber.py`: Add filtering logic.
- `vault_manager.py`: Add "Discovery Mode" logic.
- `google_manager.py`: Refactor for per-user credentials.
- `state_manager.py`: (NEW) Handle persistence.
- `schema.py`: (NEW) Define data integrity models.

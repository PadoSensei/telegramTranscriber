# 📝 Audit Report: Universal Media Ingestion for 2ndBrain

## 🕵️ Overview
This audit evaluates the current state of the 2ndBrain Orchestrator and identifies the requirements for supporting non-textual media ingestion (Images, PDFs, Videos, Files).

## 🔍 Findings by Area

### 1. Telegram Bot API (`main.py`)
- **Current State:** Handler is limited to `VOICE | AUDIO` and `TEXT`.
- **Opportunities:** `python-telegram-bot` v22.6 supports `filters.ATTACHMENT` (Photos, Documents, Videos).
- **Constraints:**
    - Bot API has a 20MB limit for `get_file` without a local Bot API server.
    - `file_size` is available in the message object before download, allowing for "fail-fast" size checks.
- **Recommendation:** Implement a new `process_media` handler that performs security checks (size + extension) before attempting any IO.

### 2. GitHub Vault (`vault_manager.py`)
- **Current State:** Optimized for appending text to daily Markdown notes.
- **Binary Handling:** Git handles binary files as "blobs". GitPython can add and commit these via `repo.git.add(A=True)`.
- **Searchability:** Binary files are not indexed by Obsidian's search.
- **Recommendation:** Store media as standalone files in `00_Inbox` with companion `.md` files containing metadata (caption, filename, size) and an Obsidian link (`![[file.jpg]]`).

### 3. Orchestration Layer (`processor.py`)
- **Current State:** `run_sync_stack` is tightly coupled with Gemini AI processing.
- **Isolation:** Tenant isolation is strong (per-request instantiation).
- **Recommendation:** Introduce a `run_media_stack` that bypasses AI processing (for now) and focuses on "Secure & Notify". This decouples the immediate need for ingestion from future complex AI vision tasks.

### 4. Infrastructure (`Railway`)
- **Disk:** Cleanup is critical. Existing `_cleanup()` in `VaultManager` must be strictly enforced for large media files to prevent "Disk Full" errors.
- **Performance:** Git clones/pushes for repositories with many binary files will eventually degrade. Admin should be warned to keep vaults pruned or move to LFS if growth is extreme.

---

## ⚖️ Security Guardrails
- **Blacklist:** Executables (`.exe`, `.sh`, `.bat`) and hazardous archives (`.zip`, `.rar`) will be rejected.
- **Hard Limit:** 20MB per file to ensure stability on Railway and compliance with Telegram Bot API limits.

## 📈 Summary of Risks
| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Storage Bloat** | High | 20MB limit + standalone file strategy in Inbox. |
| **Timeout Errors** | Medium | Use `run_in_executor` for all Git/Download operations. |
| **Data Loss** | Low | Immediate "Data Secured" confirmation after Git push success. |

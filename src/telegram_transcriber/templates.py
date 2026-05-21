from datetime import datetime

# ==========================================
# 1. AI PROMPTS (Instruction Layer)
# ==========================================

INGESTION_PROMPT = """
You are an expert Knowledge Manager. Your task is to clean up the provided transcript or text for grammar, clarity, and readability while maintaining the original intent and tone.

Please provide:
1. A polished, grammatically correct version of the content.
2. A concise 2-sentence summary of the core message.
3. Exactly 3 actionable next steps or key takeaways derived from the content.

FORMATTING RULES:
- Use clean Markdown.
- Separate the polished content from the summary and action items using the exact marker: '---ANALYSIS_SPLIT---'

CONTENT:
{content}
"""

# ==========================================
# 2. VAULT TEMPLATES (Persistence Layer)
# ==========================================

class NoteTemplate:
    @staticmethod
    def get_frontmatter(project="Unsorted", user_name="User"):
        """Generates valid YAML frontmatter for the daily inbox file."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        return (
            "---\n"
            f"owner: {user_name}\n"
            f"date: {date_str}\n"
            "status: unrouted\n"
            "---\n\n"
            f"# 📥 Inbox Captures ({date_str})\n\n"
        )

    @staticmethod
    def format_entry(clean_content, analysis_output, input_type="voice"):
        """
        Formats the entry with machine-parsable delimiters and Obsidian callouts.
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        return (
            f"\n# CAPTURE_START\n"
            f"## Capture ({timestamp})\n"
            f"- **Input Type**: {input_type}\n\n"
            f"> [!ABSTRACT] Polished Content\n{clean_content}\n\n"
            f"> [!LIGHTBULB] Analysis & Actions\n{analysis_output}\n\n"
            f"# CAPTURE_END\n"
            "--- \n"
        )

class MediaTemplate:
    @staticmethod
    def get_metadata_content(filename, original_name, mime_type, file_size, caption, timestamp):
        """
        Generates content for the companion .md file for media attachments.
        """
        size_mb = file_size / (1024 * 1024)

        content = (
            "---\n"
            f"original_name: \"{original_name}\"\n"
            f"mime_type: {mime_type}\n"
            f"size_bytes: {file_size}\n"
            f"size_mb: {size_mb:.2f}\n"
            f"ingested_at: {timestamp}\n"
            f"status: unrouted\n"
            "---\n\n"
            f"# 📎 Media Attachment: {original_name}\n\n"
            f"![[{filename}]]\n\n"
        )

        if caption:
            content += f"## 📝 Caption\n{caption}\n"

        return content

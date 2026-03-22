from datetime import datetime

class NoteTemplate:
    @staticmethod
    def get_daily_header(project):
        """Simple YAML frontmatter for a new daily note."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        return (
            "---\n"
            f"date: {date_str}\n"
            f"tags: [{project}]\n"
            "type: telegram_capture\n"
            "---\n"
            f"# 📥 Telegram Captures - {project}\n\n"
        )

    @staticmethod
    def format_entry(clean_transcript, analysis_output):
        """Formats the transcript and Gemini analysis into a timestamped entry."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        return (
            f"## 🕒 {timestamp}\n"
            f"### 📝 Transcript\n"
            f"{clean_transcript}\n\n"
            f"### 🧠 Analysis\n"
            f"{analysis_output}\n\n"
            "--- \n"
        )
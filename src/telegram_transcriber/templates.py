from datetime import datetime

# ==========================================
# 1. AI PROMPTS (Instruction Layer)
# ==========================================

STAR_PROMPT = """
You are Katie O’Donoghue's Elite Interview Coach and Brand Strategy Consultant.
The user is preparing for the 'Bloom Brand and Events Manager' role at Bord Bia.

TASK:
1. Transform the raw transcript into a high-impact, professional STAR story.
2. Structure into: **S**ituation, **T**ask, **A**ction, and **Result**.
3. Focus on stakeholder management, ROI, and consumer-led experiences.

FORMATTING RULES:
- Use clean Markdown.
- Separate the polished story from the strategic analysis using: '---ANALYSIS_SPLIT---'

TRANSCRIPT:
{content}
"""

GENERAL_PROMPT = """
You are an expert Knowledge Manager. Clean up this transcript for grammar and readability.
Maintain the original intent. Provide a brief analysis and 3 action items.

FORMATTING RULES:
- Separate the polished text from the analysis using: '---ANALYSIS_SPLIT---'

TRANSCRIPT:
{content}
"""

# ==========================================
# 2. VAULT TEMPLATES (Persistence Layer)
# ==========================================

class NoteTemplate:
    @staticmethod
    def get_frontmatter(project, user_name="User"):
        """Generates valid YAML frontmatter with dynamic tags."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        return (
            "---\n"
            f"owner: {user_name}\n"
            f"date: {date_str}\n"
            f"project: {project}\n"
            f"tags: [2ndbrain, {project.lower()}]\n"
            "status: processed\n"
            "---\n\n"
            f"# 📥 {project} Captures\n\n"
        )

    @staticmethod
    def format_entry(clean_transcript, analysis_output, is_star=False):
        """
        Formats the entry using Obsidian Callouts for high-readability.
        Ideal for mobile review during travel.
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        icon = "🌟" if is_star else "📝"
        title = "STAR Story" if is_star else "Transcript"
        
        return (
            f"## {icon} {title} ({timestamp})\n\n"
            f"> [!ABSTRACT] Polished Content\n"
            f"{clean_transcript}\n\n"
            f"> [!LIGHTBULB] Second Brain Analysis\n"
            f"{analysis_output}\n\n"
            "--- \n"
        )

class MediaTemplate:
    @staticmethod
    def get_metadata_content(filename, original_name, mime_type, file_size, caption, timestamp):
        """
        Generates content for the companion .md file for media attachments.
        Includes frontmatter and an Obsidian link to the binary file.
        """
        size_mb = file_size / (1024 * 1024)

        content = (
            "---\n"
            f"original_name: \"{original_name}\"\n"
            f"mime_type: {mime_type}\n"
            f"size_bytes: {file_size}\n"
            f"size_mb: {size_mb:.2f}\n"
            f"ingested_at: {timestamp}\n"
            "---\n\n"
            f"# 📎 Media Attachment: {original_name}\n\n"
            f"![[{filename}]]\n\n"
        )

        if caption:
            content += f"## 📝 Caption\n{caption}\n"

        return content
# ai_engine.py
import os
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold 
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from google.api_core import exceptions
from .templates import STAR_PROMPT, GENERAL_PROMPT

class AIEngine:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        # We don't call genai.configure() here because it's global and brittle.
        # Instead, we'll use a local model instance with the key if possible,
        # but since google-generativeai is globally configured, we must be careful.
        # If we need absolute isolation, we should use the google-genai (Vertex/Firebase)
        # or just accept that the key is currently global in this specific library version.
        # Given the current library, we will ensure configure is only called if the key changes.
        if os.getenv("GEMINI_API_KEY") != self.api_key:
             genai.configure(api_key=self.api_key)
        else:
             genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        self.model = genai.GenerativeModel("gemini-2.0-flash")

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    @retry(
        retry=retry_if_exception_type(exceptions.ResourceExhausted),
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6)
    )
    async def generate(self, prompt):
        response = await self.model.generate_content_async(prompt)
        return response.text

    async def get_structured_output(self, text, user_name, is_star=False):
        prompt_template = STAR_PROMPT if is_star else GENERAL_PROMPT
        prompt = prompt_template.format(user_name=user_name, content=text)
        
        full_response = await self.generate(prompt)
        if "---ANALYSIS_SPLIT---" in full_response:
            return full_response.split("---ANALYSIS_SPLIT---", 1)
        return full_response, "No separate analysis generated."
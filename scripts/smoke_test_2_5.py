import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

async def run_smoke_test():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found.")
        return

    # 1. Configuration
    genai.configure(api_key=api_key)
    
    # We use the full name confirmed by your diagnostic script
    model_name = "gemini-2.5-flash"
    print(f"🚀 Initializing Smoke Test for: {model_name}...")

    try:
        # 2. Model Initialization
        model = genai.GenerativeModel(model_name)
        
        # 3. Simple Generation Attempt
        # We use a short, simple prompt to minimize token usage
        prompt = "Hello! Briefly confirm if you are Gemini 2.5 Flash and if you can see this message."
        
        print("📡 Sending request to Google AI...")
        response = await model.generate_content_async(prompt)
        
        # 4. Validation of Output
        if response and response.text:
            print("\n✅ SMOKE TEST PASSED!")
            print(f"📄 Model Response: {response.text.strip()}")
            print("-" * 30)
            print(f"💡 Use 'models/{model_name}' or '{model_name}' in your ai_engine.py")
        else:
            print("⚠️ Request succeeded but returned empty text.")

    except Exception as e:
        print(f"\n❌ SMOKE TEST FAILED")
        print(f"Error Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        
        if "404" in str(e):
            print("🔍 Analysis: The model name is likely valid in the API list but not yet enabled for your specific API key/region.")
        elif "403" in str(e):
            print("🔍 Analysis: Permission denied. Your API key might not have access to the 2.5 series.")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
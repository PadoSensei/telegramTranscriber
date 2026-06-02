import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def list_available_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in environment.")
        return

    genai.configure(api_key=api_key)

    print(f"🔍 Checking available models for key ending in ...{api_key[-4:]}")
    
    try:
        available_models = genai.list_models()
        print("\nAvailable Models that support 'generateContent':")
        print("-" * 50)
        
        found_any = False
        for m in available_models:
            if 'generateContent' in m.supported_generation_methods:
                print(f"✅ {m.name:35} | {m.display_name}")
                found_any = True
        
        if not found_any:
            print("⚠️ No models found that support content generation. Check your API permissions.")
            
    except Exception as e:
        print(f"❌ Failed to list models: {e}")

if __name__ == "__main__":
    list_available_models()
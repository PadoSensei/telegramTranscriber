import os
import time
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv

load_dotenv()

def check_gemini_quota(api_key=None, model_name="gemini-2.5-flash", iterations=3):
    """
    Tests an API key for immediate 429 errors and measures RPM threshold.
    """
    target_key = api_key or os.getenv("GEMINI_API_KEY")
    
    if not target_key:
        print("❌ ERROR: No API Key found in .env or arguments.")
        return

    print(f"🔍 Testing Key: {target_key[:10]}...{target_key[-5:]}")
    print(f"🤖 Model: {model_name}")
    print("-" * 40)

    genai.configure(api_key=target_key)
    model = genai.GenerativeModel(model_name)

    success_count = 0
    
    for i in range(1, iterations + 1):
        print(f"Attempt {i}/{iterations}: ", end="")
        start_time = time.time()
        
        try:
            # We use a tiny prompt to minimize token usage while testing RPM
            response = model.generate_content("Ping. Reply with 'Pong'.")
            latency = time.time() - start_time
            print(f"✅ SUCCESS ({latency:.2f}s) -> Result: {response.text.strip()}")
            success_count += 1
            
        except exceptions.ResourceExhausted as e:
            print(f"🛑 429 ERROR: Quota Exhausted.")
            print(f"\n[REASON]: You have hit the Requests Per Minute (RPM) limit.")
            print("[ACTION]: Switch to a different key or upgrade to a Pay-as-you-go plan.")
            break
            
        except exceptions.PermissionDenied:
            print("❌ ERROR: Invalid API Key or API not enabled for this project.")
            break
            
        except Exception as e:
            print(f"❓ UNKNOWN ERROR: {e}")
            break

    print("-" * 40)
    if success_count == iterations:
        print("🟢 STATUS: KEY IS HEALTHY (Stable RPM)")
    elif success_count > 0:
        print("🟡 STATUS: KEY IS WEAK (Throttling detected)")
    else:
        print("🔴 STATUS: KEY IS DEAD/BLOCKED")

if __name__ == "__main__":
    # iteration=5 tests if the key can handle multiple users at once
    check_gemini_quota(iterations=5)
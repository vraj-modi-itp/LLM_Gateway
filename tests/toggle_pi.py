import requests
import argparse
import os

# Configuration
ADMIN_URL = "http://localhost:8000/admin/flags/prompt_intelligence_enabled"
# It defaults to your test key, but realistically it should pull from your environment
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "your_super_secret_admin_password")

def toggle_kill_switch(is_enabled: bool, updated_by: str):
    """Sends the HTTP request to the admin API to toggle the PI Engine."""
    state_str = "ENABLED" if is_enabled else "DISABLED"
    print(f"🚦 Attempting to set Prompt Intelligence to: {state_str}...")
    
    headers = {
        "Content-Type": "application/json", 
        "x-admin-key": ADMIN_KEY
    }
    
    payload = {
        "is_enabled": is_enabled, 
        "updated_by": updated_by
    }
    
    try:
        response = requests.post(ADMIN_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"✅ Success! Database state updated to: {state_str}")
            print("⏳ Remember: It will take up to 30 seconds for the TTL cache to propagate this change.")
        elif response.status_code == 403:
            print("❌ Forbidden: Invalid Admin Key. Check your ADMIN_API_KEY environment variable.")
        else:
            print(f"❌ Failed: HTTP {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is the FastAPI gateway running on port 8000?")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Admin Utility: Toggle Prompt Intelligence Flag")
    
    # Mutually exclusive group so you can't pass both --on and --off
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--on", action="store_true", help="Enable the Prompt Intelligence Engine")
    group.add_argument("--off", action="store_true", help="Disable the Prompt Intelligence Engine")
    
    parser.add_argument("--user", type=str, default="CLI Admin", help="Name of the person/script making the change")
    
    args = parser.parse_args()
    
    # Execute the toggle based on the passed arguments
    toggle_kill_switch(is_enabled=args.on, updated_by=args.user)
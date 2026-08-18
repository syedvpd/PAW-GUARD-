"""Quick FCM credential validation."""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pawguard.core.config import get_settings

s = get_settings()
if s.fcm_credentials_json:
    try:
        d = json.loads(s.fcm_credentials_json)
        keys = ["type", "project_id", "private_key", "client_email", "token_uri"]
        missing = [k for k in keys if k not in d]
        print(f"FCM_CREDENTIALS_JSON: VALID ({len(s.fcm_credentials_json)} chars)")
        print(f"  project_id: {d.get('project_id', '?')}")
        print(f"  type: {d.get('type', '?')}")
        print(f"  client_email: {d.get('client_email', '?')}")
        if missing:
            print(f"  MISSING keys: {missing}")
        else:
            print("  All required keys present")
    except json.JSONDecodeError as e:
        print(f"FCM_CREDENTIALS_JSON: INVALID JSON - {e}")
elif s.fcm_credentials_path:
    print(f"Using FCM_CREDENTIALS_PATH: {s.fcm_credentials_path}")
    try:
        with open(s.fcm_credentials_path) as f:
            d = json.load(f)
            print(f"  project_id: {d.get('project_id', '?')}")
            print("  Local file: VALID")
    except Exception as e:
        print(f"  Local file error: {e}")
else:
    print("NO FCM CREDENTIALS CONFIGURED")

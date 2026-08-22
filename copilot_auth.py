"""GitHub Copilot authentication via OAuth device flow."""
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = "01ab8ac9400c4e429b23"
SCOPES = "read:user"
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_env() -> dict:
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _save_env(updates: dict):
    env = _load_env()
    env.update(updates)
    lines = [f'{k}="{v}"' for k, v in env.items()]
    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def _api_post(url: str, data: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Accept": "application/json", "User-Agent": "charlyn/1.0"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def device_login(print_fn=print) -> str:
    """Run GitHub device authorization flow. Returns the access token."""
    data = _api_post("https://github.com/login/device/code", {
        "client_id": CLIENT_ID,
        "scope": SCOPES,
    })

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data.get("verification_uri", "https://github.com/login/device")
    interval = data.get("interval", 5)

    print_fn(f"\n🔑 GitHub Copilot Login")
    print_fn("=" * 40)
    print_fn(f"1. Visit: {verification_uri}")
    print_fn(f"2. Enter code: {user_code}")
    print_fn(f"\nWaiting for authorization...")

    while True:
        time.sleep(interval)
        data = _api_post("https://github.com/login/oauth/access_token", {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })

        if "access_token" in data:
            token = data["access_token"]
            _save_env({"COPILOT_TOKEN": token})
            print_fn("✅ Login successful!")
            return token
        elif data.get("error") == "authorization_pending":
            continue
        elif data.get("error") == "slow_down":
            interval += 5
            continue
        elif data.get("error") == "expired_token":
            raise Exception("Device code expired. Please run login again.")
        else:
            raise Exception(
                f"Login failed: {data.get('error_description', data.get('error', 'Unknown error'))}"
            )


def validate_token(token: str) -> bool:
    """Check if a Copilot token looks valid by hitting the Copilot API."""
    req = urllib.request.Request(
        "https://api.githubcopilot.com/models",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "charlyn/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return False
    except Exception:
        return None


def logout():
    """Remove the saved token from .env."""
    env = _load_env()
    env.pop("COPILOT_TOKEN", None)
    lines = [f'{k}="{v}"' for k, v in env.items()]
    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

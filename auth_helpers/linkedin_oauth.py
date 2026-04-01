"""Interactive helper script to obtain a LinkedIn OAuth 2.0 access token.

Prerequisites:
1. Create a LinkedIn App at https://www.linkedin.com/developers/
2. Add the redirect URL: http://localhost:8000/callback
3. Request the following scopes/products:
   - Share on LinkedIn (w_member_social)
   - Sign In with LinkedIn using OpenID Connect (openid, profile)

Usage:
    python auth_helpers/linkedin_oauth.py

This will:
1. Open your browser to LinkedIn's authorization page
2. Start a local server to catch the callback
3. Exchange the authorization code for an access token
4. Print the access token to add to your .env file
"""

import http.server
import json
import os
import sys
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = "openid profile w_member_social"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
PROFILE_URL = "https://api.linkedin.com/v2/userinfo"


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this window.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your .env file first.")
        sys.exit(1)

    # Step 1: Open browser for authorization
    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })
    auth_full_url = f"{AUTH_URL}?{auth_params}"

    print(f"Opening browser for LinkedIn authorization...")
    print(f"URL: {auth_full_url}\n")
    webbrowser.open(auth_full_url)

    # Step 2: Start local server to catch callback
    print("Waiting for callback on http://localhost:8000/callback ...")
    server = http.server.HTTPServer(("localhost", 8000), CallbackHandler)
    server.handle_request()

    if not CallbackHandler.auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    print(f"Authorization code received!")

    # Step 3: Exchange code for access token
    token_data = {
        "grant_type": "authorization_code",
        "code": CallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    resp = requests.post(TOKEN_URL, data=token_data, timeout=30)
    resp.raise_for_status()
    token_info = resp.json()

    access_token = token_info["access_token"]
    expires_in = token_info.get("expires_in", "unknown")

    print(f"\nAccess token obtained! Expires in {expires_in} seconds.\n")

    # Step 4: Get person URN
    headers = {"Authorization": f"Bearer {access_token}"}
    profile_resp = requests.get(PROFILE_URL, headers=headers, timeout=30)
    profile_resp.raise_for_status()
    profile = profile_resp.json()

    person_id = profile.get("sub", "")
    person_urn = f"urn:li:person:{person_id}"

    print("=" * 60)
    print("Add these to your .env file:")
    print("=" * 60)
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
    print(f"LINKEDIN_PERSON_URN={person_urn}")
    print("=" * 60)
    print(f"\nNote: Token expires in ~{int(expires_in)//86400} days. You'll need to refresh it.")


if __name__ == "__main__":
    main()

"""Interactive helper script to obtain a LinkedIn OAuth 2.0 access token.

Prerequisites:
1. Create a LinkedIn App at https://www.linkedin.com/developers/
2. Add the redirect URL: http://localhost:9999/callback
   (Auth tab -> Authorized redirect URLs)
3. Request the following scopes/products:
   - Share on LinkedIn (w_member_social)
   - Sign In with LinkedIn using OpenID Connect (openid, profile)

Usage:
    python auth_helpers/linkedin_oauth.py

This will:
1. Start a temporary HTTP server on port 9999
2. Open your browser to LinkedIn's authorization page
3. Catch the callback and exchange the code for an access token
4. Fetch your person URN
5. Print LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN to add to .env
"""

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:9999/callback"
SCOPES = "openid profile w_member_social"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
PROFILE_URL = "https://api.linkedin.com/v2/userinfo"

TIMEOUT_SECONDS = 120


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code = None
    auth_error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                b"<h1>Authorization successful!</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            CallbackHandler.auth_error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = f"Authorization denied: {CallbackHandler.auth_error}"
            self.wfile.write(
                f"<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                f"<h1>Authorization Failed</h1><p>{msg}</p>"
                f"</body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server request logs


def main():
    print()
    print("=" * 60)
    print("  LinkedIn OAuth Setup")
    print("=" * 60)
    print()
    print("  IMPORTANT: Make sure this redirect URL is added in your")
    print("  LinkedIn app settings:")
    print()
    print("    Auth tab -> Authorized redirect URLs -> Add:")
    print(f"    {REDIRECT_URI}")
    print()
    print("=" * 60)
    print()

    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your .env file first.")
        sys.exit(1)

    # Step 1: Start temporary HTTP server on port 9999
    try:
        server = http.server.HTTPServer(("localhost", 9999), CallbackHandler)
    except OSError as e:
        print(f"ERROR: Cannot start server on port 9999: {e}")
        print("Make sure nothing else is using port 9999 and try again.")
        sys.exit(1)

    server.timeout = TIMEOUT_SECONDS

    # Step 2: Open browser for authorization
    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })
    auth_full_url = f"{AUTH_URL}?{auth_params}"

    print("Opening browser for LinkedIn authorization...")
    print(f"(If the browser doesn't open, copy this URL manually:)")
    print(f"  {auth_full_url}")
    print()
    webbrowser.open(auth_full_url)

    # Step 3: Wait for callback (with timeout)
    print(f"Waiting for callback on {REDIRECT_URI} ...")
    print(f"(Will timeout after {TIMEOUT_SECONDS} seconds)")
    print()

    server.handle_request()
    server.server_close()

    # Check what we got
    if CallbackHandler.auth_error:
        print(f"ERROR: Authorization denied by user: {CallbackHandler.auth_error}")
        sys.exit(1)

    if not CallbackHandler.auth_code:
        print("ERROR: No authorization code received (timed out or browser was closed).")
        sys.exit(1)

    print("Authorization code received!")

    # Step 4: Exchange code for access token
    print("Exchanging code for access token...")
    token_data = {
        "grant_type": "authorization_code",
        "code": CallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    try:
        resp = requests.post(TOKEN_URL, data=token_data, timeout=30)
        resp.raise_for_status()
        token_info = resp.json()
    except requests.RequestException as e:
        print(f"\nERROR: Token exchange failed: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

    access_token = token_info["access_token"]
    expires_in = token_info.get("expires_in", 0)

    # Step 5: Get person URN
    print("Fetching person URN...")
    person_urn = ""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_resp = requests.get(PROFILE_URL, headers=headers, timeout=30)
        profile_resp.raise_for_status()
        profile = profile_resp.json()
        person_id = profile.get("sub", "")
        person_urn = f"urn:li:person:{person_id}"
    except requests.RequestException as e:
        print(f"\nWARNING: Could not fetch person URN: {e}")
        print("You can find it manually at: https://www.linkedin.com/developers/")
        print("The access token is still valid — see below.\n")

    # Step 6: Print results
    print()
    print("=" * 60)
    print("  Add these to your .env file:")
    print("=" * 60)
    print(f"  LINKEDIN_ACCESS_TOKEN={access_token}")
    if person_urn:
        print(f"  LINKEDIN_PERSON_URN={person_urn}")
    print("=" * 60)

    if expires_in:
        days = int(expires_in) // 86400
        print(f"\n  Token expires in: ~{days} days ({expires_in} seconds)")
        print("  You will need to re-run this script when it expires.")
    print()


if __name__ == "__main__":
    main()

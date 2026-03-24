#!/usr/bin/env python3
"""One-off WHOOP OAuth2 helper — spins up a local server, opens the browser,
catches the callback, exchanges the code for tokens, and saves the refresh token.
Uses only standard library (no requests needed)."""

import http.server
import urllib.parse
import urllib.request
import webbrowser
import json
import secrets
import sys
import os

CLIENT_ID = "081560a2-7c7f-4788-b6d4-68a6c1455f74"
REDIRECT_URI = "http://localhost:9876/callback"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPES = "offline read:recovery read:sleep read:workout read:body_measurement read:cycles"

STATE = secrets.token_urlsafe(32)

AUTH_URL = (
    f"https://api.prod.whoop.com/oauth/oauth2/auth"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&response_type=code"
    f"&scope={urllib.parse.quote(SCOPES)}"
    f"&state={STATE}"
)


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"\n  Received callback: {self.path}")
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        print(f"  Query params: {dict(params)}")
        code = params.get("code", [None])[0]

        if code:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Got it! You can close this tab.</h2>")
            self.server.auth_code = code
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = params.get("error", ["unknown"])[0]
            desc = params.get("error_description", [""])[0]
            self.wfile.write(f"<h2>Error: {error}</h2><p>{desc}</p>".encode())
            self.server.auth_code = None

    def log_message(self, format, *args):
        pass  # suppress request logs


def main():
    client_secret = input("Paste your WHOOP_CLIENT_SECRET: ").strip()
    if not client_secret:
        print("No secret provided, aborting.")
        sys.exit(1)

    server = http.server.HTTPServer(("localhost", 9876), CallbackHandler)
    server.auth_code = None

    print(f"\nOpening browser for WHOOP authorization...\n")
    webbrowser.open(AUTH_URL)
    print("Waiting for callback on http://localhost:9876/callback ...")

    server.handle_request()  # blocks until one request comes in

    code = server.auth_code
    if not code:
        print("No authorization code received. Aborting.")
        sys.exit(1)

    print(f"\nGot auth code. Exchanging for tokens...")

    # Use urllib (stdlib) instead of requests
    post_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=post_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Token exchange failed: {e.code}")
        print(e.read().decode())
        sys.exit(1)

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not refresh_token:
        print("No refresh token in response!")
        print(tokens)
        sys.exit(1)

    # Save to .whoop_refresh_token
    token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whoop_refresh_token")
    with open(token_file, "w") as f:
        f.write(refresh_token + "\n")

    print(f"\nSuccess!")
    print(f"  Access token:  ...{access_token[-8:]}")
    print(f"  Refresh token: ...{refresh_token[-8:]}")
    print(f"  Saved to: .whoop_refresh_token")
    print(f"\nDon't forget to also update the GitHub secret:")
    print(f"  gh secret set WHOOP_REFRESH_TOKEN --body '{refresh_token}'")


if __name__ == "__main__":
    main()

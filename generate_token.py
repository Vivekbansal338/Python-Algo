#!/usr/bin/env python3
"""
================================================================================
ZERODHA KITE CONNECT - ACCESS TOKEN GENERATOR
================================================================================
Generate and refresh access tokens for Kite Connect API

Flow:
1. User navigates to login URL with api_key
2. After login, user is redirected with request_token
3. Script exchanges request_token for access_token using api_secret
4. Access token is saved to .env file

Author: Sector Analysis System
Date: January 2026
================================================================================
"""

import os
import sys
import hashlib
import requests
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv, set_key
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Kite Connect API endpoints
KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"
KITE_TOKEN_URL = "https://api.kite.trade/session/token"
KITE_LOGOUT_URL = "https://api.kite.trade/session/token"


class TokenGenerator:
    """Generate and manage Kite Connect access tokens"""
    
    def __init__(self, env_file: str = ".env"):
        """
        Initialize token generator
        
        Args:
            env_file: Path to .env file
        """
        self.env_file = Path(env_file)
        self.api_key = None
        self.api_secret = None
        self.redirect_url = "http://127.0.0.1:8080"  # Local redirect
        
        # Load existing credentials if available
        load_dotenv(self.env_file)
        self.api_key = os.getenv("KITE_API_KEY")
        self.api_secret = os.getenv("KITE_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            logger.error("KITE_API_KEY and KITE_API_SECRET not found in .env file")
            sys.exit(1)
    
    def get_login_url(self) -> str:
        """
        Generate the login URL where user should navigate
        
        Returns:
            Full login URL
        """
        return f"{KITE_LOGIN_URL}?v=3&api_key={self.api_key}"
    
    def generate_checksum(self, request_token: str) -> str:
        """
        Generate checksum for token exchange
        
        Checksum = SHA-256(api_key + request_token + api_secret)
        
        Args:
            request_token: Request token from login
            
        Returns:
            Checksum hash
        """
        message = f"{self.api_key}{request_token}{self.api_secret}"
        checksum = hashlib.sha256(message.encode()).hexdigest()
        return checksum
    
    def exchange_token(self, request_token: str) -> dict:
        """
        Exchange request_token for access_token
        
        Args:
            request_token: Token received after user login
            
        Returns:
            Response dict with access_token and user details
        """
        checksum = self.generate_checksum(request_token)
        
        payload = {
            "api_key": self.api_key,
            "request_token": request_token,
            "checksum": checksum
        }
        
        headers = {
            "X-Kite-Version": "3"
        }
        
        try:
            logger.info("Exchanging request token for access token...")
            response = requests.post(KITE_TOKEN_URL, data=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "success":
                logger.info("✅ Token exchange successful!")
                return data.get("data", {})
            else:
                logger.error(f"❌ Token exchange failed: {data}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API request failed: {e}")
            return None
    
    def save_token(self, access_token: str, user_id: str = None):
        """
        Save access token to .env file
        
        Args:
            access_token: New access token
            user_id: User ID (optional)
        """
        # Create .env if it doesn't exist
        if not self.env_file.exists():
            self.env_file.touch()
        
        # Save token without extra quotes (dotenv handles formatting)
        set_key(self.env_file, "KITE_ACCESS_TOKEN", access_token)
        
        if user_id:
            set_key(self.env_file, "KITE_USER_ID", user_id)
        
        logger.info(f"✅ Token saved to {self.env_file}")
        logger.info(f"   Access Token: {access_token[:20]}...")
    
    def logout(self, access_token: str):
        """
        Logout and invalidate the current access token
        
        Args:
            access_token: Token to invalidate
        """
        params = {
            "api_key": self.api_key,
            "access_token": access_token
        }
        
        headers = {
            "X-Kite-Version": "3"
        }
        
        try:
            logger.info("Logging out and invalidating token...")
            response = requests.delete(KITE_LOGOUT_URL, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") == "success":
                logger.info("✅ Logout successful")
            else:
                logger.warning(f"⚠️  Logout response: {data}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Logout failed: {e}")
    
    def generate_via_browser(self) -> bool:
        """
        Interactive token generation via browser
        
        Steps:
        1. Opens browser with login URL
        2. User logs in and is redirected
        3. User extracts and pastes just the request_token
        4. Script exchanges request_token for access_token
        5. Token is saved to .env
        
        Returns:
            True if successful
        """
        print("\n" + "="*70)
        print("ZERODHA KITE CONNECT - ACCESS TOKEN GENERATOR")
        print("="*70)
        print("\n📋 Instructions:")
        print("1. Your browser will open shortly with the Kite Connect login page")
        print("2. Log in with your Zerodha account credentials")
        print("3. After successful login, you'll see a redirect URL in your browser")
        print("4. Copy only the REQUEST TOKEN from the URL (the long alphanumeric string)")
        print("\n⚠️  Example:")
        print("   If redirect URL is: http://127.0.0.1:8080/?request_token=xyz123abc&status=success")
        print("   Copy only this: xyz123abc")
        print("\n" + "-"*70 + "\n")
        
        # Open login URL in browser
        login_url = self.get_login_url()
        print(f"🌐 Opening login page...\n   {login_url}\n")
        
        try:
            webbrowser.open(login_url)
        except Exception as e:
            logger.warning(f"Could not open browser automatically: {e}")
            print(f"📌 Please open this URL manually: {login_url}\n")
        
        # Get request token from user (just the token, not the full URL)
        request_token = input("📌 Paste the REQUEST TOKEN here:\n> ").strip()
        
        # Validate request_token
        if not request_token or len(request_token) < 10:
            logger.error("❌ Invalid request token (too short)")
            return False
        
        logger.info(f"✅ Request token received: {request_token[:20]}...")
        
        # Exchange request_token for access_token
        user_data = self.exchange_token(request_token)
        if not user_data:
            return False
        
        # Save token to .env
        access_token = user_data.get("access_token")
        user_id = user_data.get("user_id")
        
        if not access_token:
            logger.error("❌ No access token in response")
            return False
        
        self.save_token(access_token, user_id)
        
        # Print user details
        print("\n" + "="*70)
        print("✅ TOKEN GENERATION SUCCESSFUL")
        print("="*70)
        print(f"\n👤 User Details:")
        print(f"   User ID: {user_data.get('user_id')}")
        print(f"   Name: {user_data.get('user_name')}")
        print(f"   Email: {user_data.get('email')}")
        print(f"   Broker: {user_data.get('broker')}")
        print(f"\n🔐 Token Details:")
        print(f"   Access Token: {access_token[:30]}...")
        print(f"   Expires: Next day at 6 AM (regulatory requirement)")
        print(f"\n💾 Saved to: {self.env_file.absolute()}")
        print("\n" + "="*70 + "\n")
        
        return True
    
    def validate_token(self, access_token: str) -> bool:
        """
        Validate if an access token is still valid
        
        Args:
            access_token: Token to validate
            
        Returns:
            True if token is valid
        """
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{access_token}"
        }
        
        try:
            response = requests.get(
                "https://api.kite.trade/user/profile",
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") == "success":
                logger.info("✅ Token is valid!")
                user_data = data.get("data", {})
                print(f"\n📊 Current User:")
                print(f"   User ID: {user_data.get('user_id')}")
                print(f"   Name: {user_data.get('user_name')}")
                print(f"   Email: {user_data.get('email')}")
                return True
            else:
                logger.error("❌ Token validation failed")
                return False
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("❌ Token is invalid or expired")
                return False
            else:
                logger.error(f"❌ Validation failed: {e}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request failed: {e}")
            return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Zerodha Kite Connect - Access Token Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate new token (interactive)
  python generate_token.py
  
  # Validate current token
  python generate_token.py --validate
  
  # Logout and invalidate current token
  python generate_token.py --logout
  
  # Exchange request token directly
  python generate_token.py --exchange xxxxx
        """
    )
    
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file (default: .env)"
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--validate",
        action="store_true",
        help="Validate the current access token"
    )
    group.add_argument(
        "--logout",
        action="store_true",
        help="Logout and invalidate the current access token"
    )
    group.add_argument(
        "--exchange",
        metavar="REQUEST_TOKEN",
        help="Exchange a request token directly (skip browser flow)"
    )
    
    args = parser.parse_args()
    
    # Initialize generator
    generator = TokenGenerator(args.env)
    
    # Handle different operations
    if args.validate:
        # Validate current token
        load_dotenv(args.env)
        access_token = os.getenv("KITE_ACCESS_TOKEN")
        
        if not access_token:
            logger.error("No KITE_ACCESS_TOKEN found in .env")
            sys.exit(1)
        
        # Remove quotes if present
        if access_token.startswith("'") and access_token.endswith("'"):
            access_token = access_token[1:-1]
        
        if generator.validate_token(access_token):
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif args.logout:
        # Logout and invalidate token
        load_dotenv(args.env)
        access_token = os.getenv("KITE_ACCESS_TOKEN")
        
        if not access_token:
            logger.error("No KITE_ACCESS_TOKEN found in .env")
            sys.exit(1)
        
        # Remove quotes if present
        if access_token.startswith("'") and access_token.endswith("'"):
            access_token = access_token[1:-1]
        
        generator.logout(access_token)
        sys.exit(0)
    
    elif args.exchange:
        # Exchange request token directly
        user_data = generator.exchange_token(args.exchange)
        if user_data:
            access_token = user_data.get("access_token")
            user_id = user_data.get("user_id")
            generator.save_token(access_token, user_id)
            sys.exit(0)
        else:
            sys.exit(1)
    
    else:
        # Interactive browser-based flow (default)
        if generator.generate_via_browser():
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()

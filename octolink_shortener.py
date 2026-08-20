import asyncio
import aiohttp
import random
import string
import time
import os
import sys
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(base_dir, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Configuration
GENERATED_LINKS = int(os.getenv('GENERATED_LINKS', 10))
CONCURRENT_SCAN_PER_LINK = int(os.getenv('CONCURRENT_SCAN_PER_LINK', 3))
REFRESH_INTERVAL = int(os.getenv('REFRESH_INTERVAL', 60))

# Telegram Configuration from Environment Variables (with embedded defaults)
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip() or '8832029872:AAELLvE4tZp4oAxItMbk__LKifDo745N0TA'
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip() or '-1004419177767'
AUTHORIZED_USER_ID = os.getenv('AUTHORIZED_USER_ID', '').strip() or 'your_telegram_user_id_here'

# Octolink API Configuration (with embedded default)
OCTOLINK_API_TOKEN = os.getenv('OCTOLINK_API_TOKEN', '').strip() or '38f98360d21736123c234eddc4aa527702c6a8fe'
OCTOLINK_API_URL = "https://octolink.vip/api"

# Step Campaign Types
STEP_CAMPAIGNS = {
    "step2": 3,  # Google Search 3 Step
    "step3": 4,  # Google Search 2 Step
    "step4": 5   # Google Search 4 Step
}


class TelegramSender:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_message_id = None
    
    async def send_message(self, text):
        """Send message to Telegram and return message_id"""
        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    result = await response.json()
                    if result.get("ok"):
                        message_id = result.get("result", {}).get("message_id")
                        self.last_message_id = message_id
                        return message_id
                    else:
                        print(f"Telegram error: {result.get('description', 'Unknown error')}")
                        return None
        except Exception as e:
            print(f"Telegram connection error: {e}")
            return None
    

    async def delete_message(self, message_id):
        """Delete Telegram message"""
        url = f"{self.base_url}/deleteMessage"
        params = {
            "chat_id": self.chat_id,
            "message_id": message_id
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    result = await response.json()
                    return result.get("ok", False)
        except Exception as e:
            print(f"Telegram delete error: {e}")
            return False

    async def edit_message_text(self, text):
        """Edit existing message text"""
        if not self.last_message_id:
            return await self.send_message(text)
        
        url = f"{self.base_url}/editMessageText"
        params = {
            "chat_id": self.chat_id,
            "message_id": self.last_message_id,
            "text": text
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    result = await response.json()
                    if result.get("ok"):
                        return True
                    else:
                        print(f"Telegram edit error: {result.get('description', 'Unknown error')}")
                        # If edit fails, send new message
                        return await self.send_message(text)
        except Exception as e:
            print(f"Telegram edit error: {e}")
            return await self.send_message(text)


class OctolinkShortener:
    def __init__(self, api_token):
        self.api_token = api_token
        self.base_url = OCTOLINK_API_URL
    
    async def shorten_url(self, long_url, alias=None, campaign_type=3, max_retries=3, browser=None):
        """
        Shorten URL using Octolink API with Cloudflare bypass support
        """
        params = {
            "api": self.api_token,
            "url": long_url,
            "type": campaign_type
        }
        
        if alias:
            params["alias"] = alias
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://octolink.vip/",
            "Origin": "https://octolink.vip"
        }
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(self.base_url, params=params, timeout=15) as response:
                        text = await response.text()
                        
                        # Check if response is HTML (Cloudflare challenge / error page)
                        if text.strip().startswith('<!DOCTYPE html>') or text.strip().startswith('<html') or response.status == 403:
                            # If browser is available, fallback to real Chromium execution
                            if browser:
                                print(f"Cloudflare datacenter detected, using Browser API fallback (attempt {attempt + 1})...")
                                try:
                                    context = await browser.new_context(user_agent=headers["User-Agent"])
                                    page = await context.new_page()
                                    full_api_url = f"{self.base_url}?api={self.api_token}&url={long_url}&type={campaign_type}"
                                    if alias:
                                        full_api_url += f"&alias={alias}"
                                    await page.goto(full_api_url, wait_until="domcontentloaded", timeout=15000)
                                    body_text = await page.inner_text("body")
                                    await page.close()
                                    await context.close()
                                    
                                    import json
                                    res_json = json.loads(body_text.strip())
                                    if res_json.get("status") == "success":
                                        return res_json.get("shortenedUrl")
                                except Exception as be:
                                    print(f"Browser fallback attempt failed: {be}")
                            
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            else:
                                print(f"API returned HTML error page - status {response.status}")
                                return None
                        
                        # Handle JSON response
                        try:
                            result = await response.json()
                            if result.get("status") == "success":
                                return result.get("shortenedUrl")
                            else:
                                print(f"API error: {result.get('message', 'Unknown error')}")
                                return None
                        except:
                            if text.strip():
                                return text.strip()
                            else:
                                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    print(f"Connection error: {e}")
                    return None
        
        return None
    
    def generate_random_url(self):
        """Generate a random URL for testing"""
        domains = ["example.com", "test.com", "demo.org", "sample.net"]
        domain = random.choice(domains)
        random_path = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        return f"https://{domain}/{random_path}"
    
    def generate_random_alias(self, length=8):
        """Generate random alias"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


class TaskScanner:
    def __init__(self, shortener, telegram_sender):
        self.shortener = shortener
        self.telegram_sender = telegram_sender
        self.task_ids = set()
        self.browser = None
        self.playwright = None
        self.semaphore = asyncio.Semaphore(5)  # Limit concurrent browser operations
        
        # Step states
        self.step2_enabled = False
        self.step3_enabled = False
        self.step4_enabled = True
        
        # Scanner state
        self.paused = False
        self.refresh_interval = REFRESH_INTERVAL
        self.next_scan_time = None
        self.scanning = False
    
    async def init_browser(self):
        """Initialize Playwright browser"""
        if self.browser is None:
            self.playwright = await async_playwright().start()
            browser_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-features=site-per-process",
            ]
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=browser_args
                )
            except Exception as e:
                print(f"Warning: Default Chromium launch failed ({e}). Trying system Edge/Chrome...")
                try:
                    self.browser = await self.playwright.chromium.launch(
                        headless=True,
                        channel="msedge",
                        args=browser_args
                    )
                    print("Successfully launched with Microsoft Edge.")
                except Exception as e2:
                    try:
                        self.browser = await self.playwright.chromium.launch(
                            headless=True,
                            channel="chrome",
                            args=browser_args
                        )
                        print("Successfully launched with Google Chrome.")
                    except Exception as e3:
                        print(f"Error launching browser: {e3}")
                        raise e3
    
    async def close_browser(self):
        """Close Playwright browser"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
    
    async def scan_link(self, short_url, max_retries=3):
        """
        Scan a single short link to extract task ID
        
        Args:
            short_url: Short link to scan
            max_retries: Number of retries on failure
        
        Returns:
            Task ID or None
        """
        async with self.semaphore:  # Limit concurrent operations
            for attempt in range(max_retries):
                page = None
                context = None
                try:
                    # Check if browser is still connected, re-init if needed
                    if not self.browser or not self.browser.is_connected():
                        print("Browser disconnected, re-initializing...")
                        await self.close_browser()
                        await self.init_browser()
                    
                    context = await self.browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
                    )
                    page = await context.new_page()
                    
                    # Navigate to short link
                    await page.goto(short_url, timeout=30000, wait_until="domcontentloaded")
                    
                    # Wait for redirect
                    await asyncio.sleep(2)
                    
                    # Get final URL
                    final_url = page.url
                    
                    # Close page and context
                    await page.close()
                    await context.close()
                    page = None
                    context = None
                    
                    # Extract task ID from URL
                    # Expected format: https://linkhuongdan.online/<task-id>/?qq=complete
                    if "linkhuongdan.online" in final_url:
                        parsed = urlparse(final_url)
                        path = parsed.path.strip('/')
                        # Remove query parameters
                        if '/' in path:
                            path = path.split('/')[0]
                        # Remove suffixes like -2, -3, etc.
                        if '-' in path:
                            path = path.split('-')[0]
                        if path:
                            return path
                    
                    return None
                    
                except Exception as e:
                    # Clean up resources on error
                    if page:
                        try:
                            await page.close()
                        except:
                            pass
                    if context:
                        try:
                            await context.close()
                        except:
                            pass
                    
                    if attempt < max_retries - 1:
                        print(f"Scan error for {short_url}, retry {attempt + 1}/{max_retries}: {e}")
                        await asyncio.sleep(2)
                        continue
                    else:
                        print(f"Scan failed for {short_url}: {e}")
                        return None
    
    async def scan_link_concurrent(self, short_url, concurrent_count=CONCURRENT_SCAN_PER_LINK):
        """
        Scan a single link sequentially multiple times.
        """
        task_ids = set()
        for i in range(concurrent_count):
            result = await self.scan_link(short_url)
            if result:
                task_ids.add(result)
        return task_ids
    
    async def scan_cycle(self):
        """
        Perform one complete scan cycle
        
        Returns:
            Set of all task IDs found
        """
        self.task_ids.clear()
        self.scanning = True
        
        try:
            # Get enabled steps
            enabled_steps = []
            if self.step2_enabled:
                enabled_steps.append("step2")
            if self.step3_enabled:
                enabled_steps.append("step3")
            if self.step4_enabled:
                enabled_steps.append("step4")
            
            if not enabled_steps:
                print("No steps enabled, skipping scan")
                return set()
            
            await self.init_browser()
            
            # Generate exactly GENERATED_LINKS total, distributed among enabled steps
            all_links = []
            for i in range(GENERATED_LINKS):
                # Round-robin through enabled steps
                step = enabled_steps[i % len(enabled_steps)]
                short_url = await self.shortener.shorten_url(
                    long_url=self.shortener.generate_random_url(),
                    alias=self.shortener.generate_random_alias(),
                    campaign_type=STEP_CAMPAIGNS[step],
                    browser=self.browser
                )
                if short_url:
                    print(f"✓ Link {i+1}/{GENERATED_LINKS} ({step}): {short_url}")
                    all_links.append(short_url)
                else:
                    print(f"✗ Failed to create link {i+1}/{GENERATED_LINKS} ({step})")
            
            if not all_links:
                print("No links generated, skipping scan")
                return set()
            
            # Scan all links concurrently (10 pages per link)
            scan_tasks = []
            for link in all_links:
                scan_tasks.append(self.scan_link_concurrent(link))
            
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)
            
            # Collect all task IDs
            for result in results:
                if isinstance(result, set):
                    self.task_ids.update(result)
            
            print(f"Found {len(self.task_ids)} unique task IDs")
            
            return self.task_ids
            
        finally:
            self.scanning = False
    
    async def send_telegram_report(self):
        """Send report to Telegram"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if self.task_ids:
            # Shuffle task IDs randomly for variety
            shuffled_ids = list(self.task_ids)
            random.shuffle(shuffled_ids)
            ids_text = "-".join(shuffled_ids)
            count = len(shuffled_ids)
            message = f"<u>{count} Mã</u>: {ids_text}"
        else:
            message = "HẾT MÃ"
        
        if self.telegram_sender.last_message_id:
            try:
                await self.telegram_sender.delete_message(
                    self.telegram_sender.last_message_id
                )
            except Exception as e:
                print(f"Delete old message failed: {e}")
            self.telegram_sender.last_message_id = None

        await self.telegram_sender.send_message(message)
    
    async def run_scan_loop(self):
        """Main scan loop"""
        print("Starting scanner loop...")
        
        while True:
            if self.paused:
                print("Scanner paused, waiting...")
                await asyncio.sleep(5)
                continue
            
            try:
                # Perform scan
                await self.scan_cycle()
                
                # Send report
                await self.send_telegram_report()
                
                # Clear task IDs after sending
                self.task_ids.clear()
                
                # Wait for next scan
                self.next_scan_time = time.time() + self.refresh_interval
                print(f"Next scan in {self.refresh_interval} seconds...")
                
                # Wait with ability to be interrupted by /refresh
                start_wait = time.time()
                while time.time() - start_wait < self.refresh_interval:
                    if self.paused:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                print(f"Error in scan loop: {e}")
                await asyncio.sleep(5)
    
    async def refresh_now(self):
        """Trigger immediate refresh"""
        self.next_scan_time = time.time()
        print("Refresh triggered")
    
    async def pause(self):
        """Pause scanning"""
        self.paused = True
        print("Scanner paused")
    
    async def resume(self):
        """Resume scanning"""
        self.paused = False
        print("Scanner resumed")
    
    async def restart(self):
        """Restart scanner"""
        self.task_ids.clear()
        self.paused = False
        print("Scanner restarted")


class TelegramCommandHandler:
    def __init__(self, bot_token, chat_id, authorized_user_id, scanner):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.authorized_user_id = authorized_user_id
        self.scanner = scanner
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.offset = 0
        self.running = True
    
    async def get_updates(self):
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self.offset,
            "timeout": 30
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=35) as response:
                    result = await response.json()
                    if result.get("ok"):
                        updates = result.get("result", [])
                        if updates:
                            self.offset = updates[-1]["update_id"] + 1
                        return updates
        except Exception as e:
            print(f"Error getting updates: {e}")
        
        return []
    
    async def send_message(self, chat_id, text):
        """Send message to Telegram"""
        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": text
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    result = await response.json()
                    return result.get("ok")
        except Exception as e:
            print(f"Error sending message: {e}")
            return False
    
    def is_authorized(self, user_id):
        """Check if user is authorized"""
        return str(user_id) == self.authorized_user_id
    
    async def handle_command(self, message):
        """Handle incoming command"""
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")
        
        if not self.is_authorized(user_id):
            print(f"Unauthorized command from user {user_id}")
            return
        
        print(f"Command from authorized user {user_id}: {text}")
        
        if text == "/help":
            help_text = """Available Commands:

/help - Show this help message
/status - Show scanner status
/step2 on - Enable Step 2
/step2 off - Disable Step 2
/step3 on - Enable Step 3
/step3 off - Disable Step 3
/step4 on - Enable Step 4
/step4 off - Disable Step 4
/all on - Enable all steps
/all off - Disable all steps
/pause - Pause scanning
/resume - Resume scanning
/refresh - Immediate refresh
/restart - Restart scanner
/time <seconds> - Set refresh interval (30-3600)
/info - Show configuration"""
            await self.send_message(chat_id, help_text)
        
        elif text == "/status":
            next_scan = max(0, int(self.scanner.next_scan_time - time.time())) if self.scanner.next_scan_time else 0
            status_text = f"""🟢 Scanner Running

Step 2 : {'ON' if self.scanner.step2_enabled else 'OFF'}
Step 3 : {'ON' if self.scanner.step3_enabled else 'OFF'}
Step 4 : {'ON' if self.scanner.step4_enabled else 'OFF'}

Refresh Interval : {self.scanner.refresh_interval} seconds
Next Scan : {next_scan} seconds"""
            await self.send_message(chat_id, status_text)
        
        elif text == "/step2 on":
            self.scanner.step2_enabled = True
            await self.send_message(chat_id, "✓ Step 2 enabled")
        
        elif text == "/step2 off":
            self.scanner.step2_enabled = False
            await self.send_message(chat_id, "✓ Step 2 disabled")
        
        elif text == "/step3 on":
            self.scanner.step3_enabled = True
            await self.send_message(chat_id, "✓ Step 3 enabled")
        
        elif text == "/step3 off":
            self.scanner.step3_enabled = False
            await self.send_message(chat_id, "✓ Step 3 disabled")
        
        elif text == "/step4 on":
            self.scanner.step4_enabled = True
            await self.send_message(chat_id, "✓ Step 4 enabled")
        
        elif text == "/step4 off":
            self.scanner.step4_enabled = False
            await self.send_message(chat_id, "✓ Step 4 disabled")
        
        elif text == "/all on":
            self.scanner.step2_enabled = True
            self.scanner.step3_enabled = True
            self.scanner.step4_enabled = True
            await self.send_message(chat_id, "✓ All steps enabled")
        
        elif text == "/all off":
            self.scanner.step2_enabled = False
            self.scanner.step3_enabled = False
            self.scanner.step4_enabled = False
            await self.send_message(chat_id, "✓ All steps disabled")
        
        elif text == "/pause":
            await self.scanner.pause()
            await self.send_message(chat_id, "✓ Scanner paused")
        
        elif text == "/resume":
            await self.scanner.resume()
            await self.send_message(chat_id, "✓ Scanner resumed")
        
        elif text == "/refresh":
            await self.scanner.refresh_now()
            await self.send_message(chat_id, "✓ Refresh triggered")
        
        elif text == "/restart":
            await self.scanner.restart()
            await self.send_message(chat_id, "✓ Scanner restarted")
        
        elif text.startswith("/time "):
            try:
                seconds = int(text.split()[1])
                if 30 <= seconds <= 3600:
                    self.scanner.refresh_interval = seconds
                    await self.send_message(chat_id, f"✓ Refresh interval set to {seconds} seconds")
                else:
                    await self.send_message(chat_id, "✗ Interval must be between 30 and 3600 seconds")
            except:
                await self.send_message(chat_id, "✗ Invalid format. Use: /time <seconds>")
        
        elif text == "/info":
            info_text = f"""Generated Links : {GENERATED_LINKS}
Concurrent Per Link : {CONCURRENT_SCAN_PER_LINK}
Refresh Interval : {self.scanner.refresh_interval}
Browser : Playwright
Mode : Async"""
            await self.send_message(chat_id, info_text)
    
    async def run(self):
        """Run command listener loop"""
        print("Starting Telegram command handler...")
        
        while self.running:
            try:
                updates = await self.get_updates()
                
                for update in updates:
                    message = update.get("message")
                    if message and message.get("text"):
                        await self.handle_command(message)
                
            except Exception as e:
                print(f"Error in command handler: {e}")
                await asyncio.sleep(5)
    
    def stop(self):
        """Stop command handler"""
        self.running = False


async def main():
    # Initialize components
    shortener = OctolinkShortener(OCTOLINK_API_TOKEN)
    telegram_sender = TelegramSender(BOT_TOKEN, CHAT_ID)
    scanner = TaskScanner(shortener, telegram_sender)
    command_handler = TelegramCommandHandler(BOT_TOKEN, CHAT_ID, AUTHORIZED_USER_ID, scanner)
    
    # Initialize browser
    await scanner.init_browser()
    
    # Create Flask app for health check
    app = Flask(__name__)
    
    @app.route('/')
    def health_check():
        return {"status": "ok", "service": "octolink-scanner"}
    
    @app.route('/health')
    def health():
        return {"status": "healthy"}
    
    # Run Flask in background thread
    import threading
    port = int(os.environ.get('PORT', 5000))
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, use_reloader=False)
    )
    flask_thread.daemon = True
    flask_thread.start()
    print(f"Flask server running on port {port}")
    
    # Run scanner and command handler concurrently
    try:
        await asyncio.gather(
            scanner.run_scan_loop(),
            command_handler.run()
        )
    except KeyboardInterrupt:
        print("\nShutting down...")
        command_handler.stop()
        await scanner.close_browser()


if __name__ == "__main__":
    asyncio.run(main())

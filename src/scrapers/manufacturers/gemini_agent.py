"""Gemini Computer Use agent for manufacturer spec scraping."""

import time
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from playwright.sync_api import sync_playwright, Page
from dotenv import load_dotenv

from google import genai
from google.genai import types
from google.genai.types import Content, Part, FinishReason

# Load environment variables (needed for GOOGLE_GENERATIVE_AI_API_KEY)
env_path = Path(__file__).parent.parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Constants
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
MAX_TURNS = 30
MODEL = "gemini-2.5-computer-use-preview-10-2025"
MAX_RECENT_TURN_WITH_SCREENSHOTS = 3  # Keep screenshots only in last 3 turns

# Predefined computer use functions (for screenshot cleanup tracking)
PREDEFINED_COMPUTER_USE_FUNCTIONS = [
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "key_combination",
    "drag_and_drop",
]

# Playwright key mapping (from Google reference implementation)
PLAYWRIGHT_KEY_MAP = {
    "backspace": "Backspace",
    "tab": "Tab",
    "return": "Enter",
    "enter": "Enter",
    "shift": "Shift",
    "control": "ControlOrMeta",  # Cross-platform: Ctrl on Windows/Linux, Cmd on Mac
    "ctrl": "ControlOrMeta",
    "alt": "Alt",
    "escape": "Escape",
    "space": "Space",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "end": "End",
    "home": "Home",
    "left": "ArrowLeft",
    "up": "ArrowUp",
    "right": "ArrowRight",
    "down": "ArrowDown",
    "insert": "Insert",
    "delete": "Delete",
    "meta": "Meta",
    "command": "Meta",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
}

SYSTEM_INSTRUCTION = """You are a helpful assistant that extracts product specifications from web pages.

CRITICAL: ALWAYS GO TO THE MANUFACTURER'S OFFICIAL WEBSITE
- NEVER use retailer sites like Amazon, Argos, John Lewis, Currys, AO, etc.
- ONLY use the manufacturer's official website (e.g., Philips.com, Ninja.com, Tefal.com, Tower.com, Cuisinart.com)
- If search results show retailer links, SKIP THEM and click the manufacturer's official site
- Look for links ending in the brand name (e.g., philips.com, ninjakitchen.co.uk, tefal.co.uk)

CRITICAL SPEED OPTIMIZATION - DO THIS FIRST:
1. As soon as you land on a product page, IMMEDIATELY use key_combination with "Control+f" to open find-in-page
2. Type "spec" or "technical" to jump directly to specifications section
3. Press Enter to navigate to matches
4. This saves 5-10 scroll actions and is MUCH faster
5. ONLY scroll if keyboard search doesn't find anything

Other instructions:
- Use DuckDuckGo for searches (more reliable than Google for automation)
- Accept cookie banners immediately when you see them
- CAPTCHA handling:
  * For "click and hold" or "press and hold" CAPTCHAs: use drag_and_drop with the SAME x,y coordinates for both start and destination (e.g., drag_and_drop(x=500, y=400, destination_x=500, destination_y=400))
  * This will automatically hold for 5 seconds which solves most press-and-hold verifications
  * For checkbox CAPTCHAs: just click normally
  * For image/puzzle CAPTCHAs: skip to a different website (too complex)
  * If CAPTCHA persists after one attempt, move on to a different website
- Once you find specifications on the manufacturer site, extract them immediately
- Return specifications as a clean JSON object with lowercase, underscored keys
"""


def denormalize_x(x: int, screen_width: int) -> int:
    """Convert normalized x coordinate (0-999) to actual pixel coordinate."""
    return int(x / 1000 * screen_width)


def denormalize_y(y: int, screen_height: int) -> int:
    """Convert normalized y coordinate (0-999) to actual pixel coordinate."""
    return int(y / 1000 * screen_height)


def get_model_response_with_retry(client, model: str, contents: List[Content], config, max_retries: int = 5, base_delay_s: int = 1):
    """Get model response with exponential backoff retry logic.

    Args:
        client: Gemini client
        model: Model name
        contents: Conversation history
        config: Generation config
        max_retries: Maximum number of retry attempts
        base_delay_s: Base delay in seconds (doubles each retry)

    Returns:
        Model response

    Raises:
        Exception: If all retries fail
    """
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay_s * (2 ** attempt)
                print(f"  -> API call failed (attempt {attempt + 1}/{max_retries}). Retrying in {delay}s...")
                print(f"     Error: {str(e)[:100]}")
                time.sleep(delay)
            else:
                print(f"  -> API call failed after {max_retries} attempts")
                raise


def cleanup_old_screenshots(contents: List[Content], max_recent_turns: int = MAX_RECENT_TURN_WITH_SCREENSHOTS):
    """Remove screenshot data from old turns to prevent context overflow.

    Only keeps screenshots in the most recent turns. This prevents hitting
    context limits in long scraping sessions while maintaining recent visual context.

    Args:
        contents: Conversation history (modified in place)
        max_recent_turns: Number of recent turns to keep screenshots for
    """
    turn_with_screenshots_found = 0

    # Iterate backwards through conversation history
    for content in reversed(contents):
        if content.role == "user" and content.parts:
            # Check if content has screenshot from computer use functions
            has_screenshot = False
            for part in content.parts:
                if (part.function_response
                    and part.function_response.parts
                    and part.function_response.name in PREDEFINED_COMPUTER_USE_FUNCTIONS):
                    has_screenshot = True
                    break

            if has_screenshot:
                turn_with_screenshots_found += 1
                # Remove screenshot if beyond the limit
                if turn_with_screenshots_found > max_recent_turns:
                    for part in content.parts:
                        if (part.function_response
                            and part.function_response.parts
                            and part.function_response.name in PREDEFINED_COMPUTER_USE_FUNCTIONS):
                            part.function_response.parts = None


def handle_new_page(context, current_page):
    """Handle new page/tab opening by redirecting to current page.

    Computer Use model only supports single tab. Some websites try to open
    new tabs - intercept and navigate current page to new URL instead.

    Args:
        context: Playwright browser context
        current_page: Current page object (modified via closure)
    """
    def _on_page(new_page):
        try:
            new_url = new_page.url
            new_page.close()
            current_page.goto(new_url)
        except Exception as e:
            print(f"  -> Warning: Failed to handle new page: {e}")

    context.on("page", _on_page)


def execute_function_calls(candidate, page: Page, screen_width: int, screen_height: int, debug_dir: Path = None, turn: int = 0) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Execute function calls from Gemini Computer Use model response.

    Args:
        candidate: The model response candidate
        page: Playwright page object
        screen_width: Browser width in pixels
        screen_height: Browser height in pixels

    Returns:
        List of tuples (function_name, result_dict, safety_info_dict)
    """
    results = []
    function_calls = []

    # Extract all function calls from response
    for part in candidate.content.parts:
        if part.function_call:
            function_calls.append(part.function_call)

    # Execute each function call
    for function_call in function_calls:
        action_result = {}
        safety_info = {}

        # Safely extract function name and args
        try:
            fname = function_call.name if hasattr(function_call, 'name') else str(function_call)
            args = function_call.args if hasattr(function_call, 'args') else {}
        except Exception as e:
            print(f"  -> Error parsing function call: {e}")
            results.append(("unknown", {"error": f"Failed to parse function call: {e}"}, {}))
            continue

        # Check for safety decision
        if 'safety_decision' in args:
            safety_decision = args['safety_decision']
            decision = safety_decision.get('decision', '')
            explanation = safety_decision.get('explanation', '')

            print(f"  -> Safety decision: {decision}")
            if explanation:
                print(f"     {explanation}")

            # Save screenshot for debugging
            if debug_dir:
                screenshot_path = debug_dir / f"turn_{turn:02d}_safety_{fname}.png"
                page.screenshot(path=str(screenshot_path))
                print(f"     Screenshot saved: {screenshot_path.name}")

            # Auto-acknowledge for testing (in production, prompt user for confirmation)
            safety_info['safety_acknowledgement'] = True

        print(f"  -> Executing: {fname}")

        try:
            if fname == "open_web_browser":
                # Browser already open
                pass

            elif fname == "search":
                # Navigate to DuckDuckGo (more bot-friendly than Google)
                page.goto("https://duckduckgo.com")

            elif fname == "navigate":
                url = args.get("url", "")
                page.goto(url)

            elif fname == "click_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                page.mouse.click(actual_x, actual_y)

            elif fname == "hover_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                page.mouse.move(actual_x, actual_y)

            elif fname == "type_text_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                text = args["text"]
                press_enter = args.get("press_enter", False)
                clear_before_typing = args.get("clear_before_typing", True)

                page.mouse.click(actual_x, actual_y)

                if clear_before_typing:
                    # Clear field (Command+A, Backspace for Mac)
                    page.keyboard.press("Meta+A")
                    page.keyboard.press("Backspace")

                page.keyboard.type(text)

                if press_enter:
                    page.keyboard.press("Enter")

            elif fname == "key_combination":
                keys_str = args.get("keys", "")
                # Split by + to get individual keys (e.g., "Control+f" -> ["Control", "f"])
                keys = [k.strip() for k in keys_str.split('+')]

                # Normalize keys using the key map
                normalized_keys = [PLAYWRIGHT_KEY_MAP.get(k.lower(), k) for k in keys]

                # Press modifier keys first, then the final key
                for key in normalized_keys[:-1]:
                    page.keyboard.down(key)

                page.keyboard.press(normalized_keys[-1])

                # Release modifier keys in reverse order
                for key in reversed(normalized_keys[:-1]):
                    page.keyboard.up(key)

            elif fname == "scroll_document":
                direction = args.get("direction", "down")
                if direction == "down":
                    page.keyboard.press("PageDown")
                elif direction == "up":
                    page.keyboard.press("PageUp")
                elif direction == "left":
                    page.keyboard.press("ArrowLeft")
                elif direction == "right":
                    page.keyboard.press("ArrowRight")

            elif fname == "scroll_at":
                actual_x = denormalize_x(args["x"], screen_width)
                actual_y = denormalize_y(args["y"], screen_height)
                direction = args.get("direction", "down")
                magnitude = args.get("magnitude", 800)

                # Click to focus on element
                page.mouse.click(actual_x, actual_y)

                # Scroll using wheel
                delta_y = magnitude if direction == "down" else -magnitude if direction == "up" else 0
                delta_x = magnitude if direction == "right" else -magnitude if direction == "left" else 0

                page.mouse.wheel(delta_x, delta_y)

            elif fname == "go_back":
                page.go_back()

            elif fname == "go_forward":
                page.go_forward()

            elif fname == "wait_5_seconds":
                time.sleep(5)

            elif fname == "drag_and_drop":
                start_x = denormalize_x(args["x"], screen_width)
                start_y = denormalize_y(args["y"], screen_height)
                dest_x = denormalize_x(args["destination_x"], screen_width)
                dest_y = denormalize_y(args["destination_y"], screen_height)

                page.mouse.move(start_x, start_y)
                page.mouse.down()

                # If start and destination are the same (or very close), treat as "press and hold"
                # This handles CAPTCHA "click and hold" scenarios
                distance = ((dest_x - start_x) ** 2 + (dest_y - start_y) ** 2) ** 0.5
                if distance < 10:  # Less than 10 pixels = press and hold
                    print(f"  -> Detected press-and-hold (distance: {distance:.1f}px), holding for 5 seconds...")
                    time.sleep(5)  # Hold for 5 seconds for CAPTCHAs
                else:
                    page.mouse.move(dest_x, dest_y)

                page.mouse.up()

            else:
                print(f"Warning: Unimplemented function {fname}")
                action_result = {"error": f"Unimplemented function: {fname}"}

            # Wait for potential navigations/renders (reduced timeout for speed)
            page.wait_for_load_state(timeout=2000)
            time.sleep(0.3)  # Reduced from 1 second

        except Exception as e:
            print(f"Error executing {fname}: {e}")
            action_result = {"error": str(e)}

        results.append((fname, action_result, safety_info))

    return results


def get_function_responses(page: Page, results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> List[types.FunctionResponse]:
    """Capture current page state and create function responses.

    Args:
        page: Playwright page object
        results: List of (function_name, result_dict, safety_info_dict) tuples

    Returns:
        List of FunctionResponse objects to send back to model
    """
    screenshot_bytes = page.screenshot(type="png")
    current_url = page.url

    function_responses = []
    for name, result, safety_info in results:
        response_data = {"url": current_url}
        response_data.update(result)
        response_data.update(safety_info)  # Add safety acknowledgement if present

        function_responses.append(
            types.FunctionResponse(
                name=name,
                response=response_data,
                parts=[
                    types.FunctionResponsePart(
                        inline_data=types.FunctionResponseBlob(
                            mime_type="image/png",
                            data=screenshot_bytes
                        )
                    )
                ]
            )
        )

    return function_responses


def create_scraper_session(headless: bool = True):
    """
    Create a persistent Gemini scraper session (browser + client).
    Use for worker pools to reuse browser across multiple products.

    Returns:
        Tuple of (playwright, browser, page, client)
    """
    # Get API key
    api_key = os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_GENERATIVE_AI_API_KEY not found in environment")

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

    # Setup Playwright with security arguments and anti-detection
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",  # Hide automation
            "--disable-extensions",
            "--disable-file-system",
            "--disable-plugins",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            # No '--no-sandbox' - sandbox is ON for security
        ]
    )
    # Add stealth context to avoid CAPTCHA detection
    context = browser.new_context(
        viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="en-GB",
        timezone_id="Europe/London",
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
    )
    page = context.new_page()

    # Override navigator.webdriver to hide automation
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # Setup new page interception (handle sites that open new tabs)
    handle_new_page(context, page)

    # Navigate to DuckDuckGo (more bot-friendly than Google)
    page.goto("https://duckduckgo.com")

    return playwright, browser, page, client


def scrape_with_session(page, client, product_name: str, debug_dir: Path = None) -> Dict[str, Any]:
    """
    Scrape product specs using existing session (browser already open).
    For use in worker pools.

    Args:
        page: Playwright page object
        client: Gemini client
        product_name: Product to scrape
        debug_dir: Optional debug screenshot directory

    Returns:
        Dict with specs, source_url, status, error
    """
    result = {
        "product": product_name,
        "specs": {},
        "source_url": "",
        "status": "failed",
        "error": None
    }

    try:
        # Reset page to clean state (in case previous product left page in bad state like CAPTCHA)
        try:
            page.goto("https://duckduckgo.com", wait_until="domcontentloaded", timeout=10000)
        except Exception as e:
            # If even DuckDuckGo fails, try to create a new page
            print(f"  Warning: Could not reset to DuckDuckGo: {e}")

        # Configure the model with Computer Use tool
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_BROWSER
            ))],
        )

        # Initial screenshot
        initial_screenshot = page.screenshot(type="png")

        # Create initial prompt
        USER_PROMPT = f"""Search DuckDuckGo for '{product_name} specifications' and navigate to the MANUFACTURER'S OFFICIAL WEBSITE.

CRITICAL: You MUST go to the manufacturer's official website (NOT Amazon, Argos, Currys, AO, etc.)
- From search results, click ONLY the manufacturer's official site
- Look for URLs like philips.com, ninjakitchen.co.uk, tefal.co.uk, cuisinart.com, tower.com, etc.
- Skip all retailer links

Once on the manufacturer's site, find the product page and extract all specifications.

Return the specifications as a JSON object with key-value pairs where keys are spec names (lowercase, underscored)
and values are the spec values with units.

Example format:
{{
  "capacity": "11L",
  "power": "1500W",
  "dimensions": "30 x 40 x 35 cm"
}}

If no specifications are found on this page, return an empty object {{}}.
"""

        # Initialize conversation history
        contents = [
            Content(role="user", parts=[
                Part(text=USER_PROMPT),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        # Agent loop
        for turn in range(1, MAX_TURNS + 1):
            try:
                # Generate response from model with retry logic
                response = get_model_response_with_retry(
                    client=client,
                    model=MODEL,
                    contents=contents,
                    config=config,
                )

                if not response or not response.candidates or len(response.candidates) == 0:
                    result["error"] = "Empty response from model"
                    break

                candidate = response.candidates[0]

                if not candidate or not candidate.content:
                    result["error"] = "Invalid candidate in response"
                    break

                contents.append(candidate.content)

                # Check if model returned function calls or final answer
                has_function_calls = any(part.function_call for part in candidate.content.parts if part and hasattr(part, 'function_call'))
                has_reasoning = any(part.text for part in candidate.content.parts if part and hasattr(part, 'text'))

                # Handle malformed function calls - retry the request
                if (not has_function_calls
                    and not has_reasoning
                    and hasattr(candidate, 'finish_reason')
                    and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL):
                    print(f"  -> Malformed function call detected, retrying...")
                    continue

            except Exception as e:
                result["error"] = f"Error in turn {turn}: {str(e)}"
                break

            if not has_function_calls:
                # Model has finished - extract text response
                text_response = " ".join([part.text for part in candidate.content.parts if part.text])

                # Try to parse specs from response
                import json
                import re

                try:
                    # Find JSON object with regex
                    json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response, re.DOTALL)

                    specs = {}
                    for json_str in json_matches:
                        try:
                            potential_specs = json.loads(json_str)
                            if isinstance(potential_specs, dict) and potential_specs:
                                if len(potential_specs) > len(specs):
                                    specs = potential_specs
                        except json.JSONDecodeError:
                            continue

                    if specs:
                        result["specs"] = specs
                        result["source_url"] = page.url
                        result["status"] = "success"
                    else:
                        result["error"] = "No valid JSON specifications found in response"

                except Exception as e:
                    result["error"] = f"Failed to extract specs: {e}"

                break

            # Execute function calls
            execution_results = execute_function_calls(candidate, page, SCREEN_WIDTH, SCREEN_HEIGHT, debug_dir, turn)

            # Capture new state
            function_responses = get_function_responses(page, execution_results)

            # Add function responses to conversation
            contents.append(
                Content(role="user", parts=[Part(function_response=fr) for fr in function_responses])
            )

            # Clean up old screenshots to prevent context overflow
            cleanup_old_screenshots(contents)

        # If we reached max turns without getting specs
        if result["status"] == "failed" and not result["error"]:
            result["error"] = f"Max turns ({MAX_TURNS}) reached without finding specifications"

    except Exception as e:
        result["error"] = str(e)

    return result


def scrape_with_urls(page, client, product_name: str, urls: List[str], debug_dir: Path = None) -> Dict[str, Any]:
    """
    Scrape product specs starting from pre-fetched URLs (with fallback).

    This is more efficient than scrape_with_session() because it:
    1. Skips DuckDuckGo search (saves 5-6 turns)
    2. Starts directly on manufacturer page
    3. Tries multiple URLs if first fails (CAPTCHA/no specs)

    Args:
        page: Playwright page object
        client: Gemini client
        product_name: Product to scrape
        urls: List of URLs to try (prioritized: manufacturer first, then fallbacks)
        debug_dir: Optional debug screenshot directory

    Returns:
        Dict with specs, source_url, status, error

    Example:
        >>> urls = ["https://ninja.com/product", "https://lakeland.co.uk/...", ...]
        >>> result = scrape_with_urls(page, client, "Ninja AF101", urls)
        >>> result['status']
        'success'
    """
    result = {
        "product": product_name,
        "specs": {},
        "source_url": "",
        "status": "failed",
        "error": None
    }

    if not urls:
        result["error"] = "No URLs provided"
        return result

    print(f"  Trying {len(urls)} URLs for {product_name}...")

    # Try each URL until we get specs
    for i, url in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] Attempting: {url[:60]}...")

        try:
            # Navigate directly to URL
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)  # Let page settle

            # Configure the model with Computer Use tool
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER
                ))],
            )

            # Initial screenshot
            initial_screenshot = page.screenshot(type="png")

            # Create initial prompt (different from search-based prompt)
            USER_PROMPT = f"""You are already on a product page for '{product_name}'.

TASK: Extract ALL product specifications from this page.

Use Ctrl+F to search for "spec", "technical", or "features" to find the specifications section quickly.

Return the specifications as a JSON object with key-value pairs where keys are spec names (lowercase, underscored)
and values are the spec values with units.

Example format:
{{
  "capacity": "11L",
  "power": "1500W",
  "dimensions": "30 x 40 x 35 cm"
}}

If no specifications are found on this page, return an empty object {{}}.
"""

            # Initialize conversation history
            contents = [
                Content(role="user", parts=[
                    Part(text=USER_PROMPT),
                    Part.from_bytes(data=initial_screenshot, mime_type='image/png')
                ])
            ]

            # Agent loop (reduced max turns since no search needed)
            max_turns_per_url = 20  # Reduced from 30 since we skip search

            for turn in range(1, max_turns_per_url + 1):
                try:
                    # Generate response from model with retry logic
                    response = get_model_response_with_retry(
                        client=client,
                        model=MODEL,
                        contents=contents,
                        config=config,
                    )

                    if not response or not response.candidates or len(response.candidates) == 0:
                        break

                    candidate = response.candidates[0]

                    if not candidate or not candidate.content:
                        break

                    contents.append(candidate.content)

                    # Check if model returned function calls or final answer
                    has_function_calls = any(part.function_call for part in candidate.content.parts if part and hasattr(part, 'function_call'))
                    has_reasoning = any(part.text for part in candidate.content.parts if part and hasattr(part, 'text'))

                    # Handle malformed function calls - retry the request
                    if (not has_function_calls
                        and not has_reasoning
                        and hasattr(candidate, 'finish_reason')
                        and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL):
                        continue

                except Exception as e:
                    print(f"  [{i}/{len(urls)}] Error in turn {turn}: {e}")
                    break

                if not has_function_calls:
                    # Model has finished - extract text response
                    text_response = " ".join([part.text for part in candidate.content.parts if part.text])

                    # Try to parse specs from response
                    import json
                    import re

                    try:
                        # Find JSON object with regex
                        json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response, re.DOTALL)

                        specs = {}
                        for json_str in json_matches:
                            try:
                                potential_specs = json.loads(json_str)
                                if isinstance(potential_specs, dict) and potential_specs:
                                    if len(potential_specs) > len(specs):
                                        specs = potential_specs
                            except json.JSONDecodeError:
                                continue

                        if specs:
                            result["specs"] = specs
                            result["source_url"] = page.url
                            result["status"] = "success"
                            print(f"  [{i}/{len(urls)}] SUCCESS! Found {len(specs)} specs ✓")
                            return result  # Success - return immediately
                        else:
                            print(f"  [{i}/{len(urls)}] No specs found, trying next URL...")
                            break  # Try next URL

                    except Exception as e:
                        print(f"  [{i}/{len(urls)}] Failed to extract specs: {e}")
                        break  # Try next URL

                # Execute function calls
                execution_results = execute_function_calls(candidate, page, SCREEN_WIDTH, SCREEN_HEIGHT, debug_dir, turn)

                # Capture new state
                function_responses = get_function_responses(page, execution_results)

                # Add function responses to conversation
                contents.append(
                    Content(role="user", parts=[Part(function_response=fr) for fr in function_responses])
                )

                # Clean up old screenshots to prevent context overflow
                cleanup_old_screenshots(contents)

            # If we reached here, this URL didn't yield specs - try next
            print(f"  [{i}/{len(urls)}] Max turns reached without specs, trying next URL...")

        except Exception as e:
            print(f"  [{i}/{len(urls)}] Failed: {e}, trying next URL...")
            continue

    # If we tried all URLs and none worked
    result["error"] = f"Tried {len(urls)} URLs, none yielded specifications"
    return result


def scrape_product_specs(product_name: str, headless: bool = False, save_debug_screenshots: bool = True) -> Dict[str, Any]:
    """Scrape product specifications using Gemini Computer Use.

    Args:
        product_name: Name of the product to search for (e.g., "Tower T17190 Vortx 11L")
        headless: Whether to run browser in headless mode

    Returns:
        Dictionary with keys:
            - product: Product name
            - specs: Dict of specifications (or empty dict if failed)
            - source_url: URL where specs were found
            - status: "success" or "failed"
            - error: Error message (if failed)
    """
    print(f"\nProcessing: {product_name}")

    # Initialize result structure
    result = {
        "product": product_name,
        "specs": {},
        "source_url": "",
        "status": "failed",
        "error": None
    }

    # Get API key from environment
    api_key = os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
    if not api_key:
        result["error"] = "GOOGLE_GENERATIVE_AI_API_KEY not found in environment"
        print(f"  ✗ Failed: {result['error']}")
        return result

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

    # Setup debug directory if needed
    debug_dir = None
    if save_debug_screenshots:
        # Create debug directory for this product
        safe_product_name = "".join(c if c.isalnum() or c in (' ', '-') else '_' for c in product_name)
        safe_product_name = safe_product_name.replace(' ', '_')[:50]  # Limit length
        debug_dir = Path(os.getcwd()) / "output" / "gemini_debug" / safe_product_name
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug screenshots: {debug_dir}")

    # Setup Playwright with security arguments and anti-detection
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",  # Hide automation
            "--disable-extensions",
            "--disable-file-system",
            "--disable-plugins",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            # No '--no-sandbox' - sandbox is ON for security
        ]
    )
    # Add stealth context to avoid CAPTCHA detection
    context = browser.new_context(
        viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="en-GB",
        timezone_id="Europe/London",
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
    )
    page = context.new_page()

    # Override navigator.webdriver to hide automation
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # Setup new page interception (handle sites that open new tabs)
    handle_new_page(context, page)

    try:
        # Navigate to Google
        page.goto("https://www.google.com")

        # Configure the model with Computer Use tool
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(computer_use=types.ComputerUse(
                environment=types.Environment.ENVIRONMENT_BROWSER
            ))],
        )

        # Initial screenshot
        initial_screenshot = page.screenshot(type="png")

        # Create initial prompt
        USER_PROMPT = f"""Search DuckDuckGo for '{product_name} specifications' and navigate to the MANUFACTURER'S OFFICIAL WEBSITE.

CRITICAL: You MUST go to the manufacturer's official website (NOT Amazon, Argos, Currys, AO, etc.)
- From search results, click ONLY the manufacturer's official site
- Look for URLs like philips.com, ninjakitchen.co.uk, tefal.co.uk, cuisinart.com, tower.com, etc.
- Skip all retailer links

Once on the manufacturer's site, find the product page and extract all specifications.

Return the specifications as a JSON object with key-value pairs where keys are spec names (lowercase, underscored)
and values are the spec values with units.

Example format:
{{
  "capacity": "11L",
  "power": "1500W",
  "dimensions": "30 x 40 x 35 cm"
}}

If no specifications are found on this page, return an empty object {{}}.
"""

        # Initialize conversation history
        contents = [
            Content(role="user", parts=[
                Part(text=USER_PROMPT),
                Part.from_bytes(data=initial_screenshot, mime_type='image/png')
            ])
        ]

        # Agent loop
        for turn in range(1, MAX_TURNS + 1):
            print(f"  Turn {turn}/{MAX_TURNS}")

            try:
                # Generate response from model with retry logic
                response = get_model_response_with_retry(
                    client=client,
                    model=MODEL,
                    contents=contents,
                    config=config,
                )

                if not response or not response.candidates or len(response.candidates) == 0:
                    result["error"] = "Empty response from model"
                    print(f"  ✗ Empty response from model")
                    break

                candidate = response.candidates[0]

                if not candidate or not candidate.content:
                    result["error"] = "Invalid candidate in response"
                    print(f"  ✗ Invalid candidate in response")
                    break

                contents.append(candidate.content)

                # Check if model returned function calls or final answer
                has_function_calls = any(part.function_call for part in candidate.content.parts if part and hasattr(part, 'function_call'))
                has_reasoning = any(part.text for part in candidate.content.parts if part and hasattr(part, 'text'))

                # Handle malformed function calls - retry the request
                if (not has_function_calls
                    and not has_reasoning
                    and hasattr(candidate, 'finish_reason')
                    and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL):
                    print(f"  -> Malformed function call detected, retrying...")
                    continue

            except Exception as e:
                result["error"] = f"Error in turn {turn}: {str(e)}"
                print(f"  ✗ Error in turn {turn}: {e}")
                import traceback
                traceback.print_exc()
                break

            if not has_function_calls:
                # Model has finished - extract text response
                text_response = " ".join([part.text for part in candidate.content.parts if part.text])
                print(f"  Model response: {text_response[:100]}...")

                # Try to parse specs from response
                import json
                import re

                try:
                    # First, try to find JSON object with regex for better extraction
                    # Look for {...} pattern
                    json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response, re.DOTALL)

                    specs = {}
                    for json_str in json_matches:
                        try:
                            potential_specs = json.loads(json_str)
                            # Check if this looks like specs (dict with string keys and values)
                            if isinstance(potential_specs, dict) and potential_specs:
                                # Prefer larger spec dicts
                                if len(potential_specs) > len(specs):
                                    specs = potential_specs
                        except json.JSONDecodeError:
                            continue

                    if specs:
                        result["specs"] = specs
                        result["source_url"] = page.url
                        result["status"] = "success"
                        print(f"  ✓ Extracted {len(specs)} specifications")
                    else:
                        result["error"] = "No valid JSON specifications found in response"
                        print(f"  ✗ No valid JSON specifications found in response")

                except Exception as e:
                    result["error"] = f"Failed to extract specs: {e}"
                    print(f"  ✗ Failed to extract specs: {e}")

                break

            # Execute function calls
            print(f"  Executing actions...")
            execution_results = execute_function_calls(candidate, page, SCREEN_WIDTH, SCREEN_HEIGHT, debug_dir, turn)

            # Capture new state
            function_responses = get_function_responses(page, execution_results)

            # Save screenshot for first 5 turns (debugging navigation)
            if debug_dir and turn <= 5:
                screenshot_path = debug_dir / f"turn_{turn:02d}_after_actions.png"
                page.screenshot(path=str(screenshot_path))

            # Add function responses to conversation
            contents.append(
                Content(role="user", parts=[Part(function_response=fr) for fr in function_responses])
            )

            # Clean up old screenshots to prevent context overflow
            cleanup_old_screenshots(contents)

        # If we reached max turns without getting specs
        if result["status"] == "failed" and not result["error"]:
            result["error"] = f"Max turns ({MAX_TURNS}) reached without finding specifications"
            print(f"  ✗ {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  ✗ Error: {e}")

        # Save error screenshot
        if debug_dir:
            try:
                screenshot_path = debug_dir / "error_screenshot.png"
                page.screenshot(path=str(screenshot_path))
                print(f"  Error screenshot saved: {screenshot_path}")
            except:
                pass

    finally:
        # Cleanup
        browser.close()
        playwright.stop()

    return result

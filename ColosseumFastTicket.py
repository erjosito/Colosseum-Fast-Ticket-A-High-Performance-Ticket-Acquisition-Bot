import time
import random
import logging
from datetime import datetime, timedelta
import sys
import pytz
import re
import math

# --- Use undetected_chromedriver if available ---
try:
    import undetected_chromedriver as uc
    USE_UNDETECTED = True
    logging.info("undetected-chromedriver library found.")
except ImportError:
    logging.warning("undetected-chromedriver library not found. Falling back to standard Selenium.")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    USE_UNDETECTED = False

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    InvalidSelectorException,
    WebDriverException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException # Added for handling
)

# --- High Precision Timing & Reload ---

def js_reload(driver):
    """Reload the page using JavaScript for speed and reliability."""
    try:
        driver.execute_script("window.location.reload(true);") # Force cache bypass
        return True
    except Exception as e:
        logging.error(f"JavaScript reload failed: {e}")
        return False

def precise_wait_until(target_datetime):
    """Wait until the target datetime using high-precision timing."""
    # Get the timezone from the target datetime
    target_tz = target_datetime.tzinfo
    if target_tz is None:
        # Fallback or error if target_datetime is unexpectedly naive
        # This shouldn't happen based on current script logic, but good practice
        logging.error("precise_wait_until called with a naive datetime!")
        # Option 1: Assume local time (less accurate)
        # target_tz = datetime.now().astimezone().tzinfo
        # Option 2: Raise an error or return early
        return # Or raise TypeError("Target datetime must be timezone-aware")

    while True:
        # Get the current time *in the target's timezone*
        now_aware = datetime.now(target_tz)

        wait_seconds = (target_datetime - now_aware).total_seconds()
        if wait_seconds <= 0:
            break
        # Sleep granularity depends on OS, but aim for small sleeps
        sleep_duration = max(0.001, min(0.01, wait_seconds / 2.0)) # Adaptive sleep
        time.sleep(sleep_duration)


# --- Sound Notification Handling ---
# (Keep your existing sound code here if needed)
# ...

# --- Set up logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(filename)s:%(lineno)d - %(message)s', # Added milliseconds
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("ticket_bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.Formatter.converter = time.gmtime # Use UTC in logs for consistency

# Configuration 
# !!! UPDATE URL IF NEEDED !!!
BASE_URL = "https://ticketing.colosseo.it/en/eventi/full-experience-sotterranei-e-arena-percorso-didattico"

# !!! SET YOUR TARGET DATE !!!
TARGET_DATE = "2025-05-24"  # Format: YYYY-MM-DD
ACTIVATION_TIME = "09:02:00"  # Example: 9:00:00 AM Rome time (Ensure this is ROME TIME)
ROME_TIMEZONE = "Europe/Rome"

# !!! SET REQUIRED TICKETS !!!
FULL_PRICE_TICKETS = 1
REDUCED_PRICE_TICKETS = 1

# !!! SET PREFERRED TOUR LANGUAGE !!!
PREFERRED_LANGUAGE = "ENGLISH"  # Options: "ENGLISH", "ITALIAN", "SPANISH", "FRENCH"

# Timing Configuration (CRITICAL FOR SPEED) ---
# How many seconds BEFORE Activation Time to START the micro-refresh loop
# Adjust based on observation: If slots appear slightly early, increase this.
# If they appear exactly on time or slightly late, keep it low.
MICRO_REFRESH_LEAD_TIME_SECONDS = 0.8

# Duration of the micro-refresh window around activation time
# Aim for a tight window covering the likely drop moment.
MICRO_REFRESH_DURATION_BEFORE = 0.5 # Seconds BEFORE activation time
MICRO_REFRESH_DURATION_AFTER = 0.7  # Seconds AFTER activation time
# Interval between JS reloads during the micro-refresh window (VERY LOW)
MICRO_REFRESH_INTERVAL = 0.075 # Try 75ms, adjust 0.05 <-> 0.1

# Max time to wait for the main content container after a successful micro-refresh (Short)
POST_REFRESH_CONTAINER_TIMEOUT = 1.5 # seconds

# Interval between checks WITHIN the fast loop if tickets not found yet (VERY LOW)
FAST_CHECK_INTERVAL = 0.05  # Check every 50ms, adjust 0.03 <-> 0.1

# Delays WITHIN successful steps (MINIMIZE THESE)
# TEST THESE LOW VALUES - INCREASE SLIGHTLY IF SCRIPT BREAKS
DELAY_AFTER_SLOT_CLICK = 0.05  # Minimal pause for ticket options to render
DELAY_BETWEEN_QTY_SET = 0.02   # Minimal pause between Full/Reduced
DELAY_BETWEEN_PLUS_CLICKS = 0.03 # Minimal pause between clicks
DELAY_AFTER_QTY_SET = 0.05   # Minimal pause for Continue button state
DELAY_AFTER_CONTINUE = 1.5   # Needs to be slightly longer for potential page transition/API call

# Max attempts within the FAST CHECK loop (Defines the fast check window duration)
# Duration = MAX_FAST_CHECK_ATTEMPTS * FAST_CHECK_INTERVAL (approx)
# e.g., 400 attempts * 0.05s = 20 seconds of fast checking
MAX_FAST_CHECK_ATTEMPTS = 400

# Timeout for waits *within* the fast loop (after container found) - keep short
FAST_LOOP_WAIT_TIMEOUT = 0.75 # seconds


# Multilingual Text Mappings

TEXT_MAPPINGS = {
    "english": {"full_price": "Full price", "reduced_fare": "Reduced fare", "continue": "CONTINUE", "activity_in": "ACTIVITY IN"},
    "italian": {"full_price": "Prezzo intero", "reduced_fare": "Tariffa ridotta", "continue": "CONTINUA", "activity_in": "ATTIVITÀ IN"},
    # Add spanish/french if needed
}
LANGUAGE_MAPPINGS = {
    "english": {"ENGLISH": "ENGLISH", "ITALIAN": "ITALIAN", "SPANISH": "SPANISH", "FRENCH": "FRENCH"},
    "italian": {"ENGLISH": "INGLESE", "ITALIAN": "ITALIANO", "SPANISH": "SPAGNOLO", "FRENCH": "FRANCESE"},
     # Add spanish/french if needed
}

# CSS / XPATH Selectors (VERIFY THESE AGAINST LIVE SITE!)

# Choose the container that appears *first* and most reliably holds the slots/tickets
PRIMARY_CONTAINER_SELECTOR = "div.abc-slotpicker-group" # Likely holds the time slots
# PRIMARY_CONTAINER_SELECTOR = "div.abc-tariffpicker" # If ticket types appear before/without slots

# --- Time Slot Selectors ---
TIME_SLOT_CONTAINER_SELECTOR = "div.abc-slotpicker-group"
# Example: Direct XPath targeting label under specific header and with specific time
# DIRECT_SLOT_XPATH_TEMPLATE = "//h3[contains(@class, 'lang_section')][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{lang_text}')]/following-sibling::label[not(contains(@class, 'unselectable'))][descendant::input[@type='radio' and not(@disabled)]][.//span[normalize-space(text())='{time_text}']]"
AVAILABLE_SLOT_LABEL_XPATH = ".//label[not(contains(@class, 'unselectable'))][descendant::input[@type='radio' and @name='slot' and not(@disabled)]]"
SLOT_TIME_TEXT_XPATH = ".//div/span" # Relative to the label

# --- Ticket Quantity Selectors ---
TICKET_TYPE_CONTAINER_SELECTOR = "div.abc-tariffpicker"
TICKET_PLUS_BTN_SELECTOR = "button.plus, button > span.fa-plus" # Check if this is unique enough
# Find the row containing the ticket type text first:
TICKET_ROW_XPATH_TEMPLATE = ".//div[contains(@class, 'tariff-option')][.//span[contains(@class, 'title')][translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = '{}']]"

# --- Continue Button ---
CONTINUE_BUTTON_SELECTOR = "a#buy-button" # Check if ID is reliable


#ColosseumTicketBot Class

class ColosseumTicketBot:
    def __init__(self):
        self.driver = None
        self.attempt_count = 0
        self.site_language = "english" # Default assumption
        self.rome_tz = pytz.timezone(ROME_TIMEZONE)
        self.target_date_dt = datetime.strptime(TARGET_DATE, "%Y-%m-%d").date()
        self.activation_dt_rome = self._calculate_activation_dt()
        self.desired_slot_time_str = self.activation_dt_rome.strftime("%#I:%M %p" if sys.platform != 'win32' else "%#I:%M %p").strip() # Format like "9:00 AM" - adjust format code if needed
        logging.info(f"Target Rome Activation: {self.activation_dt_rome.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} Rome Time")
        logging.info(f"Desired Slot Text (Exact Match Target): '{self.desired_slot_time_str}'")
        logging.info("ColosseumTicketBot initialized.")

    def _calculate_activation_dt(self):
        """Calculates the target activation datetime in Rome time."""
        try:
            # Combine target date with activation time string
            activation_naive = datetime.strptime(f"{TARGET_DATE} {ACTIVATION_TIME}", "%Y-%m-%d %H:%M:%S")
            # Localize to Rome timezone
            return self.rome_tz.localize(activation_naive)
        except ValueError as e:
            logging.critical(f"Error parsing TARGET_DATE ('{TARGET_DATE}') or ACTIVATION_TIME ('{ACTIVATION_TIME}'): {e}")
            raise

    def setup_driver(self):
        """Sets up the WebDriver (UC or Standard Selenium)."""
        logging.info(f"Setting up {'undetected' if USE_UNDETECTED else 'standard'} chromedriver...")
        try:
            if USE_UNDETECTED:
                options = uc.ChromeOptions()
                # options.add_argument("--headless") # Headless might be detected more easily, run headed on VPS
                options.add_argument("--start-maximized")
                options.add_argument("--lang=en-US")
                # Minimal set of args known to work well with UC
                options.add_argument('--disable-gpu')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                # Suppress logs
                options.add_argument('--disable-logging')
                options.add_argument('--log-level=3')
                options.add_experimental_option("prefs", {"intl.accept_languages": "en,en_US"})
                self.driver = uc.Chrome(options=options, use_subprocess=True, version_main=119) # Specify version if needed
            else:
                # Standard Selenium setup (less likely to bypass detection)
                chrome_options = Options()
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--lang=en-US")
                chrome_options.add_experimental_option("prefs", {"intl.accept_languages": "en,en_US"})
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_argument('--log-level=3')
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            logging.info("WebDriver initialized successfully.")
            self.driver.set_page_load_timeout(15) # Timeout for initial page loads
            # Consider setting implicit wait low globally, but explicit waits are generally better
            # self.driver.implicitly_wait(0.5)
        except WebDriverException as e:
            logging.error(f"WebDriver setup failed: {e}", exc_info=True)
            if "permission denied" in str(e).lower():
                logging.error(">>> Permission denied error often means the chromedriver executable needs permissions (chmod +x) or Chrome browser itself isn't installed/found correctly on the VPS.")
            raise
        except Exception as e:
            logging.error(f"Unexpected error setting up WebDriver: {e}", exc_info=True)
            raise

    def quick_check_element(self, by, value, timeout=0.1):
        """Very fast check for element presence, minimal wait."""
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=0.05).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except TimeoutException:
            return False
        except Exception: # Catch broader errors during quick check
            return False

    def wait_and_click(self, element_or_locator, timeout=FAST_LOOP_WAIT_TIMEOUT):
        """Waits for element to be clickable and clicks using JS."""
        el_desc = str(element_or_locator)[:100]
        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=0.05) # Faster polling
            element = None
            if isinstance(element_or_locator, tuple):
                 # Wait primarily for presence, clickability check can be slow
                 element = wait.until(EC.presence_of_element_located(element_or_locator))
            elif hasattr(element_or_locator, 'is_displayed'):
                element = element_or_locator # Assume it's already a found element

            if not element:
                 logging.warning(f"Could not resolve element for clicking: {el_desc}")
                 return False

            # Attempt JS click directly - often faster/more reliable
            self.driver.execute_script("arguments[0].click();", element)
            return True

        except StaleElementReferenceException:
            logging.warning(f"Stale element encountered when trying to click {el_desc}. Retrying find/click might be needed.")
            return False # Signal failure to allow retry logic in the caller
        except TimeoutException:
            # Logging this can be noisy, only log if debugging is needed
            # logging.debug(f"Timeout waiting for element clickability: {el_desc} (timeout={timeout}s)")
            return False
        except (ElementNotInteractableException, ElementClickInterceptedException) as e:
             # JS click might still work even if Selenium deems it not interactable
             logging.warning(f"{type(e).__name__} for {el_desc}, JS click was attempted.")
             # We assume the JS click attempt in the 'try' block might have succeeded or failed silently
             # Returning True here is optimistic, False might be safer depending on how critical the click is
             return True # Optimistic, adjust if needed
        except Exception as e:
            logging.error(f"Error in wait_and_click ({el_desc}): {e}")
            return False

    def detect_site_language(self):
        """Detects site language. Call this *after* elements are loaded."""
        # This is less critical for speed, keep simple
        try:
            # Check for a known element text
            continue_button_text = ""
            try:
                # Use a short timeout, don't wait long if button isn't there
                continue_button = WebDriverWait(self.driver, 0.5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, CONTINUE_BUTTON_SELECTOR))
                )
                continue_button_text = continue_button.text.strip().upper()
            except TimeoutException:
                 logging.warning("Continue button not found quickly for language detection.")
                 # Fallback: check body text if button fails
                 body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                 if any(word in body_text for word in ["continua", "intero", "ridotta", "attività"]):
                      if self.site_language != "italian":
                           logging.info("Detected Italian language (via body text)")
                           self.site_language = "italian"
                      return "italian"

            if "CONTINUA" in continue_button_text:
                if self.site_language != "italian":
                    logging.info("Detected Italian language (via Continue button)")
                    self.site_language = "italian"
                return "italian"
            else: # Default to English otherwise
                 if self.site_language != "english":
                    logging.info("Detected English language (default/fallback)")
                    self.site_language = "english"
                 return "english"

        except Exception as e:
            logging.warning(f"Error detecting site language: {e}. Using current: {self.site_language}.")
            return self.site_language

    def handle_initial_load(self, url):
        """Loads page, handles manual CAPTCHA step."""
        logging.info(f"Loading URL: {url}")
        try:
            self.driver.get(url)
        except Exception as e:
            logging.error(f"Error loading URL {url}: {e}")
            return False

        print("-" * 60)
        logging.info(">>> ACTION REQUIRED: Check browser NOW!")
        logging.info(">>> 1. Solve any CAPTCHA / Cloudflare checks IMMEDIATELY.")
        logging.info(">>> 2. Wait for main ticket selection elements to appear.")
        input(">>> 3. Once page seems ready, press Enter here FAST...")
        print("-" * 60)
        logging.info("Resuming automation...")

        # Quick check if the primary container is visible after manual step
        time.sleep(0.1) # Tiny pause for safety
        if self.quick_check_element(By.CSS_SELECTOR, PRIMARY_CONTAINER_SELECTOR, timeout=1.0):
             logging.info("Primary container found quickly after manual step.")
             self.detect_site_language() # Detect language now
             return True
        else:
             logging.warning("Primary container not immediately found after manual interaction. Micro-refresh will handle it.")
             # Proceed anyway, the timed refresh is the main trigger
             return True

    def select_time_slot(self):
        """Finds and clicks the target time slot using JS."""
        try:
            # Locate the container first (use short timeout)
            slot_container = WebDriverWait(self.driver, FAST_LOOP_WAIT_TIMEOUT, 0.05).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, TIME_SLOT_CONTAINER_SELECTOR))
            )

            # --- Option 1: Direct XPath (Potentially Faster - TEST CAREFULLY) ---
            # lang_text_lower = LANGUAGE_MAPPINGS[self.site_language][PREFERRED_LANGUAGE].lower()
            # time_text_target = self.desired_slot_time_str # e.g., "9:00 AM"
            # direct_xpath = DIRECT_SLOT_XPATH_TEMPLATE.format(lang_text=lang_text_lower, time_text=time_text_target)
            # logging.debug(f"Attempting direct slot selection with XPath: {direct_xpath}")
            # try:
            #     # Find the specific label directly
            #     target_label = WebDriverWait(self.driver, 0.1, 0.05).until( # Very short wait
            #         EC.presence_of_element_located((By.XPATH, direct_xpath))
            #     )
            #     logging.info(f"Found target slot '{time_text_target}' via direct XPath.")
            #     if self.wait_and_click(target_label, timeout=0.2): # Quick click attempt
            #         time.sleep(DELAY_AFTER_SLOT_CLICK)
            #         return True
            #     else:
            #         logging.warning("Direct XPath found label, but click failed.")
            #         return False # Or fallback to iterating?
            # except TimeoutException:
            #     logging.debug(f"Direct XPath target slot '{time_text_target}' not found quickly.")
            #     # Fall through to iteration method below if direct fails

            # --- Option 2: Iteration (More Robust if Direct Fails or Structure Varies) ---
            activity_text_lower = TEXT_MAPPINGS[self.site_language]["activity_in"].lower()
            tour_language_display_lower = LANGUAGE_MAPPINGS[self.site_language][PREFERRED_LANGUAGE].lower()
            xpath_lower_contains = "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{}')"

            # Find the correct language header (quickly)
            language_header_xpath = f".//h3[contains(@class, 'lang_section')][{xpath_lower_contains.format(activity_text_lower)}][{xpath_lower_contains.format(tour_language_display_lower)}]"
            try:
                lang_header = WebDriverWait(slot_container, 0.2, 0.05).until(
                    EC.presence_of_element_located((By.XPATH, language_header_xpath))
                )
                 # Find available slots *after* this specific header
                available_slot_labels_xpath = f"{language_header_xpath}/following-sibling::label[not(contains(@class, 'unselectable'))][descendant::input[@type='radio' and not(@disabled)]]"
                available_slot_labels = slot_container.find_elements(By.XPATH, available_slot_labels_xpath)

                # Filter out slots belonging to the *next* language section if present
                try:
                    next_header_xpath = f"{language_header_xpath}/following-sibling::h3[contains(@class, 'lang_section')]"
                    next_header = slot_container.find_element(By.XPATH, next_header_xpath)
                    next_y = next_header.location['y']
                    filtered_labels = [label for label in available_slot_labels if label.location['y'] < next_y]
                except NoSuchElementException:
                    filtered_labels = available_slot_labels # No next header found

            except TimeoutException:
                logging.warning(f"Language header for '{PREFERRED_LANGUAGE}' not found quickly. Checking all available slots.")
                # Fallback: check all available slots if header fails
                filtered_labels = slot_container.find_elements(By.XPATH, AVAILABLE_SLOT_LABEL_XPATH)
            except Exception as e:
                 logging.error(f"Error finding language section/slots: {e}. Checking all.")
                 filtered_labels = slot_container.find_elements(By.XPATH, AVAILABLE_SLOT_LABEL_XPATH)


            # Check the found labels for the exact time match
            for label in filtered_labels:
                try:
                    # Check visibility quickly before getting text
                    if not label.is_displayed(): continue

                    time_span = label.find_element(By.XPATH, SLOT_TIME_TEXT_XPATH)
                    slot_time_text = time_span.text.strip()

                    # Use exact match for the desired time string
                    if slot_time_text == self.desired_slot_time_str:
                        logging.info(f"Found desired slot: '{slot_time_text}' for {PREFERRED_LANGUAGE}.")
                        # Use fast JS click
                        if self.wait_and_click(label, timeout=0.2): # Quick click
                            time.sleep(DELAY_AFTER_SLOT_CLICK) # Minimal pause after successful click
                            return True
                        else:
                            logging.warning(f"Found slot '{slot_time_text}' but failed to click.")
                            # Maybe try standard click as fallback?
                            # try: label.click(); time.sleep(DELAY_AFTER_SLOT_CLICK); return True
                            # except: pass
                            return False # Failed to click
                except StaleElementReferenceException:
                    logging.debug("Stale element encountered while checking slot label, skipping.")
                    continue # Skip this stale label
                except (NoSuchElementException, TimeoutException):
                    continue # Skip label if time span not found quickly
                except Exception as e_inner:
                    logging.warning(f"Minor error processing slot label: {e_inner}", exc_info=False)
                    continue

            # If loop finishes without finding/clicking the exact match
            logging.info(f"Target slot '{self.desired_slot_time_str}' for {PREFERRED_LANGUAGE} not found among available slots.")
            return False

        except TimeoutException:
            logging.debug("Time slot container not found within fast loop timeout.")
            return False # Container itself wasn't found quickly enough
        except Exception as e:
            logging.error(f"Error in select_time_slot: {e}", exc_info=False)
            return False

    def set_ticket_quantities(self):
        """Sets ticket quantities using fast JS clicks."""
        try:
            # Wait briefly for the container
            ticket_container = WebDriverWait(self.driver, FAST_LOOP_WAIT_TIMEOUT, 0.05).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, TICKET_TYPE_CONTAINER_SELECTOR))
            )

            def set_quantity(ticket_text_key, num_tickets):
                if num_tickets <= 0: return True
                ticket_display_text_lower = TEXT_MAPPINGS[self.site_language].get(ticket_text_key, "").lower()
                if not ticket_display_text_lower:
                    logging.error(f"Text mapping missing for '{ticket_text_key}' in '{self.site_language}'")
                    return False

                try:
                    # Find the specific row for the ticket type
                    row_xpath = TICKET_ROW_XPATH_TEMPLATE.format(ticket_display_text_lower)
                    # Use a short wait within the already found container
                    ticket_row = WebDriverWait(ticket_container, 0.2, 0.05).until(
                        EC.presence_of_element_located((By.XPATH, row_xpath))
                    )

                    # Find the plus button within this row
                    plus_button = WebDriverWait(ticket_row, 0.1, 0.05).until(
                         EC.presence_of_element_located((By.CSS_SELECTOR, TICKET_PLUS_BTN_SELECTOR))
                    )

                    # Click the plus button the required number of times using JS
                    for i in range(num_tickets):
                        try:
                            self.driver.execute_script("arguments[0].click();", plus_button)
                            time.sleep(DELAY_BETWEEN_PLUS_CLICKS) # Minimal pause between clicks
                        except Exception as click_err:
                            logging.error(f"JS plus click error iter {i+1} for {ticket_text_key}: {click_err}")
                            return False
                    return True
                except TimeoutException:
                     logging.warning(f"Timeout finding row or plus button for '{ticket_text_key}'.")
                     return False
                except StaleElementReferenceException:
                     logging.warning(f"Stale element finding row/button for '{ticket_text_key}'.")
                     return False # Let the main loop retry
                except Exception as e_inner:
                    logging.error(f"Error in set_quantity for '{ticket_text_key}': {e_inner}", exc_info=False)
                    return False

            # Set quantities, pausing briefly between types
            if not set_quantity("full_price", FULL_PRICE_TICKETS): return False
            time.sleep(DELAY_BETWEEN_QTY_SET)
            if not set_quantity("reduced_fare", REDUCED_PRICE_TICKETS): return False

            time.sleep(DELAY_AFTER_QTY_SET) # Pause after setting all
            return True

        except TimeoutException:
            logging.debug("Ticket type container not found within fast loop timeout.")
            return False
        except Exception as e:
            logging.error(f"Error in set_ticket_quantities: {e}", exc_info=False)
            return False

    def click_continue(self):
        """Clicks the continue button using JS."""
        try:
            # Locate and click using the fast wait_and_click helper
            if self.wait_and_click((By.CSS_SELECTOR, CONTINUE_BUTTON_SELECTOR), timeout=FAST_LOOP_WAIT_TIMEOUT):
                logging.info("Continue button clicked successfully.")
                time.sleep(DELAY_AFTER_CONTINUE) # Wait for potential transition
                return True
            else:
                logging.warning(f"Continue button ('{CONTINUE_BUTTON_SELECTOR}') click failed.")
                # Optionally save screenshot here if debugging needed
                # self.save_screenshot("debug_continue_click_fail")
                return False
        except Exception as e:
            logging.error(f"Error finding/clicking continue: {e}", exc_info=False)
            return False

    def micro_refresh_loop(self):
        """Performs rapid JS reloads around the activation time."""
        start_time = self.activation_dt_rome - timedelta(seconds=MICRO_REFRESH_DURATION_BEFORE)
        end_time = self.activation_dt_rome + timedelta(seconds=MICRO_REFRESH_DURATION_AFTER)
        interval = MICRO_REFRESH_INTERVAL

        logging.info(f"Starting micro-refresh window: "
                     f"{start_time.strftime('%H:%M:%S.%f')[:-3]} to "
                     f"{end_time.strftime('%H:%M:%S.%f')[:-3]} Rome Time "
                     f"(Interval: {int(interval * 1000)}ms)")

        # Precise wait until the start of the window
        precise_wait_until(start_time)
        logging.info("Micro-refresh window entered.")

        refresh_count = 0
        start_perf = time.perf_counter()
        container_found = False
        last_reload_time = start_perf

        while time.perf_counter() < start_perf + (MICRO_REFRESH_DURATION_BEFORE + MICRO_REFRESH_DURATION_AFTER):
            current_perf = time.perf_counter()
            # Reload only if interval has passed
            if current_perf - last_reload_time >= interval:
                if js_reload(self.driver):
                     refresh_count += 1
                     now_dt = datetime.now(self.rome_tz) # Use Rome TZ for logging consistency
                     logging.debug(f"[Micro Refresh {refresh_count}] {now_dt.strftime('%H:%M:%S.%f')[:-3]}")
                     last_reload_time = current_perf

                     # VERY quick check for container presence immediately after reload
                     # Don't wait long here, just see if it appeared *instantly*
                     if self.quick_check_element(By.CSS_SELECTOR, PRIMARY_CONTAINER_SELECTOR, timeout=0.1):
                         logging.info(f"*** Primary container FOUND during micro-refresh at {now_dt.strftime('%H:%M:%S.%f')[:-3]}! ***")
                         container_found = True
                         break # Exit micro-refresh loop immediately
                else:
                     # Reload failed, wait briefly before trying again
                     time.sleep(0.1)
                     last_reload_time = time.perf_counter() # Reset timer after failure delay

            # Minimal sleep to prevent pure CPU spin
            time.sleep(0.005)

        logging.info(f"Micro-refresh window finished. Total refreshes: {refresh_count}. Container found: {container_found}")

        # After loop, if container was found, wait slightly longer for it to stabilize
        if container_found:
            try:
                 WebDriverWait(self.driver, POST_REFRESH_CONTAINER_TIMEOUT, 0.1).until(
                     EC.visibility_of_element_located((By.CSS_SELECTOR, PRIMARY_CONTAINER_SELECTOR))
                 )
                 logging.info("Primary container visibility confirmed after micro-refresh.")
                 self.detect_site_language() # Detect language now that container is stable
                 return True
            except TimeoutException:
                 logging.error("Container found during micro-refresh, but disappeared or timed out confirming visibility.")
                 return False
        else:
             logging.warning("Primary container was NOT found during the micro-refresh window.")
             # Attempt one last check just in case it appeared right at the end
             if self.quick_check_element(By.CSS_SELECTOR, PRIMARY_CONTAINER_SELECTOR, timeout=0.5):
                 logging.info("Container found in final check after micro-refresh window.")
                 self.detect_site_language()
                 return True
             else:
                 logging.error("Micro-refresh failed to find the primary container.")
                 return False


    def check_for_tickets(self):
        """Main logic: Initial load -> Timed micro-refresh -> Fast check loop."""
        if not self.driver:
            try:
                self.setup_driver()
            except Exception as e:
                logging.critical(f"CRITICAL: WebDriver setup failed: {e}")
                return False

        # Construct URL with target date
        url_with_date = BASE_URL
        date_param = f"?t={TARGET_DATE}"
        if '?' in url_with_date:
             # Avoid adding ?t= if query params already exist (might need smarter handling)
             if f"t={TARGET_DATE}" not in url_with_date:
                  logging.warning(f"URL '{url_with_date}' already has params, date param '{date_param}' might not work as expected.")
                  # Attempt to append, but this might break URL logic
                  # url_with_date += f"&t={TARGET_DATE}" # Less safe
                  pass # Assume date is handled differently or already correct
        else:
             url_with_date += date_param
        logging.info(f"Final URL for attempt: {url_with_date}")


        # === Step 1: Initial Load & Manual Interaction ===
        if not self.handle_initial_load(url_with_date):
            logging.error("Initial load or manual CAPTCHA step failed.")
            return False

        # === Step 2: Wait for Micro-Refresh Trigger ===
        refresh_trigger_time = self.activation_dt_rome - timedelta(seconds=MICRO_REFRESH_LEAD_TIME_SECONDS)
        logging.info(f"Waiting until ~{refresh_trigger_time.strftime('%H:%M:%S.%f')[:-3]} Rome Time to start micro-refresh...")
        precise_wait_until(refresh_trigger_time)
        logging.info(f"Trigger time reached. Starting micro-refresh sequence.")

        # === Step 3: Execute Micro-Refresh Loop ===
        container_ready = self.micro_refresh_loop()

        if not container_ready:
            logging.error("Micro-refresh sequence completed but primary container is not ready. Aborting attempt.")
            self.save_screenshot("debug_container_not_found_after_microrefresh")
            return False

        # === Step 4: Fast Ticket Check Loop ===
        logging.info("=== STARTING FAST CHECK LOOP ===")
        self.attempt_count = 0
        start_fast_loop_time = time.perf_counter()
        max_loop_duration = MAX_FAST_CHECK_ATTEMPTS * FAST_CHECK_INTERVAL + 5 # Add buffer time

        while time.perf_counter() < start_fast_loop_time + max_loop_duration:
            loop_start_perf = time.perf_counter()
            self.attempt_count += 1
            logging.debug(f"Fast Check Attempt {self.attempt_count}...")

            # --- Core Ticket Selection Logic ---
            try:
                # Step 4a: Select Time Slot (includes internal delay)
                slot_selected = self.select_time_slot()
                if not slot_selected:
                    # If slots were expected but not found/clicked, pause and retry loop
                    time.sleep(FAST_CHECK_INTERVAL)
                    continue # Go to next attempt immediately

                # --- Slot Selected ---
                logging.debug(f"Attempt {self.attempt_count}: Slot selected. Setting quantities...")

                # Step 4b: Set Ticket Quantities (includes internal delays)
                quantities_set = self.set_ticket_quantities()
                if not quantities_set:
                    # If setting quantities failed, pause slightly longer and retry loop
                    logging.warning(f"Attempt {self.attempt_count}: Failed to set quantities.")
                    time.sleep(FAST_CHECK_INTERVAL * 1.5)
                    # Consider a reload/refresh here if quantity setting fails consistently? Risky.
                    continue

                # --- Quantities Set ---
                logging.info(f"Attempt {self.attempt_count}: Quantities set! Clicking continue...")

                # Step 4c: Click Continue/Checkout (includes internal delay)
                continue_clicked = self.click_continue()
                if not continue_clicked:
                     logging.warning(f"Attempt {self.attempt_count}: Failed to click continue.")
                     time.sleep(FAST_CHECK_INTERVAL * 1.5)
                     # Maybe save screenshot on continue failure
                     # self.save_screenshot(f"debug_continue_fail_attempt_{self.attempt_count}")
                     continue

                # == SUCCESS! ==
                loop_end_perf = time.perf_counter()
                logging.info(f"SUCCESS on Fast Check Attempt {self.attempt_count}! (Loop time: {loop_end_perf - loop_start_perf:.4f}s)")
                logging.info(f"Total time from fast loop start: {loop_end_perf - start_fast_loop_time:.4f}s")
                self.ticket_secured()
                return True # Exit successfully

            except StaleElementReferenceException:
                 logging.warning(f"StaleElementReferenceException during fast check {self.attempt_count}. Retrying loop.")
                 time.sleep(FAST_CHECK_INTERVAL / 2.0) # Very short pause before retry
                 continue
            except (TimeoutException, NoSuchElementException) as e_find:
                 # These are expected if elements aren't ready yet
                 logging.debug(f"Element not found/timed out in attempt {self.attempt_count}: {type(e_find).__name__}. Continuing check.")
                 time.sleep(FAST_CHECK_INTERVAL)
                 continue
            except Exception as loop_e:
                logging.error(f"Unhandled error during fast check {self.attempt_count}: {loop_e}", exc_info=True)
                self.save_screenshot(f"debug_fast_loop_error_{self.attempt_count}")
                time.sleep(FAST_CHECK_INTERVAL * 2) # Longer pause after unexpected error
                continue
            # --- End of Fast Loop Iteration ---

        # Loop finished without success
        logging.warning(f"Fast check loop completed {self.attempt_count} attempts without securing tickets.")
        self.save_screenshot("debug_fast_loop_timeout")
        return False


    def ticket_secured(self):
        """Handles successful ticket acquisition."""
        logging.info("="*60)
        logging.info(" TICKET ACQUISITION LIKELY SUCCESSFUL! ")
        logging.info(" Browser window remains open. COMPLETE PURCHASE MANUALLY NOW!")
        logging.info(" Check website for time limit in cart (usually 10-15 mins).")
        logging.info("="*60)
        # Add sound alert logic here if desired
        # ... (your winsound code) ...
        print("-" * 60)
        input(">>> Press Enter here ONLY after finishing/abandoning purchase...")
        print("-" * 60)

    def save_screenshot(self, filename_prefix="debug_screenshot"):
        """Saves a screenshot, useful for debugging failures."""
        if not self.driver: return
        try:
            filename = f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
            if self.driver.save_screenshot(filename):
                logging.info(f"Saved screenshot: {filename}")
            else:
                logging.warning(f"Call to save_screenshot for '{filename}' returned False.")
        except Exception as e:
            logging.error(f"Could not save screenshot '{filename_prefix}': {e}")

    def close(self):
        """Cleans up the WebDriver instance."""
        if self.driver:
            logging.info("Closing browser...")
            try:
                self.driver.quit()
                logging.info("Browser closed.")
            except (WebDriverException, OSError) as e:
                 logging.warning(f"Ignoring error during browser close: {type(e).__name__} - {e}")
            except Exception as e:
                 logging.error(f"Unexpected error during browser close: {e}", exc_info=True)
            finally:
                 self.driver = None

# Main Execution Block
if __name__ == "__main__":
    # === CRITICAL PRE-RUN CHECKS ===
    logging.warning("="*70)
    logging.warning(" VERY IMPORTANT: ")
    logging.warning(" 1. RUN THIS SCRIPT ON A VPS IN EUROPE (CLOSE TO ITALY) FOR LOW LATENCY.")
    logging.warning(" 2. ENSURE THE VPS SYSTEM CLOCK IS PERFECTLY SYNCED USING NTP.")
    logging.warning(" 3. DOUBLE-CHECK ALL CSS/XPATH SELECTORS AGAINST THE LIVE WEBSITE!")
    logging.warning(" 4. TEST THE AGGRESSIVE TIMINGS (DELAYS, INTERVALS) BEFORE A REAL DROP.")
    logging.warning("="*70)
    time.sleep(4) # Give user time to read warnings

    bot = ColosseumTicketBot() # Initialization calculates activation time etc.
    final_status = False
    try:
        logging.info("="*60 + "\n Starting Optimized Ticket Bot \n" + "="*60)
        # Log key configurations
        logging.info(f" Target Date: {TARGET_DATE}")
        logging.info(f" Activation Time (Rome): {ACTIVATION_TIME}")
        logging.info(f" Desired Slot Match: '{bot.desired_slot_time_str}' ({PREFERRED_LANGUAGE})")
        logging.info(f" Tickets: {FULL_PRICE_TICKETS} Full / {REDUCED_PRICE_TICKETS} Reduced")
        logging.info(f" Micro-Refresh: Lead={MICRO_REFRESH_LEAD_TIME_SECONDS}s, Window={MICRO_REFRESH_DURATION_BEFORE}s+{MICRO_REFRESH_DURATION_AFTER}s, Interval={MICRO_REFRESH_INTERVAL*1000:.0f}ms")
        logging.info(f" Fast Check: Interval={FAST_CHECK_INTERVAL*1000:.0f}ms, Max Attempts={MAX_FAST_CHECK_ATTEMPTS} (~{MAX_FAST_CHECK_ATTEMPTS*FAST_CHECK_INTERVAL:.1f}s window)")
        logging.info(f" Key Delays (ms): SlotClick={DELAY_AFTER_SLOT_CLICK*1000:.0f}, QtySet={DELAY_BETWEEN_QTY_SET*1000:.0f}, PlusClick={DELAY_BETWEEN_PLUS_CLICKS*1000:.0f}, AfterQty={DELAY_AFTER_QTY_SET*1000:.0f}")
        logging.info(f" Using Undetected Chromedriver: {USE_UNDETECTED}")
        logging.info("="*60)

        # --- Run the main process ---
        final_status = bot.check_for_tickets()

    except KeyboardInterrupt:
        logging.info("\n" + "="*60 + "\n Script interrupted by user (Ctrl+C). \n" + "="*60)
        bot.save_screenshot("debug_user_interrupt")
    except Exception as e:
        logging.critical("\n" + "="*60 + f"\n CRITICAL ERROR in main execution: {e} \n" + "="*60, exc_info=True)
        bot.save_screenshot("debug_critical_main_error")
    finally:
        logging.info("="*60 + f"\n Script finished. Ticket Secured Status: {final_status} \n" + "="*60)
        bot.close()
        logging.info(" Cleanup complete. Exiting. ")
        logging.info("="*60)

# Colosseum-Fast-Ticket-A-High-Performance-Ticket-Acquisition-Bot
A specialized Python Selenium bot engineered to secure high-demand Colosseum underground tour tickets within milliseconds of release, outperforming commercial reseller bots through precise timing and optimized browser automation

## Overview

This project is a Python-based Selenium bot designed to automate the challenging process of purchasing high-demand tickets for the Colosseum in Rome, specifically targeting sought-after experiences like the Underground tours. It was born out of the frustration of battling reseller bots and consistently missing out on tickets that vanish in fractions of a second. This bot aims to level the playing field by executing a precisely timed purchase sequence.

**Outcome:** This bot successfully secured two "Full Experience Underground and Arena" tour tickets against intense competition, proving its effectiveness and providing invaluable hands-on experience with advanced web automation techniques.

## The Challenge: A Digital Gladiator Arena

Securing tickets for popular Colosseum attractions, especially the Underground tours, is notoriously difficult. Tickets are released at specific times and are often bought out within seconds, frequently by automated reseller bots that then list them at exorbitant prices. My personal attempts to acquire tickets manually were futile; I'd often see "Out of Stock" mere moments after the supposed release time, without ever seeing them available. This project was my answer to that challenge.

## Key Features & Hurdles Overcome

This bot was engineered to overcome several significant obstacles:

1.  **Cloudflare Anti-Bot Measures:**
    *   Utilizes `undetected-chromedriver` to present a more human-like browser fingerprint, significantly improving the chances of bypassing initial bot detection.
    *   Includes a manual intervention step to solve any CAPTCHAs that `undetected-chromedriver` might not handle automatically, ensuring the bot can proceed to the purchase page.

2.  **Millisecond-Precise Timing (The "Snipe"):**
    *   **Targeted Activation:** The bot calculates the exact activation time in the Colosseum's local timezone (Europe/Rome).
    *   **Micro-Refresh Loop:** Implements a high-frequency JavaScript-based page reload (`window.location.reload(true)`) loop within a tight window (e.g., +/- 0.5-1 second) around the exact ticket release time. This is crucial for catching the tickets the instant they become available.
    *   **Precise Waits:** Employs custom high-precision wait functions (`precise_wait_until`) to synchronize actions with the system clock down to small fractions of a second.
    *   **Minimized Delays:** All internal script delays (e.g., after clicks) are aggressively minimized (e.g., 20-50 milliseconds) to shave off crucial time during the purchase sequence.

3.  **Dynamic Element Interaction & Navigation:**
    *   **Reliable Selectors:** Uses robust CSS and XPath selectors to locate buttons, time slots, and ticket quantity controls.
    *   **Language Adaptability:** Incorporates mappings for different site languages (English, Italian) to ensure selectors work even if the website's language changes.
    *   **Targeted Slot Selection:** Specifically identifies and selects the desired tour time slot (e.g., "09:00 AM") for the preferred language.
    *   **JavaScript Clicks:** Favors JavaScript-based clicks (`element.execute_script("arguments[0].click();")`) for speed and to bypass potential click interceptions or elements deemed "not interactable" by standard Selenium methods.

4.  **Error Handling & Robustness:**
    *   Includes `try-except` blocks to handle common Selenium exceptions like `TimeoutException`, `NoSuchElementException`, and `StaleElementReferenceException`, allowing the bot to retry or proceed gracefully.
    *   Saves screenshots on critical errors or at key failure points for easier debugging.

## How It Works (High-Level)

1.  **Setup & Initial Load:**
    *   Initializes `undetected-chromedriver`.
    *   Navigates to the Colosseum ticketing page for the target date.
    *   Prompts the user for manual CAPTCHA/Cloudflare challenge completion.
2.  **Synchronization:**
    *   Waits precisely until a few moments before the configured ticket release time.
3.  **Micro-Refresh Snipe:**
    *   Enters a rapid JavaScript-reload loop around the exact release time, constantly checking for the primary content container to appear (signaling tickets *might* be available).
4.  **Fast Check & Purchase Sequence:**
    *   Once the container is detected, it rapidly executes the following:
        *   Selects the preferred language and the *exact* desired time slot.
        *   Sets the required number of full-price and reduced-price tickets.
        *   Clicks the "Continue" or "Add to Cart" button.
5.  **Success & Manual Checkout:**
    *   If successful, it notifies the user that tickets are likely in the cart and pauses, allowing the user to complete the purchase manually. The website usually provides a 10-15 minute timer to finalize payment.

## Configuration Highlights

The script includes several key configuration variables at the top that need to be set:

*   `BASE_URL`: The ticketing page URL.
*   `TARGET_DATE`: The desired date for tickets (YYYY-MM-DD).
*   `ACTIVATION_TIME`: The *exact* ticket release time in Rome (Europe/Rome timezone, HH:MM:SS).
*   `FULL_PRICE_TICKETS` / `REDUCED_PRICE_TICKETS`: Number of each ticket type.
*   `PREFERRED_LANGUAGE`: For tour language selection.
*   **Timing Parameters:** `MICRO_REFRESH_LEAD_TIME_SECONDS`, `MICRO_REFRESH_DURATION_BEFORE/AFTER`, `MICRO_REFRESH_INTERVAL`, and various `DELAY_` constants. These require careful tuning.

## Disclaimer

This script was created for personal, educational purposes to understand and overcome the challenges of automated web interactions on high-traffic, protected websites. Ticket availability and website structure can change, requiring updates to selectors and logic. Use responsibly and be aware of the terms of service of any website you interact with. This script does *not* handle payment.

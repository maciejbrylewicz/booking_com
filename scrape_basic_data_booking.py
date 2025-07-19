import asyncio
import logging
from playwright.async_api import async_playwright
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

URL = "https://www.booking.com/searchresults.html?label=gen173nr-1FCAEoggI46AdIM1gEaEaIAQGYATG4ARnIAQ_YAQHoAQH4AQKIAgGoAgO4Apa47cMGwAIB0gIkNjg4M2Q3NTYtZTE2MC00ZDhmLWI3MzMtYjQ5NjgzNTViMjE52AIF4AIB&aid=304142&ss=Playa+del+Ingles&ssne=Playa+del_Ingles&ssne_untouched=Playa+del_Ingles&efdco=1&lang=en-us&sb=1&src_elem=sb&dest_id=900039399&dest_type=city&checkin=2025-11-16&checkout=2025-11-23&group_adults=2&no_rooms=1&group_children=0&order=price"

async def scroll_to_bottom(page, max_time=60):
    logging.info("Scrolling to bottom for up to %d seconds...", max_time)
    start = time.time()
    previous_height = await page.evaluate("() => document.body.scrollHeight")

    while time.time() - start < max_time:
        await page.mouse.wheel(0, 10000)
        await page.wait_for_timeout(1500)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == previous_height:
            logging.info("Reached the bottom (no more scrollable content).")
            break
        previous_height = new_height

    logging.info("Scrolling done.")

async def handle_cookie_consent(page):
    logging.info("Checking for cookie consent banner...")
    consent_selectors = [
        '#onetrust-accept-btn-handler',
        'button.osano-cm-btn.osano-cm-accept',
        'button[data-gdpr-consent-type="accept"]',
        'button[aria-label="Accept cookies"]',
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        'button:has-text("Agree")'
    ]
    for selector in consent_selectors:
        try:
            consent_button = page.locator(selector)
            if await consent_button.is_visible():
                logging.info(f"Clicking cookie consent button with selector: '{selector}'")
                await consent_button.click()
                # Instead of just networkidle, we'll return True and let the main function
                # wait for the property cards after this is done.
                logging.info("Cookie consent clicked. Waiting for page to react...")
                return True
        except Exception as e:
            logging.debug(f"No cookie consent button found with selector '{selector}' or error clicking: {e}")
    logging.info("No visible cookie consent banner found or successfully handled.")
    return False

async def scrape_booking():
    async with async_playwright() as p:
        # Keep headless=False for now to visually debug this timeout issue.
        browser = await p.chromium.launch(headless=False) 
        page = await browser.new_page()
        logging.info("Navigating to Booking.com search results...")
        
        await page.goto(URL, timeout=90000)
        await page.wait_for_load_state('load') # Wait for 'load' first, then 'networkidle'

        # Attempt to handle any cookie consent pop-ups
        consent_handled = await handle_cookie_consent(page)
        
        # Give the page a moment to settle after potential cookie banner dismissal
        if consent_handled:
            logging.info("Cookie consent was handled. Giving page a moment to stabilize.")
            await page.wait_for_load_state('networkidle') # Wait for network to settle after click
            await page.wait_for_timeout(2000) # Add a small fixed delay as a safety measure

        # NOW, wait for the property cards. The timeout here is crucial.
        logging.info("Waiting for property cards to be visible (max 45 seconds)...")
        try:
            # Increased timeout for waiting for property cards to be very generous
            await page.wait_for_selector('div[data-testid="property-card-container"], div[data-testid="property-card"]', timeout=45000)
            logging.info("Property cards found and visible.")
        except Exception as e:
            html = await page.content()
            logging.error("Timeout waiting for property cards. Dumping partial HTML for debugging:")
            print(html[:2000])
            logging.error(f"Error details: {e}")
            await browser.close()
            raise e

        # Now scroll
        await scroll_to_bottom(page)
        
        cards = await page.query_selector_all('div[data-testid="property-card-container"], div[data-testid="property-card"]')
        logging.info(f"Found {len(cards)} property cards (before deduplication).")

        unique_properties = set()
        results = []
        
        for idx, card in enumerate(cards, start=1):
            try:
                name_el = await card.query_selector('div[data-testid="title"]')
                name = (await name_el.inner_text()).strip() if name_el else "N/A"

                price_el = await card.query_selector('span[data-testid="price-and-discounted-price"]')
                
                if not price_el:
                    # Look for other common patterns within the card
                    # Prioritize stable elements or those found reliably near prices
                    # Re-evaluating based on common Booking.com structures
                    
                    # Try a more specific descendant of the card that wraps pricing info
                    price_el = await card.query_selector('.bui-price-display__value')
                    
                    if not price_el:
                        price_el = await card.query_selector('div.prco- 금액 -actual_value') # Updated general price class
                    
                    if not price_el:
                        price_el = await card.query_selector('span.prco- 금액 -actual_value') # Updated general price class

                    if not price_el:
                        price_el = await card.query_selector('div[data-testid="price-for-x-nights"]')

                    if not price_el:
                        # Sometimes the price is inside a span directly in the main price wrapper
                        price_el = await card.query_selector('.price span')
                    
                    if not price_el:
                        # Fallback for dynamic classes, but only if they contain the currency
                        price_el = await card.query_selector('span:has-text("€")') or await card.query_selector('div:has-text("€")')

                price = (await price_el.inner_text()).strip().replace('\u00a0', ' ') if price_el else "N/A"

                if price == "N/A":
                    logging.warning(f"Price not found for property: {name}")
                
                property_id = f"{name}-{price}"

                if property_id not in unique_properties:
                    unique_properties.add(property_id)
                    results.append({
                        "order": len(results) + 1,
                        "name": name,
                        "price": price,
                    })
                else:
                    logging.debug(f"Skipping duplicate property: {name} - {price}")

            except Exception as e:
                logging.warning(f"Error processing card #{idx} (Name: {name if 'name' in locals() else 'N/A'}): {e}. Skipping this card.")

        print("\n--- Scraped Results ---\n")
        for item in results:
            print(f"{item['order']}. {item['name']} - {item['price']}")
        print(f"\nTotal unique properties scraped: {len(results)}")

        await browser.close()
        logging.info("Browser closed. Scraping process finished.")

if __name__ == "__main__":
    try:
        asyncio.run(scrape_booking())
    except Exception as e:
        logging.critical(f"An unhandled error occurred during scraping: {e}")
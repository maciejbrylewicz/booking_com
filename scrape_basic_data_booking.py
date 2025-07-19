import asyncio
import logging
from playwright.async_api import async_playwright
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

URL = "https://www.booking.com/searchresults.html?label=gen173nr-1FCAEoggI46AdIM1gEaEaIAQGYATG4ARnIAQ_YAQHoAQH4AQKIAgGoAgO4Apa47cMGwAIB0gIkNjg4M2Q3NTYtZTE2MC00ZDhmLWI3MzMtYjQ5NjgzNTViMjE52AIF4AIB&aid=304142&ss=Playa+del+Ingles&ssne=Playa+del+Ingles&ssne_untouched=Playa+del+Ingles&efdco=1&lang=en-us&sb=1&src_elem=sb&dest_id=900039399&dest_type=city&checkin=2025-11-16&checkout=2025-11-23&group_adults=2&no_rooms=1&group_children=0&order=price"

async def scroll_to_bottom(page, max_time=60):
    logging.info("Scrolling to bottom for up to %d seconds...", max_time)
    start = time.time()
    previous_height = await page.evaluate("() => document.body.scrollHeight")

    while time.time() - start < max_time:
        await page.mouse.wheel(0, 10000)
        await page.wait_for_timeout(1500)  # 1.5s pause to let content load

        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == previous_height:
            logging.info("Reached the bottom (no more scroll).")
            break
        previous_height = new_height

    logging.info("Scrolling done.")

async def scrape_booking():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--enable-logging=stderr", "--v=1"])
        page = await browser.new_page()
        logging.info("Opening Booking.com...")
        await page.goto(URL, timeout=60000)

        await page.wait_for_selector('div[data-testid="property-card-container"]', timeout=30000)
        await scroll_to_bottom(page)

        cards = await page.query_selector_all('div[data-testid="property-card-container"]')
        logging.info(f"Found {len(cards)} property cards.")

        results = []
        for idx, card in enumerate(cards, start=1):
            try:
                name_el = await card.query_selector('div[data-testid="title"]')
                price_el = await card.query_selector('span[data-testid="price-and-discounted-price"]')

                name = await name_el.inner_text() if name_el else "N/A"
                price = await price_el.inner_text() if price_el else "N/A"

                results.append({
                    "order": idx,
                    "name": name.strip(),
                    "price": price.strip().replace('\u00a0', ' '),
                })
            except Exception as e:
                logging.warning(f"Error processing card #{idx}: {e}")

        print("\n--- Results ---\n")
        for item in results:
            print(f"{item['order']}. {item['name']} - {item['price']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_booking())

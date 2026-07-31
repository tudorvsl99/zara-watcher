"""
Zara Romania restock watcher - single-pass version for GitHub Actions.

Checks every product in config.json once, compares against state.json
(committed back to the repo by the workflow after each run) to avoid
duplicate emails, and sends an email via SMTP when a watched size flips
from out-of-stock to in-stock.

Email credentials come from environment variables (set as GitHub Actions
secrets) - never from a committed file - so nothing sensitive ends up in
the repo, even if the repo is public.
"""

import json
import os
import random
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
STATE_PATH = HERE / "state.json"

ANY_SIZE_TOKEN = "ANY"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ro-RO")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Selenium Manager (bundled with selenium>=4.6) auto-resolves a matching
    # chromedriver for whatever Chrome the workflow installed - no
    # webdriver-manager needed in CI.
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver


def accept_cookies(driver):
    try:
        wait = WebDriverWait(driver, 8)
        btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        btn.click()
    except Exception:
        pass


def check_product_stock(driver, url, wanted_sizes):
    driver.get(url)
    accept_cookies(driver)
    wait = WebDriverWait(driver, 20)

    try:
        add_to_cart = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-qa-action='add-to-cart']"))
        )
        overlays = driver.find_elements(By.CLASS_NAME, "zds-backdrop")
        if overlays:
            driver.execute_script("arguments[0].remove();", overlays[0])
        driver.execute_script("arguments[0].click();", add_to_cart)
    except Exception:
        pass

    results = {}
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "size-selector-sizes"))
        )
        size_elements = driver.find_elements(By.CLASS_NAME, "size-selector-sizes-size")
        for li in size_elements:
            try:
                label = li.find_element(
                    By.CSS_SELECTOR, "div[data-qa-qualifier='size-selector-sizes-size-label']"
                ).text.strip()
            except NoSuchElementException:
                continue
            if ANY_SIZE_TOKEN in wanted_sizes or label in wanted_sizes:
                button = li.find_element(By.CLASS_NAME, "size-selector-sizes-size__button")
                action = button.get_attribute("data-qa-action") or ""
                results[label] = action in ("size-in-stock", "size-low-on-stock")
        if ANY_SIZE_TOKEN in wanted_sizes:
            results["__any__"] = any(results.values()) if results else False
    except TimeoutException:
        if ANY_SIZE_TOKEN in wanted_sizes:
            try:
                driver.find_element(By.CSS_SELECTOR, "button[data-qa-action='add-to-cart']")
                results["__any__"] = True
            except NoSuchElementException:
                results["__any__"] = False
    return results


def send_email(subject, body):
    sender = os.environ.get("SENDER_EMAIL")
    password = os.environ.get("SENDER_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL")
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    if not sender or not password or not recipient:
        log("EMAIL NOT SENT: SENDER_EMAIL / SENDER_APP_PASSWORD / RECIPIENT_EMAIL secrets are missing.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        log(f"Email sent: {subject}")
    except Exception as exc:
        log(f"ERROR sending email: {exc}")


def main():
    config = load_json(CONFIG_PATH, {"products": []})
    state = load_json(STATE_PATH, {})
    products = config.get("products", [])

    driver = None
    try:
        driver = build_driver()
        for product in products:
            url = product["url"]
            name = product.get("name", url)
            wanted_sizes = product.get("sizes", [ANY_SIZE_TOKEN])

            try:
                results = check_product_stock(driver, url, wanted_sizes)
            except (WebDriverException, TimeoutException) as exc:
                log(f"[{name}] page error: {exc}")
                continue
            except Exception as exc:
                log(f"[{name}] unexpected error: {exc}")
                continue

            if not results:
                log(f"[{name}] could not find requested size(s) {wanted_sizes}.")
                continue

            for size_label, in_stock in results.items():
                display_size = "any size" if size_label == "__any__" else size_label
                key = f"{url}::{size_label}"
                was_in_stock = state.get(key, False)

                log(f"[{name}] {display_size}: {'IN STOCK' if in_stock else 'out of stock'}")

                if in_stock and not was_in_stock:
                    subject = f"Zara RO restock: {name} ({display_size})"
                    body = (
                        f"{display_size} is back in stock for:\n{name}\n\n{url}\n\n"
                        f"Detected at {time.strftime('%Y-%m-%d %H:%M:%S')} UTC."
                    )
                    send_email(subject, body)

                state[key] = in_stock

            time.sleep(random.uniform(1.0, 2.5))
    finally:
        if driver is not None:
            driver.quit()
        save_json(STATE_PATH, state)


if __name__ == "__main__":
    main()

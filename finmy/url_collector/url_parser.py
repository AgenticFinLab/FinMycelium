"""
URL Parser Module

This module provides functionality to parse web pages and extract structured content
including text, images, and videos while maintaining their original layout order.
It includes fallback to Selenium for JavaScript-heavy pages that cannot be parsed with requests.
"""


import csv
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import Error
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

class URLParser:
    """
    A class to parse multiple URLs and extract structured content including text,
    images, and videos while preserving the original layout order.
    Includes fallback to Selenium for JavaScript-heavy pages.
    """

    def __init__(
        self,
        user_agent: str = None,
        delay: float = 1.0,
        timeout: int = 30,
        use_selenium_fallback: bool = True,
        selenium_wait_time: int = 5,
        chromedriver_path: str = None,
    ):
        """
        Initialize the URL Parser with configuration options.

        Args:
            user_agent (str, optional): Custom user agent for requests.
                Defaults to a common browser user agent.
            delay (float): Delay between requests in seconds to avoid being blocked.
            timeout (int): Request timeout in seconds.
            use_selenium_fallback (bool): Whether to use Selenium as fallback for difficult pages.
            selenium_wait_time (int): Time to wait for page load in Selenium (seconds).
            chromedriver_path (str, optional): Path to ChromeDriver executable.
        """
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.delay = delay
        self.timeout = timeout
        self.use_selenium_fallback = use_selenium_fallback
        self.selenium_wait_time = selenium_wait_time
        self.chromedriver_path = chromedriver_path

        self.session = requests.Session()
        self.setup_session()

        # Configure logging
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def setup_session(self) -> None:
        """Set up the requests session with headers and configuration."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.session.headers.update(headers)

    def parse_urls(self, url_list: List[str]) -> List[Dict[str, Any]]:
        """
        Parse a list of URLs and extract structured content.

        Args:
            url_list (List[str]): List of URLs to parse.

        Returns:
            List[Dict[str, Any]]: List of parsed results with ID, URL, parse time, and content.
        """
        results = []

        for idx, url in enumerate(url_list, 1):
            try:
                self.logger.info(f"Parsing URL {idx}/{len(url_list)}: {url}")

                # Add delay between requests to avoid being blocked
                if idx > 1:
                    time.sleep(self.delay + random.uniform(0.1, 0.5))

                # Parse individual URL
                result = self.parse_single_url(url, idx)
                if result:
                    results.append(result)
                else:
                    # Create error result entry
                    results.append(
                        {
                            "ID": idx,
                            "url": url,
                            "parsertime": datetime.now().isoformat(),
                            "content": {"error": "Failed to parse URL"},
                        }
                    )

            except Exception as e:
                self.logger.error(f"Error parsing URL {url}: {str(e)}")
                # Create error result entry
                results.append(
                    {
                        "ID": idx,
                        "url": url,
                        "parsertime": datetime.now().isoformat(),
                        "content": {"error": str(e)},
                    }
                )

        return results

    def parse_single_url(self, url: str, url_id: int) -> Optional[Dict[str, Any]]:
        """
        Parse a single URL and extract its content using requests first,
        with Selenium fallback if enabled and needed.

        Args:
            url (str): URL to parse.
            url_id (int): ID for the URL.

        Returns:
            Optional[Dict[str, Any]]: Parsed result or None if failed.
        """
        # First try with requests (faster)
        result = self._parse_with_requests(url, url_id)

        # If requests failed or extracted minimal content, try Selenium fallback
        if self.use_selenium_fallback and (
            result is None or self._has_minimal_content(result)
        ):
            self.logger.info(f"Trying Selenium fallback for URL: {url}")
            selenium_result = self._parse_with_selenium(url, url_id)
            if selenium_result and not self._has_minimal_content(selenium_result):
                return selenium_result

        return result

    def _parse_with_requests(self, url: str, url_id: int) -> Optional[Dict[str, Any]]:
        """
        Parse URL using requests and BeautifulSoup.

        Args:
            url (str): URL to parse.
            url_id (int): ID for the URL.

        Returns:
            Optional[Dict[str, Any]]: Parsed result or None if failed.
        """
        try:
            # Fetch the web page
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Detect encoding and decode properly
            if response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding

            # Parse HTML content
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract content in order
            content_elements = self.extract_content_elements(soup, url)

            # Structure the result
            result = {
                "ID": url_id,
                "url": url,
                "parsertime": datetime.now().isoformat(),
                "content": content_elements,
            }

            return result

        except requests.RequestException as e:
            self.logger.error(f"Request error for URL {url}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error parsing URL {url}: {str(e)}")
            return None

    def _parse_with_selenium(self, url: str, url_id: int) -> Optional[Dict[str, Any]]:
        """
        Parse URL using Selenium WebDriver for JavaScript-heavy pages.

        Args:
            url (str): URL to parse.
            url_id (int): ID for the URL.

        Returns:
            Optional[Dict[str, Any]]: Parsed result or None if failed.
        """
        driver = None
        try:
            # Set up Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in background
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"user-agent={self.user_agent}")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option(
                "excludeSwitches", ["enable-automation"]
            )
            chrome_options.add_experimental_option("useAutomationExtension", False)

            # Initialize driver
            if self.chromedriver_path:
                service = Service(executable_path=self.chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                driver = webdriver.Chrome(options=chrome_options)

            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Load page and wait for content
            driver.get(url)

            # Wait for page to load completely
            WebDriverWait(driver, self.selenium_wait_time).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # Additional wait for body content to be present
            try:
                WebDriverWait(driver, self.selenium_wait_time).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                self.logger.warning(
                    "Body content not fully loaded, but proceeding anyway"
                )

            # Get page source and parse with BeautifulSoup
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")

            # Extract content
            content_elements = self.extract_content_elements(soup, url)

            result = {
                "ID": url_id,
                "url": url,
                "parsertime": datetime.now().isoformat(),
                "content": content_elements,
            }

            return result

        except WebDriverException as e:
            self.logger.error(f"Selenium WebDriver error for URL {url}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error with Selenium for URL {url}: {str(e)}")
            return None
        finally:
            if driver:
                driver.quit()

    def _has_minimal_content(self, result: Dict[str, Any]) -> bool:
        """
        Check if the parsed result has minimal content (likely incomplete parsing).

        Args:
            result (Dict[str, Any]): Parsing result to check.

        Returns:
            bool: True if content is minimal, False otherwise.
        """
        content = result.get("content", [])

        # If no content elements, consider it minimal
        if not content:
            return True

        # Count meaningful text elements (more than 10 characters)
        meaningful_elements = 0
        for element in content:
            if "text" in element and len(element["text"].strip()) > 10:
                meaningful_elements += 1

        # If very few meaningful elements, consider it minimal
        return meaningful_elements < 3

    def extract_content_elements(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[Dict[str, Any]]:
        """
        Extract text, images, and videos from the HTML while preserving order.

        Args:
            soup (BeautifulSoup): Parsed HTML soup object.
            base_url (str): Base URL for resolving relative links.

        Returns:
            List[Dict[str, Any]]: List of content elements in order.
        """
        content_elements = []
        element_counter = 1

        # Create a copy of soup to avoid modifying original
        soup_copy = BeautifulSoup(soup.prettify(), "html.parser")

        # Remove script and style elements
        for script in soup_copy(["script", "style", "noscript", "meta", "link"]):
            script.decompose()

        # Find all elements that might contain content
        # Expanded list of tags to include more structural elements
        elements = soup_copy.find_all(
            [
                "p",
                "div",
                "span",
                "img",
                "video",
                "iframe",
                "a",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "article",
                "section",
                "header",
                "footer",
                "main",
                "aside",
                "figure",
                "figcaption",
            ]
        )

        for element in elements:
            try:
                element_content = self._process_element(
                    element, base_url, element_counter
                )
                if element_content:
                    content_elements.extend(element_content)
                    element_counter += len(element_content)

            except Exception as e:
                self.logger.warning(f"Error processing element: {str(e)}")
                continue

        # Filter out empty text elements and clean up content
        cleaned_elements = []
        for element in content_elements:
            if self._is_valid_element(element):
                cleaned_elements.append(element)

        return cleaned_elements

    def _process_element(
        self, element, base_url: str, counter: int
    ) -> List[Dict[str, Any]]:
        """
        Process individual HTML element and extract relevant content.

        Args:
            element: BeautifulSoup element object.
            base_url (str): Base URL for resolving relative links.
            counter (int): Current element counter.

        Returns:
            List[Dict[str, Any]]: List of content dictionaries.
        """
        elements = []

        # Process text elements
        if element.name in [
            "p",
            "div",
            "span",
            "a",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "article",
            "section",
            "header",
            "footer",
            "main",
            "aside",
            "figcaption",
        ]:
            text_content = self.extract_text_element(element)
            if text_content and text_content.strip():
                href = element.get("href")
                if href and element.name == "a":
                    # Resolve relative URLs
                    href = urljoin(base_url, href)

                elements.append(
                    {
                        "text": text_content.strip(),
                        "no": counter,
                        "href": href if href and href != "#" else None,
                    }
                )

        # Process images
        elif element.name == "img":
            img_src = element.get("src")
            if img_src:
                # Resolve relative URLs
                img_src = urljoin(base_url, img_src)
                img_alt = element.get("alt", "")

                # Find parent link if exists
                img_href = None
                parent_link = element.find_parent("a")
                if parent_link and parent_link.get("href"):
                    img_href = urljoin(base_url, parent_link.get("href"))

                elements.append(
                    {
                        "image": img_src,
                        "no": counter,
                        "href": img_href if img_href and img_href != "#" else None,
                        "alt": img_alt if img_alt else None,
                    }
                )

        # Process videos
        elif element.name in ["video", "iframe"]:
            video_src = self.extract_video_source(element, base_url)
            if video_src:
                elements.append({"video": video_src, "no": counter, "href": None})

        # Process figures (may contain images with captions)
        elif element.name == "figure":
            # Extract image from figure
            img = element.find("img")
            if img and img.get("src"):
                img_src = urljoin(base_url, img.get("src"))
                img_alt = img.get("alt", "")

                elements.append(
                    {
                        "image": img_src,
                        "no": counter,
                        "href": None,
                        "alt": img_alt if img_alt else None,
                    }
                )

                # Extract caption if exists
                figcaption = element.find("figcaption")
                if figcaption:
                    caption_text = self.extract_text_element(figcaption)
                    if caption_text and caption_text.strip():
                        elements.append(
                            {
                                "text": caption_text.strip(),
                                "no": counter + 1,
                                "href": None,
                            }
                        )
                        return elements  # Return both image and caption

        return elements

    def extract_text_element(self, element) -> str:
        """
        Extract clean text content from an HTML element.

        Args:
            element: BeautifulSoup element object.

        Returns:
            str: Clean text content.
        """
        # Get text and clean it
        text = element.get_text(strip=False)

        # Clean the text: remove extra whitespace, normalize
        text = re.sub(
            r"\s+", " ", text
        )  # Replace multiple whitespace with single space
        text = text.strip()

        return text

    def extract_video_source(self, element, base_url: str) -> Optional[str]:
        """
        Extract video source URL from video or iframe elements.

        Args:
            element: BeautifulSoup element object.
            base_url (str): Base URL for resolving relative links.

        Returns:
            Optional[str]: Video source URL or None if not found.
        """
        video_src = None

        if element.name == "video":
            # Check for source tags inside video element
            source_tags = element.find_all("source")
            if source_tags:
                for source in source_tags:
                    video_src = source.get("src")
                    if video_src:
                        break
            else:
                video_src = element.get("src")

        elif element.name == "iframe":
            # Common video embedding sources
            video_src = element.get("src")
            # Check for common video platforms
            if any(
                platform in str(video_src).lower()
                for platform in ["youtube", "vimeo", "youku", "bilibili"]
            ):
                video_src = element.get("src")

        # Resolve relative URLs
        if video_src and not video_src.startswith(("http://", "https://")):
            video_src = urljoin(base_url, video_src)

        return video_src

    def _is_valid_element(self, element: Dict[str, Any]) -> bool:
        """
        Check if an extracted element is valid and meaningful.

        Args:
            element (Dict[str, Any]): Element to validate.

        Returns:
            bool: True if element is valid, False otherwise.
        """
        if "text" in element:
            text = element["text"].strip()
            # Filter out very short texts that are likely navigation or noise
            if len(text) < 2:
                return False
            # Filter out common non-content patterns
            noise_patterns = [
                r"^\d+$",  # Just numbers
                r"^[\.\-\s]+$",  # Just dots, dashes, or spaces
            ]
            for pattern in noise_patterns:
                if re.match(pattern, text):
                    return False
            return True

        elif "image" in element or "video" in element:
            return True

        return False

    def save_to_json(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """
        Save parsed data to JSON file.

        Args:
            data (List[Dict[str, Any]]): Data to save.
            filename (str, optional): Output filename. Defaults to auto-generated name.

        Returns:
            str: Path to the saved file.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"parsed_urls_{timestamp}.json"

        # Create directory if it doesn't exist
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Data saved to JSON file: {filename}")
        return filename

    def save_to_csv(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """
        Save parsed data to CSV file.

        Args:
            data (List[Dict[str, Any]]): Data to save.
            filename (str, optional): Output filename. Defaults to auto-generated name.

        Returns:
            str: Path to the saved file.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"parsed_urls_{timestamp}.csv"

        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(["ID", "url", "parsertime", "content"])

            # Write data
            for item in data:
                writer.writerow(
                    [
                        item["ID"],
                        item["url"],
                        item["parsertime"],
                        json.dumps(item["content"], ensure_ascii=False),
                    ]
                )

        self.logger.info(f"Data saved to CSV file: {filename}")
        return filename

    def save_to_mysql(
        self,
        data: List[Dict[str, Any]],
        host: str,
        user: str,
        password: str,
        database: str,
        table: str = "parsed_urls",
    ) -> bool:
        """
        Save parsed data to MySQL database.

        Args:
            data (List[Dict[str, Any]]): Data to save.
            host (str): MySQL host.
            user (str): MySQL username.
            password (str): MySQL password.
            database (str): Database name.
            table (str): Table name.

        Returns:
            bool: True if successful, False otherwise.
        """
        connection = None
        try:
            connection = mysql.connector.connect(
                host=host, user=user, password=password, database=database
            )

            if connection.is_connected():
                cursor = connection.cursor()

                # Create table if not exists
                create_table_query = f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    url_id INT NOT NULL,
                    url TEXT NOT NULL,
                    parsertime DATETIME NOT NULL,
                    content JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)

                # Insert data
                insert_query = f"""
                INSERT INTO {table} (url_id, url, parsertime, content)
                VALUES (%s, %s, %s, %s)
                """

                for item in data:
                    cursor.execute(
                        insert_query,
                        (
                            item["ID"],
                            item["url"],
                            item["parsertime"],
                            json.dumps(item["content"], ensure_ascii=False),
                        ),
                    )

                connection.commit()
                self.logger.info(f"Data saved to MySQL table: {table}")
                return True

        except Error as e:
            self.logger.error(f"MySQL error: {str(e)}")
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()


# Example usage and testing
if __name__ == "__main__":
    # Example URL list including problematic URLs
    sample_urls = [
        "http://www.jyb.cn/rmtzcg/xwy/wzxw/202511/t20251119_2111415715.html",
        "http://v.people.cn/n1/2025/1121/c431305-40608834.html",
        "https://baijiahao.baidu.com/s?id=1850027474872762323&wfr=spider&for=pc",
        # Add more URLs here for testing
    ]

    # Initialize parser with Selenium fallback enabled
    parser = URLParser(delay=2.0, use_selenium_fallback=True, selenium_wait_time=5)

    # Parse URLs
    results = parser.parse_urls(sample_urls)

    # Save results to JSON (default)
    json_file = parser.save_to_json(results)

    # Example of saving to other formats
    # csv_file = parser.save_to_csv(results)
    # mysql_success = parser.save_to_mysql(results, 'localhost', 'user', 'password', 'database_name')

    print("Parsing completed. Results:")
    for result in results:
        print(f"URL {result['ID']}: {result['url']}")
        print(f"Elements found: {len(result['content'])}")
        print(f"First few elements: {result['content'][:3]}")  # Show first 3 elements
        print("-" * 50)

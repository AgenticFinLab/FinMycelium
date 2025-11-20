"""
URL Parser Module

This module provides functionality to parse web pages and extract structured content
including text, images, and videos while maintaining their original layout order.
"""

import requests
import time
import json
import csv
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import mysql.connector
from mysql.connector import Error
from bs4 import BeautifulSoup
import random
from datetime import datetime


class URLParser:
    """
    A class to parse multiple URLs and extract structured content including text,
    images, and videos while preserving the original layout order.
    """

    def __init__(self, user_agent: str = None, delay: float = 1.0, timeout: int = 30):
        """
        Initialize the URL Parser with configuration options.

        Args:
            user_agent (str, optional): Custom user agent for requests.
                Defaults to a common browser user agent.
            delay (float): Delay between requests in seconds to avoid being blocked.
            timeout (int): Request timeout in seconds.
        """
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.delay = delay
        self.timeout = timeout
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
        Parse a single URL and extract its content.

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

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Find all relevant elements in order
        elements = soup.find_all(["p", "div", "span", "img", "video", "iframe", "a"])

        for element in elements:
            try:
                # Extract text content
                if element.name in ["p", "div", "span", "a"]:
                    text_content = self.extract_text_element(element)
                    if text_content and text_content.strip():
                        href = element.get("href")
                        if href and element.name == "a":
                            # Resolve relative URLs
                            href = urljoin(base_url, href)

                        content_elements.append(
                            {
                                "text": text_content.strip(),
                                "no": element_counter,
                                "href": href if href and href != "#" else None,
                            }
                        )
                        element_counter += 1

                # Extract images
                elif element.name == "img":
                    img_src = element.get("src")
                    if img_src:
                        # Resolve relative URLs
                        img_src = urljoin(base_url, img_src)
                        img_href = (
                            element.parent.get("href")
                            if element.parent.name == "a"
                            else None
                        )
                        if img_href:
                            img_href = urljoin(base_url, img_href)

                        content_elements.append(
                            {
                                "image": img_src,
                                "no": element_counter,
                                "href": (
                                    img_href if img_href and img_href != "#" else None
                                ),
                            }
                        )
                        element_counter += 1

                # Extract videos
                elif element.name in ["video", "iframe"]:
                    video_src = self.extract_video_source(element, base_url)
                    if video_src:
                        content_elements.append(
                            {
                                "video": video_src,
                                "no": element_counter,
                                "href": None,  # Video elements typically don't have separate hrefs
                            }
                        )
                        element_counter += 1

            except Exception as e:
                self.logger.warning(f"Error processing element: {str(e)}")
                continue

        return content_elements

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

        # Replace multiple whitespaces with single space
        text = " ".join(text.split())

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
                video_src = source_tags[0].get("src")
            else:
                video_src = element.get("src")

        elif element.name == "iframe":
            # Common video embedding sources
            video_src = element.get("src")
            # Check for common video platforms
            if "youtube" in str(element) or "vimeo" in str(element):
                video_src = element.get("src")

        # Resolve relative URLs
        if video_src and not video_src.startswith(("http://", "https://")):
            video_src = urljoin(base_url, video_src)

        return video_src

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
            if connection.is_connected():
                cursor.close()
                connection.close()


# Example usage and testing
if __name__ == "__main__":
    # Example URL list
    sample_urls = [
        "http://www.jyb.cn/rmtzcg/xwy/wzxw/202511/t20251119_2111415715.html",
        # Add more URLs here for testing
    ]

    # Initialize parser
    parser = URLParser(delay=2.0)

    # Parse URLs
    results = parser.parse_urls(sample_urls)

    # Save results to JSON (default)
    parser.save_to_json(results)

    # Example of saving to other formats
    # parser.save_to_csv(results)
    # parser.save_to_mysql(results, 'localhost', 'user', 'password', 'database_name')

    print("Parsing completed. Results:")
    for result in results:
        print(f"URL {result['ID']}: {result['url']}")
        print(f"Elements found: {len(result['content'])}")

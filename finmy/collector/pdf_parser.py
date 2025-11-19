"""
This script processes PDF files using the Mineru API with the following features:
1. Splits large PDFs into smaller chunks
2. Uploads batches of PDFs for parsing, converting them into Markdown files and images
3. Downloads and extracts the processed results
4. PDFs that failed to be parsed the first time were re-uploaded for parsing

Notes:
1. Mineru imposes limits on PDF parsing: each PDF must be less than 200 MB and 600 pages. Files exceeding these limits will be automatically split into multiple smaller PDFs.
2. Each batch can process up to 200 PDFs. If more than 200 PDFs are submitted, they will be automatically divided into multiple batches.
3. Mineru API tokens expire after 14 days. Please obtain a new token from https://mineru.net/apiManage/token before expiration and update it in your .env file.
"""

import os
import re
import csv
import glob
import time
import zipfile
import datetime
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse

from PyPDF2 import PdfReader, PdfWriter


def split_large_pdf(pdf_path, max_pages=600):
    """Split a large PDF into smaller chunks if it exceeds max_pages."""
    try:
        # Create a PDF reader object to read the input PDF file
        reader = PdfReader(pdf_path)

        # Check if the PDF is encrypted and try to decrypt it
        if reader.is_encrypted:
            print(f"Warning: {pdf_path} is encrypted, trying to decrypt...")
            try:
                # Try to decrypt with an empty password
                reader.decrypt("")
            except Exception:
                print(f"Failed to decrypt {pdf_path}, skipping...")
                return []

        # Get the total number of pages in the PDF
        total_pages = len(reader.pages)

        # If the PDF has fewer pages than the maximum, return the original file
        if total_pages <= max_pages:
            return [pdf_path]

        # Extract the base name and directory from the PDF path
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        base_dir = os.path.dirname(pdf_path)
        split_files = []

        # Split the PDF into chunks of max_pages each
        for start_page in range(0, total_pages, max_pages):
            # Calculate the end page for this chunk
            end_page = min(start_page + max_pages, total_pages)
            # Create a PDF writer object for this chunk
            writer = PdfWriter()

            # Add pages from start_page to end_page to the writer
            for i in range(start_page, end_page):
                try:
                    writer.add_page(reader.pages[i])
                except Exception as e:
                    print(f"Warning: Could not add page {i} from {pdf_path}: {e}")
                    continue

            # Create the path for the split file
            split_path = os.path.join(
                base_dir, f"{base_name}_part_{start_page // max_pages + 1}.pdf"
            )
            try:
                # Write the chunk to a new PDF file
                with open(split_path, "wb") as f:
                    writer.write(f)
                split_files.append(split_path)
            except Exception as e:
                print(f"Error writing split file {split_path}: {e}")
                continue

        # If multiple parts were created, remove the original file
        if len(split_files) > 1:
            try:
                os.remove(pdf_path)
                print(f"Removed original file: {pdf_path}")
            except Exception as e:
                print(f"Warning: Could not remove original file {pdf_path}: {e}")

        return split_files

    except Exception as e:
        print(f"Error splitting {pdf_path}: {e}")
        return []


def get_pdf_info(pdf_path):
    """Get file size and page count; delete unreadable files."""
    try:
        # Calculate the file size in megabytes
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        # Create a PDF reader object
        reader = PdfReader(pdf_path)

        # Check if the PDF is encrypted
        if reader.is_encrypted:
            try:
                # Try to decrypt with an empty password
                if reader.decrypt("") == 0:
                    print(f"Could not decrypt {pdf_path}, deleting file...")
                    os.remove(pdf_path)
                    print(f"Deleted: {pdf_path}")
                    return 0, 0
            except Exception as decrypt_error:
                print(f"Decryption failed for {pdf_path}: {decrypt_error}, deleting...")
                os.remove(pdf_path)
                print(f"Deleted: {pdf_path}")
                return 0, 0

        # Get the page count from the PDF
        page_count = len(reader.pages)
        return file_size_mb, page_count

    except Exception as pdf_error:
        # If the PDF can't be read, delete the file and return 0 for both values
        print(
            f"Warning: Could not read PDF info for {pdf_path}: {pdf_error}, deleting..."
        )
        try:
            os.remove(pdf_path)
            print(f"Deleted: {pdf_path}")
        except Exception as delete_error:
            print(f"Failed to delete {pdf_path}: {delete_error}")
        return (
            os.path.getsize(pdf_path) / (1024 * 1024) if os.path.exists(pdf_path) else 0
        ), 0


def check_and_process_pdfs(
    api_key,
    pdf_directory,
    max_files_per_batch=200,
    language="en",
    max_pdf_size_mb=200,
    max_pdf_pages=600,
    check_pdf_limits=True,
):
    """Process PDF files in batches using Mineru API with auto-splitting support."""
    # Find all PDF files in the specified directory
    pdf_files = glob.glob(os.path.join(pdf_directory, "*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {pdf_directory}")
        return [], []

    # Set up the API endpoint and headers
    api_url = "https://mineru.net/api/v4/file-urls/batch"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    # List to store successful batch IDs
    batch_ids = []
    # List to store all files that need to be processed (after splitting if needed)
    all_files_to_process = []

    # Check PDF limits and split large files if enabled
    if check_pdf_limits:
        print("Analyzing PDF files...")
        for pdf in pdf_files:
            try:
                # Get file size and page count for the current PDF
                file_size_mb, page_count = get_pdf_info(pdf)

                # Skip files that couldn't be read properly
                if page_count == 0 and file_size_mb > 0:
                    print(f"Skipping {pdf} due to PDF reading errors")
                    continue

                # Skip files with access issues
                if file_size_mb == 0:
                    print(f"Skipping {pdf} due to file access issues")
                    continue

                # Check if the file exceeds size or page limits
                if file_size_mb > max_pdf_size_mb or page_count > max_pdf_pages:
                    print(
                        f"Splitting {pdf} due to size ({file_size_mb:.2f} MB) or pages ({page_count})"
                    )
                    # Split the large PDF into smaller chunks
                    split_paths = split_large_pdf(pdf, max_pages=max_pdf_pages)
                    if split_paths:
                        # Add the split files to the processing list
                        all_files_to_process.extend(split_paths)
                    else:
                        print(f"Failed to split {pdf}, skipping...")
                else:
                    # Add the original file to the processing list if it doesn't need splitting
                    all_files_to_process.append(pdf)

            except Exception as e:
                print(f"Error processing {pdf}: {e}")
                continue
    else:
        print("Skipping PDF limit checks, processing all files directly...")
        all_files_to_process = pdf_files

    # Return early if no valid files to process
    if not all_files_to_process:
        print("No valid files to process")
        return [], []

    # Calculate batch information
    total_files = len(all_files_to_process)
    total_batches = (total_files + max_files_per_batch - 1) // max_files_per_batch
    print(f"Found {total_files} files. Processing in {total_batches} batches...")

    # Process files in batches
    for batch_index in range(total_batches):
        # Calculate the start index for this batch
        start_idx = batch_index * max_files_per_batch
        # Get the files for this batch
        batch_files = all_files_to_process[start_idx : start_idx + max_files_per_batch]
        print(
            f"\nProcessing batch {batch_index + 1}/{total_batches} ({len(batch_files)} files)"
        )
        start_time = time.time()

        # Prepare file data for the API request
        files_data = []
        for pdf in batch_files:
            try:
                # Extract the base name and extension from the PDF path
                base_name = os.path.basename(pdf)
                base_without_ext = os.path.splitext(base_name)[0]

                # Truncate the name if it's too long (to avoid API issues)
                truncated_name = (
                    base_without_ext[:16]
                    if len(base_without_ext) > 16
                    else base_without_ext
                )

                # Create a unique data ID for this file in this batch
                data_id = f"{truncated_name}_b{batch_index + 1}"

                # Add file information to the batch data
                files_data.append(
                    {
                        "name": base_name,
                        "is_ocr": True,
                        "data_id": data_id,
                        "language": language,
                    }
                )
            except Exception as e:
                print(f"Error preparing {pdf} for batch: {e}")
                continue

        # Skip this batch if no valid files were prepared
        if not files_data:
            print(f"Batch {batch_index + 1} has no valid files, skipping...")
            continue

        try:
            # Send the batch information to the API
            response = requests.post(
                api_url,
                headers=headers,
                json={
                    "enable_formula": True,
                    "language": "en",
                    "layout_model": "doclayout_yolo",
                    "enable_table": True,
                    "files": files_data,
                },
            )
            response.raise_for_status()
            result = response.json()

            # Check if the API request was successful
            if result.get("code") != 0:
                print(
                    f"Batch {batch_index + 1} failed: {result.get('msg', 'Unknown error')}"
                )
                continue
        except Exception as e:
            print(f"API request failed for batch {batch_index + 1}: {str(e)}")
            continue

        # Get the batch ID and file upload URLs from the response
        batch_id = result["data"]["batch_id"]
        file_urls = result["data"]["file_urls"]
        success_count = 0

        # Upload each PDF file to its corresponding URL
        for upload_url, pdf_path in zip(file_urls, batch_files):
            try:
                # Open and upload the PDF file
                with open(pdf_path, "rb") as f:
                    upload_res = requests.put(upload_url, data=f)
                    # Check if the upload was successful
                    if upload_res.status_code in [200, 201]:
                        success_count += 1
                    else:
                        print(f"Upload failed for {pdf_path}: {upload_res.status_code}")
            except Exception as e:
                print(f"Upload error for {pdf_path}: {e}")
                continue

        # Record successful batch if any files were uploaded
        if success_count > 0:
            batch_ids.append(batch_id)
            print(
                f"Batch {batch_index + 1} processed: {success_count}/{len(batch_files)} files"
            )
            print(f"Batch ID: {batch_id}")
            end_time = time.time()
            print(f"Time taken: {end_time - start_time:.2f}s")
        else:
            print(f"Batch {batch_index + 1} failed: No files uploaded successfully")

    # Return the original list of files processed in this batch
    return batch_ids, all_files_to_process 


def _sanitize_filename(filename):
    """
    Sanitize a filename by removing or replacing characters that are invalid.
    """
    # 1. Replace invalid characters with an underscore
    # Also remove leading/trailing spaces and dots which are problematic
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Add this line to remove leading and trailing spaces and dots
    sanitized = sanitized.strip(" .") # Removes spaces and dots from start and end

    # 2. Handle reserved names (CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9)
    # Case-insensitive check at the beginning followed by a dot or end of string
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", sanitized.upper()):
        # If it matches a reserved name, prepend an underscore
        sanitized = f"_{sanitized}"

    return sanitized


def _truncate_filename(filename, max_length=80):
    """
    Truncate filename and remove illegal characters to avoid path issues.
    """
    name, ext = os.path.splitext(filename)

    # First, sanitize the name part and the extension part separately
    sanitized_name = _sanitize_filename(name)
    sanitized_ext = _sanitize_filename(ext)

    # If the sanitized extension is empty or just dots, provide a default
    if not sanitized_ext or sanitized_ext.strip(".") == "":
        sanitized_ext = (
            ".pdf"  # Or '.txt', or whatever default you prefer, or just '.tmp'
        )

    # Combine the sanitized parts
    full_sanitized = sanitized_name + sanitized_ext

    # Now check length and truncate if necessary
    if len(full_sanitized) <= max_length:
        return full_sanitized

    # Keep extension and truncate the main part
    available_length = max_length - len(sanitized_ext)
    if available_length <= 0:
        # If the sanitized extension is longer than max_length, just return the truncated extension
        # This is an edge case, but ensure we return something valid
        return sanitized_ext[:max_length]

    truncated_name = sanitized_name[:available_length]
    # Ensure the truncated name doesn't end in a dot or space after truncation
    truncated_name = truncated_name.rstrip(".")

    result = truncated_name + sanitized_ext

    # Final result length check:
    if len(result) > max_length:
        # Fallback: truncate the name part more aggressively if somehow still too long
        # This could happen if sanitized_ext was different than original ext
        final_available = max_length - len(sanitized_ext)
        if final_available > 0:
            result = sanitized_name[:final_available].rstrip(".") + sanitized_ext
        else:
            result = sanitized_ext[:max_length]

    return result.strip()


def download_results(
    api_key, batch_id, input_directory, output_directory, max_wait_minutes=120, poll_interval=30
):
    """
    Download processed results for a given batch ID.

    Args:
        api_key (str): API key for authentication
        batch_id (str): Unique identifier for the batch to process
        input_directory (str): Directory where input files are located
        output_directory (str): Directory to save downloaded files
        max_wait_minutes (int): Maximum time to wait for processing (default: 60)
        poll_interval (int): Time interval between status checks (default: 120)

    Returns:
        tuple: (success_count, total_files, status_report, failed_files_map)
        - success_count: Number of successfully downloaded files
        - total_files: Total number of files in the batch
        - status_report: Dictionary with counts for each state
        - failed_files_map: Dictionary mapping 'data_id' from the batch to the original file path
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    # Define the path for the parser information CSV file
    csv_file_path = os.path.join(output_directory, "parser_information.csv")
    # Define the field names for the CSV
    csv_fieldnames = ["Source","Location", "Time", "Copyright", "Method", "Tag", "BatchID"]

    # Initialize the CSV file with headers if it doesn't exist
    if not os.path.exists(csv_file_path):
        with open(csv_file_path, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_fieldnames)
            writer.writeheader()

    # Set up the API endpoint for checking batch status
    api_url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Initialize status counters to track all possible states
    status_report = {
        "done": 0,
        "pending": 0,
        "waiting-file": 0,
        "running": 0,
        "converting": 0,
        "failed": 0,
    }
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60

    print(f"\nMonitoring batch {batch_id} for completion...")

    # Poll the API until all files are processed or timeout occurs
    while (time.time() - start_time) < max_wait_seconds:
        try:
            # Get the current status of the batch
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            batch_data = response.json().get("data", {})

            # Reset status counters and count incomplete files
            status_report = {k: 0 for k in status_report}
            incomplete_count = 0

            # Count the status of each file in the batch and identify incomplete states
            for item in batch_data.get("extract_result", []):
                state = item.get("state", "unknown")

                # Update status counter for this state
                if state in status_report:
                    status_report[state] = status_report.get(state, 0) + 1
                else:
                    # Handle any unexpected states by adding them to the report
                    status_report[state] = status_report.get(state, 0) + 1

                # Define states that indicate the file is NOT yet complete
                # Add any other incomplete states that the API might return
                incomplete_states = [
                    "converting",
                    "failed",
                    "pending",
                    "waiting-file",
                    "running",
                ]

                if state in incomplete_states:
                    incomplete_count += 1

            # If no files are still incomplete, break out of the polling loop
            if incomplete_count == 0:
                print("All files processed. Starting download...")
                break

            # Print current status and wait before next poll
            status_msg = ", ".join([f"{k}:{v}" for k, v in status_report.items()])
            print(
                f"  Status: {status_msg} | Incomplete: {incomplete_count} | Waiting {poll_interval}s..."
            )
            time.sleep(poll_interval)

        except requests.exceptions.RequestException as e:
            print(f"Status check error (network): {e}")
            time.sleep(poll_interval)
        except Exception as e:
            print(f"Status check error (general): {e}")
            time.sleep(poll_interval)
    else:
        # This else clause executes if the while loop completed without breaking
        # (i.e., timeout occurred)
        print(
            f"Timeout reached after {max_wait_minutes} minutes. Proceeding with available results..."
        )

    # Initialize download counters
    success_count = 0
    total_files = sum(status_report.values())
    # Dictionary to map data_id to original file path
    failed_files_map = {}

    try:
        # Get the final status after polling (or timeout)
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        batch_data = response.json().get("data", {})

        # Download the results for successfully processed files
        for idx, item in enumerate(batch_data.get("extract_result", [])):
            state = item.get("state", "unknown")
            original_filename = item.get("file_name", f"file_{idx}")
            # Get the data_id
            data_id = item.get("data_id", f"unknown_{idx}")

            # Truncate filename to avoid path length issues
            filename = _truncate_filename(original_filename)

            # Store failed files' data_id and potentially original path
            if state == "failed":
                # Map this back later
                failed_files_map[data_id] = None 
                print(f"File {filename} (data_id: {data_id}) failed processing.")

            # Only download if the file was processed successfully and has download URL
            if state == "done" and "full_zip_url" in item:
                # Determine the intended extraction directory (where the zip content goes)
                base_name = os.path.splitext(original_filename)[0]
                source_path = os.path.join(input_directory, original_filename)
                raw_data_path = os.path.join(output_directory, base_name)

                source_path = os.path.abspath(source_path)
                raw_data_path = os.path.abspath(raw_data_path)

                if _download_zip(item["full_zip_url"], filename, output_directory):
                    success_count += 1

                    # Prepare data for the CSV row
                    csv_row_data = {
                        # Store the path where the original input file was located if passed down
                        "Source": source_path,
                        # Store the path where the raw data is stored
                        "Location": raw_data_path,
                        # Time of processing for this file
                        "Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        # Copyright information
                        "Copyright": "N/A",
                        # Method used for processing
                        "Method": "MinerU",
                        # Tag for categorization
                        "Tag": "AgenticFin, HKUST(GZ)",
                        "BatchID": batch_id,
                    }

                    # Append the row to the CSV file
                    try:
                        # Open in append mode
                        with open(csv_file_path, mode='a', newline='', 
                        encoding='utf-8') as csvfile: 
                            writer = csv.DictWriter(csvfile, fieldnames=csv_fieldnames)
                            # Write the single row
                            writer.writerow(csv_row_data)
                        print(f"Logged successful processing for: {original_filename}")
                    except IOError as e:
                        print(f"Error writing to CSV for {original_filename}: {e}")
                else:
                    print(f"Failed to download file: {filename} (state: {state})")
            elif state != "done":
                print(f"Skipping file {filename} with state: {state}")

        # Print the completion summary
        print(f"\nBatch {batch_id} completed:")
        for state, count in status_report.items():
            if count > 0:
                print(f"  - {state.capitalize()}: {count}")
        print(f"Downloaded: {success_count}/{total_files} files")

    except requests.exceptions.RequestException as e:
        print(f"Download error (network): {str(e)}")
    except Exception as e:
        print(f"Download error (general): {str(e)}")

    return success_count, total_files, status_report, failed_files_map


def _download_zip(zip_url, original_name, output_dir):
    """Helper function to download and extract a ZIP file."""
    try:
        # Extract the base name without extension for directory creation
        base_name = os.path.splitext(original_name)[0]
        # Create a directory for this file's results
        extraction_dir = os.path.join(output_dir, base_name)
        os.makedirs(extraction_dir, exist_ok=True)

        # Download the ZIP file from the provided URL
        response = requests.get(zip_url, stream=True)
        response.raise_for_status()

        # Get the filename from the URL and create the local path
        zip_name = os.path.basename(urlparse(zip_url).path)
        zip_path = os.path.join(extraction_dir, zip_name)

        # Write the downloaded content to a local ZIP file
        with open(zip_path, "wb") as f:
            # 1MB chunks
            for chunk in response.iter_content(chunk_size=1048576):
                f.write(chunk)

        # Extract all contents from the ZIP file to the extraction directory
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extraction_dir)
        # Remove the ZIP file after extraction
        os.remove(zip_path)

        return True

    except Exception as e:
        print(f"Download/extract error for {original_name}: {e}")
        return False


def parse_pdfs(
    input_dir: str = "input",
    output_dir: str = "output",
    batch_size: int = 200,
    language: str = "en",
    check_pdf_limits=True,
):
    """Process PDFs via Mineru API and download results.

    Args:
        input_dir (str): Directory containing PDF files to process.
        output_dir (str): Directory to save processed results.
        batch_size (int): Maximum number of files per batch.
        language (str): Document language code.
        check_pdf_limits (bool): Whether to check PDF size/pages and split if needed (default: True)
    """

    # Load environment variables from .env file
    load_dotenv()

    # Get the API key from environment variables
    api_key = os.getenv("MINERU_API_KEY")
    if not api_key:
        raise ValueError("MINERU_API_KEY environment variable not set")

    # Process PDF files in batches and get the batch IDs and original file list
    batch_ids, original_files_list = check_and_process_pdfs(
        api_key=api_key,
        pdf_directory=input_dir,
        max_files_per_batch=batch_size,
        language=language,
        check_pdf_limits=check_pdf_limits,
    )

    # Since the MinerU API is currently in a trial/testing phase, it's possible that a task may be successfully submitted and a batch_id obtained, yet the results cannot be downloaded. Therefore, you can manually specify a list of batch_ids to download the parsed results.
    # batch_ids = ["4c8b91b5-xxxx-xxxx-9370-52574ee87e69"]

    # If no batches were processed successfully, return early
    if not batch_ids:
        print("\nNo batches processed successfully")
        return [], original_files_list

    # Start downloading the results for each batch
    print("\nStarting result downloads...")
    # Collect failed files maps from all batches
    all_failed_files_maps = {} 
    for batch_id in batch_ids:
        success, total, status_report, failed_map = download_results(
            api_key=api_key, batch_id=batch_id, input_directory=input_dir, output_directory=output_dir
        )
        # Store the failed map for this batch
        all_failed_files_maps[batch_id] = failed_map

    # Return the collected failed maps and the original lists
    return all_failed_files_maps, original_files_list 


def retry_failed_files(
    all_failed_files_maps, 
    original_files_list, 
    input_dir: str = "input", 
    output_dir: str = "output_retry", 
    batch_size: int = 200, 
    language: str = "en", 
    check_pdf_limits=True
):
    """
    Collects failed files from initial processing results and retries them in a new batch.

    Args:
        all_failed_files_maps (dict): Dictionary returned by parse_pdfs, mapping batch_id to failed files map.
        original_files_list (list): List of original file paths returned by parse_pdfs.
        input_dir (str): Directory containing the original PDF files.
        output_dir (str): Directory to save results of the retry batch.
        batch_size (int): Maximum number of files per retry batch.
        language (str): Document language code.
        check_pdf_limits (bool): Whether to check PDF size/pages and split if needed for retry batch.
    """
    print("\n--- Starting Retry Process for Failed Files ---")

    # Load environment variables from .env file
    load_dotenv()
    api_key = os.getenv("MINERU_API_KEY")
    if not api_key:
        raise ValueError("MINERU_API_KEY environment variable not set for retry")

    # Collect the original file paths for failed items
    # Use a set to avoid duplicates if a file was split and both parts failed
    files_to_retry = set() 

    for batch_id, failed_map in all_failed_files_maps.items():
        print(f"Analyzing batch {batch_id} for failed files...")
        if not failed_map:
            print(f"  No failed files recorded for batch {batch_id}.")
            continue

        for data_id in failed_map.keys():
            # Attempt to map data_id back to the original file path
            # This relies on the naming convention used in check_and_process_pdfs
            # Format: {truncated_name}_b{batch_index + 1}
            # Example data_id: "MyDoc_b1"
            # Extract the original truncated name part (first 16 chars of original name)
            # Split from the right, take the first part
            original_name_part = data_id.rsplit('_b', 1)[0] 
            print(f"  Looking for original file associated with data_id: {data_id} (original part: {original_name_part})")

            # Find the original file path that matches this part
            matched_original_file = None
            for orig_path in original_files_list:
                orig_basename = os.path.splitext(os.path.basename(orig_path))[0]
                truncated_orig_name = orig_basename[:16] if len(orig_basename) > 16 else orig_basename
                if truncated_orig_name == original_name_part:
                    matched_original_file = orig_path
                    break

            if matched_original_file:
                print(f"Matched data_id {data_id} to original file: {matched_original_file}")
                files_to_retry.add(matched_original_file)
            else:
                print(f"Warning: Could not find original file for data_id {data_id}")

    if not files_to_retry:
        print("\nNo files identified for retry.")
        return

    print(f"\nIdentified {len(files_to_retry)} unique files for retry.")
    print("Files to retry:")
    for f in files_to_retry:
        print(f"  - {f}")

    # Create a temporary directory to hold the files for the retry batch
    # This is necessary because the API functions expect a directory of PDFs
    temp_retry_dir = os.path.join(input_dir, "_retry_temp")
    os.makedirs(temp_retry_dir, exist_ok=True)

    # Copy the files to retry into the temporary directory
    copied_files = []
    for src_file in files_to_retry:
        if os.path.exists(src_file):
            dest_file = os.path.join(temp_retry_dir, os.path.basename(src_file))
            # Use copy2 to preserve metadata
            shutil.copy2(src_file, dest_file) 
            copied_files.append(dest_file)
        else:
            print(f"Warning: Original file for retry not found: {src_file}")

    if not copied_files:
        print("\nNo files were successfully copied for retry.")
        # Clean up temp directory if empty
        try:
            os.rmdir(temp_retry_dir)
        except OSError:
            # Directory not empty or other error, ignore for now
            pass 
        return

    print(f"\nCopied {len(copied_files)} files to temporary retry directory: {temp_retry_dir}")

    # Process the copied files in the temp directory as a new batch
    retry_batch_ids, _ = check_and_process_pdfs(
        api_key=api_key,
        pdf_directory=temp_retry_dir,
        max_files_per_batch=batch_size,
        language=language,
        # Apply limits again for the retry batch
        check_pdf_limits=check_pdf_limits, 
    )

    if not retry_batch_ids:
        print("\nRetry batch processing failed. No batch IDs obtained.")
        # Clean up temp directory
        shutil.rmtree(temp_retry_dir)
        return

    # Download results for the retry batch
    print("\nStarting result downloads for retry batch...")
    for retry_batch_id in retry_batch_ids:
        download_results(
            api_key=api_key, batch_id=retry_batch_id, input_directory=input_dir, output_directory=output_dir
        )

    # Clean up the temporary directory after processing
    print(f"\nCleaning up temporary retry directory: {temp_retry_dir}")
    shutil.rmtree(temp_retry_dir)

    print("\n--- Retry Process Completed ---")

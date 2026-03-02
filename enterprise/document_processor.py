"""
Document Processor for PLM Enterprise Platform.
Handles PDF, TXT, and CSV file processing and chunking for knowledge base ingestion.
"""

import csv
import io
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes documents into chunks suitable for embedding and knowledge base storage."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_text(self, text: str, file_name: str = "text_input") -> List[Dict[str, Any]]:
        """Process raw text into chunks."""
        chunks = self._chunk_text(text)
        return [
            {
                "content": chunk,
                "source": file_name,
                "source_type": "text",
                "file_name": file_name,
                "chunk_index": i,
            }
            for i, chunk in enumerate(chunks)
        ]

    def process_pdf(self, file_bytes: bytes, file_name: str) -> List[Dict[str, Any]]:
        """Process a PDF file into chunks."""
        try:
            import pdfplumber
        except ImportError:
            logger.error("pdfplumber not installed. Run: pip install pdfplumber")
            raise ValueError("PDF processing requires pdfplumber. Install with: pip install pdfplumber")

        text_parts: List[str] = []
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
        except Exception as e:
            logger.error(f"Failed to process PDF {file_name}: {e}")
            raise ValueError(f"Failed to process PDF: {e}")

        if not text_parts:
            raise ValueError("PDF appears to be empty or contains only images (no extractable text)")

        full_text = "\n\n".join(text_parts)
        chunks = self._chunk_text(full_text)
        return [
            {
                "content": chunk,
                "source": file_name,
                "source_type": "pdf",
                "file_name": file_name,
                "chunk_index": i,
            }
            for i, chunk in enumerate(chunks)
        ]

    def process_csv(self, file_bytes: bytes, file_name: str) -> List[Dict[str, Any]]:
        """Process a CSV file into knowledge entries (one per row)."""
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))
        entries: List[Dict[str, Any]] = []

        for i, row in enumerate(reader):
            # Combine all column values into a single content string
            parts = []
            for key, value in row.items():
                if value and value.strip():
                    parts.append(f"{key}: {value.strip()}")
            if parts:
                content = "\n".join(parts)
                entries.append({
                    "content": content,
                    "source": file_name,
                    "source_type": "csv",
                    "file_name": file_name,
                    "chunk_index": i,
                })

        if not entries:
            raise ValueError("CSV file is empty or has no valid rows")

        return entries

    def process_file(
        self, file_bytes: bytes, file_name: str, content_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Auto-detect file type and process accordingly."""
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

        if ext == "pdf" or (content_type and "pdf" in content_type):
            return self.process_pdf(file_bytes, file_name)
        elif ext == "csv" or (content_type and "csv" in content_type):
            return self.process_csv(file_bytes, file_name)
        elif ext in ("txt", "md", "log") or (content_type and "text" in content_type):
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = file_bytes.decode("latin-1")
            return self.process_text(text, file_name)
        else:
            # Try as text
            try:
                text = file_bytes.decode("utf-8")
                return self.process_text(text, file_name)
            except UnicodeDecodeError:
                raise ValueError(
                    f"Unsupported file type: .{ext}. Supported: PDF, TXT, CSV, MD"
                )

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap, respecting sentence boundaries."""
        if not text or not text.strip():
            return []

        text = text.strip()

        if len(text) <= self.chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size

            if end >= text_len:
                chunks.append(text[start:].strip())
                break

            # Try to find a sentence boundary near the end
            boundary = self._find_sentence_boundary(text, end)
            if boundary > start:
                end = boundary

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start forward, accounting for overlap
            start = end - self.chunk_overlap
            if start <= (end - self.chunk_size):
                start = end  # Prevent going backwards

        return chunks

    @staticmethod
    def _find_sentence_boundary(text: str, position: int) -> int:
        """Find the nearest sentence boundary before the given position."""
        search_start = max(0, position - 200)
        search_region = text[search_start:position]

        # Look for sentence-ending punctuation followed by space or newline
        for marker in [". ", ".\n", "! ", "!\n", "? ", "?\n", "\n\n"]:
            idx = search_region.rfind(marker)
            if idx != -1:
                return search_start + idx + len(marker)

        # Fallback: look for any newline
        idx = search_region.rfind("\n")
        if idx != -1:
            return search_start + idx + 1

        # No boundary found, split at position
        return position

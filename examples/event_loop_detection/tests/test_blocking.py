"""
Tests demonstrating pyleak catching event loop blocking.

Requires MinIO running: docker-compose up -d
Run with: uv run pytest test_blocking.py -v -s
"""

import io

import fitz
import pytest
from httpx import ASGITransport, AsyncClient
from pdf_ingest.app import app
from PIL import Image
from pyleak import EventLoopBlockError, no_event_loop_blocking


@pytest.fixture
def sample_pdf() -> bytes:
    doc = fitz.open()
    for page_num in range(3):
        page = doc.new_page()
        page.insert_text((50, 50), f"Page {page_num + 1}")

        img = Image.new("RGB", (200, 200), color=(page_num * 80, 100, 150))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page.insert_image(fitz.Rect(50, 100, 250, 300), stream=buf.getvalue())

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_blocking_endpoint_detected(sample_pdf: bytes):
    """pyleak detects blocking in /ingest/blocking endpoint."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(EventLoopBlockError) as exc_info:
            async with no_event_loop_blocking(action="raise", threshold=0.01):
                await client.post("/ingest/blocking", files={"file": ("test.pdf", sample_pdf, "application/pdf")})

    print(f"\n{'='*60}\nBLOCKING DETECTED:\n{'='*60}\n{exc_info.value}\n{'='*60}")


@pytest.mark.asyncio
async def test_async_endpoint_no_blocking(sample_pdf: bytes):
    """/ingest/async endpoint does not block the event loop."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with no_event_loop_blocking(action="raise", threshold=0.01):
            response = await client.post("/ingest/async", files={"file": ("test.pdf", sample_pdf, "application/pdf")})

    assert response.status_code == 200
    data = response.json()
    assert len(data["images"]) == 3
    print(f"\nAsync endpoint completed without blocking. Processed {data['page_count']} pages, {len(data['images'])} images.")

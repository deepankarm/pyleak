"""
PDF Document Ingestion API

Demonstrates event loop blocking vs async patterns:
- /ingest/blocking - Blocks the event loop (BAD)
- /ingest/async - Uses asyncio.to_thread (GOOD)
"""

import asyncio
import uuid

import boto3
import fitz
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

app = FastAPI(title="PDF Ingestion API")

s3_client = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",  # noqa: S106
)
BUCKET_NAME = "documents"


class ImageInfo(BaseModel):
    page: int
    index: int
    s3_url: str


class IngestResponse(BaseModel):
    document_id: str
    text: str
    images: list[ImageInfo]
    page_count: int


# --- Shared helpers ---


def _extract_text(doc: fitz.Document) -> str:
    return "\n".join(page.get_text() for page in doc)


def _extract_images(doc: fitz.Document) -> list[tuple[int, int, bytes, str]]:
    images = []
    for page_num, page in enumerate(doc):
        for img_index, img_info in enumerate(page.get_images(full=True)):
            base_image = doc.extract_image(img_info[0])
            images.append(
                (page_num + 1, img_index, base_image["image"], base_image["ext"])
            )
    return images


def _upload_to_s3(key: str, body: bytes, content_type: str):
    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=key, Body=body, ContentType=content_type
    )


# --- Blocking endpoint ---


@app.post("/ingest/blocking", response_model=IngestResponse)
async def ingest_blocking(file: UploadFile = File(...)) -> IngestResponse:
    """
    Ingest a PDF - BLOCKING VERSION.
    All operations run on the event loop and block other requests.
    """
    document_id = str(uuid.uuid4())
    pdf_bytes = await file.read()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")  # Blocks
    text = _extract_text(doc)  # Blocks
    extracted = _extract_images(doc)  # Blocks
    page_count = len(doc)
    doc.close()

    images = []
    for idx, (page_num, img_index, img_bytes, ext) in enumerate(extracted):
        s3_key = f"{document_id}/img_{idx}.{ext}"
        _upload_to_s3(s3_key, img_bytes, f"image/{ext}")  # Blocks
        images.append(
            ImageInfo(
                page=page_num, index=img_index, s3_url=f"s3://{BUCKET_NAME}/{s3_key}"
            )
        )

    return IngestResponse(
        document_id=document_id, text=text, images=images, page_count=page_count
    )


# --- Async endpoint ---


def _process_pdf_sync(
    pdf_bytes: bytes,
) -> tuple[str, int, list[tuple[int, int, bytes, str]]]:
    """Runs in thread pool via asyncio.to_thread"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = _extract_text(doc)
    images = _extract_images(doc)
    page_count = len(doc)
    doc.close()
    return text, page_count, images


async def _upload_image_async(
    document_id: str,
    idx: int,
    page_num: int,
    img_index: int,
    img_bytes: bytes,
    ext: str,
) -> ImageInfo:
    s3_key = f"{document_id}/img_{idx}.{ext}"
    await asyncio.to_thread(
        _upload_to_s3, s3_key, img_bytes, f"image/{ext}"
    )  # Offloaded to thread pool
    return ImageInfo(
        page=page_num, index=img_index, s3_url=f"s3://{BUCKET_NAME}/{s3_key}"
    )


@app.post("/ingest/async", response_model=IngestResponse)
async def ingest_async(file: UploadFile = File(...)) -> IngestResponse:
    """
    Ingest a PDF - ASYNC VERSION.
    CPU work offloaded to thread pool, S3 uploads run concurrently.
    """
    document_id = str(uuid.uuid4())
    pdf_bytes = await file.read()

    # Offload CPU-bound PDF processing to thread pool
    text, page_count, extracted = await asyncio.to_thread(_process_pdf_sync, pdf_bytes)

    # Upload images concurrently
    upload_tasks = [
        _upload_image_async(document_id, idx, page_num, img_index, img_bytes, ext)
        for idx, (page_num, img_index, img_bytes, ext) in enumerate(extracted)
    ]
    images = await asyncio.gather(*upload_tasks)

    return IngestResponse(
        document_id=document_id, text=text, images=list(images), page_count=page_count
    )


@app.get("/health")
async def health():
    return {"status": "ok"}

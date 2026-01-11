"""Generate a sample PDF for testing."""

import io
from pathlib import Path

import fitz
from PIL import Image


def create_sample_pdf(output_path: Path = Path("sample.pdf"), num_pages: int = 10):
    doc = fitz.open()
    colors = [
        (66, 133, 244),
        (234, 67, 53),
        (251, 188, 5),
        (52, 168, 83),
        (155, 89, 182),
    ]

    for page_num in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"Document Page {page_num + 1}", fontsize=24)

        for i in range(8):
            page.insert_text(
                (50, 100 + i * 25),
                f"{i + 1}. Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            )

        color = colors[page_num % len(colors)]
        img = Image.new("RGB", (200, 150), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page.insert_image(fitz.Rect(50, 350, 250, 500), stream=buf.getvalue())

    doc.save(str(output_path))
    doc.close()
    print(f"Created {output_path} ({num_pages} pages)")


if __name__ == "__main__":
    import sys

    num_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    output = sys.argv[2] if len(sys.argv) > 2 else "sample.pdf"
    create_sample_pdf(Path(output), num_pages)

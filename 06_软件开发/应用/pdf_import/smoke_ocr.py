"""Read-only recognition check against a selected real PDF page."""
import argparse
import hashlib
import json
from pathlib import Path

from .config import configure_environment
from .privacy import disable_outbound_connections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--page', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    configure_environment()
    disable_outbound_connections()
    import pymupdf
    from PIL import Image
    from .ocr import recognise_image
    with args.pdf.open('rb') as source:
        before = hashlib.file_digest(source, 'sha256').hexdigest()
    with pymupdf.open(args.pdf) as doc:
        page = doc[args.page - 1]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False, colorspace=pymupdf.csRGB)
        result = recognise_image(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
    with args.pdf.open('rb') as source:
        after = hashlib.file_digest(source, 'sha256').hexdigest()
    result.update(source_sha256=before, original_unchanged=before == after, page=args.page, network='outbound_connections_blocked')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'seconds': result['seconds'], 'lines': len(result['lines']), 'formulas': sum(v['type'] != 'text' for v in result['blocks']), 'original_unchanged': result['original_unchanged']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

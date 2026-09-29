"""
OCR Extraction — Django REST views backing the OCR Annotation UI.

Every endpoint here operates on a PDF uploaded straight from the browser to
this LOCAL Django server (127.0.0.1) and written to a per-upload temp
directory outside the repo (see storage.py) — the file itself is never
committed, never proxied elsewhere, and only exists for the lifetime of the
annotation session. Only the saved JSON *templates* it produces (box
coordinates + cell labels — no document content at all) are meant to live
in the repo.
"""

from __future__ import annotations

import base64
import io

from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from . import storage
from .renderer import get_page_count, render_page_to_image
from .script import run_template

DEFAULT_DPI = 200


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload_pdf(request):
    f = request.FILES.get("file")
    if not f:
        return Response(
            {"error": "No file uploaded (expected multipart field 'file')"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    doc_id, doc_dir = storage.new_upload_dir()
    pdf_path = doc_dir / "source.pdf"
    with open(pdf_path, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    try:
        page_count = get_page_count(str(pdf_path))
    except Exception as exc:
        storage.discard_upload(doc_id)
        return Response({"error": f"Could not read PDF: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"doc_id": doc_id, "page_count": page_count})


@api_view(["GET"])
def page_image(request):
    doc_id = request.query_params.get("doc_id", "")
    try:
        page_number = int(request.query_params.get("page", "1"))
        dpi = int(request.query_params.get("dpi", str(DEFAULT_DPI)))
    except ValueError:
        return Response({"error": "page/dpi must be integers"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        doc_dir = storage.upload_dir(doc_id)
    except (ValueError, FileNotFoundError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    pdf_path = doc_dir / "source.pdf"
    try:
        image = render_page_to_image(str(pdf_path), page_number, dpi)
    except Exception as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return Response({
        "image": f"data:image/png;base64,{encoded}",
        "width": image.width,
        "height": image.height,
        "dpi": dpi,
    })


@api_view(["DELETE"])
def discard_upload(request, doc_id):
    try:
        storage.discard_upload(doc_id)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"success": True})


@api_view(["GET"])
def list_templates(request):
    return Response({"templates": storage.list_templates()})


@api_view(["GET"])
def get_template(request, name):
    try:
        return Response(storage.load_template(name))
    except FileNotFoundError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def save_template(request):
    name = request.data.get("template_name", "")
    annotations = request.data.get("annotations", [])
    dpi = request.data.get("dpi", DEFAULT_DPI)

    if not name:
        return Response({"error": "template_name is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not annotations:
        return Response({"error": "At least one annotation is required"}, status=status.HTTP_400_BAD_REQUEST)
    for ann in annotations:
        if not ann.get("cell"):
            return Response({"error": "Every annotation needs a cell key"}, status=status.HTTP_400_BAD_REQUEST)
        for field in ("page", "x0", "y0", "x1", "y1"):
            if field not in ann:
                return Response({"error": f"Annotation for {ann.get('cell')!r} is missing {field!r}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        path = storage.save_template(name, {
            "template_name": name,
            "dpi": dpi,
            "annotations": annotations,
        })
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"success": True, "path": path})


@api_view(["DELETE"])
def delete_template(request, name):
    try:
        storage.delete_template(name)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"success": True})


@api_view(["POST"])
def run_extraction(request):
    doc_id = request.data.get("doc_id", "")
    template_name = request.data.get("template_name", "")

    try:
        doc_dir = storage.upload_dir(doc_id)
    except (ValueError, FileNotFoundError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

    pdf_path = doc_dir / "source.pdf"
    try:
        values = run_template(str(pdf_path), template_name)
    except FileNotFoundError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return Response({"error": f"OCR extraction failed: {type(exc).__name__}: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"success": True, "values": values})

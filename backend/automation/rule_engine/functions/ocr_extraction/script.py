"""
OCR Extraction — registered function for the ReactFlow workflow builder.

`ocr_extract_by_template()` renders a PDF's pages at a saved template's DPI,
crops each annotation box, and OCRs it — the same annotate-once/reuse-many
flow as the standalone OCR Annotation UI (see views.py), but callable as an
ordinary workflow node so it can be chained into a rule alongside any other
registered function — e.g. ahead of a claims_split_ub/claim_split_hcfa
function, to backfill one specific field that pipeline's own coordinate/
text-based extraction can't reliably read (the reason this whole feature
exists: some PDFs render values in a way that confuses plain text
extraction, and need actual OCR on the rendered image instead).
"""

from __future__ import annotations

from rule_engine.registry import register_function

from .ocr_engine import ocr_crop
from .renderer import render_page_to_image
from .storage import load_template


def run_template(pdf_path: str, template_name: str) -> dict:
    """Shared by the registered function below and views.run_extraction()."""
    template = load_template(template_name)
    dpi = template.get("dpi", 200)

    by_page: dict[int, list[dict]] = {}
    for ann in template.get("annotations", []):
        by_page.setdefault(int(ann["page"]), []).append(ann)

    values: dict[str, str] = {}
    for page_number, anns in sorted(by_page.items()):
        image = render_page_to_image(pdf_path, page_number, dpi)
        for ann in anns:
            box = (ann["x0"], ann["y0"], ann["x1"], ann["y1"])
            text = ocr_crop(image, box)
            values[ann["cell"]] = text
            print(f"[ocr_extraction] {ann['cell']} (page {page_number}) -> {text!r}")
    return values


@register_function(
    name="ocr_extract_by_template",
    tag="OCR Extraction",
    color="#8e44ad",
    inputs=[
        {"name": "pdf_path", "type": "str"},
        {"name": "template_name", "type": "str"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "values", "type": "dict"},
    ],
)
def ocr_extract_by_template(pdf_path: str, template_name: str, context=None):
    print(f"[ocr_extract_by_template] template={template_name!r} pdf={pdf_path!r}")
    try:
        values = run_template(pdf_path, template_name)
    except FileNotFoundError as exc:
        return {"success": False, "values": {}, "error": str(exc)}
    except Exception as exc:
        print(f"[ocr_extract_by_template] error: {exc}")
        return {"success": False, "values": {}, "error": f"{type(exc).__name__}: {exc}"}
    return {"success": True, "values": values}

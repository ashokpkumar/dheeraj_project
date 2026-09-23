"""
Claims Split UB — PART 1 (cont'd): parsing the downloaded PDF.

Ports oReadPdf.txt. Where the VBA wrote each box straight into a ClaimInfo
(CI) / ClaimServiceLInes (CS) worksheet cell, this returns plain dicts —
`extract_claim()` is the one entry point script.py calls; it returns
    {"demographics": {...}, "service_lines": [...]}
mirroring the original two-sheet split as two Python structures instead of
two Excel tabs. Same shape convention as claim_split_hcfa/pdf_extract.py,
but this is a UB-04 form, not a HCFA-1500 — every box coordinate below was
re-traced from claims_split_ub's OWN oReadPdf.txt, not copied from the HCFA
port (the two forms' box layouts share nothing in common beyond both being
CMS claim forms).

*** UNVALIDATED AGAINST A REAL PDF *** — same caveat as claim_split_hcfa's
pdf_extract.py: every box coordinate and hand-tuned offset below (e.g. the
`- 23.25` / `- 12.44` repricing/COB offsets) is ported as literally as
possible from the VBA, which was itself calibrated against a specific
rendered report layout we can't see. Needs checking against a real UB-04
claim PDF before being trusted. See pdf_backend.py's module docstring for
the underlying coordinate-conversion risk this all sits on top of.

Two real naming quirks in the source VBA, preserved here rather than
"corrected", both flagged inline where they matter:
  * oScratch.txt/oScratchNotOnline's local variable `Box70A_Pri_Dx` is
    actually populated from ClaimInfo column EW, which oReadPdf.txt itself
    labels 'Box67_Primary_Dx (the Box 67 *principal* diagnosis) — not
    Box 70A (Patient's Reason For Visit, which is columns FQ/FR/FS here).
    This dict uses `DX_PRIMARY` for column EW (matching what it actually
    is), and cps_entry.py reads `DX_PRIMARY` wherever the VBA read
    Box70A_Pri_Dx from column EW — see cps_entry.py's own comment there.
  * `PLACEVALUE Trim(wS.Range("HP" & a)), 7, 30` in UB_Scratch_NotOnline
    (oScratchNotOnline line 132) reads ClaimInfo column HP, which no
    extraction routine in oReadPdf.txt ever writes — a pre-existing gap in
    the VBA itself (same class of issue as claim_split_hcfa's documented
    "FOR PRV SELECTION" / "PROVIDER INTERNAL MANUAL ID" dead field). Kept
    as `BOX_HP_UNPOPULATED` here, always "", not silently dropped.
"""

from __future__ import annotations

from .pdf_backend import ClaimPdfReader


def _norm(s: str) -> str:
    """Mirrors NORMALIZE_EDIT_MSG VBA — collapse whitespace, uppercase, trim."""
    return " ".join((s or "").split()).upper()


# ---------------------------------------------------------------------------
# Small string helpers — mirror PoBOXADR_COLLECTIONS / REFORMAT_CITY_STATE_ZIP
# / RETURN_BLANK_VALUE VBA
# ---------------------------------------------------------------------------

_PO_BOX_VARIANTS = [
    "POST OFFICE BOX", "P.O BOX", "P.O. BOX", "P. O. BOX", "P.O.BOX",
    "P  O  BOX", "P  O BOX", "P O BOX", "POBOX",
]


def po_box_normalize(addr: str) -> str:
    """Mirrors PoBOXADR_COLLECTIONS VBA — normalize any PO Box spelling to 'PO BOX '."""
    if not addr or not addr.strip():
        return addr
    upper = addr.upper()
    for variant in _PO_BOX_VARIANTS:
        idx = upper.find(variant)
        if idx != -1:
            return addr[:idx] + "PO BOX " + addr[idx + len(variant):].lstrip()
    return addr


def reformat_city_state_zip(val: str) -> dict:
    """
    Mirrors REFORMAT_CITY_STATE_ZIP VBA. Input is a single space-separated
    "CITY STATE ZIP" line (unlike claim_split_hcfa's Box32/33, which are
    pipe-delimited multi-line blocks) — the VBA peels the ZIP off the end,
    then the STATE off what's left, leaving CITY as everything remaining.
    Note this literally takes the LAST space-separated token as ZIP and the
    one before that as STATE, so a multi-word city name is preserved
    correctly but a ZIP+4 with an embedded space (rare) would misparse —
    same limitation the VBA itself has (`InStrRev` from the end).
    """
    val = (val or "").strip()
    out = {"CITY": "", "STATE": "", "ZIP": ""}
    if not val:
        return out
    zip_idx = val.rfind(" ")
    if zip_idx == -1:
        out["CITY"] = val
        return out
    zip_code = val[zip_idx + 1:].strip()
    val = val[:zip_idx].strip()
    state_idx = val.rfind(" ")
    if state_idx == -1:
        out["STATE"] = val
        out["ZIP"] = zip_code
        return out
    state = val[state_idx + 1:].strip()
    city = val[:state_idx].strip()
    out["CITY"], out["STATE"], out["ZIP"] = city, state, zip_code
    return out


def return_blank_value(val: str) -> str:
    """Mirrors RETURN_BLANK_VALUE VBA — "" unless the trimmed value is >2 chars."""
    val = (val or "").strip()
    return val if len(val) > 2 else ""


def _strip_label_lines(text: str, *labels: str) -> str:
    """
    Removes any pipe-delimited "line" (see pdf_backend.py's `read_page`
    line-join) that is JUST one of the given box labels by itself — e.g.
    Box67's tiny printed "67" caption, or a lettered sub-box's own "A"/"B"/
    "C" caption, landing as its own separate line right next to the real
    scraped value.

    The VBA's own `Replace(val, "|67", "")` / `Replace(val, "|A", "")` only
    strips this when the label lands as a SUFFIX ("VALUE|67") — a plain
    substring replace. Confirmed against a real claim PDF that on this
    macro's actual PDF layout the label instead lands as a PREFIX
    ("67|X9934 02 A", "A|M25572", ...), which the VBA's own replace can
    never match (searching for "|67", not "67|"). This strips either order,
    matching the VBA's evident INTENT rather than its exact (apparently
    order-mismatched even in the source macro) string replace. Exact-token
    matched, not a blind substring replace, so it can't accidentally eat a
    real value that merely contains the label character sequence.

    Handles the label landing THREE different ways, all confirmed against
    real claims:
      1. As its own separate "|"-joined LINE (stripped whole).
      2. The printed box caption ("66 DX", "67", ...) sitting close enough
         to the real value that pdfplumber picks both up as words on the
         SAME line — as a leading/trailing TOKEN, space-joined with the
         value (e.g. "67 XS62623A"). Only a leading/trailing token is
         stripped (never a token in the middle), so a real value can't be
         corrupted by this pass.
      3. Confirmed via a real claim's Excel formula bar (`EW3` read back
         literally as `67XS62623A`, ZERO separator — not even a space):
         pdfplumber can fuse the caption directly onto the value as one
         single "word" with no gap at all, which pass 1/2 above can't
         detect (there's no line or token boundary to split on). Handled
         by a final literal-prefix/literal-suffix strip: if what's left
         after passes 1-2 starts or ends with one of the labels as a plain
         substring, that many characters are trimmed off the corresponding
         end. Longer labels are tried first so a short label can't
         partially eat a longer one. This is the one pass with a real,
         accepted risk: a genuine value that happens to start/end with the
         same characters as the label (e.g. a DX code starting with "67")
         would get over-trimmed — accepted because every confirmed
         real-claim case so far needed exactly this, and the labels here
         are short, low-collision box captions, not arbitrary substrings.
    """
    labels_upper = {l.upper().rstrip(".") for l in labels}
    lines = [p.strip() for p in (text or "").split("|")]
    cleaned: list[str] = []
    for line in lines:
        if line.upper().rstrip(".") in labels_upper:
            continue  # the whole line is just the label
        words = line.split(" ")
        while words and words[0].upper().rstrip(".") in labels_upper:
            words.pop(0)
        while words and words[-1].upper().rstrip(".") in labels_upper:
            words.pop()
        line = " ".join(words).strip()
        if line:
            cleaned.append(line)
    result = " ".join(cleaned).strip()

    for label in sorted(labels, key=len, reverse=True):
        label = label.rstrip(".")
        if not label:
            continue
        if result.upper().startswith(label.upper()):
            result = result[len(label):]
        if result.upper().endswith(label.upper()):
            result = result[: len(result) - len(label)]
    return result.strip()


def _collapse_code_spaces(text: str) -> str:
    """
    Removes stray internal spaces from a short alphanumeric code value —
    ICD-10/procedure/PPS/ECI codes never legitimately contain a space, but
    pdfplumber's word-boundary detection can split one printed code into
    two separate "words" on a subtle kerning/spacing gap within the glyphs
    that `read_page()` then joins back together WITH a space (same-line
    words are meant to be space-separated — correct for everything else,
    wrong for a single fused code). Confirmed against a real claim: Box70A
    Patient Dx read back "S626 23A" instead of "S62623A". Safe to apply to
    any field where a legitimate value is never more than one token.
    """
    return (text or "").replace(" ", "")


def _fix_amount_decimal(raw: str) -> str:
    """
    Best-effort recovery of a decimal point on a bare-digit currency box —
    same trick oReadPdf.txt's own "ADDED 2025.11.05" comment uses for Box47
    service-line charges (ported as `_format_box47_charges` below), applied
    here to every OTHER currency box in this module that only ever gets a
    plain `.replace(" ", ".")` in the VBA (Box39-41 value-code amounts,
    Box54/55 payer prior-payments/est-amount-due): when pdfplumber's word
    extraction doesn't preserve a space between whole and cents (unlike
    whatever spacing the proprietary DLL reader produces — see
    pdf_backend.py's module docstring on this exact tokenization risk), the
    VBA's `Replace(val, " ", ".")` is a no-op and a value like "38.00"
    comes back as the bare digits "3800" instead — confirmed against a real
    claim (Box39A Value Code Amount). NOT a VBA port — the VBA has no such
    fallback for these boxes (only Box47 does) — added specifically to
    correct this.
    """
    raw = (raw or "").strip()
    if not raw:
        return raw
    if " " in raw:
        return raw.replace(" ", ".").replace(",", "")
    digits = raw.replace(",", "")
    if len(digits) > 2 and digits.lstrip("-").isdigit():
        return f"{digits[:-2]}.{digits[-2:]}"
    return digits


def parse_multiline_name_address(raw: str) -> dict:
    """
    Splits a "|"-joined multi-line name/address block (see pdf_backend.py's
    `read_page` line-joining) into NAME/ADDR1/ADDR2/CITY/STATE/ZIP — used
    for Box 38 (Responsible Party Name and Address).

    NOT a VBA port: oReadPdf.txt reads Box 38 as ONE raw block with no
    further splitting at all (`CI.Range("BX" & rW) = NORMALIZE_EDIT_MSG(
    .ReadPage(pFile, 1, 9, 588, 308, 642)) 'Box38`, oReadPdf.txt:78) — the
    breakdown here is a Python-side addition, added to match the reference
    workbook's own Address1/Address2/City/State/Zipcode columns for this
    box. Reuses this module's own space-separated `reformat_city_state_zip`
    for the last line (this form's own convention — NOT claim_split_hcfa's
    comma-separated "City, ST Zip" shape, which doesn't apply here).
    """
    parts = [p.strip() for p in (raw or "").split("|") if p.strip()]
    out = {"NAME": "", "ADDR1": "", "ADDR2": "", "CITY": "", "STATE": "", "ZIP": ""}
    if not parts:
        return out
    out["NAME"] = parts[0]
    if len(parts) >= 2:
        out["ADDR1"] = po_box_normalize(parts[1])
    if len(parts) >= 4:
        out["ADDR2"] = po_box_normalize(parts[2])
    if len(parts) >= 3:
        csz = reformat_city_state_zip(parts[-1])
        out["CITY"], out["STATE"], out["ZIP"] = csz["CITY"], csz["STATE"], csz["ZIP"]
    return out


# ---------------------------------------------------------------------------
# CLAIM_DEMOGRAPHICS_INFORMATION — Box-by-box UB-04 page-1 extraction
# ---------------------------------------------------------------------------

def extract_demographics(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> dict:
    """Mirrors CLAIM_DEMOGRAPHICS_INFORMATION VBA (always page 1)."""
    rp = lambda l, b, r, t: _norm(reader.read_page(pdf_path, 1, l, b, r, t))  # noqa: E731

    d: dict = {"CLAIM_NO": ccn}

    d["PROVIDER_NAME"] = rp(9, 768, 185, 774)                                  # Box1
    d["PROVIDER_ADDR1"] = po_box_normalize(rp(9, 755, 185, 767))
    d["PROVIDER_ADDR2"] = po_box_normalize(rp(9, 744, 185, 755))
    box1_csz = reformat_city_state_zip(rp(9, 732, 185, 744))
    d["PROVIDER_CITY"], d["PROVIDER_STATE"], d["PROVIDER_ZIP"] = (
        box1_csz["CITY"], box1_csz["STATE"], box1_csz["ZIP"])

    d["BILLING_NAME"] = rp(185, 768, 365, 774)                                 # Box2
    d["BILLING_ADDR1"] = po_box_normalize(rp(185, 755, 365, 767))
    d["BILLING_ADDR2"] = po_box_normalize(rp(185, 744, 365, 755))
    box2_csz = reformat_city_state_zip(rp(185, 732, 365, 744))
    d["BILLING_CITY"], d["BILLING_STATE"], d["BILLING_ZIP"] = (
        box2_csz["CITY"], box2_csz["STATE"], box2_csz["ZIP"])

    d["PAT_CNTL_NO"] = rp(388, 768, 559, 774)                                  # Box3A
    d["MED_REC_NO"] = rp(388, 755, 559, 767)                                   # Box3B
    d["TYPE_OF_BILL"] = rp(559, 755, 597, 767)                                 # Box4
    d["FED_TAX_ID"] = rp(365, 732, 438, 744)                                   # Box5
    d["PERIOD_COV_FROM"] = rp(438, 732, 488, 744)                              # Box6
    d["PERIOD_COV_TO"] = rp(488, 732, 539, 744)
    d["PATIENT_NAME"] = rp(86, 719, 221, 732)                                  # Box8A
    d["PATIENT_ADDR"] = po_box_normalize(rp(301, 719, 596, 732))               # Box9A
    d["PATIENT_DOB"] = rp(9, 685, 71, 696)                                     # Box10
    d["PATIENT_SEX"] = rp(71, 685, 93, 696)                                    # Box11
    d["ADMISSION_DATE"] = rp(93, 685, 135, 696)                                # Box12
    d["ADMISSION_HR"] = rp(135, 685, 157, 696)                                 # Box13
    d["ADMISSION_TYPE"] = rp(158, 685, 179, 696)                               # Box14
    d["ADMISSION_SRC"] = rp(179, 685, 194, 696)                                # Box15
    d["DHR"] = rp(194, 685, 222, 696)                                          # Box16
    d["STAT"] = rp(222, 685, 238, 696)                                         # Box17

    # Box18-29 — 12 condition-code slots, same 20-23pt-wide band, Box29 last
    cond_code_boxes = [
        (238, 685, 266, 696), (266, 685, 286, 696), (286, 685, 309, 696), (309, 685, 330, 696),
        (330, 685, 351, 696), (351, 685, 374, 696), (374, 685, 395, 696), (395, 685, 416, 696),
        (416, 685, 438, 696), (438, 685, 459, 696), (459, 685, 481, 696), (481, 685, 505, 696),
    ]
    for i, box in enumerate(cond_code_boxes, start=18):
        d[f"COND_CODE_{i}"] = rp(*box)

    # Box31A-37A / Box31B-37B — occurrence codes/dates + occurrence-span rows
    d["OCC_A_31_CODE"] = rp(9, 662, 27, 672)
    d["OCC_A_31_DATE"] = rp(27, 662, 77, 672)
    d["OCC_A_32_CODE"] = rp(77, 662, 99, 672)
    d["OCC_A_32_DATE"] = rp(99, 662, 150, 672)
    d["OCC_A_33_CODE"] = rp(150, 662, 171, 672)
    d["OCC_A_33_DATE"] = rp(171, 662, 222, 672)
    d["OCC_A_34_CODE"] = rp(222, 662, 243, 672)
    d["OCC_A_34_DATE"] = rp(243, 662, 294, 672)
    d["OCC_SPAN_A_35_CODE"] = rp(294, 662, 315, 672)
    d["OCC_SPAN_A_35_FROM"] = rp(315, 662, 366, 672)
    d["OCC_SPAN_A_35_THRU"] = rp(366, 662, 417, 672)
    d["OCC_SPAN_A_36_CODE"] = rp(417, 662, 438, 672)
    d["OCC_SPAN_A_36_FROM"] = rp(438, 662, 489, 672)
    d["OCC_SPAN_A_36_THRU"] = rp(489, 662, 539, 672)
    d["BOX37A"] = rp(539, 662, 596, 672)

    d["OCC_B_31_CODE"] = rp(9, 649, 27, 662)
    d["OCC_B_31_DATE"] = rp(27, 649, 77, 662)
    d["OCC_B_32_CODE"] = rp(77, 649, 99, 662)
    d["OCC_B_32_DATE"] = rp(99, 649, 150, 662)
    d["OCC_B_33_CODE"] = rp(150, 649, 171, 662)
    d["OCC_B_33_DATE"] = rp(171, 649, 222, 662)
    d["OCC_B_34_CODE"] = rp(222, 649, 243, 662)
    d["OCC_B_34_DATE"] = rp(243, 649, 294, 662)
    d["OCC_SPAN_B_35_CODE"] = rp(294, 649, 315, 662)
    d["OCC_SPAN_B_35_FROM"] = rp(315, 649, 366, 662)
    d["OCC_SPAN_B_35_THRU"] = rp(366, 649, 417, 662)
    d["OCC_SPAN_B_36_CODE"] = rp(417, 649, 438, 662)
    d["OCC_SPAN_B_36_FROM"] = rp(438, 649, 489, 662)
    d["OCC_SPAN_B_36_THRU"] = rp(489, 649, 539, 662)
    d["BOX37B"] = rp(539, 662, 596, 672)  # VBA reads the SAME T=662..672 band as Box37A (oReadPdf.txt:77) — kept as-is

    box38_raw = rp(9, 588, 308, 642)                                           # Box38 (Responsible Party Name/Addr)
    d["BOX38"] = box38_raw
    box38 = parse_multiline_name_address(box38_raw)
    d["BOX38_NAME"] = box38["NAME"]
    d["BOX38_ADDR1"] = box38["ADDR1"]
    d["BOX38_ADDR2"] = box38["ADDR2"]
    d["BOX38_CITY"] = box38["CITY"]
    d["BOX38_STATE"] = box38["STATE"]
    d["BOX38_ZIP"] = box38["ZIP"]

    # Box39A-41D — 4 value-code/amount pairs x 4 rows
    value_code_boxes = [
        ("VALUE_39A", (315, 624, 338, 636), (338, 624, 409, 636)),
        ("VALUE_39B", (315, 612, 338, 624), (338, 612, 409, 624)),
        ("VALUE_39C", (315, 599, 338, 612), (338, 599, 409, 612)),
        ("VALUE_39D", (315, 587, 338, 599), (338, 587, 409, 599)),
        ("VALUE_40A", (409, 624, 431, 636), (431, 624, 501, 636)),
        ("VALUE_40B", (409, 612, 431, 624), (431, 612, 501, 624)),
        ("VALUE_40C", (409, 599, 431, 612), (431, 599, 501, 612)),
        ("VALUE_40D", (409, 587, 431, 599), (431, 587, 501, 599)),
        ("VALUE_41A", (501, 624, 524, 636), (524, 624, 596, 636)),
        ("VALUE_41B", (501, 624, 612, 624), (524, 612, 596, 624)),  # VBA reads B/T = 624/624 (0-height) for 41B code — ported literally, see oReadPdf.txt:98
        ("VALUE_41C", (501, 599, 524, 612), (524, 599, 596, 612)),
        ("VALUE_41D", (501, 587, 524, 599), (524, 587, 596, 599)),
    ]
    for key, code_box, amt_box in value_code_boxes:
        d[f"{key}_CODE"] = rp(*code_box)
        d[f"{key}_AMT"] = _fix_amount_decimal(rp(*amt_box))

    # Box50A-55A/B/C — payer name / plan ID / release info / assignment / prior payments / est amount due
    for suffix, top, bottom in (("A", 289, 276), ("B", 276, 266), ("C", 266, 253)):
        d[f"PAYER_{suffix}_NAME"] = rp(6, bottom, 171, top)
        d[f"PAYER_{suffix}_PLAN_ID"] = rp(171, bottom, 279, top)
        d[f"PAYER_{suffix}_REL_INFO"] = rp(279, bottom, 294, top)
        d[f"PAYER_{suffix}_ASG_BEN"] = rp(300, bottom, 315, top)
        d[f"PAYER_{suffix}_PRIOR_PMT"] = _fix_amount_decimal(rp(315, bottom, 387, top))
        d[f"PAYER_{suffix}_EST_DUE"] = _fix_amount_decimal(rp(387, bottom, 466, top))

    d["NPI_56"] = rp(487, 289, 596, 300)                                       # Box56
    d["BOX57"] = rp(487, 276, 596, 289)                                        # Box57
    d["BOX57_OTHER"] = rp(487, 266, 596, 276)
    d["BOX57_PRV_ID"] = rp(487, 253, 596, 266)

    for suffix, top, bottom in (("A", 240, 229), ("B", 229, 217), ("C", 217, 204)):
        d[f"INSURED_{suffix}_NAME"] = rp(6, bottom, 193, top)                  # Box58
        d[f"INSURED_{suffix}_P_REL"] = rp(193, bottom, 215, top)               # Box59
        d[f"INSURED_{suffix}_UNIQUE_ID"] = rp(215, bottom, 359, top)           # Box60
        d[f"INSURED_{suffix}_GROUP_NAME"] = rp(359, bottom, 467, top)          # Box61
        d[f"INSURED_{suffix}_GROUP_NO"] = rp(467, bottom, 596, top)            # Box62

    for suffix, top, bottom in (("A", 191, 180), ("B", 180, 168), ("C", 168, 156)):
        d[f"TREATMENT_AUTH_{suffix}"] = rp(6, bottom, 228, top)                # Box63
        d[f"DOC_CONTROL_NO_{suffix}"] = rp(228, bottom, 415, top)              # Box64
        d[f"EMPLOYER_NAME_{suffix}"] = rp(415, bottom, 596, top)               # Box65

    # *** Box66 unresolved — see module docstring "Known open issue" note.
    # Confirmed against a real claim (raw fused text "069" instead of a
    # clean "0"): this box's own printed caption bleeds into the value the
    # same way Box67/70/72's captions do. Guards against "66"/"DX" (this
    # box's own caption) AND "69" — the observed raw text ("069") strips
    # cleanly to "0" against a trailing "69", which doesn't match this
    # box's own label at all; most likely Box69's neighboring caption
    # ("69 ADMIT DX", the very next box down) bleeding in rather than
    # Box66's own — the exact mechanism is still unconfirmed (see the
    # coordinate-adjacency theory below), but stripping "69" here is a
    # pragmatic fix matched to the real observed data.
    d["BOX66_DX_VERSION"] = _collapse_code_spaces(_strip_label_lines(rp(6, 132, 14, 144), "66", "69", "DX"))  # Box66

    # Box67 principal diagnosis + Box67A-Q (17 secondary diagnoses). Every
    # code field below also goes through _collapse_code_spaces() — confirmed
    # against a real claim that pdfplumber can split one printed code into
    # two words on a kerning gap (Box70A read back "S626 23A" instead of
    # "S62623A") — these are all short alphanumeric codes that never
    # legitimately contain a space.
    d["DX_PRIMARY"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(16, 144, 71, 156)), "67"))   # Box67 (EW) — see module docstring
    dx67_boxes = {
        "A": (71, 144, 129, 156), "B": (129, 144, 185, 156), "C": (185, 144, 243, 156), "D": (243, 144, 300, 156),
        "E": (300, 144, 359, 156), "F": (359, 144, 416, 156), "G": (416, 144, 474, 156), "H": (474, 144, 531, 156),
        "I": (16, 132, 71, 144), "J": (71, 132, 129, 144), "K": (129, 132, 185, 144), "L": (185, 132, 243, 144),
        "M": (243, 132, 300, 144), "N": (300, 132, 359, 144), "O": (359, 132, 416, 144), "P": (416, 132, 474, 144),
        "Q": (474, 132, 531, 144),
    }
    for letter, box in dx67_boxes.items():
        d[f"DX_67{letter}"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(*box)), letter))

    d["DX_ADMIT_69"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(36, 120, 86, 132)), "69"))  # Box69
    d["DX_PATIENT_REASON_A_70"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(121, 120, 171, 132)), "A"))  # Box70A
    d["DX_PATIENT_REASON_B_70"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(171, 120, 222, 132)), "B"))  # Box70B
    d["DX_PATIENT_REASON_C_70"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(222, 120, 274, 132)), "C"))  # Box70C
    d["PPS_CODE_71"] = _collapse_code_spaces(_strip_label_lines(rp(301, 120, 336, 132), "71"))        # Box71
    d["ECI_A_72"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(351, 120, 408, 132)), "A"))  # Box72A-C
    d["ECI_B_72"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(408, 120, 466, 132)), "B"))
    d["ECI_C_72"] = _collapse_code_spaces(_strip_label_lines(return_blank_value(rp(466, 120, 525, 132)), "C"))

    d["PRINCIPAL_PROC_CODE_74"] = rp(6, 97, 65, 109)                           # Box74
    d["PRINCIPAL_PROC_DATE_74"] = rp(65, 97, 114, 109)
    d["OTHER_PROC_A_CODE_74"] = rp(114, 97, 171, 109)                          # Box74A-B
    d["OTHER_PROC_A_DATE_74"] = rp(171, 97, 222, 109)
    d["OTHER_PROC_B_CODE_74"] = rp(222, 97, 281, 109)
    d["OTHER_PROC_B_DATE_74"] = rp(281, 97, 330, 109)
    d["OTHER_PROC_C_CODE_74"] = rp(6, 73, 65, 84)                              # Box74C-D
    d["OTHER_PROC_C_DATE_74"] = rp(65, 73, 114, 84)
    d["OTHER_PROC_D_CODE_74"] = rp(114, 73, 171, 84)
    d["OTHER_PROC_D_DATE_74"] = rp(171, 73, 222, 84)
    d["OTHER_PROC_E_CODE_74"] = rp(222, 73, 281, 84)                           # Box74E
    d["OTHER_PROC_E_DATE_74"] = rp(281, 73, 330, 84)

    d["ATTENDING_NPI_76"] = rp(430, 109, 500, 120)                             # Box76
    d["ATTENDING_QUAL_76"] = rp(518, 109, 596, 120)
    d["ATTENDING_LAST_76"] = rp(385, 96, 493, 109)
    d["ATTENDING_FIRST_76"] = rp(514, 96, 596, 109)
    d["OPERATING_NPI_77"] = rp(430, 84, 500, 97)                               # Box77
    d["OPERATING_QUAL_77"] = rp(518, 84, 596, 97)
    d["OPERATING_LAST_77"] = rp(385, 73, 493, 84)
    d["OPERATING_FIRST_77"] = rp(514, 73, 596, 84)
    d["OTHER1_NPI_78"] = rp(430, 60, 500, 73)                                  # Box78
    d["OTHER1_QUAL_78"] = rp(518, 60, 596, 73)
    d["OTHER1_LAST_78"] = rp(385, 50, 493, 60)
    d["OTHER1_FIRST_78"] = rp(514, 50, 596, 60)
    d["OTHER2_NPI_79"] = rp(430, 37, 500, 50)                                  # Box79
    d["OTHER2_QUAL_79"] = rp(518, 37, 596, 50)
    d["OTHER2_LAST_79"] = rp(385, 26, 493, 37)
    d["OTHER2_FIRST_79"] = rp(514, 26, 596, 37)

    d["BOX_HP_UNPOPULATED"] = ""  # see module docstring — never written by any VBA extraction routine

    return d


# ---------------------------------------------------------------------------
# CLAIM_SERVICELINES_INFORMATION — Box 42-49 service-line grid
# ---------------------------------------------------------------------------

def extract_service_lines(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> list[dict]:
    """
    Mirrors CLAIM_SERVICELINES_INFORMATION VBA. Scans every page for a
    "42 REV.CD." marker (the Box 42-49 grid header), then reads up to 22
    lines per matching page — unlike claim_split_hcfa's "GoTo JUSTEXIT"
    (which stops extraction for the WHOLE PDF the moment one line comes back
    empty), a blank Box42 REV CD here only breaks out of THIS page's loop
    (mirrors `GoTo NextPage`, whose label sits right after `Next i` — i.e.
    the outer page loop keeps going).
    """
    total_pages = reader.total_pages(pdf_path)
    lines: list[dict] = []
    line_no = 0

    L = (6, 40, 220, 327, 378, 434, 508, 578)
    R = (40, 220, 327, 378, 434, 508, 578, 596)

    for page in range(1, total_pages + 1):
        if not reader.text_coordinates(pdf_path, "42 REV.CD.", page):
            continue

        t = 575
        for _ in range(22):
            rev_cd = _norm(reader.read_page(pdf_path, page, L[0], t - 11, R[0], t))
            description = _norm(reader.read_page(pdf_path, page, L[1], t - 11, R[1], t))
            hcpcs_raw = _norm(reader.read_page(pdf_path, page, L[2], t - 11, R[2], t))
            serv_date = _norm(reader.read_page(pdf_path, page, L[3], t - 11, R[3], t))
            serv_units = _norm(reader.read_page(pdf_path, page, L[4], t - 11, R[4], t))
            total_charges_raw = _norm(reader.read_page(pdf_path, page, L[5], t - 11, R[5], t))
            non_covered_raw = _norm(reader.read_page(pdf_path, page, L[6], t - 11, R[6], t))
            box49 = _norm(reader.read_page(pdf_path, page, L[7], t - 11, R[7], t))

            if not rev_cd:
                break  # mirrors `GoTo NextPage` — stop THIS page, outer page loop continues

            line_no += 1
            hcpcs_code = hcpcs_raw
            mod_a = mod_b = mod_c = mod_d = ""
            if len(hcpcs_raw) > 5:
                sp = hcpcs_raw.find(" ")
                if sp != -1:
                    hcpcs_code = hcpcs_raw[:sp].strip()
                    modifiers = hcpcs_raw[sp:].strip().split(",")
                    mods = (modifiers + ["", "", "", ""])[:4]
                    mod_a, mod_b, mod_c, mod_d = mods

            svl = {
                "CLAIM_NO": ccn,
                "LINE_NO": line_no,
                "REV_CD": rev_cd,
                "DESCRIPTION": description,
                "HCPCS_CODE": hcpcs_code,
                "MOD_A": mod_a, "MOD_B": mod_b, "MOD_C": mod_c, "MOD_D": mod_d,
                "SERV_DATE": serv_date,
                "SERV_UNITS": serv_units,
                "TOTAL_CHARGES": _format_box47_charges(total_charges_raw),
                "NON_COVERED_CHARGES": non_covered_raw.replace(" ", ".").replace(",", ""),
                "BOX49": box49,
            }
            lines.append(svl)
            t -= 12

    extract_medicare_cob_detail(reader, pdf_path, lines)
    return lines


def _format_box47_charges(raw: str) -> str:
    """
    Mirrors the VBA's Box47_TotalCharges formatting (oReadPdf.txt:534-541):
    when the raw scrape has no space (the cents weren't picked up as a
    separate token), splice one in two characters from the end before
    treating the space as a decimal point — same trick as the ADDED
    2025.11.05 comment describes.
    """
    if raw:
        if " " not in raw:
            raw = raw[:-2] + " " + raw[-2:] if len(raw) > 2 else raw
    else:
        raw = "0"
    val = raw.replace(" ", ".").replace(",", "")
    try:
        return f"{float(val):.2f}"
    except ValueError:
        return "0.00"


# ---------------------------------------------------------------------------
# MEDICARE_MEDICAID_COB_DETAIL — per-line COB figures (V:AC on CS)
# ---------------------------------------------------------------------------

def extract_medicare_cob_detail(reader: ClaimPdfReader, pdf_path: str, service_lines: list[dict]) -> None:
    """
    Mirrors MEDICARE_MEDICAID_COB_DETAIL VBA ('Added 2024.10.15). Mutates
    each entry of `service_lines` in place, matched by its 1-based line
    number against a "NNNNNN" (Format(i, "000000")) marker on the COB
    support-document page(s). `page` persists forward across service lines
    (never resets to the first COB page for a later line) — mirrors the
    VBA's CurPg carrying over between loop iterations of `i`, i.e. an
    assumption that line markers appear in ascending page order.

    If a line's marker text is found on a page but none of its "L,B,R,T"
    matches sits at the expected LINE_L=36 left-edge, that line is silently
    left without COB detail and the next line is tried from the SAME page
    (no page increment) — this is a literal port of the VBA, which has no
    retry/else branch for that specific case either (oReadPdf.txt:324-338).
    """
    total_pages = reader.total_pages(pdf_path)
    cob_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", page):
            cob_page = page
            break
    if cob_page is None:
        return

    LINE_L, DATE_FRM_L, DATE_THR_L, CPT_HCPCS_L = 36, 75, 125, 175
    CHARGES_L, PTNT_RSPNS_L, DED_L, APPVD_L, PAID_L = 229, 274, 466, 501, 546

    page = cob_page
    for i, svl in enumerate(service_lines, start=1):
        while page <= total_pages:
            coords = reader.text_coordinates(pdf_path, f"{i:06d}", page)
            if not coords:
                page += 1
                continue
            for match in coords.split("|"):
                parts = match.split(",")
                if len(parts) < 4:
                    continue
                if round(float(parts[0])) != LINE_L:
                    continue
                b, t = float(parts[1]), float(parts[3])
                svl["COB_DATE_FROM"] = _norm(reader.read_page(pdf_path, cob_page, DATE_FRM_L, b, 115, t))
                svl["COB_DATE_TO"] = _norm(reader.read_page(pdf_path, cob_page, DATE_THR_L, b, 164, t))
                svl["COB_CPT_HCPCS"] = _norm(reader.read_page(pdf_path, cob_page, CPT_HCPCS_L, b, 219, t))
                svl["COB_CHARGES"] = _norm(reader.read_page(pdf_path, cob_page, CHARGES_L, b, 264, t)).replace("$", "")
                svl["COB_PTNT_RESP"] = _norm(reader.read_page(pdf_path, cob_page, PTNT_RSPNS_L, b, 323, t)).replace("$", "")
                svl["COB_DEDUCTIBLE"] = _norm(reader.read_page(pdf_path, cob_page, DED_L, b, 481, t)).replace("$", "")
                svl["COB_APPVD"] = _norm(reader.read_page(pdf_path, cob_page, APPVD_L, b, 525, t)).replace("$", "")
                svl["COB_PAID"] = _norm(reader.read_page(pdf_path, cob_page, PAID_L, b, 566, t)).replace("$", "")
                break
            break


# ---------------------------------------------------------------------------
# CLAIM_REPRICING_INFORMATION — repricing figures + claim-level totals/flags
# ---------------------------------------------------------------------------

def extract_repricing_info(reader: ClaimPdfReader, pdf_path: str, service_lines: list[dict]) -> dict:
    """
    Mirrors CLAIM_REPRICING_INFORMATION VBA. Mutates `service_lines` in
    place (REPRICE_DATE_FROM/TO, REPRICE_HCPCS, REPRICE_CHARGES,
    REPRICE_UNITS, REPRICED, DISCOUNT, DISCOUNT_REASON per line, matched by
    position, same as the VBA writing CS rows by an incrementing `rW`) and
    returns the claim-level totals/flags dict.

    Unlike claim_split_hcfa's version (whose only claim-level fields here
    are REPRICED_IND/TIMELY_FILING/CLAIM_NTE/REPRICED_BY/METHOD_INFO), this
    macro's oReadPdf.txt ALSO reads a "HIC Number" label directly off the
    repricing page itself (a genuine structural difference from HCFA, where
    HIC/member number instead comes from Medicare_Medicaid_Cob_Information
    by scanning upward from the COB page's LINE# table — see
    extract_medicare_medicaid_cob_information() below, which does NOT
    populate HIC_NUMBER for this macro).

    Both KeyPattern label sets the VBA tries (older lowercase report layout
    AND the "ADDED 2025.11.05" uppercase/slash layout) are ported, in the
    same order, same as claim_split_hcfa's port — see that module's
    docstring for why both need trying rather than branching on
    `use_new_api`. NOTE: unlike claim_split_hcfa, this macro's "Units"
    KeyPattern does NOT branch its coordinate transform on
    `MN.chkWbClaim.Value` — oReadPdf.txt:451-455 branches only on WHICH
    box to write into (CS.Range("R") either way) using the SAME l/B/r/T
    either way, so `use_new_api` isn't threaded into this function at all.
    """
    total_pages = reader.total_pages(pdf_path)
    totals = {
        "TOTAL_REPRICED": 0.0, "TOTAL_DISCOUNTS": 0.0, "REPRICED_IND": "",
        "HIC_NUMBER": "", "REPRICED_BY": "", "CLAIM_NTE": "", "TIMELY_FILING": "",
        "METHOD_INFO": "",
    }

    repricing_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "REPRICE INFO, RENDERING PHYSICIAN, & NOTES", page):
            repricing_page = page
            break
    if repricing_page is None:
        return totals

    totals["REPRICED_IND"] = _read_labeled_field(reader, pdf_path, repricing_page, "Re-Price Ind", "RE-PRICE IND")
    totals["TIMELY_FILING"] = _read_labeled_field(reader, pdf_path, repricing_page, "Timely Filing", "TIMELY FILING")
    totals["METHOD_INFO"] = _read_labeled_field(reader, pdf_path, repricing_page, "Method", "METHOD")
    totals["CLAIM_NTE"] = _read_labeled_field(reader, pdf_path, repricing_page, "Claim NTE", "CLAIM NTE")
    totals["HIC_NUMBER"] = _read_labeled_field(
        reader, pdf_path, repricing_page, "HIC Number", "HIC NUMBER", right=432,
    ).replace(" ", "")
    totals["REPRICED_BY"] = _read_labeled_field(reader, pdf_path, repricing_page, "Re-Priced By", "RE-PRICED BY")

    key_patterns: list[tuple[str, bool]] = [
        ("Date Frm", False), ("DATE FRM", True),
        ("Date Thr", False), ("DATE THR", True),
        ("HCPCS", False), ("CPT/HCPCS", True),
        ("Charges", False), ("CHARGES", True),
        ("Units", False),
        ("/Repriced", False), ("Allowed/", True),
        ("/Ineligible", False), ("Discount/", True),
    ]
    # Legacy patterns whose box is widened by +10 on the right (mirrors the
    # VBA's "Case Else" default, oReadPdf.txt:430-435 — Date Frm/Date
    # Thr/HCPCS/Units keep the raw right edge, everything else gets +10).
    _LEGACY_WIDE = {"Charges", "/Repriced", "/Ineligible"}

    for pattern, new_style in key_patterns:
        # Gather every raw match across ALL pages first, tagged with the
        # page it came from, instead of slicing `matches[:-1]` fresh on
        # EACH page. The VBA's `For x = 0 To UBound(olSet) - 1` does the
        # latter — drops the last match on every single page — which
        # assumes each page's TextCoordinates() call always returns one
        # "junk" match beyond the real per-line ones. Confirmed against a
        # real 11-line claim split across 2 PDF pages (5 lines on one, 6 on
        # the other) that pdfplumber's own text_coordinates() does NOT
        # reliably produce that same extra junk match: dropping one match
        # per page discarded the LAST real service line's REPRICE data on
        # EACH page (entries #5 and #11 — the last line on page 2 and the
        # last line on page 3 respectively — came back with blank REPRICE
        # columns, everything else matched). Dropping is now based on
        # actual evidence — only when there are more raw matches in total
        # than real service lines — and applied once across the whole
        # document, not once per page.
        all_matches: list[tuple[int, list[str]]] = []
        page = repricing_page
        while page <= total_pages:
            coords = reader.text_coordinates(pdf_path, pattern, page)
            if coords:
                for match in coords.split("|"):
                    parts = match.split(",")
                    if len(parts) >= 4:
                        all_matches.append((page, parts))
            page += 1

        if len(all_matches) > len(service_lines):
            all_matches = all_matches[:-1]

        for rw, (match_page, parts) in enumerate(all_matches):
            l, b, r, t = (float(x) for x in parts)
            if new_style:
                l2, b2, r2, t2 = l, b - 23.25, r, t - 15.25
            else:
                l2, b2 = l, b - 15
                r2 = r + 10 if pattern in _LEGACY_WIDE else r
                t2 = b
            # `svl` is None once `rw` runs past the last real service line
            # — the VBA has no such bound (it just keeps writing
            # CS.Range("S" & rW) etc. into whatever row rW reaches next,
            # harmless in Excel), so per-line writes below are skipped past
            # the end, but the running TOTAL_REPRICED/TOTAL_DISCOUNTS sum is
            # NOT: the VBA accumulates unconditionally inside the Select
            # Case, with no rW bounds check at all (oReadPdf.txt:456-479).
            # A prior version of this port gated the whole match (read +
            # accumulate) on `rw < len(service_lines)`, silently dropping
            # every repricing match beyond the last service line from the
            # total — confirmed against a real claim where that
            # undercounted TOTAL_REPRICED/TOTAL_DISCOUNTS (990.00/330.00
            # instead of the real macro's 1390.50/463.50).
            svl = service_lines[rw] if rw < len(service_lines) else None
            if pattern in ("Date Frm", "DATE FRM"):
                if svl is not None:
                    svl["REPRICE_DATE_FROM"] = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2))
            elif pattern in ("Date Thr", "DATE THR"):
                if svl is not None:
                    svl["REPRICE_DATE_TO"] = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2))
            elif pattern in ("HCPCS", "CPT/HCPCS"):
                if svl is not None:
                    svl["REPRICE_HCPCS"] = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2))
            elif pattern in ("Charges", "CHARGES"):
                if svl is not None:
                    svl["REPRICE_CHARGES"] = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2)).replace("$", "").replace(",", "")
            elif pattern == "Units":
                if svl is not None:
                    svl["REPRICE_UNITS"] = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2)).replace(",", "")
            elif pattern in ("/Repriced", "Allowed/"):
                val = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2)).replace("$", "")
                if pattern == "Allowed/":
                    val = val.replace("REPRICED|", "").replace("REPRICED", "")
                if svl is not None:
                    svl["REPRICED"] = f"{float(val):.2f}" if val else "0.00"
                try:
                    totals["TOTAL_REPRICED"] += float(val) if val else 0.0
                except ValueError:
                    pass
            elif pattern in ("/Ineligible", "Discount/"):
                val = _norm(reader.read_page(pdf_path, match_page, l2, b2, r2, t2)).replace("$", "")
                if pattern == "Discount/":
                    val = val.replace("INELIGIBLE|", "").replace("INELIGIBLE", "")
                if svl is not None:
                    svl["DISCOUNT"] = f"{float(val):.2f}" if val else "0.00"
                    svl["DISCOUNT_REASON"] = _norm(
                        reader.read_page(pdf_path, match_page, r2, b2, r2 + 41, t2)
                    ).replace(",", "")
                try:
                    totals["TOTAL_DISCOUNTS"] += float(val) if val else 0.0
                except ValueError:
                    pass

    totals["TOTAL_REPRICED"] = round(totals["TOTAL_REPRICED"], 2)
    totals["TOTAL_DISCOUNTS"] = round(totals["TOTAL_DISCOUNTS"], 2)
    return totals


def _read_labeled_field(
    reader: ClaimPdfReader, pdf_path: str, page: int, label: str, strip_label: str, right: float = 575,
) -> str:
    coords = reader.text_coordinates(pdf_path, label, page)
    if not coords:
        return ""
    first = coords.split("|")[0].split(",")
    if len(first) < 4:
        return ""
    l, b, _r, t = (float(x) for x in first)
    text = _norm(reader.read_page(pdf_path, page, l, b, right, t))
    return text.replace(strip_label, "").strip()


# ---------------------------------------------------------------------------
# MEDICARE_MEDICAID_COB_INFORMATION — claim-level COB figures
# ---------------------------------------------------------------------------

_COB_KEY_FIELDS = {
    "Deductible": "COB_DEDUCTIBLE",
    "Coinsurance": "COB_COINSURANCE",
    "Calculated Approved Amount": "COB_CALC_APPROVED_AMT",
    "Paid": "COB_PAID_TOTAL",
    "Patient Responsibility": "COB_PATIENT_RESPONSIBILITY",
    "Non-Covered": "COB_NON_COVERED",
    "Contractual": "COB_CONTRACTUAL",
    "Medicare ID": "COB_MEDICARE_ID",
    "Other Insurance Type": "COB_OTHER_INS_TYPE",
}


def extract_medicare_medicaid_cob_information(reader: ClaimPdfReader, pdf_path: str) -> dict:
    """
    Mirrors MEDICARE_MEDICAID_COB_INFORMATION VBA. Claim-level, not per-line
    (see extract_medicare_cob_detail() above for the per-service-line COB
    reader). Note "HIC Number" is listed in the VBA's Select Case
    (oReadPdf.txt:250, writing CI column HO) but its KeyPattern array
    (indices 0-8) never actually includes "HIC Number" as a search term —
    that Case branch is dead code in the VBA itself, same class of
    pre-existing dead branch as claim_split_hcfa's "HIC Number" Select Case
    inside its own Medicare_Medicaid_Cob_Information (see that macro's
    memory notes). NOT ported here for that reason — this macro's actual
    HIC Number comes from CLAIM_REPRICING_INFORMATION's own "HIC Number"
    label read (see extract_repricing_info() above), matching what really
    runs, not the dead branch.
    """
    total_pages = reader.total_pages(pdf_path)
    out = {v: "" for v in _COB_KEY_FIELDS.values()}
    out["COB_ADJUSTMENT_DETAIL"] = ""

    cob_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", page):
            cob_page = page
            break
    if cob_page is None:
        return out

    for label, key in _COB_KEY_FIELDS.items():
        coords = reader.text_coordinates(pdf_path, label, cob_page)
        if not coords:
            continue
        first = coords.split("|")[0].split(",")
        if len(first) < 4:
            continue
        l, b, _r, t = (float(x) for x in first)
        val = _norm(reader.read_page(pdf_path, cob_page, l, b, 432, t))
        val = val.replace(label.upper(), "").replace(" ", "")
        out[key] = val

    marker = reader.text_coordinates(pdf_path, "SEQ) GRP CD, ADJ RSN: AMT", cob_page)
    pieces = marker.split("|") if marker else []
    adj_parts: list[str] = []
    for piece in pieces:
        parts = piece.split(",")
        if len(parts) < 4:
            continue
        b = round(float(parts[1]))
        t = round(float(parts[3]))
        right = round(float(parts[2]))
        header_text = reader.read_page(pdf_path, cob_page, 36, b, right, t)
        if "LINE#" in header_text.upper():
            bb, tt = float(b), float(t)
            for _ in range(22):
                bb -= 12.44
                tt -= 12.44
                val = reader.read_page(pdf_path, cob_page, float(parts[0]), bb, right, tt).replace(" ", "")
                if not val:
                    val = reader.read_page(pdf_path, cob_page, float(parts[0]) + 5, bb + 5, right, tt + 5).replace(" ", "")
                if val:
                    adj_parts.append(val)
        else:
            bb, tt = float(b), float(t)
            for i in range(1, 5):
                bb -= 9
                tt -= 8
                val = reader.read_page(pdf_path, cob_page, float(parts[0]), bb, right, tt).replace(" ", "")
                if val.startswith(f"{i})"):
                    adj_parts.append(val)
    out["COB_ADJUSTMENT_DETAIL"] = " ".join(adj_parts).strip()
    return out


# ---------------------------------------------------------------------------
# Top-level entry point — script.py calls this once per claim
# ---------------------------------------------------------------------------

def extract_claim(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> dict:
    """
    Mirrors the sequence Main.txt's cmdRUN_Click runs per claim during
    "02.GET EDI DETAILS": demographics, then service lines (which pulls in
    COB detail per line), then repricing (mutates service lines further and
    yields claim-level totals/flags), then claim-level COB, rolling up total
    charges the same way Main.txt does (`CI.Range("HB" & x) = TotalCharges`,
    accumulated inside CLAIM_SERVICELINES_INFORMATION itself in the VBA —
    done here as a post-pass sum instead, same value either way).
    """
    demographics = extract_demographics(reader, pdf_path, ccn)
    service_lines = extract_service_lines(reader, pdf_path, ccn)

    total_charges = 0.0
    for svl in service_lines:
        try:
            total_charges += float(svl.get("TOTAL_CHARGES") or 0)
        except ValueError:
            print(f"[{ccn}] WARNING: service line {svl.get('LINE_NO')} has a "
                  f"non-numeric TOTAL_CHARGES value {svl.get('TOTAL_CHARGES')!r} — excluded from TOTAL_CHARGES")
    demographics["TOTAL_CHARGES"] = f"{total_charges:.2f}"

    totals = extract_repricing_info(reader, pdf_path, service_lines)
    demographics["TOTAL_REPRICED"] = f"{totals['TOTAL_REPRICED']:.2f}" if totals["TOTAL_REPRICED"] else "-"
    demographics["TOTAL_DISCOUNTS"] = f"{totals['TOTAL_DISCOUNTS']:.2f}" if totals["TOTAL_DISCOUNTS"] else "-"
    demographics["REPRICED_IND"] = totals["REPRICED_IND"]
    demographics["HIC_NUMBER"] = totals["HIC_NUMBER"]
    demographics["REPRICED_BY"] = totals["REPRICED_BY"]
    demographics["CLAIM_NTE"] = totals["CLAIM_NTE"]
    demographics["TIMELY_FILING"] = totals["TIMELY_FILING"]
    demographics["METHOD_INFO"] = totals["METHOD_INFO"]

    demographics.update(extract_medicare_medicaid_cob_information(reader, pdf_path))

    return {"demographics": demographics, "service_lines": service_lines}

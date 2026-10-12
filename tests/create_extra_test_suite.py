#!/usr/bin/env python3
"""Generates tests/extra_corpus and tests/extra_questions.json for stress testing MC3.

Covers:
- Swapped withdrawn/current revisions
- Decoy files with similar values
- 3-hop reasoning chains
- Answers in 2nd XLSX sheets
- Answers in DOCX tables
- Answers only in new images (PNG/JPG rendered via PIL)
- Python constants with old values in comments
- Questions answerable only from encrypted files (refusal)
- Unanswerable queries (refusal)
- Edge cases: empty folder, unknown binary file, chmod 000 file
"""
import json
import os
import shutil
import stat
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import docx
import openpyxl

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PROJ_ROOT = Path(__file__).resolve().parent.parent
SRC_CORPUS = PROJ_ROOT / "mc3-corpus"
EXTRA_CORPUS = PROJ_ROOT / "tests" / "extra_corpus"
QUESTIONS_FILE = PROJ_ROOT / "tests" / "extra_questions.json"


def create_simple_pdf(path: Path, text: str):
    """Create a valid single-page PDF with given text using ReportLab."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    for line in text.split("\n"):
        c.drawString(50, y, line)
        y -= 20
    c.save()


def main():
    if EXTRA_CORPUS.exists():
        shutil.rmtree(EXTRA_CORPUS)
    shutil.copytree(SRC_CORPUS, EXTRA_CORPUS)

    # 1. Swapped revisions
    # specs/accelerator_v3_r1.pdf (Active) vs specs/accelerator_v3_r2_WITHDRAWN.pdf (Withdrawn)
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "accelerator_v3_r1.pdf",
        "Accelerator v3 Hardware Specifications. Status: Production. Maximum TDP: 350W. Recommended voltage: 1.1V."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "accelerator_v3_r2_WITHDRAWN.pdf",
        "[WITHDRAWN] NOTICE: Superseded draft. Do not cite. Maximum TDP: 420W. Test voltage: 1.25V."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq80_power_spec_revA.pdf",
        "TQ-80 Power Subsystem Specification. Status: ACTIVE APPROVED. Core supply voltage: 0.85V. Quiescent current: 4.2A."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq80_power_spec_revB_OBSOLETE.pdf",
        "STATUS: OBSOLETE DEPRECATED. TQ-80 Power Spec Rev B. Core supply voltage: 0.95V."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq50_thermal_guidelines_v2.pdf",
        "THIS DOCUMENT IS SUPERSEDED. TQ-50 thermal flow. Recommended airflow: 120 CFM."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq50_thermal_guidelines_v3.pdf",
        "Status: CURRENT RELEASE. TQ-50 thermal guidelines v3. Recommended airflow: 85 CFM."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq30_architecture_DEPRECATED.pdf",
        "STATUS: DEPRECATED WITHDRAWN. TQ-30 Controller. Host interface: x16 PCIe Gen4."
    )
    create_simple_pdf(
        EXTRA_CORPUS / "specs" / "tq30_architecture_current.pdf",
        "Status: ACTIVE. TQ-30 Controller. Host interface width: x8."
    )

    # 2. Decoy files with similar values
    (EXTRA_CORPUS / "planning" / "headcount_budget_tq90.txt").write_text(
        "TQ-90 compute cluster total personnel and operational budget: 4500000 USD.\nApproved by Finance.\n"
    )
    (EXTRA_CORPUS / "planning" / "capex_budget_tq90.txt").write_text(
        "TQ-90 compute cluster hardware capex budget: 3200000 USD.\nExcludes staff operations.\n"
    )
    (EXTRA_CORPUS / "specs" / "main_psu_specs.txt").write_text(
        "Main power supply standby power dissipation: 15W. Full load: 1200W.\n"
    )
    (EXTRA_CORPUS / "specs" / "auxiliary_psu_specs.txt").write_text(
        "Auxiliary power supply standby power dissipation: 3.5W. Auxiliary bus: 12V.\n"
    )
    (EXTRA_CORPUS / "planning" / "datacenter_room_a_policy.txt").write_text(
        "Server Room A HVAC policy. Maximum allowable ambient temperature: 28C.\n"
    )
    (EXTRA_CORPUS / "planning" / "datacenter_room_b_policy.txt").write_text(
        "Server Room B high-density zone HVAC policy. Maximum allowable ambient temperature: 22C.\n"
    )
    (EXTRA_CORPUS / "specs" / "primary_core_clocks.txt").write_text(
        "Primary processor base clock rate: 2400 MHz. Turbo: 3100 MHz.\n"
    )
    (EXTRA_CORPUS / "specs" / "secondary_coprocessor_clocks.txt").write_text(
        "Secondary coprocessor fixed clock rate: 1600 MHz. Voltage: 0.9V.\n"
    )

    # 3. 3-hop reasoning chains
    (EXTRA_CORPUS / "logs" / "incident_2026-10-01.log").write_text(
        "2026-10-01T14:22:01Z node-12 CRITICAL alert: hardware fault in rack logged under incident INC-9901\n"
    )
    (EXTRA_CORPUS / "support" / "asset_registry.csv").write_text(
        "incident_id,asset_id,dispatch_code\nINC-9901,AST-7721,DSP-884\n"
    )
    # create support/batch_manifest.xlsx
    wb_manifest = openpyxl.Workbook()
    ws_m = wb_manifest.active
    ws_m.title = "Assets"
    ws_m.append(["asset_id", "vendor_sn", "status"])
    ws_m.append(["AST-7721", "SN-8849-X", "replaced"])
    wb_manifest.save(EXTRA_CORPUS / "support" / "batch_manifest.xlsx")

    (EXTRA_CORPUS / "logs" / "deploy_error.log").write_text(
        "2026-10-02T08:11:32Z Cluster K8S-EAST fatal rollout error in configuration CFG-4412\n"
    )
    (EXTRA_CORPUS / "engineering" / "config_map.csv").write_text(
        "config_id,module_name,version\nCFG-4412,pipeline_router,2.1.0\n"
    )
    (EXTRA_CORPUS / "engineering" / "router_settings.txt").write_text(
        "Service pipeline_router configuration:\nnetwork.listen_port = 9092\nworker_threads = 4\n"
    )

    (EXTRA_CORPUS / "support" / "orders.csv").write_text(
        "po_number,tracking_code,vendor\nPO-55102,TRK-8819,Orrery\n"
    )
    (EXTRA_CORPUS / "support" / "shipments.txt").write_text(
        "Shipment log:\nTracking TRK-8819 delivered chassis assembly CHS-301 to facility B\n"
    )
    (EXTRA_CORPUS / "support" / "warranty_tiers.csv").write_text(
        "chassis_model,warranty_tier,sla_hours\nCHS-301,Gold-24x7,4\n"
    )

    (EXTRA_CORPUS / "logs" / "pcie_telemetry.log").write_text(
        "2026-10-03T11:00:00Z WARN: PCIe link width degraded to x1 on host srv-node-42\n"
    )
    (EXTRA_CORPUS / "engineering" / "inventory_hosts.csv").write_text(
        "host_id,image_profile,rack\nsrv-node-42,IMG-ROCKY-9,Rack-04\n"
    )
    (EXTRA_CORPUS / "engineering" / "build_catalog.txt").write_text(
        "Deployment profile catalog:\nProfile IMG-ROCKY-9 bundles firmware build 8812-B with security fix.\n"
    )

    # 4. Answers in 2nd XLSX sheets
    wb_rma = openpyxl.Workbook()
    ws_rma1 = wb_rma.active
    ws_rma1.title = "Summary"
    ws_rma1.append(["Metric", "Count"])
    ws_rma1.append(["Open RMAs", 14])
    ws_rma2 = wb_rma.create_sheet(title="Parts_Catalog")
    ws_rma2.append(["Part Name", "SKU", "Lead Time Days"])
    ws_rma2.append(["High-pressure coolant pump", "PMP-9942-C", 45])
    ws_rma2.append(["Thermal bypass valve", "VLV-1102-A", 14])
    wb_rma.save(EXTRA_CORPUS / "support" / "rma_extended.xlsx")

    wb_comp = openpyxl.Workbook()
    ws_c1 = wb_comp.active
    ws_c1.title = "General"
    ws_c1.append(["Item", "Revision"])
    ws_c1.append(["Board", "Rev-1"])
    ws_c2 = wb_comp.create_sheet(title="Environmental")
    ws_c2.append(["Component", "Min Temp C", "Max Temp C", "Burn-in Hours"])
    ws_c2.append(["Optical transceiver", -20, 85, 168])
    wb_comp.save(EXTRA_CORPUS / "support" / "component_matrix.xlsx")

    # 5. Answers in DOCX tables
    doc_matrix = docx.Document()
    doc_matrix.add_heading("Hardware Subsystem Specification Matrix", level=1)
    doc_matrix.add_paragraph("Approved design parameters for next-generation silicon targets:")
    tbl = doc_matrix.add_table(rows=1, cols=3)
    hdr_cells = tbl.rows[0].cells
    hdr_cells[0].text = "Subsystem"
    hdr_cells[1].text = "Target Clock MHz"
    hdr_cells[2].text = "Power Target W"
    
    rows_data = [
        ("Matrix Engine", "1850", "120"),
        ("Vector Core", "2100", "95"),
        ("L3 Cache Tile", "3200", "45"),
        ("Host Memory Controller", "512", "60"),
    ]
    for r in rows_data:
        row_cells = tbl.add_row().cells
        row_cells[0].text = r[0]
        row_cells[1].text = r[1]
        row_cells[2].text = r[2]
    doc_matrix.save(EXTRA_CORPUS / "planning" / "spec_matrix.docx")

    # 6. Answers only in new images (rendered using PIL)
    # Image 1: specs/pcie_bracket.png
    im1 = Image.new("RGB", (600, 200), color=(255, 255, 255))
    d1 = ImageDraw.Draw(im1)
    d1.text((30, 30), "MECHANICAL SPECIFICATION - TQ ACCESSORIES", fill=(0, 0, 0))
    d1.text((30, 70), "PART NUMBER: BKT-5521-A", fill=(0, 0, 0))
    d1.text((30, 110), "SLOT FORM FACTOR: 2-SLOT FULL HEIGHT", fill=(0, 0, 0))
    d1.text((30, 150), "MATERIAL: STAINLESS STEEL 304", fill=(0, 0, 0))
    im1.save(EXTRA_CORPUS / "specs" / "pcie_bracket.png")

    # Image 2: support/warranty_sticker.jpg
    im2 = Image.new("RGB", (500, 200), color=(240, 240, 240))
    d2 = ImageDraw.Draw(im2)
    d2.text((20, 20), "OFFICIAL SERVICE WARRANTY SEAL", fill=(0, 0, 0))
    d2.text((20, 60), "WARRANTY CODE: W-99120-X", fill=(0, 0, 0))
    d2.text((20, 100), "STATUS: FACTORY VERIFIED", fill=(0, 0, 0))
    d2.text((20, 140), "VALID THRU: 2029-12-31", fill=(0, 0, 0))
    im2.save(EXTRA_CORPUS / "support" / "warranty_sticker.jpg")

    # Image 3: support/motherboard_barcode.png
    im3 = Image.new("RGB", (500, 180), color=(255, 255, 255))
    d3 = ImageDraw.Draw(im3)
    d3.text((20, 30), "SYSTEM MOTHERBOARD TRACEABILITY", fill=(0, 0, 0))
    d3.text((20, 70), "ASSY SN: MB-2026-9041", fill=(0, 0, 0))
    d3.text((20, 110), "FAB LOCATION: TAIWAN LOT 4", fill=(0, 0, 0))
    im3.save(EXTRA_CORPUS / "support" / "motherboard_barcode.png")

    # Image 4: support/heatsink_badge.jpg
    im4 = Image.new("RGB", (450, 180), color=(245, 245, 245))
    d4 = ImageDraw.Draw(im4)
    d4.text((20, 30), "COPPER VAPOR CHAMBER HEATSINK", fill=(0, 0, 0))
    d4.text((20, 70), "INSPECTION STAMP: QC-PASS-77", fill=(0, 0, 0))
    d4.text((20, 110), "FLATNESS TOLERANCE: 0.02MM", fill=(0, 0, 0))
    im4.save(EXTRA_CORPUS / "support" / "heatsink_badge.jpg")

    # 7. Python constants with old values in comments
    (EXTRA_CORPUS / "engineering" / "network_daemon.py").write_text(
        '"""Network daemon configuration."""\n'
        '# Previous retry limit was 5 before refactoring in Q2\n'
        '# RETRY_LIMIT = 5\n'
        'RETRY_LIMIT = 12\n\n'
        '# Old socket timeout was 30 seconds; increased for heavy load\n'
        '# SOCKET_TIMEOUT = 30\n'
        'SOCKET_TIMEOUT = 75\n'
    )
    (EXTRA_CORPUS / "engineering" / "event_processor.py").write_text(
        '"""Event processing worker service."""\n'
        '# Initial thread pool size of 8 caused bottleneck\n'
        '# WORKER_POOL_SIZE = 8\n'
        'WORKER_POOL_SIZE = 32\n\n'
        '# Legacy heartbeat 10s was too frequent\n'
        '# HEARTBEAT_INTERVAL_S = 10\n'
        'HEARTBEAT_INTERVAL_S = 25\n'
    )

    # 8. Extra Edge Cases:
    # Empty folder
    (EXTRA_CORPUS / "archive" / "empty_subfolder").mkdir(parents=True, exist_ok=True)
    # Unknown file type
    (EXTRA_CORPUS / "engineering" / "firmware_dump.bin").write_bytes(os.urandom(256))
    # chmod 000 file
    locked_file = EXTRA_CORPUS / "support" / "locked_audit.log"
    locked_file.write_text("Confidential security audit record - should not be readable\n")
    try:
        locked_file.chmod(0o000)
    except Exception:
        pass

    # Build the 42 questions
    questions = [
        # Swapped revisions (1-4)
        {
            "n": 1,
            "query": "What is the maximum TDP of the accelerator v3?",
            "expected_answer": "350",
            "expected_citations": ["specs/accelerator_v3_r1.pdf"],
            "category": "swapped revision trap"
        },
        {
            "n": 2,
            "query": "What is the core voltage specification for the TQ-80 board?",
            "expected_answer": "0.85",
            "expected_citations": ["specs/tq80_power_spec_revA.pdf"],
            "category": "swapped revision trap"
        },
        {
            "n": 3,
            "query": "What is the recommended airflow in CFM for the TQ-50 chassis?",
            "expected_answer": "85",
            "expected_citations": ["specs/tq50_thermal_guidelines_v3.pdf"],
            "category": "superseded revision trap"
        },
        {
            "n": 4,
            "query": "What is the host interface width for the TQ-30 controller?",
            "expected_answer": "x8",
            "answer_aliases": ["x8 PCIe Gen5", "PCIe Gen5", "x8"],
            "expected_citations": ["specs/tq30_architecture_current.pdf"],
            "category": "deprecated revision trap"
        },
        # Decoys with similar values (5-8)
        {
            "n": 5,
            "query": "What is the hardware capex budget for the TQ-90 compute cluster?",
            "expected_answer": "3200000",
            "expected_citations": ["planning/capex_budget_tq90.txt"],
            "category": "decoy value trap"
        },
        {
            "n": 6,
            "query": "What is the standby power dissipation of the auxiliary power supply?",
            "expected_answer": "3.5",
            "expected_citations": ["specs/auxiliary_psu_specs.txt"],
            "category": "decoy value trap"
        },
        {
            "n": 7,
            "query": "What is the maximum allowable ambient temperature in Server Room B?",
            "expected_answer": "22",
            "expected_citations": ["planning/datacenter_room_b_policy.txt"],
            "category": "decoy zone trap"
        },
        {
            "n": 8,
            "query": "What is the target clock rate of the secondary coprocessor?",
            "expected_answer": "1600",
            "expected_citations": ["specs/secondary_coprocessor_clocks.txt"],
            "category": "decoy processor trap"
        },
        # 3-hop chains (9-12)
        {
            "n": 9,
            "query": "What is the vendor serial number of the asset replaced in incident INC-9901?",
            "expected_answer": "SN-8849-X",
            "expected_citations": ["logs/incident_2026-10-01.log", "support/asset_registry.csv", "support/batch_manifest.xlsx"],
            "category": "3-hop chain"
        },
        {
            "n": 10,
            "query": "Which listen port is configured for the module that failed in cluster K8S-EAST?",
            "expected_answer": "9092",
            "expected_citations": ["engineering/config_map.csv", "engineering/router_settings.txt", "logs/deploy_error.log"],
            "category": "3-hop chain"
        },
        {
            "n": 11,
            "query": "What is the warranty tier for the chassis delivered on PO-55102?",
            "expected_answer": "Gold-24x7",
            "expected_citations": ["support/orders.csv", "support/shipments.txt", "support/warranty_tiers.csv"],
            "category": "3-hop chain"
        },
        {
            "n": 12,
            "query": "What is the firmware build number installed on the host reporting GPU PCIe link degradation?",
            "expected_answer": "8812-B",
            "expected_citations": ["engineering/build_catalog.txt", "engineering/inventory_hosts.csv", "logs/pcie_telemetry.log"],
            "category": "3-hop chain"
        },
        # Answers in second XLSX sheets (13-16)
        {
            "n": 13,
            "query": "What is the part SKU for the high-pressure coolant pump?",
            "expected_answer": "PMP-9942-C",
            "expected_citations": ["support/rma_extended.xlsx"],
            "category": "second xlsx sheet"
        },
        {
            "n": 14,
            "query": "What is the lead time in days for the high-pressure coolant pump?",
            "expected_answer": "45",
            "expected_citations": ["support/rma_extended.xlsx"],
            "category": "second xlsx sheet"
        },
        {
            "n": 15,
            "query": "What is the minimum operating temperature in Celsius for the optical transceiver?",
            "expected_answer": "-20",
            "expected_citations": ["support/component_matrix.xlsx"],
            "category": "second xlsx sheet"
        },
        {
            "n": 16,
            "query": "What is the test duration in hours for the burn-in cycle in the qualification sheet?",
            "expected_answer": "168",
            "expected_citations": ["support/component_matrix.xlsx"],
            "category": "second xlsx sheet"
        },
        # Answers in DOCX tables (17-20)
        {
            "n": 17,
            "query": "What is the target clock frequency in MHz of the Matrix Engine?",
            "expected_answer": "1850",
            "expected_citations": ["planning/spec_matrix.docx"],
            "category": "docx table"
        },
        {
            "n": 18,
            "query": "What is the power target in Watts for the Vector Core?",
            "expected_answer": "95",
            "expected_citations": ["planning/spec_matrix.docx"],
            "category": "docx table"
        },
        {
            "n": 19,
            "query": "What is the target clock frequency in MHz for the L3 cache tile?",
            "expected_answer": "3200",
            "expected_citations": ["planning/spec_matrix.docx"],
            "category": "docx table"
        },
        {
            "n": 20,
            "query": "What is the target clock frequency in MHz of the Host Memory Controller?",
            "expected_answer": "512",
            "expected_citations": ["planning/spec_matrix.docx"],
            "category": "docx table"
        },
        # Answers only in new images (21-24)
        {
            "n": 21,
            "query": "What is the part number of the PCIe bracket?",
            "expected_answer": "BKT-5521-A",
            "expected_citations": ["specs/pcie_bracket.png"],
            "category": "image vision png"
        },
        {
            "n": 22,
            "query": "What is the warranty code printed on the warranty sticker?",
            "expected_answer": "W-99120-X",
            "expected_citations": ["support/warranty_sticker.jpg"],
            "category": "image vision jpg"
        },
        {
            "n": 23,
            "query": "What is the ASSY SN on the motherboard traceability label?",
            "expected_answer": "MB-2026-9041",
            "expected_citations": ["support/motherboard_barcode.png"],
            "category": "image vision png"
        },
        {
            "n": 24,
            "query": "What is the inspection stamp ID on the heatsink badge?",
            "expected_answer": "QC-PASS-77",
            "expected_citations": ["support/heatsink_badge.jpg"],
            "category": "image vision jpg"
        },
        # Python constants with old values in comments (25-28)
        {
            "n": 25,
            "query": "What is the configured retry limit in the network daemon?",
            "expected_answer": "12",
            "expected_citations": ["engineering/network_daemon.py"],
            "category": "python constant comment trap"
        },
        {
            "n": 26,
            "query": "What is the socket timeout in seconds in the network daemon?",
            "expected_answer": "75",
            "expected_citations": ["engineering/network_daemon.py"],
            "category": "python constant comment trap"
        },
        {
            "n": 27,
            "query": "What is the worker thread pool size in the event processor?",
            "expected_answer": "32",
            "expected_citations": ["engineering/event_processor.py"],
            "category": "python constant comment trap"
        },
        {
            "n": 28,
            "query": "What is the heartbeat interval in seconds in the event processor?",
            "expected_answer": "25",
            "expected_citations": ["engineering/event_processor.py"],
            "category": "python constant comment trap"
        },
        # Encrypted file questions (29-32) - refusal
        {
            "n": 29,
            "query": "What is the penalty fee percentage specified in the supplier agreement?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "encrypted refusal"
        },
        {
            "n": 30,
            "query": "What is the minimum annual purchase volume in the supplier agreement?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "encrypted refusal"
        },
        {
            "n": 31,
            "query": "What is the arbitration jurisdiction named in the encrypted vendor contract?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "encrypted refusal"
        },
        {
            "n": 32,
            "query": "What is the late delivery credit percentage in the encrypted supplier agreement?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "encrypted refusal"
        },
        # Unanswerable questions (33-36) - refusal
        {
            "n": 33,
            "query": "What is the internal clock jitter specification for the TQ-999?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "unanswerable refusal"
        },
        {
            "n": 34,
            "query": "What is the shipping weight of the pallet delivery for order 99281?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "unanswerable refusal"
        },
        {
            "n": 35,
            "query": "Which quantum encryption algorithm is used by the Meridian cluster?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "unanswerable refusal"
        },
        {
            "n": 36,
            "query": "What is the chemical purity rating of the thermal interface paste?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "unanswerable refusal"
        },
        # Regression checks from baseline corpus (37-40)
        {
            "n": 37,
            "query": "Which firmware release addressed the PCIe doorbell hang under small-batch load?",
            "expected_answer": "4.3.1",
            "expected_citations": ["engineering/meridian_release_notes.txt", "support/bug_database.csv"],
            "category": "text search"
        },
        {
            "n": 38,
            "query": "What is the maximum junction temperature of the TQ-40?",
            "expected_answer": "94",
            "expected_citations": ["specs/tq40_datasheet_r2.pdf"],
            "category": "superseded trap baseline"
        },
        {
            "n": 39,
            "query": "What board revision is printed on the asset label?",
            "expected_answer": "REV-C2",
            "expected_citations": ["support/asset_label.jpg"],
            "category": "multimodal baseline"
        },
        {
            "n": 40,
            "query": "What error code is logged when the thermal throttle engages?",
            "expected_answer": "E7731",
            "expected_citations": ["logs/prod_inference_2026-09-02.log"],
            "category": "log baseline"
        },
        # Withdrawn-only and unknown file edge cases (41-42) - refusal
        {
            "n": 41,
            "query": "What is the maximum junction temperature of the TQ-10?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "withdrawn only refusal"
        },
        {
            "n": 42,
            "query": "What is the memory size in GiB reported in the telemetry dump file?",
            "expected_answer": "",
            "expected_citations": [],
            "category": "unknown binary refusal"
        }
    ]

    out_data = {
        "challenge": "mini-challenge-3",
        "description": "Extra stress test suite with 42 questions across all edge cases.",
        "corpus": "tests/extra_corpus",
        "queries": questions,
        "seed": 42
    }

    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"Generated {len(questions)} questions in {QUESTIONS_FILE}")
    print(f"Generated extra corpus at {EXTRA_CORPUS}")


if __name__ == "__main__":
    main()

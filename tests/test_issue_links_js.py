"""frontend/issue_links.js — uyarıdan planlamaya derin bağlantı (Node ile çalıştırılır)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.readiness import check_blocks
from app.manifest.planning import read_blocks

ROOT = Path(__file__).resolve().parent.parent
MODULE = (ROOT / "frontend" / "issue_links.js").as_uri()
FIXTURE = ROOT / "tests" / "fixtures" / "seat_template_ekim.xlsx"
NODE = shutil.which("node")

BLOCKS = [
    {"lead_row": 4, "rows": [4, 5, 6], "lead_name": "AHMET YILMAZ",
     "passengers": [
         {"row": 4, "name": "AHMET YILMAZ", "passport_no": "U1", "nationality": "TUR", "sex": "M"},
         {"row": 5, "name": "", "passport_no": "", "nationality": "TUR", "sex": "F"},
         {"row": 6, "name": "ŞEYMA ÖZTÜRK", "passport_no": "DUP1", "nationality": "TUR", "sex": "F"},
     ]},
    {"lead_row": 83, "rows": [83, 84], "lead_name": "JOHN SMITH",
     "passengers": [
         {"row": 83, "name": "JOHN SMITH", "passport_no": "GB1", "nationality": "GBR", "sex": "M"},
         {"row": 84, "name": "JANE SMITH", "passport_no": "DUP1", "nationality": "GBR", "sex": "F"},
     ]},
]
ISSUES = [
    {"code": "missing_pickup", "lead_row": 83, "message": "Satır 83: pickup eksik."},
    {"code": "missing_pickup", "lead_row": 4, "lead_name": "AHMET Y.", "message": "x"},
    {"code": "missing_identity", "lead_row": 4, "row": 5, "message": "Satır 5: isim, pasaport/kimlik no eksik."},
    {"code": "duplicate_document", "rows": [6, 84], "message": "DUP1 birden fazla satırda"},
    {"code": "pending_ocr_review", "message": "2 sarı OCR sonucu"},
]


def run_node(body: str):
    script = f"""
import * as L from {json.dumps(MODULE)};
const blocks = {json.dumps(BLOCKS)};
const issues = {json.dumps(ISSUES)};
{body}
"""
    res = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True,
                         text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not NODE, reason="node yok")
def test_describe_and_links():
    got = run_node("""
console.log(JSON.stringify({
  d: issues.map(i => L.describeIssue(i, blocks, '22.10.2026')),
  route: L.planningRoute({ sheet: '22.10.2026', issue: 'missing_pickup' }),
  day: L.planningRoute({ sheet: '22.10.2026' }),
  pickup: [...L.issueLeadRows(issues, blocks, 'missing_pickup')].sort((a, b) => a - b),
  dup: [...L.issueLeadRows(issues, blocks, 'duplicate_document')].sort((a, b) => a - b),
  idx: [L.findBlockIndexForRow(blocks, 84), L.findBlockIndexForRow(blocks, 4), L.findBlockIndexForRow(blocks, 99)],
}));
""")
    pickup83, pickup4, identity, dup, pending = got["d"]
    assert pickup83 == {"who": "JOHN SMITH", "label": "pickup eksik", "row": 83,
                        "href": "#/planning?sheet=22.10.2026&row=83"}
    assert pickup4["who"] == "AHMET Y."  # issue.lead_name önce gelir
    assert identity["who"] == "AHMET YILMAZ grubu" and identity["row"] == 5
    assert identity["label"] == "isim, pasaport no eksik"
    assert identity["href"].endswith("&row=5")
    assert dup["who"] == "ŞEYMA ÖZTÜRK" and dup["row"] == 6 and dup["label"] == "DUP1 birden fazla satırda"
    assert pending["href"] == "" and pending["row"] is None
    assert got["route"] == "planning?sheet=22.10.2026&issue=missing_pickup"
    assert got["day"] == "planning?sheet=22.10.2026"
    assert got["pickup"] == [4, 83]
    assert got["dup"] == [4, 83]
    assert got["idx"] == [1, 0, -1]


@pytest.mark.skipif(not NODE, reason="node yok")
def test_fixture_issues_map_to_blocks():
    """Gerçek şablon (PII'siz): satır taşıyan her uyarı bir bloğa bağlanır."""
    checked = 0
    for sheet in ("21.10.2026", "22.10.2026", "23.10.2026"):
        blocks = read_blocks(FIXTURE, sheet)
        result = check_blocks(blocks, balloon_capacity=28)
        linked = [i for i in result["issues"] if i.get("lead_row") is not None or i.get("rows")]
        if not linked:
            continue
        payload = [{"lead_row": b.lead_row, "rows": list(b.rows), "lead_name": b.lead_name or "",
                    "passengers": [{"row": p.row, "name": p.name or ""} for p in b.passengers]} for b in blocks]
        script = f"""
import * as L from {json.dumps(MODULE)};
const blocks = {json.dumps(payload)};
const issues = {json.dumps(linked)};
console.log(JSON.stringify(issues.map(i => L.findBlockIndexForRow(blocks, L.issueTargetRow(i)))));
"""
        res = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True,
                             text=True, encoding="utf-8", timeout=30)
        assert res.returncode == 0, res.stderr
        assert all(i >= 0 for i in json.loads(res.stdout)), sheet
        checked += len(linked)
    assert checked, "fixture'da satırlı uyarı yok"

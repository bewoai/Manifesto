"""frontend/planning_search.js — alan adlı planlama araması (Node ile çalıştırılır)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = (Path(__file__).resolve().parent.parent / "frontend" / "planning_search.js").as_uri()
NODE = shutil.which("node")

BLOCKS = [
    {"lead_row": 4, "pax": 5, "lead_name": "AHMET YILMAZ", "hotel": "ARGOS", "agency": "BEDEL TURİZM",
     "balloon": "BZR", "driver": "2", "pilot": "ALİ", "pickup": "04:30", "room": "ODA 202",
     "passengers": [{"name": "AHMET YILMAZ", "passport_no": "U1234567", "nationality": "TUR", "sex": "M"},
                    {"name": "ŞEYMA ÖZTÜRK", "passport_no": "T2200033", "nationality": "TUR", "sex": "F"}]},
    {"lead_row": 9, "pax": 2, "lead_name": "JOHN SMITH", "hotel": "MUSEUM", "agency": "ACENTE 3",
     "balloon": "BYF", "driver": "12", "pilot": "PILOT 2", "pickup": "05:00",
     "passengers": [{"name": "JOHN SMITH", "passport_no": "GB998877", "nationality": "GBR", "sex": "M"}]},
    {"lead_row": 11, "pax": 3, "lead_name": "MARIA ROSSI", "hotel": "ARGOS", "agency": "ACENTE 3",
     "balloon": "BYF", "driver": "1", "passengers": []},
]


def run(queries):
    script = f"""
import {{ parseQuery, matchesBlock }} from {json.dumps(MODULE)};
const blocks = {json.dumps(BLOCKS)};
const out = {{}};
for (const q of {json.dumps(queries)}) out[q] = blocks.filter(b => matchesBlock(b, parseQuery(q))).map(b => b.lead_row);
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not NODE, reason="node yok")
def test_field_queries():
    got = run([
        "pax 5", "PAX 5", "pax:2", "pax5", "pax 2-3", "pax >2", "pax > 4", "pax<=3",
        "isim ahmet", "isim şeyma", "isim seyma", "otel argos", "acente bedel turizm",
        "şoför 2", "sofor 1", "balon byf", "pasaport T22", "uyruk gbr", "cinsiyet kadın",
        "saat 04:30", "oda 202", "argos pax 3", "smith", "turizm", "yok böyle",
    ])
    assert got["pax 5"] == [4] and got["PAX 5"] == [4] and got["pax:2"] == [9] and got["pax5"] == [4]
    assert got["pax 2-3"] == [9, 11] and got["pax >2"] == [4, 11] and got["pax > 4"] == [4] and got["pax<=3"] == [9, 11]
    assert got["isim ahmet"] == [4] and got["isim şeyma"] == [4] and got["isim seyma"] == [4]
    assert got["otel argos"] == [4, 11] and got["acente bedel turizm"] == [4]
    assert got["şoför 2"] == [4]          # 12'yi bulmaz
    assert got["sofor 1"] == [11]
    assert got["balon byf"] == [9, 11] and got["pasaport T22"] == [4] and got["uyruk gbr"] == [9]
    assert got["cinsiyet kadın"] == [4] and got["saat 04:30"] == [4] and got["oda 202"] == [4]
    assert got["argos pax 3"] == [11]     # koşullar birlikte
    assert got["smith"] == [9] and got["turizm"] == [4] and got["yok böyle"] == []

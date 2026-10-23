"""frontend/capacity_rules.js — balon başına kapasite, balon sınırı, acente kotası yardımcıları (Node)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = (Path(__file__).resolve().parent.parent / "frontend" / "capacity_rules.js").as_uri()
NODE = shutil.which("node")


def run(body: str):
    script = f"import * as m from {json.dumps(MODULE)};\nconst out = {{}};\n{body}\nconsole.log(JSON.stringify(out));"
    res = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not NODE, reason="node yok")
def test_capacity_for_uses_own_then_default():
    got = run("""
const d = { capacity: 28, capacities: { BZR: 40, BYF: 0 } };
out.own = m.capacityFor(d, 'BZR');
out.zero = m.capacityFor(d, 'BYF');
out.missing = m.capacityFor(d, 'BTK');
out.noData = m.capacityFor({}, 'BTK');
""")
    assert got == {"own": 40, "zero": 28, "missing": 28, "noData": 28}


@pytest.mark.skipif(not NODE, reason="node yok")
def test_agency_rows_merge_case_and_turkish_insensitive():
    got = run("""
out.rows = m.agencyQuotaRows(['Bedel Turizm', 'Şahin Tur', 'Acente 3'], { 'BEDEL TURIZM': 30, 'SAHIN TUR': '0', 'YENİ': 12 });
out.map = m.collectIntMap([{ name: 'A', value: '5' }, { name: 'B', value: '' }, { name: 'C', value: '0' }, { name: ' ', value: '3' }]);
out.upper = m.collectIntMap([{ name: 'bzr', value: '40' }], { upperKey: true });
""")
    assert got["rows"] == [
        {"name": "Bedel Turizm", "quota": 30},
        {"name": "Şahin Tur", "quota": None},
        {"name": "Acente 3", "quota": None},
        {"name": "YENİ", "quota": 12},
    ]
    assert got["map"] == {"A": 5}
    assert got["upper"] == {"BZR": 40}


@pytest.mark.skipif(not NODE, reason="node yok")
def test_limit_text_quota_rows_and_quota_error():
    got = run("""
out.limited = m.balloonLimitText(3, 4, 5);
out.free = m.balloonLimitText(3, 0, 5);
out.rows = m.quotaRows([{ agency: 'A', used: 5, quota: 10 }, { agency: 'B', used: 12, quota: 10 }, { agency: 'C', used: 3, quota: 0 }]);
out.isQuota = m.isQuotaExceeded({ status: 409, detail: { code: 'agency_quota_exceeded' } });
out.notQuota = m.isQuotaExceeded({ status: 409, detail: { code: 'capacity_confirmation_required' } });
const opts = m.quotaConfirmOptions({ message: 'X <kota>', agency: 'A', used: 8, pax: 4, quota: 10 }, s => String(s).replace(/</g, '&lt;'));
out.label = opts.confirmLabel; out.tone = opts.tone; out.body = opts.bodyHtml;
""")
    assert got["limited"] == "3/4 balon" and got["free"] == "5 balon"
    assert [r["agency"] for r in got["rows"]] == ["B", "A"] and got["rows"][0]["over"] is True
    assert got["isQuota"] is True and got["notQuota"] is False
    assert got["label"] == "Kotayı aşarak ekle" and got["tone"] == "danger"
    assert "X &lt;kota>" in got["body"] and "12/10" in got["body"]

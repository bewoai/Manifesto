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
def test_collect_int_map_and_limit_text():
    got = run("""
out.map = m.collectIntMap([{ name: 'A', value: '5' }, { name: 'B', value: '' }, { name: 'C', value: '0' }, { name: ' ', value: '3' }]);
out.upper = m.collectIntMap([{ name: 'bzr', value: '40' }], { upperKey: true });
out.limited = m.balloonLimitText(3, 4, 5);
out.free = m.balloonLimitText(3, 0, 5);
""")
    assert got["map"] == {"A": 5} and got["upper"] == {"BZR": 40}
    assert got["limited"] == "3/4 balon" and got["free"] == "5 balon"


@pytest.mark.skipif(not NODE, reason="node yok")
def test_day_seats_respects_balloon_limit_and_daily_capacity():
    got = run("""
const day = [
  { code: 'BYF', cap: 28, used: 28 }, { code: 'BTK', cap: 14, used: 0 }, { code: 'BYJ', cap: 28, used: 28 },
  { code: 'BZR', cap: 28, used: 28 }, { code: 'BZV', cap: 28, used: 28 }, { code: 'BSC', cap: 2, used: 0 },
  { code: 'BZK', cap: 20, used: 0 },
];
out.none = m.daySeats(day);
out.limit = m.daySeats(day, { maxBalloons: 4 });
out.both = m.daySeats(day, { maxBalloons: 4, dailyCapacity: 112 });
const partial = [{ code: 'A', cap: 28, used: 20 }, { code: 'B', cap: 14, used: 0 }, { code: 'C', cap: 20, used: 0 }];
out.room = m.daySeats(partial, { maxBalloons: 2 });
out.capped = m.daySeats(partial, { dailyCapacity: 40 });
out.isCap = m.isDailyCapacityExceeded({ status: 409, detail: { code: 'daily_capacity_exceeded' } });
out.notCap = m.isDailyCapacityExceeded({ status: 409, detail: { code: 'capacity_confirmation_required' } });
const opts = m.dailyCapacityConfirmOptions({ message: 'X <k>', used: 110, pax: 4, capacity: 112 }, s => String(s).replace(/</g, '&lt;'));
out.label = opts.confirmLabel; out.body = opts.bodyHtml;
""")
    # Ekran görüntüsündeki gün: sınırsız 148/36; 4 balon sınırıyla uçmayanlar düşer → 112/0
    assert (got["none"]["seats"], got["none"]["free"]) == (148, 36)
    assert (got["limit"]["seats"], got["limit"]["free"]) == (112, 0)
    assert sorted(got["limit"]["usable"]) == ["BYF", "BYJ", "BZR", "BZV"]
    assert (got["both"]["seats"], got["both"]["free"]) == (112, 0)
    # sınıra yer varsa en büyük boş balon eklenir
    assert got["room"]["usable"] == ["A", "C"] and got["room"]["free"] == 28
    assert (got["capped"]["seats"], got["capped"]["free"]) == (40, 20)
    assert got["isCap"] is True and got["notCap"] is False
    assert got["label"] == "Kapasiteyi aşarak ekle" and "X &lt;k>" in got["body"] and "114/112" in got["body"]

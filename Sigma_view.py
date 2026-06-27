from flask import Flask, jsonify, render_template_string, request, send_from_directory
from supabase import create_client, Client
import json
import os
import re
from collections import defaultdict

# ================== CONFIG ==================
SUPABASE_URL = "https://zrtcilmboikavgesdwuh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpydGNpbG1ib2lrYXZnZXNkd3VoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg3NjM2NDEsImV4cCI6MjA5NDMzOTY0MX0.HyyVu8ygZgCaupx0GGnQHuc9VuT72KjP_IMF5vrRDQk"
RESULT_TABLE = "Result"  # đổi nếu bảng Supabase của Ken tên khác, ví dụ: match_result/results
# Bảng danh sách VĐV/đoàn trong Supabase
# Sam để fallback vì có nơi đặt là "Information list", có nơi gõ thiếu r là "Infomation list"
INFORMATION_TABLE_CANDIDATES = [
    "Information Lists",
    "Information lists",
    "Information_Lists",
    "Information_lists",
]

JSON_FILE = os.path.join(
    os.path.dirname(__file__),
    "sigma",
    "Open Taekwondo Championships 2026.json"
)

LOGO_FILE = "/icon/NTP.png"            # đặt file vào thư mục static/NTP.png
# ============================================

app = Flask(__name__)
SETUP_FILE = os.path.join(
    os.path.dirname(__file__),
    "Setup",
    "Open Taekwondo Championships 2026.json"
)

def load_setup():
    try:
        with open(SETUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

@app.route("/icon/<path:filename>")
def icon_files(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "icon"),
        filename
    )
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TYPE_ALIASES = {
    "recognized": "Recognized",
    "recogmized": "Recognized",
    "recog": "Recognized",
    "freestyle": "Freestyle",
    "free": "Freestyle",
    "demonstration": "Demonstration",
    "demonstartion": "Demonstration",
    "demon": "Demonstration",
    "demo": "Demonstration",
    "mixer": "Mixer",
    "mixed": "Mixer",
}

DIVISION_WORDS = ["Individual", "Pair", "Team"]

def normalize_type(raw: str) -> str:
    s = str(raw or "").strip()
    low = s.lower()
    for k, v in TYPE_ALIASES.items():
        if k in low:
            return v
    return s.title() if s else "Other"

def parse_division_key(key: str):
    """Parse: Recognized - Individual Male Cadet -> type/division/age/gender"""
    key = str(key or "").strip()
    if " - " in key:
        raw_type, rest = key.split(" - ", 1)
    else:
        raw_type, rest = "Other", key

    typ = normalize_type(raw_type)
    division = "Other"
    for d in DIVISION_WORDS:
        if re.search(rf"\b{d}\b", rest, re.I):
            division = d
            break

    gender = ""
    if re.search(r"\bMale\b", rest, re.I):
        gender = "Male"
    elif re.search(r"\bFemale\b", rest, re.I):
        gender = "Female"

    age = rest
    age = re.sub(r"\b(Individual|Pair|Team|Male|Female)\b", "", age, flags=re.I)
    age = re.sub(r"\s+", " ", age).strip(" -")
    return {"key": key, "type": typ, "division": division, "age": age or "Open", "gender": gender}

def load_event_json():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def build_menu():
    data = load_event_json()

    menu = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(list)
            )
        )
    )
    flat = []

    for key, athletes in data.get("divisions", {}).items():
        meta = parse_division_key(key)

        athlete_rows = athletes or []

        # Số dòng thật trong file Sigma
        meta["count"] = len(athlete_rows)

        # Số VĐV/đội thi thật dựa theo No.
        # Individual: mỗi No. là 1 VĐV
        # Pair/Team: nhiều dòng chung 1 No. nhưng chỉ tính là 1 đội
        competitor_nos = set()

        for a in athlete_rows:
            no = str(a.get("No.", "") or "").strip()
            if no:
                competitor_nos.add(no)

        meta["competitor_count"] = len(competitor_nos) if competitor_nos else len(athlete_rows)

        flat.append(meta)

        gender = meta.get("gender") or "Mixed"

        menu[
            meta["type"]
        ][
            meta["division"]
        ][
            gender
        ][
            meta["age"]
        ].append(meta)

    return data.get("event_name", "Event"), convert_dict(menu), flat

def safe_float(v):
    try:
        if v is None or v == "": return None
        return float(v)
    except Exception:
        return None

def get_information_list_rows():
    """
    Lấy danh sách chung từ Supabase.
    Ken đang nói bảng là Information list / Infomation list,
    nên Sam thử nhiều tên để tránh sai chính tả table.
    """
    last_error = None

    for table_name in INFORMATION_TABLE_CANDIDATES:
        try:
            res = supabase.table(table_name).select("*").execute()
            rows = res.data or []

            # Nếu lấy được table thì trả luôn, kể cả rỗng
            return rows

        except Exception as e:
            last_error = e
            print(f"Information list load error with table {table_name}:", e)

    print("All information table candidates failed:", last_error)
    return []

def get_results_for_division(division_key: str):
    """
    Bảng Result hiện tại không có cột Division, nên không lọc theo Division ở Supabase.
    Trả toàn bộ Result để JS tự đối chiếu theo Match/Result và không làm văng web.
    """
    try:
        res = supabase.table(RESULT_TABLE).select("*").execute()
        rows = res.data or []
        for r in rows:
            r["_score"] = safe_float(
                r.get("Total")
                or r.get("total")
                or r.get("Score")
                or r.get("score")
            )
        return rows
    except Exception as e:
        print("Result load error:", e)
        return []

INDEX_HTML = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ event_name }}</title>
  <style>

*{box-sizing:border-box}
body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#07111f;color:#eef6ff}
.topbar{
    min-height:118px;
    height:auto;
    display:grid;
    grid-template-columns:180px minmax(0,1fr) 180px;
    align-items:center;
    padding:10px 24px;
    background:linear-gradient(90deg,#03152d,#064b93,#03152d);
    border-bottom:4px solid #f5c542;
}

.logoBox img{
    max-height:92px;
    max-width:150px;
    object-fit:contain;
    background:white;
}

.eventTitle{
    text-align:center;
    min-width:0;
    overflow:hidden;
    padding:0 10px;
}

.eventTitle h1{
    margin:0 0 6px;
    font-size:clamp(20px, 3vw, 34px);
    line-height:1.12;
    text-transform:uppercase;
    letter-spacing:.8px;
    white-space:normal;
    overflow-wrap:break-word;
}

.eventTitle div{
    font-size:clamp(13px, 1.6vw, 18px);
    line-height:1.25;
}
.layout{display:grid;grid-template-columns:340px 1fr;min-height:calc(100vh - 118px)}
.sidebar{background:#081827;border-right:1px solid #21415f;padding:16px;overflow:auto}
.sideTitle{font-weight:900;color:#f5c542;margin:6px 0 14px;font-size:20px}
.quickMenu{
    margin-bottom:18px;
    padding-bottom:16px;
    border-bottom:1px solid #21415f;
}

.quickMenuTitle{
    font-weight:900;
    color:#ffd34d;
    margin:6px 0 12px;
    font-size:20px;
    text-transform:uppercase;
}

.quickMenuBtn{
    width:100%;
    display:block;
    border:1px solid #244765;
    border-radius:10px;
    background:#123c67;
    color:white;
    font-size:17px;
    font-weight:900;
    padding:13px 14px;
    margin-bottom:9px;
    text-align:left;
    cursor:pointer;
}

.quickMenuBtn:hover,
.quickMenuBtn.active{
    background:#ffd34d;
    color:#06111f;
}

.tool-card{
    background:#0b1d30;
    border:1px solid #203e5b;
    border-radius:14px;
    padding:14px;
    margin-bottom:16px;
}

.tool-title-row{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
    margin-bottom:12px;
}

.tool-title-row h3{
    margin:0;
    color:#ffd34d;
    font-size:22px;
}

.filter-grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:10px;
    margin-bottom:12px;
}

.filter-grid input,
.filter-grid select{
    width:100%;
    padding:10px 12px;
    border:1px solid #244765;
    border-radius:10px;
    background:#06192b;
    color:white;
    outline:none;
}

.filter-grid input::placeholder{
    color:#91a9bf;
}

.table-scroll{
    width:100%;
    overflow:auto;
    border:1px solid #1e3a55;
    border-radius:12px;
}

#infoListTable,
#rankingTable{
    min-width:900px;
}

.rank-gold{
    color:#ffd34d;
    font-weight:900;
}

.rank-silver{
    color:#dce7f3;
    font-weight:900;
}

.rank-bronze{
    color:#e2a85d;
    font-weight:900;
}

.rank-fourth{
    color:#9fd0ff;
    font-weight:900;
}

.ranking-card-grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(420px,1fr));
    gap:16px;
}

.ranking-division-card{
    border:1px solid #24527a;
    border-radius:14px;
    overflow:hidden;
    background:#08233c;
}

.ranking-division-title{
    background:#123c67;
    color:#ffd34d;
    font-size:18px;
    font-weight:900;
    text-align:center;
    padding:12px;
    letter-spacing:.5px;
}

.ranking-medal-table{
    width:100%;
    border-collapse:collapse;
    min-width:0!important;
}

.ranking-medal-table th{
    background:#0f2e4e;
    color:white;
    font-size:13px;
    padding:9px;
}

.ranking-medal-table td{
    color:white;
    font-size:14px;
    font-weight:700;
    padding:10px;
    border-bottom:1px solid #1e3a55;
}

.medal-cell{
    width:95px;
    white-space:nowrap;
    font-weight:900;
}

.medal-gold{
    color:#ffd34d!important;
}

.medal-silver{
    color:#dce7f3!important;
}

.medal-bronze{
    color:#e2a85d!important;
}

.ranking-empty-cell{
    color:#7893aa!important;
    font-weight:600!important;
}

.medal-standing-table{
    min-width:1200px;
    table-layout:auto;
}

.medal-standing-table th{
    text-align:center;
    vertical-align:middle;
    white-space:nowrap;
}

.medal-standing-table td{
    text-align:center;
    vertical-align:middle;
}



.medal-division-cell{
    min-width:118px;
    font-weight:900;
    line-height:1.35;
    white-space:nowrap;
}

.medal-icon-wrap{
    display:flex;
    align-items:center;
    justify-content:center;
    gap:6px;
    font-size:20px;
    min-height:24px;
}

.medal-icon-item{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    font-weight:900;
}

.medal-icon-symbol{
    font-size:22px;
    line-height:1;
}

.medal-standing-table{
    min-width:1200px;
    table-layout:auto;
    border-collapse:separate;
    border-spacing:0;
}

.medal-standing-table thead th{
    text-align:center!important;
    vertical-align:middle!important;
    white-space:nowrap;
    font-weight:900;
    border:1px solid #3b79ad!important;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.06);
}

.medal-standing-table tbody td{
    border-right:1px solid #1e3a55;
    border-bottom:1px solid #1e3a55;
}

.medal-standing-head-type{
    background:#164d82!important;
    color:#ffd34d!important;
    font-size:17px!important;
    letter-spacing:.5px;
    height:34px;
}

.medal-standing-head-division{
    background:#1fd0a6!important;
    color:#06111f!important;
    font-size:15px!important;
    height:32px;
    text-transform:uppercase;
}

.medal-standing-head-age{
    background:#0b2947!important;
    color:#d7efff!important;
    font-size:12px!important;
    min-width:120px;
    height:32px;
}

.medal-standing-fixed-head{
    background:#123c67!important;
    color:#ffd34d!important;
    font-size:14px!important;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-summary-head{
    background:#123c67!important;
    color:#ffd34d!important;
    font-size:13px!important;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

/* ===== Medal Standings: chỉ cố định cột Unit/NOC, không ăn nhầm header con ===== */

.medal-standing-fixed-head{
    position:sticky;
    left:0;
    z-index:20;
    background:#123c67!important;
    color:#ffd34d!important;
    font-size:14px!important;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-unit-cell{
    position:sticky;
    left:0;
    z-index:10;
    background:#0b1d30!important;
    font-weight:900;
    color:#ffd34d;
    text-align:left!important;
    border-right:1px solid #3b79ad!important;
    border-bottom:1px solid #1e3a55!important;
}

.medal-standing-head-type{
    background:#164d82!important;
    color:#ffd34d!important;
    font-size:17px!important;
    letter-spacing:.5px;
    height:34px;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-head-division{
    background:#1fd0a6!important;
    color:#06111f!important;
    font-size:15px!important;
    height:32px;
    text-transform:uppercase;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-head-age{
    background:#0b2947!important;
    color:#d7efff!important;
    font-size:12px!important;
    min-width:120px;
    height:32px;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-summary-head{
    background:#123c67!important;
    color:#ffd34d!important;
    font-size:13px!important;
    text-align:center!important;
    vertical-align:middle!important;
    border:1px solid #3b79ad!important;
}

.medal-standing-gold{
    color:#ffd34d;
}

.medal-standing-silver{
    color:#dce7f3;
}

.medal-standing-bronze{
    color:#e2a85d;
}

.medal-standing-total{
    font-weight:900;
    font-size:15px;
}

.medal-standing-rank{
    font-size:18px;
    font-weight:900;
    color:#7fe7ff;
}

.medal-unit-sub{
    display:block;
    margin-top:4px;
    color:#9bb7cf;
    font-size:12px;
    font-weight:700;
    line-height:1.35;
}

.medal-unit-main{
    display:block;
    color:#ffd34d;
    font-size:15px;
    font-weight:900;
    margin-bottom:4px;
}

.medal-unit-total{
    color:#ffffff;
    font-weight:900;
}

.medal-unit-male{
    color:#7fe7ff;
    font-weight:800;
}

.medal-unit-female{
    color:#ffb3d1;
    font-weight:800;
}

.medal-unit-other{
    color:#cfe6ff;
    font-weight:800;
}

.medal-unit-coach{
    color:#b8ff7a;
    font-weight:800;
}

.group{margin-bottom:10px;border:1px solid #203b57;border-radius:12px;overflow:hidden;background:#0c2135}
.groupHead,.subHead,.genderHead,.ageBtn{
    width:100%;
    border:0;
    color:#fff;
    text-align:left;
    cursor:pointer;
}

.groupHead{
    padding:14px 18px;
    background:#123c67;
    font-size:18px;
    font-weight:900;
}

.subHead{
    padding:12px 34px;
    background:#0f2e4e;
    font-size:16px;
    font-weight:800;
}

.genderHead{
    padding:11px 52px;
    background:#0c2842;
    color:#d7e9ff;
    font-size:15px;
    font-weight:800;
}

.ageBtn{
    padding:10px 76px;
    background:#0b2239;
    font-size:14px;
    border-top:1px solid #173959;
}

.ageBtn:hover,
.ageBtn.active{
    background:#f5c542;
    color:#06111f;
    font-weight:900;
}
.hidden{display:none!important}
.content{padding:18px;overflow:auto}
.selectedBox{display:flex;justify-content:space-between;align-items:center;background:#0d2238;border:1px solid #244765;border-radius:14px;padding:16px 18px;margin-bottom:16px}
.label{color:#9bb7cf;font-size:13px;text-transform:uppercase}
.selectedBox h2{margin:4px 0 0;font-size:25px}
.selectedBox button,.btn-result{padding:10px 22px;border:0;border-radius:10px;background:#ffd34d;color:#001b33;font-weight:900;cursor:pointer}
.selectedBox button:hover,.btn-result:hover{filter:brightness(1.08)}
.card{background:#0b1d30;border:1px solid #203e5b;border-radius:14px;padding:14px;margin-bottom:16px}
.section-title-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.section-title-row h3,.card h3{margin:0;color:#ffd34d}
table{
    width:100%;
    max-width:100%;
    border-collapse:collapse;
    min-width:0;
    table-layout:auto;
}
th,td{
    border-bottom:1px solid #1e3a55;
    padding:10px;
    text-align:left;
    font-size:14px;
    white-space:normal;
    word-break:normal;
    overflow-wrap:break-word;
}
#athleteTable th:nth-child(1),
#athleteTable td:nth-child(1){
    width:70px;
    text-align:center;
    white-space:nowrap;
}

#athleteTable th:nth-child(2),
#athleteTable td:nth-child(2){
    width:90px;
    text-align:center;
    white-space:nowrap;
}

#athleteTable th:nth-child(3),
#athleteTable td:nth-child(3){
    width:auto;
    min-width:260px;
    white-space:normal;
    word-break:normal;
    overflow-wrap:break-word;
}

#athleteTable th:nth-child(4),
#athleteTable td:nth-child(4){
    width:95px;
    text-align:center;
    white-space:nowrap;
}
th{background:#123c67;color:#fff;position:sticky;top:0}
tr:hover td{background:#102b46}
.empty{padding:18px;color:#b9c9d8}
.layout.result-mode{display:block}
.layout.result-mode .content{width:100%;max-width:none;padding:18px;min-height:calc(100vh - 118px)}
.layout.result-mode #sigmaView{min-height:calc(100vh - 155px);display:flex;flex-direction:column}
.layout.result-mode .sigma-bracket{flex:1;min-height:0}
.layout.result-mode .sigma-svg{height:100%;min-height:640px}
.sigma-view{margin-top:10px;border:1px solid #24527a;border-radius:14px;padding:14px;background:#06192b}
.sigma-title-row{display:grid;grid-template-columns:120px 1fr 120px;align-items:center;margin-bottom:16px}
.sigma-title{text-align:center;color:#ffd34d;font-size:30px;font-weight:900;letter-spacing:3px;margin:0}
.sigma-bracket{display:block;width:100%;overflow:hidden;padding:0}
.sigma-svg{width:100%;height:640px;display:block;background:#06192b;border:1px solid #24527a;border-radius:12px}
.sigma-svg-box{fill:#08233c;stroke:#2f6fa3;stroke-width:1.8}
.sigma-svg-box.player-blue{
    fill:#0B63CE;
    stroke:#003B8E;
    stroke-width:3;
}

.sigma-svg-box.player-red{
    fill:#C93C4A;
    stroke:#7A1F2B;
    stroke-width:3;
}

.sigma-svg-name-blue,
.sigma-svg-noc-blue,
.sigma-svg-seed-blue{
    fill:white;
    font-size:15px;
    font-weight:900;
}

.sigma-svg-name-red,
.sigma-svg-noc-red,
.sigma-svg-seed-red{
    fill:white;
    font-size:15px;
    font-weight:900;
}
.sigma-svg-line{stroke:#9fd0ff;stroke-width:1.8;stroke-linecap:square}
.sigma-svg-name{
    fill:white;
    font-size:15px;
    font-weight:900;
}

.sigma-svg-noc{
    fill:white;
    font-size:15px;
    font-weight:900;
}

.sigma-svg-seed{
    fill:white;
    font-size:15px;
    font-weight:900;
}
.sigma-svg-code-box{fill:#06192b;stroke:#ffd34d;stroke-width:2}
.sigma-svg-code{fill:#ffd34d;font-size:14px;font-weight:900}
.sigma-svg-code-box.winner{fill:#ffd34d;stroke:#ffd34d}

.sigma-svg-code-box.winner-blue{
    fill:#0B63CE;
    stroke:#003B8E;
    stroke-width:3;
}

.sigma-svg-code-box.winner-red{
    fill:#C93C4A;
    stroke:#7A1F2B;
    stroke-width:3;
}



.sigma-svg-winner-code{
    fill:#001b33;
    font-size:14px;
    font-weight:900;
}

.sigma-svg-winner-code-blue{
    fill:white;
    font-size:14px;
    font-weight:900;
}

.sigma-svg-winner-code-red{
    fill:white;
    font-size:14px;
    font-weight:900;
}

/* ===== Champion Final Box ===== */
.sigma-svg-code-box.champion{
    fill:#f6d56b!important;
    stroke:#ffbf00!important;
    stroke-width:3.5!important;
}

.sigma-svg-winner-code-champion{
    fill:#ffffff!important;
    font-size:15px!important;
    font-weight:900!important;
    paint-order:stroke;
    stroke:#5b4100;
    stroke-width:2px;
    stroke-linejoin:round;
}

.sigma-svg-champion-cup{
    font-size:42px!important;
    font-weight:900!important;
}


@media(max-width:1100px){.layout{grid-template-columns:280px 1fr}.eventTitle h1{font-size:25px}}
@media(max-width:700px){
    .topbar{
        grid-template-columns:120px minmax(0,1fr);
        padding:8px 10px;
        min-height:110px;
    }

    .rightBlank{
        display:none;
    }

    .logoBox img{
        max-height:78px;
        max-width:110px;
    }

    .eventTitle{
        padding:0 4px;
    }

    .header-title{
        font-size:clamp(18px, 6vw, 28px);
        line-height:1.08;
        letter-spacing:.5px;
    }

    .header-date,
    .header-location{
        font-size:clamp(11px, 3.2vw, 15px);
        line-height:1.18;
        margin-top:3px;
    }

    .layout{
        min-height:calc(100vh - 110px);
    }
}

@media(max-width:430px){
    .topbar{
        grid-template-columns:1fr;
        text-align:center;
        min-height:auto;
        padding:8px 8px 10px;
    }

    .logoBox{
        display:flex;
        justify-content:center;
        margin-bottom:6px;
    }

    .logoBox img{
        max-height:62px;
        max-width:96px;
    }

    .header-title{
        font-size:22px;
    }

    .header-date,
    .header-location{
        font-size:12px;
    }
}
.header-title{
    color:#FF8F0F;
    font-size:60px;
    font-weight:900;
    letter-spacing:1px;
    text-shadow:
        0 0 8px rgba(255,255,255,.35),
        0 0 20px rgba(0,180,255,.25);
}

.header-date{
    color:#ffd54a;
    font-size:18px;
    font-weight:700;
    margin-top:4px;
}

.header-location{
    color:#7fe7ff;
    font-size:18px;
    font-weight:700;
    margin-top:4px;
}
.genderHead{
    width:100%;
    border:0;
    cursor:pointer;
    text-align:left;

    padding:10px 52px;

    background:#12385d;

    color:#d7e9ff;
    font-size:15px;
    font-weight:700;

    border-left:4px solid #2f6aa3;
}
.cutoff-result-wrap{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(360px,1fr));
    gap:18px;
    padding:10px;
}

.cutoff-phase-box{
    border:1px solid #24527a;
    border-radius:14px;
    background:#08233c;
    overflow:hidden;
}

.cutoff-phase-title{
    background:#123c67;
    color:#ffd34d;
    font-size:22px;
    font-weight:900;
    text-align:center;
    padding:12px;
    letter-spacing:1px;
}

.cutoff-table{
    width:100%;
    min-width:0;
    border-collapse:collapse;
}

.cutoff-table th{
    background:#0f2e4e;
    color:white;
    font-size:14px;
    padding:10px;
}

.cutoff-table td{
    color:white;
    font-size:15px;
    font-weight:700;
    padding:10px;
    border-bottom:1px solid #1e3a55;
}

.cutoff-table td:first-child{
    color:#ffd34d;
    font-weight:900;
    text-align:center;
}

/* ================= LEFT SIDEBAR TOGGLE + DRAG TABLE ================= */

.sidebar-toggle-btn{
    position:fixed;
    left:300px;
    top:204px;
    z-index:9999;
    width:42px;
    height:42px;
    border:2px solid #ffd34d;
    border-radius:10px;
    background:#123c67;
    color:#ffd34d;
    font-size:25px;
    font-weight:900;
    line-height:1;
    cursor:pointer;
    box-shadow:0 8px 24px rgba(0,0,0,.35);
    display:flex;
    align-items:center;
    justify-content:center;
}

.sidebar-toggle-btn:hover{
    background:#ffd34d;
    color:#06111f;
}

body.sidebar-collapsed-desktop .sidebar-toggle-btn{
    left:12px;
}

.sidebar-backdrop{
    display:none;
}

.layout{
    grid-template-columns:340px minmax(0,1fr);
}

.layout > .sidebar{
    grid-column:1;
}

.layout > .content{
    grid-column:2;
    min-width:0;
}

.layout.sidebar-collapsed{
    grid-template-columns:0 minmax(0,1fr);
}

.layout.sidebar-collapsed .sidebar{
    width:0!important;
    min-width:0!important;
    padding:0!important;
    overflow:hidden!important;
    border-right:0!important;
}

.layout.sidebar-collapsed .content{
    grid-column:2;
    padding-left:18px;
}

/* Medal Standings kéo ngang/dọc */
#medalStandingsView .table-scroll{
    max-height:calc(100vh - 265px);
    overflow:auto;
    cursor:grab;
    user-select:none;
    -webkit-overflow-scrolling:touch;
    overscroll-behavior:contain;
}

#medalStandingsView .table-scroll.dragging{
    cursor:grabbing;
}

#medalStandingsTable{
    min-width:max-content;
}

/* ===== Medal Standings: đóng băng header 3 tầng, không bị hở ===== */

#medalStandingsTable{
    border-collapse:separate!important;
    border-spacing:0!important;
}

/* Ép chiều cao 3 hàng header cố định để rowspan hai bên khớp tuyệt đối */
#medalStandingsTable thead tr:nth-child(1){
    height:36px!important;
}

#medalStandingsTable thead tr:nth-child(2){
    height:32px!important;
}

#medalStandingsTable thead tr:nth-child(3){
    height:32px!important;
}

/* Tất cả ô header không dùng padding lớn nữa, tránh tạo khoảng hở */
#medalStandingsTable thead th{
    position:sticky!important;
    padding:0 8px!important;
    line-height:1.15!important;
    box-sizing:border-box!important;
    vertical-align:middle!important;
    background-clip:padding-box!important;
}

/* Hàng 1: Recognized / Freestyle + Unit/NOC + Total */
#medalStandingsTable thead tr:nth-child(1) th{
    top:0!important;
    height:36px!important;
    z-index:60!important;
}

/* Hàng 2: Individual / Pair / Team */
#medalStandingsTable thead tr:nth-child(2) th{
    top:36px!important;
    height:32px!important;
    z-index:58!important;
}

/* Hàng 3: Female Cadet / Male Cadet / ... */
#medalStandingsTable thead tr:nth-child(3) th{
    top:68px!important;
    height:32px!important;
    z-index:56!important;
}

/* Các ô rowspan 3 hàng phải cao đúng bằng 36 + 32 + 32 = 100px */
#medalStandingsTable .medal-standing-fixed-head,
#medalStandingsTable .medal-standing-summary-head{
    height:100px!important;
    min-height:100px!important;
    top:0!important;
    z-index:70!important;
}

/* Unit/NOC header vừa sticky dọc vừa sticky ngang */
#medalStandingsTable .medal-standing-fixed-head{
    position:sticky!important;
    left:0!important;
    z-index:90!important;
}

/* Cột Unit/NOC body sticky ngang */
#medalStandingsTable tbody .medal-standing-unit-cell{
    position:sticky!important;
    left:0!important;
    z-index:35!important;
    background:#0b1d30!important;
}

/* Nền chắc để không bị xuyên/chừa hở khi kéo */
#medalStandingsTable .medal-standing-head-type{
    background:#164d82!important;
}

#medalStandingsTable .medal-standing-head-division{
    background:#1fd0a6!important;
}

#medalStandingsTable .medal-standing-head-age{
    background:#0b2947!important;
}

#medalStandingsTable .medal-standing-fixed-head,
#medalStandingsTable .medal-standing-summary-head{
    background:#123c67!important;
}


/* Mobile / Tablet: menu trượt từ bên trái */
@media(max-width:900px){
    body{
        overflow-x:hidden;
    }

    .topbar{
        grid-template-columns:72px minmax(0,1fr) 48px;
        min-height:92px;
        padding:8px 8px;
    }

    .logoBox img{
        max-height:62px;
        max-width:74px;
    }

    .header-title{
        font-size:clamp(17px, 5vw, 28px)!important;
        line-height:1.08;
    }

    .header-date,
    .header-location{
        font-size:clamp(11px, 3vw, 14px)!important;
    }

    .layout{
        display:block;
        min-height:calc(100vh - 92px);
    }

    .content{
        width:100%;
        padding:10px;
    }

    .sidebar{
        position:fixed;
        top:0;
        left:-86vw;
        width:86vw;
        max-width:360px;
        height:100vh;
        z-index:9998;
        background:#081827;
        border-right:2px solid #ffd34d;
        border-left:0;
        padding:16px;
        overflow:auto;
        transition:left .24s ease;
        box-shadow:12px 0 30px rgba(0,0,0,.45);
    }

    .layout.menu-open .sidebar{
        left:0;
    }

    .sidebar-backdrop{
        position:fixed;
        inset:0;
        z-index:9997;
        background:rgba(0,0,0,.48);
        display:none;
    }

    body.sidebar-open .sidebar-backdrop{
        display:block;
    }

    .sidebar-toggle-btn{
        top:22px;
        left:10px;
        right:auto;
        width:42px;
        height:42px;
        font-size:24px;
        border-radius:11px;
    }

    body.sidebar-open .sidebar-toggle-btn{
        left:calc(min(86vw, 360px) + 8px);
    }

    .tool-card{
        padding:10px;
        border-radius:12px;
    }

    .tool-title-row{
        align-items:flex-start;
    }

    .tool-title-row h3{
        font-size:18px;
        padding-left:0;
    }

    .btn-result{
        padding:9px 14px;
        font-size:13px;
    }

    .filter-grid{
        grid-template-columns:1fr;
        gap:8px;
    }

    #medalStandingsView .table-scroll{
        max-height:calc(100vh - 225px);
        border-radius:10px;
    }

    .medal-standing-table th,
    .medal-standing-table td{
        padding:7px 8px;
        font-size:12px;
    }

    .medal-standing-head-type{
        font-size:14px!important;
        height:30px;
    }

    .medal-standing-head-division{
        font-size:12px!important;
        height:28px;
    }

    .medal-standing-head-age{
        font-size:11px!important;
        min-width:92px;
        height:28px;
    }

    .medal-standing-fixed-head{
        min-width:126px!important;
        font-size:12px!important;
    }

    .medal-standing-unit-cell{
        min-width:126px;
    }

    .medal-unit-sub{
        font-size:10px;
        line-height:1.25;
    }

    .medal-icon-symbol{
        font-size:18px;
    }

    .medal-standing-total,
    .medal-standing-rank{
        font-size:13px;
    }
}

/* ================= CLEAN MOBILE FIX: LIST / RANKING / SIGMA ================= */

/* Không cho trang chính bị kéo ngang, nhưng không ép layout con quá mức */
html,
body{
    max-width:100%;
    overflow-x:hidden;
}

.layout,
.content{
    min-width:0;
}

/* Ranking Summary: desktop giữ đẹp, mobile chuyển 1 cột */
@media(max-width:900px){

    .content{
        padding:10px!important;
        overflow:visible!important;
    }

    .tool-card,
    .card,
    .selectedBox,
    .sigma-view{
        max-width:100%;
        min-width:0;
        box-sizing:border-box;
    }

    /* Ranking không bị bóp / không tràn */
    .ranking-card-grid{
        display:grid!important;
        grid-template-columns:1fr!important;
        gap:14px!important;
        width:100%!important;
    }

    .ranking-division-card{
        width:100%!important;
        max-width:100%!important;
        min-width:0!important;
        border-radius:16px!important;
        overflow:hidden!important;
    }

    .ranking-division-title{
        font-size:20px!important;
        line-height:1.2!important;
        padding:14px 10px!important;
        word-break:break-word;
    }

    .ranking-medal-table{
        width:100%!important;
        min-width:0!important;
        table-layout:fixed!important;
    }

    .ranking-medal-table th,
    .ranking-medal-table td{
        padding:10px 8px!important;
        font-size:14px!important;
        white-space:normal!important;
        word-break:break-word!important;
    }

    .ranking-medal-table th:nth-child(1),
    .ranking-medal-table td:nth-child(1){
        width:30%!important;
    }

    .ranking-medal-table th:nth-child(2),
    .ranking-medal-table td:nth-child(2){
        width:22%!important;
    }

    .ranking-medal-table th:nth-child(3),
    .ranking-medal-table td:nth-child(3){
        width:48%!important;
    }

    .medal-cell{
        width:auto!important;
        white-space:normal!important;
    }

    /* Information List: giữ dạng kéo ngang, không bóp cột */
    #infoListView .table-scroll{
        width:100%!important;
        max-width:100%!important;
        overflow:auto!important;
        -webkit-overflow-scrolling:touch;
    }

    #infoListTable{
        min-width:900px!important;
        width:max-content!important;
    }

    /* Team/Athlete List: bảng kéo ngang trong card, không làm vỡ màn hình */
    .athlete-card{
        overflow:hidden!important;
    }

    .athlete-card #athleteTable{
        display:block!important;
        width:100%!important;
        max-width:100%!important;
        min-width:0!important;
        overflow-x:auto!important;
        -webkit-overflow-scrolling:touch;
        border-collapse:collapse!important;
    }

    #athleteTable thead,
    #athleteTable tbody,
    #athleteTable tr{
        width:max-content;
        min-width:620px;
    }

    #athleteTable th,
    #athleteTable td{
        white-space:nowrap!important;
        font-size:14px!important;
        padding:10px 12px!important;
    }

    #athleteTable th:nth-child(1),
    #athleteTable td:nth-child(1){
        min-width:60px!important;
        width:60px!important;
    }

    #athleteTable th:nth-child(2),
    #athleteTable td:nth-child(2){
        min-width:90px!important;
        width:90px!important;
    }

    #athleteTable th:nth-child(3),
    #athleteTable td:nth-child(3){
        min-width:300px!important;
        width:300px!important;
        white-space:normal!important;
    }

    #athleteTable th:nth-child(4),
    #athleteTable td:nth-child(4){
        min-width:110px!important;
        width:110px!important;
    }

    /* Watching box: không để nút Refresh đè chữ */
    .selectedBox{
        display:grid!important;
        grid-template-columns:minmax(0,1fr) auto!important;
        gap:10px!important;
        align-items:center!important;
        padding:14px!important;
        overflow:hidden!important;
    }

    .selectedBox h2{
        font-size:clamp(22px, 6vw, 36px)!important;
        line-height:1.18!important;
        word-break:break-word!important;
        margin:4px 0 0!important;
    }

    .selectedBox button{
        padding:10px 18px!important;
        min-width:110px!important;
        white-space:nowrap!important;
    }

    /* Team/Athlete title row: không để nút Sigma đè tiêu đề */
    .section-title-row{
        display:grid!important;
        grid-template-columns:minmax(0,1fr) auto!important;
        gap:10px!important;
        align-items:center!important;
    }

    .section-title-row h3{
        font-size:clamp(20px, 5.5vw, 30px)!important;
        line-height:1.18!important;
        word-break:break-word!important;
    }

    .section-title-row .btn-result{
        min-width:105px!important;
        white-space:nowrap!important;
    }

    /* Sigma Result: sửa header 3 cột bị đè */
    .sigma-title-row{
        display:grid!important;
        grid-template-columns:1fr!important;
        gap:12px!important;
        text-align:center!important;
    }

    .sigma-title-row > div:first-child{
        display:none!important;
    }

    .sigma-title-row .btn-result,
    #btnReturn{
        justify-self:center!important;
        min-width:130px!important;
        padding:11px 22px!important;
    }

    .sigma-title{
        font-size:clamp(34px, 10vw, 56px)!important;
        line-height:1.1!important;
        letter-spacing:4px!important;
    }

    #sigmaDivisionTitle{
        font-size:clamp(22px, 6.2vw, 34px)!important;
        line-height:1.2!important;
        word-break:break-word!important;
    }

    /* Cutoff/Sigma table: nằm gọn trong khung, kéo ngang khi cần */
    .sigma-bracket{
        width:100%!important;
        overflow:auto!important;
        -webkit-overflow-scrolling:touch;
    }

    .cutoff-result-wrap{
        display:grid!important;
        grid-template-columns:1fr!important;
        gap:14px!important;
        padding:8px!important;
        min-width:0!important;
    }

    .cutoff-phase-box{
        width:100%!important;
        max-width:100%!important;
        overflow:auto!important;
        border-radius:14px!important;
    }

    .cutoff-table{
        min-width:520px!important;
        width:max-content!important;
    }

    .cutoff-table th,
    .cutoff-table td{
        font-size:14px!important;
        padding:10px 8px!important;
        white-space:normal!important;
    }

    /* Medal standings giữ kéo ngang */
    #medalStandingsView{
        overflow:hidden!important;
    }

    #medalStandingsView .table-scroll{
        width:100%!important;
        max-width:100%!important;
        overflow:auto!important;
        -webkit-overflow-scrolling:touch;
    }

    #medalStandingsTable{
        min-width:max-content!important;
    }
}

/* Điện thoại nhỏ */
@media(max-width:480px){

    .content{
        padding:8px!important;
    }

    .tool-card,
    .card,
    .selectedBox,
    .sigma-view{
        border-radius:15px!important;
        padding:10px!important;
    }

    .ranking-division-title{
        font-size:18px!important;
    }

    .ranking-medal-table th,
    .ranking-medal-table td{
        font-size:13px!important;
        padding:9px 7px!important;
    }

    #athleteTable thead,
    #athleteTable tbody,
    #athleteTable tr{
        min-width:600px;
    }

    #athleteTable th,
    #athleteTable td{
        font-size:13px!important;
    }

    .selectedBox{
        grid-template-columns:1fr!important;
    }

    .selectedBox button{
        justify-self:end!important;
    }

    .section-title-row{
        grid-template-columns:1fr auto!important;
    }
}

.athlete-table-scroll{
    width:100%;
    max-width:100%;
    overflow:auto;
    -webkit-overflow-scrolling:touch;
}

@media(max-width:900px){
    .athlete-card #athleteTable{
        display:table!important;
        width:max-content!important;
        min-width:620px!important;
    }
}

/* ================= SIGMA PRINT / PDF BUTTONS ================= */

.sigma-action-box{
    display:flex;
    flex-direction:column;
    gap:8px;
    align-items:stretch;
    justify-content:center;
}

.sigma-action-btn{
    min-width:118px;
    padding:9px 14px!important;
    white-space:nowrap;
    font-size:13px!important;

    background:#123c67!important;
    color:#ffd34d!important;
    border:2px solid #ffd34d!important;
    border-radius:10px!important;

    display:flex;
    align-items:center;
    justify-content:center;
    gap:7px;

    font-weight:900!important;
    box-shadow:0 4px 12px rgba(0,0,0,.28);
}

.sigma-action-btn:hover{
    background:#ffd34d!important;
    color:#06111f!important;
    filter:none!important;
}

.sigma-action-btn:active{
    transform:translateY(1px);
}

.cutoff-phase-title-row{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    background:#123c67;
    padding:10px 12px;
}

.cutoff-phase-title-row .cutoff-phase-title{
    background:transparent!important;
    padding:0!important;
    flex:1;
}

.cutoff-phase-actions{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
    justify-content:flex-end;
}

.cutoff-print-btn{
    width:34px;
    height:30px;
    padding:0!important;

    display:inline-flex;
    align-items:center;
    justify-content:center;

    border:2px solid #ffd34d!important;
    border-radius:9px;

    background:#123c67!important;
    color:#ffd34d!important;

    font-size:15px;
    font-weight:900;
    line-height:1;

    cursor:pointer;
    white-space:nowrap;

    box-shadow:0 3px 10px rgba(0,0,0,.28);
}

.cutoff-print-btn:hover{
    background:#ffd34d!important;
    color:#06111f!important;
    filter:none!important;
}

.cutoff-print-btn:active{
    transform:translateY(1px);
}

.cutoff-phase-actions{
    display:flex;
    gap:6px;
    flex-wrap:nowrap;
    justify-content:flex-end;
    align-items:center;
}

@media(max-width:900px){
    .sigma-title-row{
        grid-template-columns:1fr!important;
        gap:12px!important;
    }

    .sigma-title-row > div:first-child{
        display:none!important;
    }

    .sigma-action-box{
        flex-direction:row;
        flex-wrap:wrap;
        justify-content:center;
        align-items:center;
    }

    .sigma-action-btn{
        min-width:105px;
        font-size:12px!important;
        padding:9px 12px!important;
    }

    .cutoff-phase-title-row{
        flex-direction:column;
        align-items:center;
        text-align:center;
    }

    .cutoff-phase-actions{
        justify-content:center;
        gap:7px;
    }

    .cutoff-print-btn{
        width:36px;
        height:32px;
        font-size:15px;
    }
}

.sigma-action-icon{
    font-size:17px;
    line-height:1;
    display:inline-flex;
    align-items:center;
    justify-content:center;
}

#btnReturn.sigma-action-btn{
    background:#ffd34d!important;
    color:#06111f!important;
    border:2px solid #ffd34d!important;
}

#btnReturn.sigma-action-btn:hover{
    background:#ffdf70!important;
    color:#06111f!important;
}

/* ================= SIDEBAR PANEL IN SIGMA RESULT ================= */

.layout.result-mode.menu-open .sidebar{
    display:block!important;
    position:fixed!important;
    top:0!important;
    left:0!important;
    width:340px!important;
    max-width:86vw!important;
    height:100vh!important;
    z-index:9998!important;

    background:#081827!important;
    border-right:2px solid #ffd34d!important;
    padding:16px!important;
    overflow:auto!important;

    box-shadow:12px 0 30px rgba(0,0,0,.45)!important;
}

.layout.result-mode.menu-open .content{
    width:100%!important;
}

.layout.result-mode.menu-open ~ .sidebar-backdrop,
body.sidebar-open .sidebar-backdrop{
    display:block!important;
}

/* Nút 3 gạch luôn nổi trên Sigma */
.layout.result-mode ~ .sidebar-toggle-btn,
body .sidebar-toggle-btn{
    z-index:10000!important;
}

/* Vị trí nút khi đang ở Sigma Result */
.layout.result-mode .sidebar-toggle-btn{
    left:14px!important;
}

/* Vì nút nằm ngoài .layout nên dùng body/result-mode bằng class phụ */
body.sigma-result-mode .sidebar-toggle-btn{
    left:14px!important;
    top:204px!important;
}

body.sigma-result-mode.sidebar-open .sidebar-toggle-btn{
    left:calc(min(340px, 86vw) + 10px)!important;
}

/* Mobile trong Sigma */
@media(max-width:900px){
    body.sigma-result-mode .sidebar-toggle-btn{
        top:22px!important;
        left:10px!important;
    }

    body.sigma-result-mode.sidebar-open .sidebar-toggle-btn{
        left:calc(min(86vw, 360px) + 8px)!important;
    }

    .layout.result-mode.menu-open .sidebar{
        width:86vw!important;
        max-width:360px!important;
    }
}



  </style>
</head>
<body>
<header class="topbar">
  <div class="logoBox"><img src="{{ logo_file }}" onerror="this.style.display='none'" /></div>
  <div class="eventTitle">
      <h1 class="header-title">{{ event_name }}</h1>

      <div class="header-date">
          {{ event_date }}
      </div>

      <div class="header-location">
          {{ event_location }}
      </div>
  </div>
  <div class="rightBlank"></div>

</header>

<button id="btnToggleSidebar" class="sidebar-toggle-btn" type="button" title="Menu">
    ☰
</button>

<div id="sidebarBackdrop" class="sidebar-backdrop"></div>

<main class="layout">
  <aside class="sidebar">

      <div class="quickMenu">
          <div class="quickMenuTitle">LIST & RANKING</div>

          <button id="btnOpenInfoList" class="quickMenuBtn">
              ▸ List
          </button>

          <button id="btnOpenMedalStandings" class="quickMenuBtn">
              ▸ Medal Standings
          </button>

          <button id="btnOpenRanking" class="quickMenuBtn">
              ▸ Ranking
          </button>
      </div>

      <div class="sideTitle">DIVISIONS</div>
      <div id="menu"></div>

  </aside>



  <section class="content">
    <section id="infoListView" class="tool-card hidden">
        <div class="tool-title-row">
            <h3>Information List</h3>
            <button class="btn-result" onclick="loadInformationList()">Refresh</button>
        </div>

        <div class="filter-grid">
            <input id="infoSearch" placeholder="Tìm tên, NOC, quốc gia, đoàn..." oninput="renderInformationList()">

            <select id="infoNocFilter" onchange="renderInformationList()">
                <option value="">Country</option>
            </select>

            <select id="infoGenderFilter" onchange="renderInformationList()">
                <option value="">Gender</option>
                <option value="MALE">MALE</option>
                <option value="FEMALE">FEMALE</option>
            </select>

            <select id="infoAgeFilter" onchange="renderInformationList()">
                <option value="">Age</option>
            </select>

            <select id="infoEventFilter" onchange="renderInformationList()">
                <option value="">Divisions</option>
            </select>
        </div>

        <div class="table-scroll">
            <table id="infoListTable"></table>
        </div>
    </section>


    <section id="rankingView" class="tool-card hidden">
        <div class="tool-title-row">
            <h3>Ranking Summary</h3>
            <button class="btn-result" onclick="loadRankingSummary()">Refresh</button>
        </div>

        <div class="filter-grid">
            <input id="rankingSearch" placeholder="Tìm NOC, tên VĐV hoặc division..." oninput="renderRankingSummary()">

            <select id="rankingTypeFilter" onchange="renderRankingSummary()">
                <option value="">All Type</option>
                <option value="Recognized">Recognized</option>
                <option value="Freestyle">Freestyle</option>
                <option value="Demonstration">Demonstration</option>
                <option value="Mixer">Mixer</option>
            </select>

            <select id="rankingMedalFilter" onchange="renderRankingSummary()">
                <option value="">All Medal</option>
                <option value="gold">Gold</option>
                <option value="silver">Silver</option>
                <option value="bronze">Bronze</option>
            </select>
        </div>

        <div id="rankingCards" class="ranking-card-grid"></div>
    </section>

    <section id="medalStandingsView" class="tool-card hidden">
        <div class="tool-title-row">
            <h3>Medal Standings</h3>
            <button class="btn-result" onclick="loadMedalStandings()">Refresh</button>
        </div>

        <div class="filter-grid">
            <input
                id="medalStandingSearch"
                placeholder="Tìm NOC, quốc gia, division..."
                oninput="renderMedalStandings()"
            >

            <select id="medalStandingTypeFilter" onchange="renderMedalStandings()">
                <option value="">All Type</option>
                <option value="Recognized">Recognized</option>
                <option value="Freestyle">Freestyle</option>
                <option value="Demonstration">Demonstration</option>
                <option value="Mixer">Mixer</option>
            </select>
        </div>

        <div class="table-scroll">
            <table id="medalStandingsTable" class="medal-standing-table"></table>
        </div>
    </section>

    <div class="selectedBox">
      <div>
        <div class="label">Watching</div>
        <h2 id="selectedTitle">Select Division</h2>
      </div>
      <button onclick="reloadCurrent()">Refresh</button>
    </div>

    <section class="card athlete-card">
      <div class="section-title-row">
        <h3>Team/Athlete List</h3>
        <button id="btnResult" class="btn-result">Sigma</button>
      </div>

      <div class="table-scroll athlete-table-scroll">
          <table id="athleteTable"></table>
      </div>
    </section>

    <div id="sigmaView" class="sigma-view hidden">
      <div class="sigma-title-row">
        <div></div>

        <div style="text-align:center">
            <div class="sigma-title">SIGMA RESULT</div>
            <div id="sigmaDivisionTitle"
                 style="
                    color:#cfe6ff;
                    font-size:18px;
                    font-weight:700;
                    margin-top:6px;
                    letter-spacing:1px;
                 ">
            </div>
        </div>

        <div class="sigma-action-box">
            <button id="btnSigmaPrint" class="btn-result sigma-action-btn" type="button">
                <span class="sigma-action-icon">🖨</span>
            </button>

            <button id="btnSigmaPdf" class="btn-result sigma-action-btn" type="button">
                <span class="sigma-action-icon">📄</span>
            </button>

            <button id="btnReturn" class="btn-result sigma-action-btn" type="button">
                Return
            </button>
        </div>
      </div>

      <div id="sigmaBracket" class="sigma-bracket"></div>
    </div>
  </section>
</main>

<script>

let CURRENT_KEY = "";
let FLAT = [];
let CURRENT_RESULTS = [];

let INFORMATION_ROWS = [];
let ALL_RESULTS_ROWS = [];
let RANKING_CARDS = [];
let MEDAL_STANDINGS_ROWS = [];
let MEDAL_STANDINGS_DIVISIONS = [];

function clearQuickMenuActive(){
    document.querySelectorAll(".quickMenuBtn").forEach(b => b.classList.remove("active"));
}

function hideMainDivisionViews(){
    const selectedBox = document.querySelector(".selectedBox");
    const athleteCard = document.querySelector(".athlete-card");
    const sigmaView = document.getElementById("sigmaView");
    const medalStandingsView = document.getElementById("medalStandingsView");
    const layout = document.querySelector(".layout");

    if(layout) layout.classList.remove("result-mode");
    if(selectedBox) selectedBox.classList.add("hidden");
    if(athleteCard) athleteCard.classList.add("hidden");
    if(sigmaView) sigmaView.classList.add("hidden");
    if(medalStandingsView) medalStandingsView.classList.add("hidden");
}

function showMainDivisionViews(){
    const selectedBox = document.querySelector(".selectedBox");
    const athleteCard = document.querySelector(".athlete-card");
    const infoListView = document.getElementById("infoListView");
    const rankingView = document.getElementById("rankingView");
    const medalStandingsView = document.getElementById("medalStandingsView");

    if(infoListView) infoListView.classList.add("hidden");
    if(rankingView) rankingView.classList.add("hidden");
    if(medalStandingsView) medalStandingsView.classList.add("hidden");

    if(selectedBox) selectedBox.classList.remove("hidden");
    if(athleteCard) athleteCard.classList.remove("hidden");

    clearQuickMenuActive();
}

function showInfoListView(){
    hideMainDivisionViews();

    const infoListView = document.getElementById("infoListView");
    const rankingView = document.getElementById("rankingView");
    const medalStandingsView = document.getElementById("medalStandingsView");

    if(infoListView) infoListView.classList.remove("hidden");
    if(rankingView) rankingView.classList.add("hidden");
    if(medalStandingsView) medalStandingsView.classList.add("hidden");

    clearQuickMenuActive();
    document.getElementById("btnOpenInfoList")?.classList.add("active");

    loadInformationList();
}

function showRankingView(){
    hideMainDivisionViews();

    const infoListView = document.getElementById("infoListView");
    const rankingView = document.getElementById("rankingView");
    const medalStandingsView = document.getElementById("medalStandingsView");

    if(infoListView) infoListView.classList.add("hidden");
    if(rankingView) rankingView.classList.remove("hidden");
    if(medalStandingsView) medalStandingsView.classList.add("hidden");

    clearQuickMenuActive();
    document.getElementById("btnOpenRanking")?.classList.add("active");

    loadRankingSummary();
}

function showMedalStandingsView(){
    hideMainDivisionViews();

    const infoListView = document.getElementById("infoListView");
    const rankingView = document.getElementById("rankingView");
    const medalStandingsView = document.getElementById("medalStandingsView");

    if(infoListView) infoListView.classList.add("hidden");
    if(rankingView) rankingView.classList.add("hidden");
    if(medalStandingsView) medalStandingsView.classList.remove("hidden");

    clearQuickMenuActive();
    document.getElementById("btnOpenMedalStandings")?.classList.add("active");

    loadMedalStandings();
}

function getRowAny(row, keys){
    for(const k of keys){
        if(row && row[k] !== undefined && row[k] !== null && row[k] !== ""){
            return row[k];
        }
    }
    return "";
}

function normalizeUpper(v){
    return String(v || "").trim().toUpperCase();
}

function getMetaMatchPrefix(meta){
    if(!meta) return "";

    const typeMap = {
        "Recognized":"R",
        "Freestyle":"F",
        "Demonstration":"D",
        "Mixer":"M"
    };

    const divMap = {
        "Individual":"I",
        "Pair":"P",
        "Team":"T"
    };

    const genderMap = {
        "Male":"M",
        "Female":"F"
    };

    const t = typeMap[meta.type] || "";
    const d = divMap[meta.division] || "";
    const g = genderMap[meta.gender] || "";

    let ageRaw = String(meta.age || "").trim().toUpperCase();

    const ageMap = {
        "CADET": "U14",
        "JUNIOR": "U17",
        "UNDER 14": "U14",
        "U 14": "U14",
        "U14": "U14",
        "UNDER 17": "U17",
        "U 17": "U17",
        "U17": "U17"
    };

    let age = ageMap[ageRaw] || ageRaw.replace(/\s+/g, "");

    return `${t}${d}${g}${age}`;
}

function getResultMatch(row){
    return normalizeUpper(getRowAny(row, ["Match", "match"]));
}

function getResultNocBlue(row){
    return String(getRowAny(row, ["NOC Blue", "NOC_Blue", "NOC blue", "noc_blue"])).trim();
}

function getResultNocRed(row){
    return String(getRowAny(row, ["NOC Red", "NOC_Red", "NOC red", "noc_red"])).trim();
}

function getResultWinnerNoc(row){
    const result = normalizeUpper(getRowAny(row, ["Result", "result", "Winner", "winner"]));
    const nocBlue = getResultNocBlue(row);
    const nocRed = getResultNocRed(row);

    // CHEONG = BLUE
    if(result.includes("CHEONG") || result.includes("BLUE")){
        return nocBlue;
    }

    // HONG = RED
    if(result.includes("HONG") || result.includes("RED")){
        return nocRed;
    }

    if(nocBlue && result.includes(nocBlue.toUpperCase())){
        return nocBlue;
    }

    if(nocRed && result.includes(nocRed.toUpperCase())){
        return nocRed;
    }

    return "";
}

function getResultLoserNoc(row){
    const winner = normalizeUpper(getResultWinnerNoc(row));
    const blue = getResultNocBlue(row);
    const red = getResultNocRed(row);

    if(!winner) return "";

    if(winner === normalizeUpper(blue)) return red;
    if(winner === normalizeUpper(red)) return blue;

    return "";
}

function getRowScore(row){
    const fields = [
        "Total Point Blue",
        "Blue Point 1",
        "Total",
        "Score",
        "score",
        "_score"
    ];

    for(const f of fields){
        const v = row[f];
        if(v !== undefined && v !== null && v !== ""){
            const n = Number(v);
            if(!Number.isNaN(n)) return n;
        }
    }

    return 0;
}

function getPhaseName(row){
    return String(getRowAny(row, ["Phase", "phase", "Round", "round"])).trim();
}

function placeLabel(place){
    if(Number(place) === 1) return `<span class="rank-gold">🥇 1</span>`;
    if(Number(place) === 2) return `<span class="rank-silver">🥈 2</span>`;
    if(Number(place) === 3) return `<span class="rank-bronze">🥉 3</span>`;
    if(Number(place) === 4) return `<span class="rank-fourth">🥉 4</span>`;
    return "";
}

async function loadInformationList(){
    const table = document.getElementById("infoListTable");
    if(table){
        table.innerHTML = `<tr><td class="empty">Đang tải Information List...</td></tr>`;
    }

    if(!FLAT || !FLAT.length){
        try{
            const menuData = await fetch("/api/menu").then(r => r.json());
            FLAT = menuData.flat || [];
        }catch(e){
            console.error(e);
        }
    }

    try{
        INFORMATION_ROWS = await fetch("/api/information-list").then(r => r.json());
    }catch(e){
        console.error(e);
        INFORMATION_ROWS = [];
    }

    buildInformationFilters();
    renderInformationList();
}

function buildInformationFilters(){
    const nocSelect = document.getElementById("infoNocFilter");
    const ageSelect = document.getElementById("infoAgeFilter");
    const eventSelect = document.getElementById("infoEventFilter");

    if(nocSelect){
        const current = nocSelect.value;
        const nocs = new Set();

        INFORMATION_ROWS.forEach(r => {
            const noc = String(getRowAny(r, ["NOC", "noc", "Country", "country", "Team", "team"])).trim();
            if(noc) nocs.add(noc);
        });

        nocSelect.innerHTML = `<option value="">Country</option>` +
            [...nocs].sort().map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");

        nocSelect.value = current;
    }

    if(ageSelect){
        const current = ageSelect.value;
        const ages = new Set();

        (FLAT || []).forEach(m => {
            const age = String(m.age || "").trim();
            if(age) ages.add(age);
        });

        ageSelect.innerHTML = `<option value="">Age</option>` +
            [...ages].sort().map(a => `<option value="${esc(a)}">${esc(a)}</option>`).join("");

        if([...ages].includes(current)){
            ageSelect.value = current;
        }else{
            ageSelect.value = "";
        }
    }

    if(eventSelect){
        const current = eventSelect.value;

        const divisionOptions = [
            "Recognized Individual",
            "Recognized Pair",
            "Recognized Team",
            "Freestyle Individual",
            "Freestyle Pair",
            "Freestyle Team",
            "Demonstration"
        ];

        eventSelect.innerHTML =
            `<option value="">Divisions</option>` +
            divisionOptions
                .map(e => `<option value="${esc(e)}">${esc(e)}</option>`)
                .join("");

        if(divisionOptions.includes(current)){
            eventSelect.value = current;
        }else{
            eventSelect.value = "";
        }
    }
}


function normText(v){
    return String(v || "")
        .trim()
        .toUpperCase()
        .replace(/\s*-\s*/g, " ")
        .replace(/\s+/g, " ");
}

function getInfoRowEvents(row){
    const events = [];

    Object.keys(row || {}).forEach(k => {
        if(String(k).toLowerCase().startsWith("event")){
            const v = String(row[k] || "").trim();
            if(v) events.push(v);
        }
    });

    return events;
}

function rowHasSelectedDivision(row, selectedDivision){
    if(!selectedDivision) return true;

    const selected = normText(selectedDivision);
    const rowEvents = getInfoRowEvents(row);

    return rowEvents.some(ev => {
        const e = normText(ev);
        return e === selected || e.includes(selected) || selected.includes(e);
    });
}

function getBirthYearFromDob(dob){
    const s = String(dob || "").trim();
    if(!s) return null;

    const m = s.match(/^(\d{4})/);
    if(!m) return null;

    const y = Number(m[1]);
    if(Number.isNaN(y)) return null;

    return y;
}

function getAgeFromRow(row){
    const dob = getRowAny(row, ["DOB", "dob", "Birthdate", "birthdate", "Date of Birth", "date_of_birth"]);
    const y = getBirthYearFromDob(dob);

    if(!y) return null;

    // Ken đang set event năm 2026
    return 2026 - y;
}

function rowHasSelectedAge(row, selectedAge){
    if(!selectedAge) return true;

    const ageText = normText(selectedAge);
    const age = getAgeFromRow(row);

    // Nếu không có DOB thì không loại, để tránh mất VĐV do dữ liệu thiếu
    if(age === null) return true;

    if(ageText.includes("CADET")){
        return age >= 12 && age <= 14;
    }

    if(ageText.includes("JUNIOR")){
        return age >= 15 && age <= 17;
    }

    if(ageText.includes("U14") || ageText.includes("UNDER 14")){
        return age <= 14;
    }

    if(ageText.includes("U17") || ageText.includes("UNDER 17")){
        return age <= 17;
    }

    if(ageText.includes("O17") || ageText.includes("OVER 17")){
        return age > 17;
    }

    if(ageText.includes("U30") || ageText.includes("UNDER 30")){
        return age <= 30;
    }

    if(ageText.includes("U40") || ageText.includes("UNDER 40")){
        return age <= 40;
    }

    if(ageText.includes("U50") || ageText.includes("UNDER 50")){
        return age <= 50;
    }

    if(ageText.includes("U60") || ageText.includes("UNDER 60")){
        return age <= 60;
    }

    if(ageText.includes("U65") || ageText.includes("UNDER 65")){
        return age <= 65;
    }

    if(ageText.includes("O65") || ageText.includes("OVER 65")){
        return age > 65;
    }

    return true;
}


function renderInformationList(){
    const table = document.getElementById("infoListTable");
    if(!table) return;

    const search = normalizeUpper(document.getElementById("infoSearch")?.value || "");
    const nocFilter = normalizeUpper(document.getElementById("infoNocFilter")?.value || "");
    const genderFilter = normalizeUpper(document.getElementById("infoGenderFilter")?.value || "");
    const ageFilter = String(document.getElementById("infoAgeFilter")?.value || "").trim();
    const eventFilter = String(document.getElementById("infoEventFilter")?.value || "").trim();


    let rows = [...INFORMATION_ROWS];

    rows = rows.filter(r => {
        const allText = normalizeUpper(Object.values(r || {}).join(" "));
        const noc = normalizeUpper(getRowAny(r, ["NOC", "noc", "Country", "country", "Team", "team"]));
        const gender = normalizeUpper(getRowAny(r, ["Gender", "gender"]));

        if(search && !allText.includes(search)) return false;
        if(nocFilter && noc !== nocFilter) return false;
        if(genderFilter && gender !== genderFilter) return false;
        if(ageFilter && !rowHasSelectedAge(r, ageFilter)) return false;
        if(eventFilter && !rowHasSelectedDivision(r, eventFilter)) return false;

        return true;
    });

    if(!rows.length){
        table.innerHTML = `<tr><td class="empty">Không có dữ liệu phù hợp</td></tr>`;
        return;
    }

    const preferred = [
        "NOC",
        "Country",
        "Full name",
        "DOB",
        "Gender",
        "Position",
        "Event_1",
        "Event_2",
        "Event_3",
        "Event_4",
        "Event_5",
        "Event_6",
        "Event_7",
        "Event_8",
        "Event_9",
        "Event_10"
    ];

    let cols = preferred.filter(c =>
        rows.some(r => r[c] !== undefined && r[c] !== null && r[c] !== "")
    );

    Object.keys(rows[0] || {})
        .filter(c =>
            !cols.includes(c) &&
            !String(c).startsWith("_") &&
            !["id", "idx"].includes(String(c).toLowerCase())
        )
        .sort((a, b) => {
            const ma = String(a).match(/^Event_(\d+)$/i);
            const mb = String(b).match(/^Event_(\d+)$/i);

            if(ma && mb){
                return Number(ma[1]) - Number(mb[1]);
            }

            if(ma) return 1;
            if(mb) return -1;

            return String(a).localeCompare(String(b));
        })
        .forEach(c => cols.push(c));

    table.innerHTML =
        `<thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
        `<tbody>${rows.map(r => `
            <tr>
                ${cols.map(c => `<td>${esc(r[c] ?? "")}</td>`).join("")}
            </tr>
        `).join("")}</tbody>`;
}

async function loadRankingSummary(){
    const box = document.getElementById("rankingCards");
    if(box){
        box.innerHTML = `<div class="empty">Đang tổng hợp Ranking...</div>`;
    }

    // Ranking bắt buộc lấy division từ file Sigma JSON
    // tức là lấy từ /api/menu -> FLAT
    try{
        const menuData = await fetch("/api/menu").then(r => r.json());
        FLAT = menuData.flat || [];
    }catch(e){
        console.error("Load sigma divisions error:", e);
        FLAT = [];
    }

    try{
        ALL_RESULTS_ROWS = await fetch("/api/all-results").then(r => r.json());
    }catch(e){
        console.error("Load all results error:", e);
        ALL_RESULTS_ROWS = [];
    }

    buildRankingCards();
    renderRankingSummary();
}

function getResultAthleteBlue(row){
    return String(getRowAny(row, [
        "Athlete Blue",
        "Athlete_Blue",
        "Full name Blue",
        "Full_name_Blue",
        "Full name",
        "Full_name",
        "Athlete",
        "athlete"
    ])).trim();
}

function getResultAthleteRed(row){
    return String(getRowAny(row, [
        "Athlete Red",
        "Athlete_Red",
        "Full name Red",
        "Full_name_Red"
    ])).trim();
}

function getResultWinnerSide(row){
    const result = normalizeUpper(getRowAny(row, ["Result", "result", "Winner", "winner"]));
    const nocBlue = normalizeUpper(getResultNocBlue(row));
    const nocRed = normalizeUpper(getResultNocRed(row));

    // CHEONG = BLUE
    if(result.includes("CHEONG") || result.includes("BLUE")){
        return "blue";
    }

    // HONG = RED
    if(result.includes("HONG") || result.includes("RED")){
        return "red";
    }

    if(nocBlue && result.includes(nocBlue)){
        return "blue";
    }

    if(nocRed && result.includes(nocRed)){
        return "red";
    }

    return "";
}

function getWinnerCompetitor(row){
    const side = getResultWinnerSide(row);

    if(side === "blue"){
        return {
            noc:getResultNocBlue(row),
            name:getResultAthleteBlue(row)
        };
    }

    if(side === "red"){
        return {
            noc:getResultNocRed(row),
            name:getResultAthleteRed(row)
        };
    }

    return {
        noc:"",
        name:""
    };
}

function getLoserCompetitor(row){
    const side = getResultWinnerSide(row);

    if(side === "blue"){
        return {
            noc:getResultNocRed(row),
            name:getResultAthleteRed(row)
        };
    }

    if(side === "red"){
        return {
            noc:getResultNocBlue(row),
            name:getResultAthleteBlue(row)
        };
    }

    return {
        noc:"",
        name:""
    };
}

function getMatchNumberByPrefix(row, prefix){
    const match = getResultMatch(row);
    if(!match || !prefix) return 0;

    const n = Number(match.replace(prefix.toUpperCase(), ""));
    return Number.isNaN(n) ? 0 : n;
}

function getRowsForDivision(meta){
    const prefix = getMetaMatchPrefix(meta).toUpperCase();

    if(!prefix) return [];

    return (ALL_RESULTS_ROWS || []).filter(r => {
        const match = getResultMatch(r);
        return match && match.startsWith(prefix);
    });
}

function isCutoffMeta(meta, rows){
    const type = String(meta?.type || "").toLowerCase();

    if(type.includes("freestyle")) return true;
    if(type.includes("demonstration")) return true;
    if(type.includes("demon")) return true;

    return (rows || []).some(r => {
        const method = String(getRowAny(r, ["Method", "method"])).toLowerCase();
        return method.includes("cut");
    });
}

function getScoreCompetitor(row){
    return {
        noc:getResultNocBlue(row),
        name:getResultAthleteBlue(row),
        score:getRowScore(row)
    };
}

function getCutoffMedalists(meta, rows){
    const finalRows = rows.filter(r => {
        const phase = getPhaseName(r).toLowerCase();
        return phase.includes("final");
    });

    const useRows = finalRows.length ? finalRows : rows;

    const byCompetitor = {};

    useRows.forEach(r => {
        const c = getScoreCompetitor(r);

        if(!c.noc && !c.name) return;

        const key = `${normalizeUpper(c.noc)}|${normalizeUpper(c.name)}`;

        if(!byCompetitor[key] || c.score > byCompetitor[key].score){
            byCompetitor[key] = c;
        }
    });

    const ranked = Object.values(byCompetitor)
        .filter(x => x.noc || x.name)
        .sort((a, b) => b.score - a.score)
        .slice(0, 4);

    return [
        {
            medal:"gold",
            label:"🥇 Gold",
            noc:ranked[0]?.noc || "",
            name:ranked[0]?.name || "",
            score:ranked[0]?.score ?? ""
        },
        {
            medal:"silver",
            label:"🥈 Silver",
            noc:ranked[1]?.noc || "",
            name:ranked[1]?.name || "",
            score:ranked[1]?.score ?? ""
        },
        {
            medal:"bronze",
            label:"🥉 Bronze",
            noc:ranked[2]?.noc || "",
            name:ranked[2]?.name || "",
            score:ranked[2]?.score ?? ""
        },
        {
            medal:"bronze",
            label:"🥉 Bronze",
            noc:ranked[3]?.noc || "",
            name:ranked[3]?.name || "",
            score:ranked[3]?.score ?? ""
        }
    ];
}

function findSingleEliminationFinal(rows, prefix){
    const valid = rows
        .map(r => ({
            row:r,
            no:getMatchNumberByPrefix(r, prefix)
        }))
        .filter(x => x.no > 0)
        .sort((a, b) => b.no - a.no);

    return valid[0]?.row || null;
}

function makeEmptyMedals(){
    return [
        {medal:"gold", label:"🥇 Gold", noc:"", name:""},
        {medal:"silver", label:"🥈 Silver", noc:"", name:""},
        {medal:"bronze", label:"🥉 Bronze", noc:"", name:""},
        {medal:"bronze", label:"🥉 Bronze", noc:"", name:""}
    ];
}

function getMatchRowByNo(rows, prefix, matchNo){
    const fullMatch = `${prefix}${String(matchNo).padStart(3, "0")}`.toUpperCase();

    return (rows || []).find(r => {
        const match = getResultMatch(r);
        return match === fullMatch;
    }) || null;
}

function getSingleEliminationMedalists(meta, rows){
    const medals = makeEmptyMedals();
    const prefix = getMetaMatchPrefix(meta).toUpperCase();

    const competitorCount = Number(
        meta.competitor_count ||
        meta.competitorCount ||
        meta.team_count ||
        meta.count ||
        0
    );

    // Single elimination: tổng trận thật = số VĐV/đội - 1
    const finalNo = competitorCount - 1;

    if(!prefix || finalNo < 1){
        return medals;
    }

    const semi1No = finalNo - 2;
    const semi2No = finalNo - 1;

    const semi1Row = semi1No > 0 ? getMatchRowByNo(rows, prefix, semi1No) : null;
    const semi2Row = semi2No > 0 ? getMatchRowByNo(rows, prefix, semi2No) : null;
    const finalRow = getMatchRowByNo(rows, prefix, finalNo);

    // Chưa có kết quả trận chung kết thì tuyệt đối không lấy trận nhỏ hơn làm Gold/Silver
    if(!finalRow){
        return medals;
    }

    const gold = getWinnerCompetitor(finalRow);
    const silver = getLoserCompetitor(finalRow);

    medals[0].noc = gold.noc;
    medals[0].name = gold.name;

    medals[1].noc = silver.noc;
    medals[1].name = silver.name;

    // HCĐ là 2 người/đội thua bán kết
    if(semi1Row){
        const bronze1 = getLoserCompetitor(semi1Row);
        medals[2].noc = bronze1.noc;
        medals[2].name = bronze1.name;
    }

    if(semi2Row){
        const bronze2 = getLoserCompetitor(semi2Row);
        medals[3].noc = bronze2.noc;
        medals[3].name = bronze2.name;
    }

    return medals;
}

function buildRankingCards(){
    const cards = [];

    // Chỉ lấy các division đã có trong file Sigma JSON
    // FLAT được tạo từ /api/menu, /api/menu lại đọc file Sigma JSON.
    (FLAT || []).forEach(meta => {
        const rows = getRowsForDivision(meta);

        let medals = [
            {medal:"gold", label:"🥇 Gold", noc:"", name:""},
            {medal:"silver", label:"🥈 Silver", noc:"", name:""},
            {medal:"bronze", label:"🥉 Bronze", noc:"", name:""},
            {medal:"bronze", label:"🥉 Bronze", noc:"", name:""}
        ];

        if(rows.length){
            const isCut = isCutoffMeta(meta, rows);

            medals = isCut
                ? getCutoffMedalists(meta, rows)
                : getSingleEliminationMedalists(meta, rows);
        }

        cards.push({
            key:meta.key,
            type:meta.type || "",
            title:meta.key,
            count:meta.count || 0,
            competitor_count:meta.competitor_count || meta.count || 0,
            hasResult:rows.length > 0,
            medals:medals
        });
    });

    RANKING_CARDS = cards;
}

function medalClass(medal){
    if(medal === "gold") return "medal-gold";
    if(medal === "silver") return "medal-silver";
    return "medal-bronze";
}

function renderRankingSummary(){
    const box = document.getElementById("rankingCards");
    if(!box) return;

    const search = normalizeUpper(document.getElementById("rankingSearch")?.value || "");
    const typeFilter = String(document.getElementById("rankingTypeFilter")?.value || "").trim();
    const medalFilter = String(document.getElementById("rankingMedalFilter")?.value || "").trim();

    let cards = [...(RANKING_CARDS || [])];

    if(typeFilter){
        cards = cards.filter(c => String(c.type || "") === typeFilter);
    }

    if(search){
        cards = cards.filter(c => {
            const text = [
                c.title,
                c.type,
                ...(c.medals || []).flatMap(m => [m.noc, m.name])
            ].join(" ");

            return normalizeUpper(text).includes(search);
        });
    }

    if(medalFilter){
        cards = cards.map(c => ({
            ...c,
            medals:(c.medals || []).filter(m => m.medal === medalFilter)
        }));
    }

    if(!cards.length){
        box.innerHTML = `<div class="empty">Chưa có division nào trong file Sigma</div>`;
        return;
    }

    box.innerHTML = cards.map(card => `
        <div class="ranking-division-card">
            <div class="ranking-division-title">
                ${esc(card.title)}
                <div style="font-size:12px;color:#cfe6ff;margin-top:4px">
                    ${card.hasResult ? "Result loaded" : "No result yet"} · ${card.competitor_count || card.count || 0} athletes/teams
                </div>
            </div>

            <table class="ranking-medal-table">
                <thead>
                    <tr>
                        <th style="width:105px">Medal</th>
                        <th style="width:90px">NOC</th>
                        <th>Full name</th>
                    </tr>
                </thead>

                <tbody>
                    ${(card.medals || []).map(m => `
                        <tr>
                            <td class="medal-cell ${medalClass(m.medal)}">${esc(m.label)}</td>
                            <td class="${m.noc ? "" : "ranking-empty-cell"}">${esc(m.noc || "-")}</td>
                            <td class="${m.name ? "" : "ranking-empty-cell"}">${esc(m.name || "-")}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `).join("");
}

async function loadMedalStandings(){
    const table = document.getElementById("medalStandingsTable");
    if(table){
        table.innerHTML = `<tr><td class="empty">Đang tổng hợp Medal Standings...</td></tr>`;
    }

    try{
        const menuData = await fetch("/api/menu").then(r => r.json());
        FLAT = menuData.flat || [];
    }catch(e){
        console.error("Load menu for medal standings error:", e);
        FLAT = [];
    }

    try{
        ALL_RESULTS_ROWS = await fetch("/api/all-results").then(r => r.json());
    }catch(e){
        console.error("Load all results for medal standings error:", e);
        ALL_RESULTS_ROWS = [];
    }

    try{
        INFORMATION_ROWS = await fetch("/api/information-list").then(r => r.json());
    }catch(e){
        console.error("Load information list for medal standings error:", e);
        INFORMATION_ROWS = [];
    }

    buildRankingCards();
    buildMedalStandingsRows();
    renderMedalStandings();
}

function getDelegationStatsByNoc(){
    const stats = {};

    (INFORMATION_ROWS || []).forEach(row => {
        const noc = String(getRowAny(row, [
            "NOC",
            "noc",
            "Country",
            "country",
            "Team",
            "team"
        ])).trim();

        if(!noc) return;

        const key = normalizeUpper(noc);

        if(!stats[key]){
            stats[key] = {
                noc:noc,

                // Tổng toàn bộ người trong đoàn / tham gia
                total:0,

                // VĐV
                athletes:0,
                maleAthletes:0,
                femaleAthletes:0,

                // Coach
                coaches:0,

                // Người còn lại không phải VĐV/Coach
                otherOfficials:0,

                // Giữ lại để tương thích code cũ
                otherAthletes:0,
                delegation:0
            };
        }

        stats[key].total += 1;
        stats[key].delegation += 1;

        const position = normalizeUpper(getRowAny(row, [
            "Position",
            "position",
            "Role",
            "role",
            "Duty",
            "duty",
            "Function",
            "function"
        ]));

        const gender = normalizeUpper(getRowAny(row, [
            "Gender",
            "gender",
            "Sex",
            "sex"
        ]));

        const isCoach =
            position.includes("COACH") ||
            position.includes("TRAINER") ||
            position.includes("HLV");

        const isAthlete =
            position.includes("ATHLETE") ||
            position.includes("PLAYER") ||
            position.includes("COMPETITOR") ||
            position === "";

        if(isCoach){
            stats[key].coaches += 1;
            return;
        }

        if(isAthlete){
            stats[key].athletes += 1;

            if(gender.includes("MALE") && !gender.includes("FEMALE")){
                stats[key].maleAthletes += 1;
            }else if(gender.includes("FEMALE")){
                stats[key].femaleAthletes += 1;
            }else{
                stats[key].otherAthletes += 1;
            }

            return;
        }

        stats[key].otherOfficials += 1;
    });

    return stats;
}

function makeMedalStandingEmptyRow(noc, delegationStats){
    const key = normalizeUpper(noc);
    const stat = delegationStats[key] || {};

    return {
        noc:noc,
        noc_key:key,
        byDivision:{},

        totalGold:0,
        totalSilver:0,
        totalBronze:0,
        totalMedal:0,

        total:Number(stat.total || stat.delegation || 0),
        athletes:Number(stat.athletes || 0),
        maleAthletes:Number(stat.maleAthletes || 0),
        femaleAthletes:Number(stat.femaleAthletes || 0),
        coaches:Number(stat.coaches || 0),
        otherAthletes:Number(stat.otherAthletes || 0),
        otherOfficials:Number(stat.otherOfficials || 0),
        delegation:Number(stat.delegation || stat.total || 0),

        ranking:0
    };
}

function buildMedalStandingsRows(){
    const delegationStats = getDelegationStatsByNoc();
    const typeFilter = String(document.getElementById("medalStandingTypeFilter")?.value || "").trim();

    let cards = [...(RANKING_CARDS || [])];

    if(typeFilter){
        cards = cards.filter(c => String(c.type || "") === typeFilter);
    }

    cards = prepareMedalStandingDivisions(
        cards.map(c => ({
            ...c,
            title:c.title,
            key:c.key
        }))
    );

    MEDAL_STANDINGS_DIVISIONS = cards.map(c => ({
        key:c.key,
        title:c.title,
        type:c.type || "",
        typeLabel:c.typeLabel,
        divisionLabel:c.divisionLabel,
        genderLabel:c.genderLabel,
        ageLabel:c.ageLabel,
        genderAgeLabel:c.genderAgeLabel
    }));

    const rowsMap = {};

    Object.values(delegationStats).forEach(stat => {
        const key = normalizeUpper(stat.noc);

        if(!rowsMap[key]){
            rowsMap[key] = makeMedalStandingEmptyRow(stat.noc, delegationStats);
        }
    });

    cards.forEach(card => {
        const divisionKey = card.key;

        (card.medals || []).forEach(m => {
            const noc = String(m.noc || "").trim();
            if(!noc) return;

            const key = normalizeUpper(noc);

            if(!rowsMap[key]){
                rowsMap[key] = makeMedalStandingEmptyRow(noc, delegationStats);
            }

            if(!rowsMap[key].byDivision[divisionKey]){
                rowsMap[key].byDivision[divisionKey] = {
                    gold:0,
                    silver:0,
                    bronze:0
                };
            }

            if(m.medal === "gold"){
                rowsMap[key].byDivision[divisionKey].gold += 1;
                rowsMap[key].totalGold += 1;
            }else if(m.medal === "silver"){
                rowsMap[key].byDivision[divisionKey].silver += 1;
                rowsMap[key].totalSilver += 1;
            }else if(m.medal === "bronze"){
                rowsMap[key].byDivision[divisionKey].bronze += 1;
                rowsMap[key].totalBronze += 1;
            }
        });
    });

    let rows = Object.values(rowsMap);

    rows.forEach(row => {
        row.totalMedal =
            Number(row.totalGold || 0) +
            Number(row.totalSilver || 0) +
            Number(row.totalBronze || 0);
    });

    rows.sort((a, b) => {
        // 1. Vàng
        if(b.totalGold !== a.totalGold) return b.totalGold - a.totalGold;

        // 2. Bạc
        if(b.totalSilver !== a.totalSilver) return b.totalSilver - a.totalSilver;

        // 3. Đồng
        if(b.totalBronze !== a.totalBronze) return b.totalBronze - a.totalBronze;

        // 4. Tổng toàn bộ huy chương
        if(b.totalMedal !== a.totalMedal) return b.totalMedal - a.totalMedal;

        // 5. Đoàn đông nhất
        if(b.total !== a.total) return b.total - a.total;
        if(b.athletes !== a.athletes) return b.athletes - a.athletes;
        if(b.delegation !== a.delegation) return b.delegation - a.delegation;

        return String(a.noc).localeCompare(String(b.noc));
    });

    rows.forEach((row, index) => {
        row.ranking = index + 1;
    });

    MEDAL_STANDINGS_ROWS = rows;
}

function parseMedalDivisionTitle(title){
    const raw = String(title || "").trim();

    let type = "Other";
    let rest = raw;

    if(raw.includes(" - ")){
        const parts = raw.split(" - ");
        type = String(parts[0] || "Other").trim();
        rest = parts.slice(1).join(" - ").trim();
    }else{
        const knownTypes = ["Recognized", "Freestyle", "Demonstration", "Mixer"];

        for(const t of knownTypes){
            if(raw.toLowerCase().startsWith(t.toLowerCase())){
                type = t;
                rest = raw.slice(t.length).trim();
                break;
            }
        }
    }

    if(/demo|demon/i.test(type)){
        type = "Demonstration";
    }

    let division = "Other";

    if(/\bIndividual\b/i.test(rest)){
        division = "Individual";
    }else if(/\bPair\b/i.test(rest)){
        division = "Pair";
    }else if(/\bTeam\b/i.test(rest)){
        division = "Team";
    }

    let gender = "Open";

    if(/\bMale\b/i.test(rest)){
        gender = "Male";
    }else if(/\bFemale\b/i.test(rest)){
        gender = "Female";
    }else if(/\bMixed\b/i.test(rest)){
        gender = "Mixed";
    }

    let age = rest
        .replace(/\bIndividual\b/ig, "")
        .replace(/\bPair\b/ig, "")
        .replace(/\bTeam\b/ig, "")
        .replace(/\bMale\b/ig, "")
        .replace(/\bFemale\b/ig, "")
        .replace(/\bMixed\b/ig, "")
        .replace(/\s+/g, " ")
        .trim();

    if(!age){
        age = "Open";
    }

    const genderAge = gender === "Open"
        ? age
        : `${gender} ${age}`;

    return {
        type:type,
        division:division,
        gender:gender,
        age:age,
        genderAge:genderAge
    };
}

function medalTypeOrder(type){
    const t = String(type || "").toLowerCase();

    if(t.includes("recognized")) return 1;
    if(t.includes("freestyle")) return 2;
    if(t.includes("demonstration") || t.includes("demon")) return 3;
    if(t.includes("mixer") || t.includes("mixed")) return 4;

    return 99;
}

function medalDivisionOrder(division){
    const d = String(division || "").toLowerCase();

    if(d.includes("individual")) return 1;
    if(d.includes("pair")) return 2;
    if(d.includes("team")) return 3;

    return 99;
}

function medalGenderOrder(gender){
    const g = String(gender || "").toLowerCase();

    if(g.includes("male")) return 1;
    if(g.includes("female")) return 2;
    if(g.includes("mixed")) return 3;

    return 99;
}

function medalAgeOrder(age){
    const a = String(age || "").toUpperCase();

    if(a.includes("U12")) return 5;
    if(a.includes("CADET")) return 10;
    if(a.includes("JUNIOR")) return 20;
    if(a.includes("U17")) return 25;
    if(a.includes("O17")) return 30;
    if(a.includes("U30")) return 40;
    if(a.includes("U40")) return 50;
    if(a.includes("U50")) return 60;
    if(a.includes("U60")) return 70;
    if(a.includes("U65")) return 80;
    if(a.includes("O65")) return 90;
    if(a.includes("OPEN")) return 100;

    const num = a.match(/\d+/);
    if(num){
        return 200 + Number(num[0]);
    }

    return 999;
}

function prepareMedalStandingDivisions(rawDivisions){
    return [...(rawDivisions || [])]
        .map(d => {
            const parsed = parseMedalDivisionTitle(d.title);

            return {
                ...d,
                typeLabel:parsed.type,
                divisionLabel:parsed.division,
                genderLabel:parsed.gender,
                ageLabel:parsed.age,
                genderAgeLabel:parsed.genderAge
            };
        })
        .sort((a, b) => {
            const ta = medalTypeOrder(a.typeLabel);
            const tb = medalTypeOrder(b.typeLabel);
            if(ta !== tb) return ta - tb;

            const da = medalDivisionOrder(a.divisionLabel);
            const db = medalDivisionOrder(b.divisionLabel);
            if(da !== db) return da - db;

            const ga = medalGenderOrder(a.genderLabel);
            const gb = medalGenderOrder(b.genderLabel);
            if(ga !== gb) return ga - gb;

            const aa = medalAgeOrder(a.ageLabel);
            const ab = medalAgeOrder(b.ageLabel);
            if(aa !== ab) return aa - ab;

            return String(a.genderAgeLabel).localeCompare(String(b.genderAgeLabel));
        });
}

function buildGroupedMedalStandingHeader(divisions){
    const firstRow = [];
    const secondRow = [];
    const thirdRow = [];

    let i = 0;

    while(i < divisions.length){
        const currentType = divisions[i].typeLabel;
        let count = 0;

        while(
            i + count < divisions.length &&
            divisions[i + count].typeLabel === currentType
        ){
            count++;
        }

        firstRow.push(`
            <th class="medal-standing-head-type" colspan="${count}">
                ${esc(currentType)}
            </th>
        `);

        i += count;
    }

    i = 0;

    while(i < divisions.length){
        const currentType = divisions[i].typeLabel;
        const currentDivision = divisions[i].divisionLabel;
        let count = 0;

        while(
            i + count < divisions.length &&
            divisions[i + count].typeLabel === currentType &&
            divisions[i + count].divisionLabel === currentDivision
        ){
            count++;
        }

        secondRow.push(`
            <th class="medal-standing-head-division" colspan="${count}">
                ${esc(currentDivision)}
            </th>
        `);

        i += count;
    }

    divisions.forEach(d => {
        thirdRow.push(`
            <th class="medal-standing-head-age">
                ${esc(d.genderAgeLabel)}
            </th>
        `);
    });

    return `
        <thead>
            <tr>
                <th class="medal-standing-fixed-head" rowspan="3" style="min-width:170px">
                    Unit / NOC
                </th>

                ${firstRow.join("")}

                <th class="medal-standing-summary-head" rowspan="3">Total Gold</th>
                <th class="medal-standing-summary-head" rowspan="3">Total Silver</th>
                <th class="medal-standing-summary-head" rowspan="3">Total Bronze</th>
                <th class="medal-standing-summary-head" rowspan="3">Total Medal</th>
                <th class="medal-standing-summary-head" rowspan="3">Ranking</th>
            </tr>

            <tr>
                ${secondRow.join("")}
            </tr>

            <tr>
                ${thirdRow.join("")}
            </tr>
        </thead>
    `;
}

function medalStandingDivisionCell(row, divisionKey){
    const d = row.byDivision[divisionKey] || {
        gold:0,
        silver:0,
        bronze:0
    };

    if(!d.gold && !d.silver && !d.bronze){
        return `<span class="ranking-empty-cell">-</span>`;
    }

    const icons = [];

    for(let i = 0; i < d.gold; i++){
        icons.push(`<span class="medal-icon-item medal-standing-gold"><span class="medal-icon-symbol">🥇</span></span>`);
    }

    for(let i = 0; i < d.silver; i++){
        icons.push(`<span class="medal-icon-item medal-standing-silver"><span class="medal-icon-symbol">🥈</span></span>`);
    }

    for(let i = 0; i < d.bronze; i++){
        icons.push(`<span class="medal-icon-item medal-standing-bronze"><span class="medal-icon-symbol">🥉</span></span>`);
    }

    return `
        <div class="medal-division-cell">
            <div class="medal-icon-wrap">
                ${icons.join("")}
            </div>
        </div>
    `;
}

function renderMedalStandings(){
    const table = document.getElementById("medalStandingsTable");
    if(!table) return;

    const search = normalizeUpper(document.getElementById("medalStandingSearch")?.value || "");

    buildMedalStandingsRows();

    let rows = [...(MEDAL_STANDINGS_ROWS || [])];
    const divisions = prepareMedalStandingDivisions(MEDAL_STANDINGS_DIVISIONS || []);

    if(search){
        rows = rows.filter(r => {
            const divisionText = divisions
                .map(d => `${d.typeLabel} ${d.divisionLabel} ${d.genderAgeLabel}`)
                .join(" ");

            const text = [
                r.noc,
                divisionText,
                r.total,
                r.athletes,
                r.maleAthletes,
                r.femaleAthletes,
                r.coaches,
                r.otherAthletes,
                r.otherOfficials,
                r.totalGold,
                r.totalSilver,
                r.totalBronze,
                r.totalMedal,
                r.ranking
            ].join(" ");

            return normalizeUpper(text).includes(search);
        });
    }

    if(!rows.length){
        table.innerHTML = `<tr><td class="empty">Chưa có dữ liệu tổng sắp huy chương</td></tr>`;
        return;
    }

    table.innerHTML = `
        ${buildGroupedMedalStandingHeader(divisions)}

        <tbody>
            ${rows.map(r => `
                <tr>
                    <td class="medal-standing-unit-cell">
                        <span class="medal-unit-main">${esc(r.noc)}</span>

                        <span class="medal-unit-sub">
                            <span class="medal-unit-total">Total: ${r.total || 0}</span><br>
                            <span class="medal-unit-coach">Coach: ${r.coaches || 0}</span><br>
                            <span class="medal-unit-male">Male Ath: ${r.maleAthletes || 0}</span><br>
                            <span class="medal-unit-female">Female Ath: ${r.femaleAthletes || 0}</span><br>
                            <span class="medal-unit-other">Official: ${(r.otherAthletes || 0) + (r.otherOfficials || 0)}</span>
                        </span>
                    </td>

                    ${divisions.map(d => `
                        <td>${medalStandingDivisionCell(r, d.key)}</td>
                    `).join("")}

                    <td class="medal-standing-total medal-standing-gold">
                        ${r.totalGold}
                    </td>

                    <td class="medal-standing-total medal-standing-silver">
                        ${r.totalSilver}
                    </td>

                    <td class="medal-standing-total medal-standing-bronze">
                        ${r.totalBronze}
                    </td>

                    <td class="medal-standing-total">
                        ${r.totalMedal || 0}
                    </td>

                    <td class="medal-standing-rank">${r.ranking}</td>
                </tr>
            `).join("")}
        </tbody>
    `;

    setTimeout(setupDragScroll, 50);
}


function getCurrentMatchPrefix(){
    const meta = (FLAT || []).find(x => x.key === CURRENT_KEY);
    if(!meta) return "";

    const typeMap = {
        "Recognized":"R",
        "Freestyle":"F",
        "Demonstration":"D",
        "Mixer":"M"
    };

    const divMap = {
        "Individual":"I",
        "Pair":"P",
        "Team":"T"
    };

    const genderMap = {
        "Male":"M",
        "Female":"F"
    };

    const t = typeMap[meta.type] || "";
    const d = divMap[meta.division] || "";
    const g = genderMap[meta.gender] || "";

    let ageRaw = String(meta.age || "").trim().toUpperCase();

    const ageMap = {
        "CADET": "U14",
        "JUNIOR": "U17",
        "UNDER 14": "U14",
        "U 14": "U14",
        "U14": "U14",
        "UNDER 17": "U17",
        "U 17": "U17",
        "U17": "U17"
    };

    let age = ageMap[ageRaw] || ageRaw.replace(/\s+/g, "");

    return `${t}${d}${g}${age}`;
}

function esc(s){
  return String(s ?? "").replace(/[&<>'"]/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'
  }[c]));
}


async function loadMenu(){
  const data = await fetch("/api/menu").then(r => r.json());
  FLAT = data.flat || [];
  const menu = data.menu || {};
  const root = document.getElementById("menu");
  if(!root) return;
  root.innerHTML = "";

  function closeSiblingBodies(currentBody, currentButton, buttonClass){
      const parent = currentBody.parentElement;
      if(!parent) return;

      Array.from(parent.children).forEach(el => {
          if(el !== currentBody && el.classList && !el.classList.contains("hidden")){
              const prevBtn = el.previousElementSibling;

              if(
                  prevBtn &&
                  prevBtn.classList &&
                  prevBtn.classList.contains(buttonClass)
              ){
                  el.classList.add("hidden");

                  const cleanText = String(prevBtn.textContent || "")
                      .replace(/^▸\s*/, "")
                      .replace(/^▾\s*/, "");

                  prevBtn.textContent = `▸ ${cleanText}`;
              }
          }
      });
  }

  function toggleAccordion(button, body, buttonClass, label){
      const willOpen = body.classList.contains("hidden");

      closeSiblingBodies(body, button, buttonClass);

      if(willOpen){
          body.classList.remove("hidden");
          button.textContent = `▾ ${label}`;
      }else{
          body.classList.add("hidden");
          button.textContent = `▸ ${label}`;
      }
  }

  Object.keys(menu).forEach(type => {
    const group = document.createElement("div");
    group.className = "group";

    const head = document.createElement("button");
    head.className = "groupHead";
    head.textContent = `▸ ${type}`;

    const body = document.createElement("div");
    body.className = "hidden";

    head.onclick = () => toggleAccordion(head, body, "groupHead", type);

    group.appendChild(head);
    group.appendChild(body);

    Object.keys(menu[type]).forEach(division => {
      const sub = document.createElement("button");
      sub.className = "subHead";
      sub.textContent = `▸ ${division}`;

      const subBody = document.createElement("div");
      subBody.className = "hidden";

      sub.onclick = () => toggleAccordion(sub, subBody, "subHead", division);

      body.appendChild(sub);
      body.appendChild(subBody);

      Object.keys(menu[type][division]).forEach(gender => {
          const genderBtn = document.createElement("button");
          genderBtn.className = "genderHead";
          genderBtn.textContent = `▸ ${gender}`;

          const genderBody = document.createElement("div");
          genderBody.className = "hidden";

          genderBtn.onclick = () => toggleAccordion(genderBtn, genderBody, "genderHead", gender);

          subBody.appendChild(genderBtn);
          subBody.appendChild(genderBody);

          Object.keys(menu[type][division][gender]).forEach(age => {
              (menu[type][division][gender][age] || []).forEach(meta => {
                  const b = document.createElement("button");
                  b.className = "ageBtn";
                  b.textContent = `${age} (${meta.count})`;

                  b.onclick = () => {
                      selectDivision(meta.key, b);
                      closeSidebarOnMobile();
                  };

                  genderBody.appendChild(b);
              });
          });
      });
    });

    root.appendChild(group);
  });
}

async function selectDivision(key, btn){
  showMainDivisionViews();

  CURRENT_KEY = key;
  document.querySelectorAll(".ageBtn").forEach(x => x.classList.remove("active"));
  if(btn) btn.classList.add("active");

  const selectedTitle = document.getElementById("selectedTitle");
  if(selectedTitle) selectedTitle.textContent = key;

  await Promise.all([loadAthletes(key), loadResults(key)]);
}

async function reloadCurrent(){
  if(CURRENT_KEY) await selectDivision(CURRENT_KEY);
}

function renderTable(id, rows){
  const table = document.getElementById(id);
  if(!table) return;

  if(!rows || !rows.length){
    table.innerHTML = `<tr><td class="empty">Chưa có dữ liệu</td></tr>`;
    return;
  }

  let cols = [];

  if(id === "athleteTable"){
    cols = ["No.", "NOC", "Full name", "Gender"];
  }else{
    const preferred = [
      "Match","Court","Phase","Division","No.","NOC","Full name",
      "Athlete Blue","Athlete Red","Poomsae 1","Poomsae 2",
      "Total","Result","Action"
    ];

    cols = preferred.filter(c =>
      rows.some(r => r[c] !== undefined && r[c] !== null && r[c] !== "")
    );

    Object.keys(rows[0]).forEach(c => {
      if(!cols.includes(c) && !String(c).startsWith("_")) cols.push(c);
    });
  }

  table.innerHTML =
    `<thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map(r => `
      <tr>
        ${cols.map(c => `<td>${esc(r[c] ?? "")}</td>`).join("")}
      </tr>
    `).join("")}</tbody>`;
}

async function loadAthletes(key){
  const rows = await fetch("/api/athletes?key=" + encodeURIComponent(key)).then(r => r.json());
  window.currentAthletes = rows || [];

  const sigmaView = document.getElementById("sigmaView");
  const athleteCard = document.querySelector(".athlete-card");
  const layout = document.querySelector(".layout");
  const selectedBox = document.querySelector(".selectedBox");
  const sidebar = document.querySelector(".sidebar");

  if(layout) layout.classList.remove("result-mode");
  document.body.classList.remove("sigma-result-mode");
  document.body.classList.remove("sidebar-open");
  if(layout) layout.classList.remove("menu-open");
  if(sidebar) sidebar.classList.remove("hidden");
  if(selectedBox) selectedBox.classList.remove("hidden");
  if(athleteCard) athleteCard.classList.remove("hidden");
  if(sigmaView) sigmaView.classList.add("hidden");

  renderTable("athleteTable", rows);
}

async function loadResults(key){
  const rows = await fetch("/api/results?key=" + encodeURIComponent(key)).then(r => r.json());
  CURRENT_RESULTS = rows || [];

  const table = document.getElementById("resultTable");
  if(table) renderTable("resultTable", rows);

  const sigmaView = document.getElementById("sigmaView");
  if(sigmaView && !sigmaView.classList.contains("hidden")){
      if(isCutOffDivision()){
          buildCutoffResult(window.currentAthletes || []);
      }else{
          buildSigmaBracket(window.currentAthletes || []);
      }
  }
}

function buildSeedOrder(size){
  if(size === 4) return [1,4,2,3];
  if(size === 8) return [1,8,4,5,2,7,3,6];
  if(size === 16) return [1,16,8,9,4,13,5,12,2,15,7,10,3,14,6,11];
  if(size === 32){
    return [1,32,16,17,8,25,9,24,4,29,13,20,5,28,12,21,2,31,15,18,7,26,10,23,3,30,14,19,6,27,11,22];
  }
  if(size === 64){
    return [
      1,64,32,33,16,49,17,48,8,57,25,40,9,56,24,41,
      4,61,29,36,13,52,20,45,5,60,28,37,12,53,21,44,
      2,63,31,34,15,50,18,47,7,58,26,39,10,55,23,42,
      3,62,30,35,14,51,19,46,6,59,27,38,11,54,22,43
    ];
  }
  return Array.from({length:size}, (_, i) => i + 1);
}

function getBracketSize(n){
  if(n <= 4) return 4;
  if(n <= 8) return 8;
  if(n <= 16) return 16;
  if(n <= 32) return 32;
  return 64;
}

function shortenName(fullName){
  const text = String(fullName || "").trim().toUpperCase();
  if(!text) return "";

  const parts = text.split(/\s+/).filter(Boolean);
  if(parts.length <= 1) return text;

  const last = parts[parts.length - 1];
  const initials = parts.slice(0, -1).map(p => p[0]).join(".");
  return `${initials}.${last}`;
}


function getTeamFullNames(row){
  const names = [];

  Object.keys(row || {}).forEach(k => {
    const key = String(k || "").toLowerCase().trim();
    const value = String(row[k] || "").trim();

    if(!value) return;

    const isNameField =
      key === "full name" ||
      key.startsWith("full name") ||
      key === "fullname" ||
      key.startsWith("fullname") ||
      key === "athlete" ||
      key.startsWith("athlete") ||
      key.includes("full_name") ||
      key.includes("full name");

    if(isNameField && !names.includes(value)){
      names.push(value);
    }
  });

  if(!names.length && row["Full name"]){
    names.push(String(row["Full name"]).trim());
  }

  return names.join(" / ");
}

function getNameLines(fullName){
  const raw = String(fullName || "").trim();
  if(!raw) return [""];

  const names = raw
    .split(/\s*(?:\/|\\|\||;|\n|\r|,)+\s*/)
    .map(x => shortenName(x))
    .filter(Boolean);

  const lines = [];
  let current = "";

  names.forEach(name => {
    const next = current ? `${current} | ${name}` : name;

    if(next.length > 36){
      if(current) lines.push(current);
      current = name;
    }else{
      current = next;
    }
  });

  if(current) lines.push(current);

  return lines.length ? lines : [""];
}

function svgEl(tag, attrs = {}){
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

function drawText(svg, x, y, text, cls, anchor = "middle"){
  const t = svgEl("text", {
    x, y,
    class: cls,
    "text-anchor": anchor,
    "dominant-baseline": "middle"
  });
  t.textContent = text;
  svg.appendChild(t);
  return t;
}

function drawTextLines(svg, x, y, lines, cls, anchor = "start"){
  const lineH = 16;
  const totalH = (lines.length - 1) * lineH;
  lines.forEach((line, idx) => {
    drawText(svg, x, y - totalH / 2 + idx * lineH, line, cls, anchor);
  });
}

function drawLine(svg, x1, y1, x2, y2){
  svg.appendChild(svgEl("line", {x1, y1, x2, y2, class:"sigma-svg-line"}));
}

function isByePlayer(p){
  return String(p?.name || "").trim().toUpperCase() === "BYE";
}

function drawPlayer(svg, p, x, y, side, cfg){
  const isBye = isByePlayer(p);
  const { playerW, playerH, seedW, nocW } = cfg;
  const nameLines = getNameLines(p.name);
  const actualH = Math.max(playerH, 26 + nameLines.length * 16);

  if(isBye){
    return side === "left"
      ? { outX:x + playerW, y, player:p, hidden:true }
      : { outX:x, y, player:p, hidden:true };
  }

  const role = p.role || "blue";

  const boxClass =
      role === "red"
      ? "sigma-svg-box player-red"
      : "sigma-svg-box player-blue";

  const seedClass =
      role === "red"
      ? "sigma-svg-seed-red"
      : "sigma-svg-seed-blue";

  const nocClass =
      role === "red"
      ? "sigma-svg-noc-red"
      : "sigma-svg-noc-blue";

  const nameClass =
      role === "red"
      ? "sigma-svg-name-red"
      : "sigma-svg-name-blue";

  svg.appendChild(svgEl("rect", {
    x,
    y:y - actualH / 2,
    width:playerW,
    height:actualH,
    rx:8,
    class:boxClass
  }));

  if(side === "left"){
    drawLine(svg, x + seedW, y - actualH / 2, x + seedW, y + actualH / 2);
    drawLine(svg, x + seedW + nocW, y - actualH / 2, x + seedW + nocW, y + actualH / 2);
    drawText(svg, x + seedW / 2, y, p.no, seedClass);
    drawText(svg, x + seedW + nocW / 2, y, p.noc, nocClass);
    drawTextLines(svg, x + seedW + nocW + 10, y, nameLines, nameClass, "start");
    return { outX:x + playerW, y, player:p, hidden:false };
  }

  drawLine(svg, x + playerW - seedW, y - actualH / 2, x + playerW - seedW, y + actualH / 2);
  drawLine(svg, x + playerW - seedW - nocW, y - actualH / 2, x + playerW - seedW - nocW, y + actualH / 2);
  drawText(svg, x + playerW - seedW / 2, y, p.no, seedClass);
  drawText(svg, x + playerW - seedW - nocW / 2, y, p.noc, nocClass);
  drawTextLines(svg, x + playerW - seedW - nocW - 10, y, nameLines, nameClass, "end");
  return { outX:x, y, player:p, hidden:false };
}

function getWinnerInfoByMatchNo(matchNo){
    const prefix = getCurrentMatchPrefix();

    const fullMatch =
        prefix +
        String(matchNo || "").padStart(3, "0");

    const row = (CURRENT_RESULTS || []).find(r => {
        const rm = String(
            r["Match"] ||
            r["match"] ||
            ""
        ).trim().toUpperCase();

        return rm === fullMatch.toUpperCase();
    });

    if(!row){
        return {
            noc:"",
            side:""
        };
    }

    const result = String(
        row["Result"] ||
        row["result"] ||
        ""
    ).toUpperCase();

    const nocBlue = String(
        row["NOC Blue"] ||
        row["NOC_Blue"] ||
        ""
    ).trim();

    const nocRed = String(
        row["NOC Red"] ||
        row["NOC_Red"] ||
        ""
    ).trim();

    // CHEONG = BLUE / xanh
    if(result.includes("CHEONG") || result.includes("BLUE")){
        return {
            noc:nocBlue,
            side:"blue"
        };
    }

    // HONG = RED / đỏ
    if(result.includes("HONG") || result.includes("RED")){
        return {
            noc:nocRed,
            side:"red"
        };
    }

    if(nocBlue && result.includes(nocBlue.toUpperCase())){
        return {
            noc:nocBlue,
            side:"blue"
        };
    }

    if(nocRed && result.includes(nocRed.toUpperCase())){
        return {
            noc:nocRed,
            side:"red"
        };
    }

    return {
        noc:"",
        side:""
    };
}

function getWinnerNocByMatchNo(matchNo){
    return getWinnerInfoByMatchNo(matchNo).noc || "";
}

function getWinnerRole(winnerNoc, topPlayer, bottomPlayer, finalSide = ""){

    const win = String(winnerNoc || "").trim().toUpperCase();
    if(!win) return "";

    if(finalSide === "blue") return "blue";
    if(finalSide === "red") return "red";
    if(finalSide === "left") return "blue";
    if(finalSide === "right") return "red";

    const topNoc = String(topPlayer?.noc || "").trim().toUpperCase();
    const bottomNoc = String(bottomPlayer?.noc || "").trim().toUpperCase();

    if(topNoc && win === topNoc) return "blue";
    if(bottomNoc && win === bottomNoc) return "red";

    return "blue";
}

function drawMatchCode(
    svg,
    x,
    y,
    text,
    cfg,
    topPlayer = null,
    bottomPlayer = null,
    finalSide = "",
    isChampion = false
){
    const winnerInfo = getWinnerInfoByMatchNo(text);
    const winnerNoc = winnerInfo.noc || "";
    const hasWinner = !!winnerNoc;

    const showText = winnerNoc || text;

    let role = "";

    if(!isChampion){
        if(finalSide === "blue" || finalSide === "left"){
            role = "blue";
        }else if(finalSide === "red" || finalSide === "right"){
            role = "red";
        }else{
            role = getWinnerRole(winnerNoc, topPlayer, bottomPlayer);
        }
    }

    let boxClass = "sigma-svg-code-box";
    let textClass = "sigma-svg-code";

    if(hasWinner){
        if(isChampion){
            boxClass = "sigma-svg-code-box champion";
            textClass = "sigma-svg-winner-code-champion";
        }else if(role === "blue"){
            boxClass = "sigma-svg-code-box winner-blue";
            textClass = "sigma-svg-winner-code-blue";
        }else if(role === "red"){
            boxClass = "sigma-svg-code-box winner-red";
            textClass = "sigma-svg-winner-code-red";
        }else{
            boxClass = "sigma-svg-code-box winner";
            textClass = "sigma-svg-winner-code";
        }
    }

    const boxW = hasWinner
        ? Math.max(cfg.codeW, isChampion ? 92 : 58)
        : cfg.codeW;

    svg.appendChild(svgEl("rect", {
        x:x - boxW / 2,
        y:y - cfg.codeH / 2,
        width:boxW,
        height:cfg.codeH,
        rx:8,
        class:boxClass
    }));

    drawText(svg, x, y, showText, textClass);

    // Cup chỉ hiện khi đây là trận chung kết cuối và đã có người thắng
    if(isChampion && hasWinner){
        const cup = svgEl("text", {
            x:x,
            y:y - (cfg.codeH / 2) - 24,
            class:"sigma-svg-champion-cup",
            "text-anchor":"middle",
            "dominant-baseline":"middle",
            "font-size":"42",
            "font-weight":"900"
        });

        cup.textContent = "🏆";
        svg.appendChild(cup);
    }

    return winnerNoc || "";
}

function drawSvgSide(svg, slots, side, matchNoMap, cfg){
  const { svgW, finalX, finalPad, playerW, startY, rowGap, jointOffset, codeGap, playerGap } = cfg;

  const rounds = Math.log2(slots.length);
  const firstX = side === "left" ? 0 : svgW - playerW;
  const dir = side === "left" ? 1 : -1;
  const startOutX = side === "left" ? firstX + playerW : firstX;
  const targetX = side === "left" ? finalX - finalPad : finalX + finalPad;
  const roundGap = Math.max(70, Math.abs(targetX - startOutX) / Math.max(rounds, 1));

  let current = [];

  for(let i = 0; i < slots.length; i++){
      const y = startY + i * rowGap;
      current.push(drawPlayer(svg, slots[i], firstX, y, side, cfg));
  }

  let roundIndex = 0;

  while(current.length > 1){
    const next = [];

    for(let i = 0; i < current.length; i += 2){
      const a = current[i];
      const b = current[i + 1];

      const aBye = isByePlayer(a.player);
      const bBye = isByePlayer(b.player);
      // Cứ vào mỗi trận mới là ép lại màu theo vị trí thật của trận đó
      if(a.player && !aBye){
          a.player.role = "blue";
      }

      if(b.player && !bBye){
          b.player.role = "red";
      }

      // QUAN TRỌNG:
      // Mỗi trận mới phải xác nhận lại:
      // người / nhánh phía trên = xanh
      // người / nhánh phía dưới = đỏ
      if(a.player && !aBye){
          a.player.role = "blue";
      }

      if(b.player && !bBye){
          b.player.role = "red";
      }

      const midY = (a.y + b.y) / 2;
      const jointX = a.outX + dir * jointOffset;
      const outX = a.outX + dir * roundGap;

      if(aBye && bBye){
        next.push({
            outX,
            y:midY,
            player:{ name:"BYE" },
            hidden:true
        });
        continue;
      }

      if(aBye || bBye){
          const winner = aBye ? b : a;

          drawLine(svg, winner.outX, winner.y, jointX, winner.y);
          drawLine(svg, jointX, winner.y, jointX, midY);
          drawLine(svg, jointX, midY, outX, midY);

          // Qua BYE thì chưa quyết màu vòng sau.
          // Vòng sau sẽ xét lại theo vị trí trên/dưới.
          next.push({
              outX,
              y:midY,
              player:{
                  ...winner.player,
                  role:""
              },
              hidden:false
          });

          continue;
      }

      drawLine(svg, a.outX, a.y, jointX, a.y);
      drawLine(svg, b.outX, b.y, jointX, b.y);
      drawLine(svg, jointX, a.y, jointX, b.y);

      const codeX = jointX + dir * codeGap;
      const lineBreak = cfg.codeW / 2 + playerGap;

      if(side === "left"){
        drawLine(svg, jointX, midY, codeX - lineBreak, midY);
        drawLine(svg, codeX + lineBreak, midY, outX, midY);
      }else{
        drawLine(svg, jointX, midY, codeX + lineBreak, midY);
        drawLine(svg, codeX - lineBreak, midY, outX, midY);
      }

      const pairIndex = Math.floor(i / 2);
      const matchNo = matchNoMap[`${side}-${roundIndex}-${pairIndex}`] || "";
      const winnerNoc = matchNo ? getWinnerNocByMatchNo(matchNo) : "";

      const winnerRole = getWinnerRole(
          winnerNoc,
          a.player,
          b.player
      );

      let nextRole = "";

      const nextIndex = Math.floor(i / 2);

      if(current.length === 2){
          nextRole = side === "left" ? "blue" : "red";
      }else{
          nextRole = (nextIndex % 2 === 0) ? "blue" : "red";
      }

      drawMatchCode(
          svg,
          codeX,
          midY,
          matchNo,
          cfg,
          a.player,
          b.player,
          nextRole
      );

      next.push({
          outX,
          y:midY,
          player:{
              no:"",
              noc:winnerNoc || "",
              name:winnerNoc ? winnerNoc : "WINNER",
              role:""
          },
          hidden:false
      });
    }

    current = next;
    roundIndex++;
  }

  return current[0] || null;
}

function getPseudoWinnerForNumbering(a, b){
    const aBye = isByePlayer(a);
    const bBye = isByePlayer(b);

    if(aBye && bBye){
        return { name:"BYE" };
    }

    if(aBye) return b;
    if(bBye) return a;

    return { name:"WINNER" };
}

function buildRoundMatchNumberMap(leftSlots, rightSlots){
    const map = {};
    let counter = 1;

    let leftCurrent = leftSlots.map(p => ({...p}));
    let rightCurrent = rightSlots.map(p => ({...p}));

    let roundIndex = 0;

    while(leftCurrent.length > 1 || rightCurrent.length > 1){

        const processSide = (sideName, current) => {
            const next = [];

            for(let i = 0; i < current.length; i += 2){
                const a = current[i];
                const b = current[i + 1];

                const pairIndex = Math.floor(i / 2);

                const aBye = isByePlayer(a);
                const bBye = isByePlayer(b);

                if(!aBye && !bBye){
                    map[`${sideName}-${roundIndex}-${pairIndex}`] =
                        String(counter).padStart(3, "0");

                    counter++;
                }

                next.push(getPseudoWinnerForNumbering(a, b));
            }

            return next;
        };

        if(leftCurrent.length > 1){
            leftCurrent = processSide("left", leftCurrent);
        }

        if(rightCurrent.length > 1){
            rightCurrent = processSide("right", rightCurrent);
        }

        roundIndex++;
    }

    const leftFinalBye = isByePlayer(leftCurrent[0]);
    const rightFinalBye = isByePlayer(rightCurrent[0]);

    if(!leftFinalBye && !rightFinalBye){
        map["final"] = String(counter).padStart(3, "0");
    }

    return map;
}

function drawSvgFinal(svg, leftEnd, rightEnd, matchNoMap, cfg){
  const { finalX, finalPad, codeW, playerGap } = cfg;
  let finalY = 270;
  if(leftEnd && rightEnd) finalY = (leftEnd.y + rightEnd.y) / 2;

  const lineBreak = codeW / 2 + playerGap;

  if(leftEnd){
    drawLine(svg, leftEnd.outX, leftEnd.y, finalX - finalPad, finalY);
    drawLine(svg, finalX - finalPad, finalY, finalX - lineBreak, finalY);
  }

  if(rightEnd){
    drawLine(svg, rightEnd.outX, rightEnd.y, finalX + finalPad, finalY);
    drawLine(svg, finalX + finalPad, finalY, finalX + lineBreak, finalY);
  }

  const matchNo = matchNoMap["final"] || "";

  drawMatchCode(
      svg,
      finalX,
      finalY,
      matchNo,
      cfg,
      leftEnd ? leftEnd.player : null,
      rightEnd ? rightEnd.player : null,
      "",
      true
  );
}

function getDisplayNames(row){
  const names = [];

  const ignoreKeys = [
    "idx","id","no.","no","noc","country","gender","position",
    "event_1","event_2","event_3","event_4","event_5","event_6","event_7","event_8","event_9","event_10"
  ];

  Object.keys(row || {}).forEach(k => {
    const key = String(k || "").toLowerCase().trim();
    const value = String(row[k] || "").trim();

    if(!value) return;
    if(ignoreKeys.includes(key)) return;
    if(key.startsWith("event")) return;

    const isNameField =
      key.includes("name") ||
      key.includes("athlete") ||
      key.includes("member") ||
      key.includes("team") ||
      key.includes("pair") ||
      key.includes("player");

    const looksLikePersonName =
      value.split(/\s+/).length >= 2 &&
      !/^(MALE|FEMALE|VIE|THA|PHI|INA|SIN|KOR|IND|ITA|MAS|LAO|CAM|TPE)$/i.test(value);

    if((isNameField || looksLikePersonName) && !names.includes(value)){
      names.push(value);
    }
  });

  return names.join(" | ");
}

function updateSigmaDivisionTitle(){

    const titleEl = document.getElementById("sigmaDivisionTitle");
    if(!titleEl) return;

    titleEl.textContent =
        String(CURRENT_KEY || "")
            .replace(/\s*-\s*/g, " ");
}

function isCutOffDivision(){
  const key = String(CURRENT_KEY || "").toLowerCase();

  if(key.includes("freestyle")) return true;
  if(key.includes("demonstration")) return true;
  if(key.includes("demon")) return true;

  const results = CURRENT_RESULTS || [];
  return results.some(r => {
    const match = String(r["Match"] || r["match"] || "").trim().toUpperCase();
    const prefix = getCurrentMatchPrefix().toUpperCase();
    const method = String(r["Method"] || r["method"] || "").toLowerCase();

    return (!prefix || match.startsWith(prefix)) && method.includes("cut");
  });
}

function getResultScore(row){
  const fields = [
    "Total Point Blue",
    "Blue Point 1",
    "Total",
    "Score",
    "score",
    "_score"
  ];

  for(const f of fields){
    const v = row[f];
    if(v !== undefined && v !== null && v !== ""){
      const n = Number(v);
      if(!Number.isNaN(n)) return n;
    }
  }

  return 0;
}
function getResultPhase(row){
  return String(
    row["Phase"] ||
    row["phase"] ||
    row["Round"] ||
    row["round"] ||
    ""
  ).trim();
}

function getCutoffCompetitorCount(athletes){
  const nos = new Set();

  (athletes || []).forEach(a => {
    const no = String(a["No."] || "").trim();
    if(no) nos.add(no);
  });

  return nos.size;
}

function buildCutoffResult(athletes){
  const box = document.getElementById("sigmaBracket");
  if(!box) return;

  const totalAthletes = getCutoffCompetitorCount(athletes);

  const phases = [];

  if(totalAthletes > 32){
    phases.push({name:"Round of 64", size:totalAthletes});
    phases.push({name:"Round of 32", size:32});
    phases.push({name:"Round of 16", size:16});
  }else if(totalAthletes > 16){
    phases.push({name:"Round of 32", size:totalAthletes});
    phases.push({name:"Round of 16", size:16});
  }else if(totalAthletes > 8){
    phases.push({name:"Round of 16", size:totalAthletes});
  }

  phases.push({name:"Final", size:Math.min(8, totalAthletes)});

  const phaseRows = {};
  phases.forEach(p => phaseRows[p.name] = []);

  (CURRENT_RESULTS || []).forEach(r => {
    const match = String(r["Match"] || r["match"] || "").trim().toUpperCase();
    const prefix = getCurrentMatchPrefix().toUpperCase();

    if(prefix && !match.startsWith(prefix)) return;

    const phase = getResultPhase(r) || phases[0].name;
    if(!phaseRows[phase]) return;

    phaseRows[phase].push({
      noc:String(r["NOC Blue"] || r["NOC_Blue"] || "").trim(),
      name:String(r["Athlete Blue"] || r["Athlete_Blue"] || "").trim(),
      score:getResultScore(r)
    });
  });

  let html = "";

  phases.forEach(phase => {
    const rows = phaseRows[phase.name] || [];
    rows.sort((a,b) => b.score - a.score);

    const tableRows = [];

    for(let i = 1; i <= phase.size; i++){
      const r = rows[i - 1];

      tableRows.push(`
        <tr>
          <td>${i}</td>
          <td>${r ? esc(r.noc) : ""}</td>
          <td>${r ? esc(shortenName(r.name)) : ""}</td>
          <td>${r ? r.score.toFixed(3) : ""}</td>
        </tr>
      `);
    }

    html += `
      <div class="cutoff-phase-box" id="cutoffPhaseBox_${phases.indexOf(phase)}" data-phase-title="${esc(phase.name)}">
        <div class="cutoff-phase-title-row">
            <div class="cutoff-phase-title">${esc(phase.name)}</div>

            <div class="cutoff-phase-actions">
                <button class="cutoff-print-btn" type="button" onclick="printCutoffPhase(${phases.indexOf(phase)}, 'print')">
                    🖨
                </button>

                <button class="cutoff-print-btn" type="button" onclick="printCutoffPhase(${phases.indexOf(phase)}, 'pdf')">
                    📄
                </button>
            </div>
        </div>

        <table class="cutoff-table">
          <thead>
            <tr>
              <th style="width:70px">Rank</th>
              <th style="width:120px">NOC</th>
              <th>Full name</th>
              <th style="width:120px">Score</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows.join("")}
          </tbody>
        </table>
      </div>
    `;
  });

  box.innerHTML = `<div class="cutoff-result-wrap">${html}</div>`;
}

function computeVisibleRoles(slots){
    const roles = new Array(slots.length).fill("");

    function isByeSlot(p){
        return String(p?.name || "").trim().toUpperCase() === "BYE";
    }

    function walk(start, end){
        if(end - start === 1){
            if(isByeSlot(slots[start])) return null;
            return {
                unresolved:[start]
            };
        }

        const mid = Math.floor((start + end) / 2);
        const left = walk(start, mid);
        const right = walk(mid, end);

        if(!left && !right) return null;
        if(left && !right) return left;
        if(!left && right) return right;

        // Khi 2 nhánh gặp nhau thành trận thật:
        // nhánh trên/trái = xanh, nhánh dưới/phải = đỏ
        (left.unresolved || []).forEach(idx => {
            if(!roles[idx]) roles[idx] = "blue";
        });

        (right.unresolved || []).forEach(idx => {
            if(!roles[idx]) roles[idx] = "red";
        });

        // Sau khi đã thành trận thật thì không kéo màu lên vòng sau nữa
        return {
            unresolved:[]
        };
    }

    walk(0, slots.length);

    return roles;
}

function buildSigmaBracket(athletes){
  const box = document.getElementById("sigmaBracket");
  if(!box) return;

  const grouped = {};

  [...athletes].forEach(a => {
    const no = Number(a["No."] || 0);
    if(!no) return;

    const key = String(no);
    const name = getDisplayNames(a);

    if(!grouped[key]){
      grouped[key] = {
        no:no,
        noc:a["NOC"] || "",
        names:[],
        gender:a["Gender"] || ""
      };
    }

    if(name && !grouped[key].names.includes(name)){
      grouped[key].names.push(name);
    }
  });

  const players = Object.values(grouped).map(p => ({
    no:p.no,
    noc:p.noc,
    name:p.names.join(" | "),
    gender:p.gender
  }));

  const bracketSize = getBracketSize(players.length);
  const seedMap = {};
  players.forEach(p => { if(p.no) seedMap[p.no] = p; });

  const slots = buildSeedOrder(bracketSize).map(seed => {
      return seedMap[seed] || { no:"", noc:"", name:"BYE", gender:"" };
  });

  const visibleRoles = computeVisibleRoles(slots);

  slots.forEach((p, index) => {
      p.role = visibleRoles[index] || "";
  });

  const maxNameLines = Math.max(1, ...slots.map(p => isByePlayer(p) ? 1 : getNameLines(p.name).length));
  const dynamicPlayerH = Math.max(bracketSize <= 8 ? 50 : 38, 28 + maxNameLines * 16);
  const dynamicRowGap = bracketSize <= 8
    ? Math.max(112, dynamicPlayerH + 68)
    : bracketSize <= 16
      ? Math.max(78, dynamicPlayerH + 42)
      : Math.max(60, dynamicPlayerH + 26);

  const svgW = 1600;
  const svgH = Math.max(
    bracketSize <= 16 ? 720 : bracketSize <= 32 ? 1000 : 1500,
    120 + dynamicRowGap * (bracketSize / 2)
  );

  const cfg = {
    svgW,
    svgH,
    finalX:svgW / 2,
    finalPad:72,
    playerW:bracketSize <= 8 ? 500 : 430,
    playerH:dynamicPlayerH,
    seedW:48,
    nocW:66,
    codeW:48,
    codeH:30,
    startY:bracketSize <= 16 ? 86 : 70,
    rowGap:dynamicRowGap,
    jointOffset:36,
    codeGap:38,
    playerGap:4
  };

  box.innerHTML = `<svg id="sigmaSvg" viewBox="0 0 ${svgW} ${svgH}" class="sigma-svg"></svg>`;

  const svg = document.getElementById("sigmaSvg");
  const leftSlots = slots.slice(0, bracketSize / 2);
  const rightSlots = slots.slice(bracketSize / 2);

  const matchNoMap = buildRoundMatchNumberMap(leftSlots, rightSlots);

  const leftEnd = drawSvgSide(svg, leftSlots, "left", matchNoMap, cfg);
  const rightEnd = drawSvgSide(svg, rightSlots, "right", matchNoMap, cfg);
  drawSvgFinal(svg, leftEnd, rightEnd, matchNoMap, cfg);
}

function getSigmaPrintEventTitle(){
    const title = document.querySelector(".header-title")?.textContent || "";
    const date = document.querySelector(".header-date")?.textContent || "";
    const location = document.querySelector(".header-location")?.textContent || "";

    const logoImg = document.querySelector(".logoBox img");
    let logo = "";

    if(logoImg){
        logo = logoImg.getAttribute("src") || "";
        if(logo && !logo.startsWith("http") && !logo.startsWith("data:")){
            logo = window.location.origin + logo;
        }
    }

    return {
        title:String(title || "").trim(),
        date:String(date || "").trim(),
        location:String(location || "").trim(),
        logo:String(logo || "").trim()
    };
}

function getSigmaCurrentDivisionTitle(){
    const title = document.getElementById("sigmaDivisionTitle")?.textContent || CURRENT_KEY || "";
    return String(title || "").trim();
}

function makePrintDocumentHtml(printTitle, contentHtml, printMode){
    const event = getSigmaPrintEventTitle();
    const modeText = printMode === "pdf"
        ? "PDF / Tài liệu"
        : "Bản in";

    return `
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>${esc(printTitle)}</title>

<style>
    *{
        box-sizing:border-box;
    }

    @page{
        size:A4 landscape;
        margin:10mm;
    }

    body{
        margin:0;
        background:white;
        color:#001b33;
        font-family:Arial, Helvetica, sans-serif;
        -webkit-print-color-adjust:exact!important;
        print-color-adjust:exact!important;
    }

    .print-page{
        width:100%;
        padding:0;
        background:white;
    }

    .print-header{
        display:grid;
        grid-template-columns:110px minmax(0,1fr) 110px;
        align-items:center;
        gap:12px;
        border-bottom:4px solid #ffd34d;
        padding:8px 0 10px;
        margin-bottom:12px;
    }

    .print-logo-box{
        display:flex;
        align-items:center;
        justify-content:center;
    }

    .print-logo-box img{
        max-width:120px;
        max-height:82px;
        object-fit:contain;
        background:white;
    }

    .print-title-box{
        text-align:center;
        min-width:0;
    }

    .print-event-title{
        color:#ff8f0f;
        font-size:26px;
        font-weight:900;
        text-transform:uppercase;
        letter-spacing:.8px;
        line-height:1.12;
    }

    .print-event-date{
        color:#003b8e;
        font-size:14px;
        font-weight:900;
        margin-top:4px;
    }

    .print-event-location{
        color:#005f8f;
        font-size:14px;
        font-weight:900;
        margin-top:3px;
    }

    .print-main-title{
        text-align:center;
        color:#003b8e;
        font-size:24px;
        font-weight:900;
        letter-spacing:3px;
        margin:10px 0 4px;
    }

    .print-division-title{
        text-align:center;
        color:#001b33;
        font-size:17px;
        font-weight:900;
        margin-bottom:12px;
    }

    .print-mode{
        text-align:right;
        color:#666;
        font-size:11px;
        font-weight:700;
        margin-bottom:5px;
    }

    .print-content{
        width:100%;
        overflow:visible;
    }

    svg{
        width:100%!important;
        height:auto!important;
        max-height:165mm;
        display:block;
        background:white!important;
        border:2px solid #2f6fa3!important;
        border-radius:8px;
    }

    .sigma-svg{
        background:white!important;
    }

    .sigma-svg-line{
        stroke:#1b5e8f!important;
        stroke-width:1.8!important;
    }

    .sigma-svg-box{
        fill:white!important;
        stroke:#2f6fa3!important;
        stroke-width:2!important;
    }

    .sigma-svg-box.player-blue{
        fill:#0B63CE!important;
        stroke:#003B8E!important;
    }

    .sigma-svg-box.player-red{
        fill:#C93C4A!important;
        stroke:#7A1F2B!important;
    }

    .sigma-svg-name-blue,
    .sigma-svg-noc-blue,
    .sigma-svg-seed-blue,
    .sigma-svg-name-red,
    .sigma-svg-noc-red,
    .sigma-svg-seed-red{
        fill:white!important;
        font-weight:900!important;
    }

    .sigma-svg-code-box{
        fill:white!important;
        stroke:#003B8E!important;
        stroke-width:2!important;
    }

    .sigma-svg-code{
        fill:#003B8E!important;
        font-weight:900!important;
    }

    .sigma-svg-code-box.winner-blue{
        fill:#0B63CE!important;
        stroke:#003B8E!important;
    }

    .sigma-svg-code-box.winner-red{
        fill:#C93C4A!important;
        stroke:#7A1F2B!important;
    }

    /* ===== Champion Final Box - Print/PDF ===== */
    .sigma-svg-code-box.champion{
        fill:#f6d56b!important;
        stroke:#ffbf00!important;
        stroke-width:3.5!important;
    }

    .sigma-svg-winner-code-champion{
        fill:#ffffff!important;
        font-size:15px!important;
        font-weight:900!important;
        paint-order:stroke!important;
        stroke:#5b4100!important;
        stroke-width:2px!important;
        stroke-linejoin:round!important;
    }

    .sigma-svg-champion-cup{
        font-size:42px!important;
        font-weight:900!important;
    }

    .sigma-svg-winner-code-blue,
    .sigma-svg-winner-code-red{
        fill:white!important;
        font-weight:900!important;
    }

    .cutoff-phase-box{
        border:2px solid #2f6fa3;
        border-radius:12px;
        overflow:hidden;
        background:white;
        page-break-inside:avoid;
    }

    .cutoff-phase-title-row,
    .cutoff-phase-title{
        background:#123c67!important;
        color:#ffd34d!important;
        text-align:center!important;
        font-size:22px!important;
        font-weight:900!important;
        padding:12px!important;
    }

    .cutoff-phase-actions{
        display:none!important;
    }

    .cutoff-table{
        width:100%;
        border-collapse:collapse;
        background:white;
    }

    .cutoff-table th{
        background:#0f2e4e!important;
        color:white!important;
        font-size:13px;
        padding:9px;
        border:1px solid #2f6fa3;
        text-align:center;
    }

    .cutoff-table td{
        color:#001b33!important;
        font-size:13px;
        font-weight:800;
        padding:9px;
        border:1px solid #aac5df;
        text-align:center;
    }

    .cutoff-table td:first-child{
        color:#003B8E!important;
        font-weight:900;
    }

    table{
        width:100%;
        border-collapse:collapse;
    }

    @media print{
        .no-print{
            display:none!important;
        }

        body{
            background:white!important;
        }
    }

/* Khóa lỗi sidebar rớt xuống dưới header khi đóng menu trong Sigma */
.layout.result-mode:not(.menu-open) .sidebar{
    display:none!important;
}

.layout.result-mode.menu-open .sidebar{
    display:block!important;
}

</style>
</head>

<body>
    <div class="print-page">
        <div class="print-header">
            <div class="print-logo-box">
                ${event.logo ? `<img src="${esc(event.logo)}">` : ""}
            </div>

            <div class="print-title-box">
                <div class="print-event-title">${esc(event.title)}</div>
                <div class="print-event-date">${esc(event.date)}</div>
                <div class="print-event-location">${esc(event.location)}</div>
            </div>

            <div></div>
        </div>

        <div class="print-mode">${esc(modeText)}</div>
        <div class="print-main-title">SIGMA RESULT</div>
        <div class="print-division-title">${esc(printTitle)}</div>

        <div class="print-content">
            ${contentHtml}
        </div>
    </div>
</body>
</html>
    `;
}

function openSigmaPrintWindow(printTitle, contentHtml, mode){
    const win = window.open("", "_blank", "width=1200,height=800");

    if(!win){
        alert("Trình duyệt đang chặn popup. Ken cho phép popup để in/xuất PDF nhé.");
        return;
    }

    win.document.open();
    win.document.write(makePrintDocumentHtml(printTitle, contentHtml, mode));
    win.document.close();

    win.onload = () => {
        setTimeout(() => {
            win.focus();
            win.print();
        }, 350);
    };
}

function printSigmaCurrent(mode){
    const divisionTitle = getSigmaCurrentDivisionTitle();

    if(isCutOffDivision()){
        const box = document.getElementById("sigmaBracket");
        if(!box){
            alert("Chưa có nội dung Sigma để in.");
            return;
        }

        openSigmaPrintWindow(
            divisionTitle,
            box.innerHTML,
            mode
        );

        return;
    }

    const svg = document.getElementById("sigmaSvg");

    if(!svg){
        alert("Chưa có sơ đồ Sigma để in.");
        return;
    }

    const svgHtml = svg.outerHTML;

    openSigmaPrintWindow(
        divisionTitle,
        svgHtml,
        mode
    );
}

function printCutoffPhase(index, mode){
    const phaseBox = document.getElementById(`cutoffPhaseBox_${index}`);

    if(!phaseBox){
        alert("Không tìm thấy khung round để in.");
        return;
    }

    const clone = phaseBox.cloneNode(true);

    clone.querySelectorAll(".cutoff-phase-actions").forEach(el => el.remove());

    const phaseTitle = phaseBox.getAttribute("data-phase-title") || "Cutoff Round";
    const divisionTitle = getSigmaCurrentDivisionTitle();

    openSigmaPrintWindow(
        `${divisionTitle} - ${phaseTitle}`,
        clone.outerHTML,
        mode
    );
}

document.getElementById("btnResult")?.addEventListener("click", () => {
  const sigmaView = document.getElementById("sigmaView");
  const athleteCard = document.querySelector(".athlete-card");
  const sidebar = document.querySelector(".sidebar");
  const layout = document.querySelector(".layout");
  const selectedBox = document.querySelector(".selectedBox");

  if(!window.currentAthletes || !window.currentAthletes.length){
    alert("Chưa có danh sách VĐV để vẽ Sigma");
    return;
  }

  if(layout) layout.classList.add("result-mode");
  document.body.classList.add("sigma-result-mode");
  if(sidebar) sidebar.classList.add("hidden");
  if(athleteCard) athleteCard.classList.add("hidden");
  if(selectedBox) selectedBox.classList.add("hidden");
  if(sigmaView) sigmaView.classList.remove("hidden");

  updateSigmaDivisionTitle();
  if(isCutOffDivision()){
      buildCutoffResult(window.currentAthletes);
  }else{
      buildSigmaBracket(window.currentAthletes);
  }
});

document.getElementById("btnReturn")?.addEventListener("click", () => {
  const sigmaView = document.getElementById("sigmaView");
  const athleteCard = document.querySelector(".athlete-card");
  const sidebar = document.querySelector(".sidebar");
  const layout = document.querySelector(".layout");
  const selectedBox = document.querySelector(".selectedBox");

  if(layout){
      layout.classList.remove("result-mode");
      layout.classList.remove("menu-open");
  }

  document.body.classList.remove("sigma-result-mode");
  document.body.classList.remove("sidebar-open");

  if(sidebar) sidebar.classList.remove("hidden");
  if(athleteCard) athleteCard.classList.remove("hidden");
  if(selectedBox) selectedBox.classList.remove("hidden");
  if(sigmaView) sigmaView.classList.add("hidden");
});

function isMobileView(){
    return window.matchMedia("(max-width:900px)").matches;
}

function closeSidebarOnMobile(){
    const layout = document.querySelector(".layout");
    const body = document.body;
    const sidebar = document.querySelector(".sidebar");

    if(!layout) return;

    // Trong Sigma Result, chọn division xong thì đóng panel menu lại
    if(layout.classList.contains("result-mode")){
        layout.classList.remove("menu-open");
        body.classList.remove("sidebar-open");

        if(sidebar){
            sidebar.classList.add("hidden");
        }

        return;
    }

    if(!isMobileView()) return;

    layout.classList.remove("menu-open");
    body.classList.remove("sidebar-open");
}

function toggleSidebar(){
    const layout = document.querySelector(".layout");
    const body = document.body;
    const sidebar = document.querySelector(".sidebar");

    if(!layout) return;

    // Khi đang ở Sigma Result:
    // bấm ☰ mở menu thì bỏ hidden
    // bấm ☰ lần nữa đóng menu thì add hidden lại
    if(layout.classList.contains("result-mode")){
        const willOpen = !layout.classList.contains("menu-open");

        if(willOpen){
            if(sidebar){
                sidebar.classList.remove("hidden");
            }

            layout.classList.add("menu-open");
            body.classList.add("sidebar-open");
        }else{
            layout.classList.remove("menu-open");
            body.classList.remove("sidebar-open");

            if(sidebar){
                sidebar.classList.add("hidden");
            }
        }

        return;
    }

    if(isMobileView()){
        layout.classList.toggle("menu-open");
        body.classList.toggle("sidebar-open", layout.classList.contains("menu-open"));
        return;
    }

    const collapsed = layout.classList.toggle("sidebar-collapsed");
    body.classList.toggle("sidebar-collapsed-desktop", collapsed);

    setTimeout(setupDragScroll, 80);
}

function setupSidebarToggle(){
    const btn = document.getElementById("btnToggleSidebar");
    const backdrop = document.getElementById("sidebarBackdrop");

    if(btn){
        btn.addEventListener("click", toggleSidebar);
    }

    if(backdrop){
        backdrop.addEventListener("click", closeSidebarOnMobile);
    }

    window.addEventListener("resize", () => {
        const layout = document.querySelector(".layout");

        if(!layout) return;

        if(!isMobileView()){
            layout.classList.remove("menu-open");
            document.body.classList.remove("sidebar-open");
        }else{
            layout.classList.remove("sidebar-collapsed");
            document.body.classList.remove("sidebar-collapsed-desktop");
        }
    });
}

function setupDragScroll(){
    document.querySelectorAll(".table-scroll").forEach(scroller => {
        if(scroller.dataset.dragReady === "1") return;
        scroller.dataset.dragReady = "1";

        let isDown = false;
        let startX = 0;
        let startY = 0;
        let scrollLeft = 0;
        let scrollTop = 0;

        scroller.addEventListener("mousedown", e => {
            isDown = true;
            scroller.classList.add("dragging");
            startX = e.pageX - scroller.offsetLeft;
            startY = e.pageY - scroller.offsetTop;
            scrollLeft = scroller.scrollLeft;
            scrollTop = scroller.scrollTop;
        });

        scroller.addEventListener("mouseleave", () => {
            isDown = false;
            scroller.classList.remove("dragging");
        });

        scroller.addEventListener("mouseup", () => {
            isDown = false;
            scroller.classList.remove("dragging");
        });

        scroller.addEventListener("mousemove", e => {
            if(!isDown) return;

            e.preventDefault();

            const x = e.pageX - scroller.offsetLeft;
            const y = e.pageY - scroller.offsetTop;

            const walkX = x - startX;
            const walkY = y - startY;

            scroller.scrollLeft = scrollLeft - walkX;
            scroller.scrollTop = scrollTop - walkY;
        });

        // Laptop: giữ Shift + lăn chuột để chạy ngang
        scroller.addEventListener("wheel", e => {
            if(e.shiftKey){
                e.preventDefault();
                scroller.scrollLeft += e.deltaY;
            }
        }, {passive:false});
    });
}

document.getElementById("btnSigmaPrint")?.addEventListener("click", () => {
    printSigmaCurrent("print");
});

document.getElementById("btnSigmaPdf")?.addEventListener("click", () => {
    printSigmaCurrent("pdf");
});

document.getElementById("btnOpenInfoList")?.addEventListener("click", () => {
    showInfoListView();
    closeSidebarOnMobile();
});

document.getElementById("btnOpenRanking")?.addEventListener("click", () => {
    showRankingView();
    closeSidebarOnMobile();
});

document.getElementById("btnOpenMedalStandings")?.addEventListener("click", () => {
    showMedalStandingsView();
    closeSidebarOnMobile();
    setTimeout(setupDragScroll, 80);
});

setupSidebarToggle();

loadMenu().then(() => {
    setupDragScroll();
});

setInterval(() => {
    if(CURRENT_KEY) loadResults(CURRENT_KEY);
}, 5000);

</script>
</body>
</html>
"""

@app.route("/")
def index():
    event_name, menu, flat = build_menu()

    setup = load_setup()

    event_name = setup.get("event", event_name)

    date_from = setup.get("date_from", "")
    date_to = setup.get("date_to", "")

    event_date = (
        f"{date_from} - {date_to}"
        if date_from and date_to
        else date_from
    )

    return render_template_string(
        INDEX_HTML,
        event_name=event_name,
        event_date=event_date,
        event_location=setup.get("location", ""),
        logo_file=LOGO_FILE,
    )

def convert_dict(d):
    if isinstance(d, defaultdict):
        d = dict(d)

    if isinstance(d, dict):
        return {k: convert_dict(v) for k, v in d.items()}

    return d


@app.route("/api/menu")
def api_menu():
    event_name, menu, flat = build_menu()
    return jsonify({
        "event_name": event_name,
        "menu": menu,
        "flat": flat
    })

@app.route("/api/athletes")
def api_athletes():
    key = request.args.get("key", "").strip()
    data = load_event_json()
    return jsonify(data.get("divisions", {}).get(key, []))

@app.route("/api/results")
def api_results():
    key = request.args.get("key", "").strip()
    rows = get_results_for_division(key)
    return jsonify(rows)

@app.route("/api/information-list")
def api_information_list():
    rows = get_information_list_rows()
    return jsonify(rows)


@app.route("/api/all-results")
def api_all_results():
    try:
        res = supabase.table(RESULT_TABLE).select("*").execute()
        rows = res.data or []

        for r in rows:
            r["_score"] = safe_float(
                r.get("Total")
                or r.get("total")
                or r.get("Score")
                or r.get("score")
                or r.get("Total Point Blue")
                or r.get("Blue Point 1")
            )

        return jsonify(rows)

    except Exception as e:
        print("All results load error:", e)
        return jsonify([])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)

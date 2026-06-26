# app_web.py
# Web version for Ken's Poomsae Judge Control Panel
# Run: pip install flask supabase && python app_web.py
# Open: http://127.0.0.1:5000

import os
from typing import Any, Dict, Optional, Tuple
from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for, send_from_directory
from supabase import create_client

# =========================
# SUPABASE CONFIG
# =========================
# Khuyến nghị khi deploy web: set biến môi trường SUPABASE_URL và SUPABASE_KEY.
# Nếu chạy local thì file vẫn dùng sẵn cấu hình cũ giống bản Kivy Ken gửi.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zrtcilmboikavgesdwuh.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpydGNpbG1ib2lrYXZnZXNkd3VoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg3NjM2NDEsImV4cCI6MjA5NDMzOTY0MX0.HyyVu8ygZgCaupx0GGnQHuc9VuT72KjP_IMF5vrRDQk",
)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ken-poomsae-scoring-web-secret")

# =========================
# LOGIC GIỐNG FILE KIVY
# =========================
def shorten_full_name(full_name: str) -> str:
    full_name = str(full_name or "").strip()
    if not full_name:
        return ""
    names = full_name.split()
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0][0]}. {names[1]}"
    family = names[0]
    given = names[-1]
    middle_initials = ".".join([m[0] for m in names[1:-1]])
    return f"{family[0]}.{middle_initials}. {given}"


def get_active_match(schedule_table: str, judge_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table(schedule_table).select("*").execute()
    for row in res.data or []:
        judge_status = str(row.get(judge_id) or "").strip().lower()
        action = str(row.get("Action") or "").strip().lower()
        if action not in ["start", "ready"]:
            continue
        if judge_status == "finish":
            continue
        valid_status = ["start", "ready", "finish 1", "blue 1 done", "blue 2 done"]
        if judge_status in valid_status:
            return row
    return None


def get_match_time(schedule_table: str, match_no: str) -> Tuple[int, int, str]:
    res = supabase.table(schedule_table).select("*").eq("Match", match_no).limit(1).execute()
    if not res.data:
        return 0, 0, ""
    row = res.data[0]
    return int(row.get("Time Minutes") or 0), int(row.get("Time Seconds") or 0), str(row.get("Control time") or "").strip().lower()


def send_judge_score(data: Dict[str, Any]):
    return supabase.table("Judge Score").insert(data).execute()


def mark_judge_finish(schedule_table: str, match_no: str, judge_id: str, status: str):
    return supabase.table(schedule_table).update({judge_id: status}).eq("Match", match_no).execute()


def clear_control_time(schedule_table: str, match_no: str):
    return supabase.table(schedule_table).update({"Control time": None}).eq("Match", match_no).execute()


def resolve_ready(row: Dict[str, Any], judge_status: str) -> Dict[str, str]:
    p1_action = str(row.get("Poomsae 1 action") or "").strip().lower()
    p2_action = str(row.get("Poomsae 2 action") or "").strip().lower()
    judge_status = str(judge_status or "").strip().lower()

    # Đã chấm xong bài 1, nhưng bài 2 chưa ready
    # => không hiện lại màn hình ready bài 1
    if judge_status == "finish 1" and p2_action != "ready":
        return {
            "slot": "",
            "poomsae": "Waiting Poomsae 2 Ready..."
        }

    # Bài 2 ready thì mới cho vào luồng bài 2
    if p2_action == "ready":
        return {
            "slot": "2",
            "poomsae": str(row.get("Poomsae 2") or "")
        }

    # Bài 1 ready thì chấm bài 1 như bình thường
    if p1_action == "ready":
        return {
            "slot": "1",
            "poomsae": str(row.get("Poomsae 1") or "")
        }

    return {
        "slot": "",
        "poomsae": "Waiting Poomsae 1 Ready..."
    }


def detect_screen(row: Dict[str, Any]) -> str:
    poomsae_type = str(row.get("Poomsae Type") or "").strip().lower()
    method = str(row.get("Method") or "").strip().lower()
    division = str(row.get("Division") or "").strip().lower()
    if poomsae_type == "freestyle":
        return "freestyle_tech"
    if poomsae_type == "demonstration":
        return "demonstration"
    if method in ["cut off", "cutoff"] or "cut" in method:
        return "recognized_cutoff"
    if "pair" in division or "team" in division:
        return "recognized_obo"
    return "recognized_sbs"


def clean_noc(noc: str) -> str:
    noc = str(noc or "").strip().upper()
    return noc.split()[0] if " " in noc else noc

# =========================
# HTML/CSS/JS WEB UI
# =========================
PAGE = r'''
<!doctype html>
<html lang="en">
<head>
<link rel="manifest" href="/manifest.json">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Poomsae Scoring Web</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Poomsae Score">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">

<style>
html, body{
    padding-top: env(safe-area-inset-top);
    padding-bottom: env(safe-area-inset-bottom);
}
</style>
<style>
:root{--bg:#05070d;--panel:#101827;--gold:#ffd447;--blue:#0a63d8;--blue2:#102d59;--red:#be1720;--red2:#4b0608;--green:#00c853;--muted:#9fb1c8}
html,body{
    width:100%;
    height:100%;
    overflow:hidden;
    overscroll-behavior:none;
    touch-action:manipulation;
}

*{box-sizing:border-box}

body{
    margin:0;
    background:#02040a;
    color:white;
    font-family:Arial,Helvetica,sans-serif;
    overflow:hidden;
}

.page{
    height:100vh;
    width:100vw;
    background:radial-gradient(circle at 50% 0%,#102340 0,#05070d 48%,#020308 100%);
    padding:26px;
    display:flex;
    flex-direction:column;
    gap:18px;
}

.center{display:flex;align-items:center;justify-content:center}
.login-card{
    width:min(520px,92vw);
    padding:clamp(14px,2vw,36px);
    border-radius:clamp(18px,2vw,28px);
    background:rgba(3,10,22,.72);
    box-shadow:0 30px 80px rgba(0,0,0,.55);
    border:1px solid rgba(255,255,255,.08);
}
.logo{
    font-size:clamp(28px,5vw,44px);
    font-weight:900;
    color:var(--gold);
    text-align:center;
    letter-spacing:1px;
}
.sub{
    text-align:center;
    font-size:clamp(16px,2.5vw,22px);
    font-weight:800;
    margin:8px 0 20px;
}
.field{margin:16px 0}
.field label{
    display:block;
    color:var(--gold);
    font-size:clamp(14px,2vw,18px);
    font-weight:900;
    margin-bottom:6px;
    text-align:center;
}

select,input{
    width:100%;
    height:clamp(46px,9vh,68px);
    border:0;
    border-radius:clamp(10px,1.5vw,16px);
    background:#111a2a;
    color:white;
    font-size:clamp(18px,3vw,28px);
    font-weight:900;
    text-align:center;
    padding:0 12px;
}

.btn{border:0;border-radius:24px;color:white;font-weight:900;cursor:pointer;box-shadow:inset 0 -4px 0 rgba(0,0,0,.25)}
.btn-main{
    width:100%;
    height:clamp(54px,10vh,86px);
    font-size:clamp(22px,3vw,32px);
    background:#00a8ff;
    margin-top:18px;
}
.logout{position:fixed;right:12px;top:12px;z-index:99;background:rgba(40,40,40,.45);height:38px;border-radius:13px;padding:0 18px;color:rgba(255,255,255,.75);border:0;font-weight:800}

.top-title{text-align:center;font-size:30px;font-weight:900;color:#2fd8ff;height:54px}
.content{flex:1;display:flex;flex-direction:column;gap:16px}

.score-page{
    height:100vh;
    width:100vw;
    display:flex;
    flex-direction:column;
    background:#050505;
    overflow:auto;
}

.score-top{
    height:215px;
    display:grid;
    grid-template-columns:42% 16% 42%;
    background:#050505;
}

.top-side{padding:12px 14px 8px;display:flex;flex-direction:column;gap:6px}
.blue-bg{background:#071e3d}
.red-bg{background:#4a0404}

.score-cards{
    height:125px;
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:8px;
}

.score-card{
    border-radius:18px;
    display:flex;
    align-items:center;
    justify-content:center;
    text-align:center;
    font-size:28px;
    font-weight:900;
    white-space:pre-line;
}

.score-card.blue{background:#092a59}
.score-card.red{background:#790808}

.center-info{padding:5px 8px;display:flex;flex-direction:column;align-items:center;gap:4px;text-align:center}
.division{width:100%;background:#1c1c1c;border-radius:16px;padding:10px 6px;font-size:14px;font-weight:900}
.timer{font-size:42px;font-weight:900;color:#ffef00}
.small{font-size:14px;font-weight:900}
.poomsae{color:var(--gold);font-weight:900;font-size:13px}

.score-bottom{
    flex:1;
    display:grid;
    grid-template-columns:33% 34% 33%;
}

.side-score{padding:50px 30px 30px;display:flex;flex-direction:column;gap:14px;align-items:stretch}
.mid-score{background:#171717;padding:28px 20px 20px;display:flex;flex-direction:column;gap:18px}

.deduct{height:130px;border-radius:24px;font-size:46px;background:#0b7cff}
.deduct.red{background:#fa313a}
.count{text-align:center;font-size:22px;font-weight:900}
.tech-total-row{
    display:grid;
    grid-template-columns:78px 1fr 78px;
    gap:10px;
    align-items:center;
    margin-bottom:4px;
}

.tech-total{
    height:58px;
    border-radius:18px;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:20px;
    font-weight:900;
    color:white;
    box-shadow:inset 0 -4px 0 rgba(0,0,0,.25);
}

.tech-total-title{
    text-align:center;
    font-size:19px;
    font-weight:900;
    color:#ffd447;
}

.blue-tech{
    background:#0d56a8;
}

.red-tech{
    background:#b3131d;
}


.pre-row{height:58px;display:grid;grid-template-columns:78px 1fr 78px;gap:10px;align-items:center}
.pre-row.cutoff{grid-template-columns:90px 1fr}
.pre-btn{height:58px;border-radius:18px;background:#0d3b78;color:white;font-size:20px;font-weight:900;border:0}
.pre-btn.red{background:#7a1010}
.pre-label{text-align:center;font-size:19px;font-weight:900}
.pre-row-slider{
    display:grid;
    grid-template-columns:60px 1fr 60px 1fr;
    gap:10px;
    align-items:center;
    min-height:70px;
}

.pre-slider-box{
    display:flex;
    flex-direction:column;
    gap:6px;
}

.pre-slider{
    width:100%;
    height:28px;
    accent-color:#00c853;
}

.pre-value{
    text-align:center;
    font-size:22px;
    font-weight:900;
    color:white;
}
.pre-slider{
    width:100%;
    height:34px;
    accent-color:#00c853;
}

.pre-value{
    text-align:center;
    font-size:20px;
    font-weight:900;
    color:white;
}

.send{height:105px;border-radius:24px;background:#00c853;font-size:36px;color:white;font-weight:900;border:0}
.send-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.send-blue{background:#0d73ff}
.send-red{background:#ff2933}

#appRoot{
    width:100vw;
    height:100vh;
    overflow:hidden;
}

.rotate-lock{
    position:fixed;
    inset:0;
    z-index:9999;
    display:none;
    align-items:center;
    justify-content:center;
    text-align:center;
    padding:28px;
    background:#02040a;
    color:white;
}

.rotate-lock-box{
    max-width:520px;
    border-radius:26px;
    padding:28px;
    background:rgba(16,24,39,.96);
    border:1px solid rgba(255,255,255,.12);
    box-shadow:0 30px 80px rgba(0,0,0,.6);
}

.rotate-lock-icon{font-size:64px;margin-bottom:14px}
.rotate-lock-title{font-size:30px;font-weight:900;color:var(--gold);margin-bottom:10px}
.rotate-lock-text{font-size:19px;font-weight:800;color:#c8dbf1;line-height:1.35}

@media screen and (orientation:portrait) and (max-width:900px){
    #appRoot{display:none}
    .logout{display:none}
    .rotate-lock{display:flex}
}

@media screen and (orientation:landscape) and (max-height:520px){
    body{overflow:hidden}
    .page{height:100dvh;width:100dvw;padding:10px;gap:8px}
    .score-page{height:100dvh;width:100dvw;overflow:hidden}
    .top-title{height:34px;font-size:20px}
    .content{gap:8px}
    .status-card{font-size:18px;padding:8px}
    .match-title{font-size:20px}
    .ready-row{height:calc(100dvh - 140px);gap:10px}
    .team-card{padding:12px;border-radius:18px}
    .noc{font-size:28px}
    .athlete{font-size:18px}

    .score-top{height:132px;grid-template-columns:42% 16% 42%}
    .score-cards{height:78px}
    .score-card{font-size:17px;border-radius:12px}
    .center-info{gap:2px;padding:3px 5px}
    .division{font-size:10px;padding:5px 3px;border-radius:10px}
    .timer{font-size:27px}
    .small{font-size:10px}
    .poomsae{font-size:9px}
    .top-side{padding:7px;gap:3px}
    .top-side .noc{font-size:22px!important}
    .top-side .athlete{font-size:14px!important}

    .score-bottom{
        grid-template-columns:33% 34% 33%;
        height:calc(100dvh - 132px);
    }

    .side-score{padding:16px 16px 10px;gap:5px}
    .mid-score{padding:12px 10px 8px;gap:8px}
    .deduct{height:62px;border-radius:16px;font-size:28px}
    .count{font-size:15px}
    .tech-total-row{
        height:clamp(38px,8vh,62px);
        grid-template-columns:clamp(58px,9vw,90px) 1fr clamp(58px,9vw,90px);
        gap:clamp(6px,1vw,12px);
        align-items:center;
        margin-bottom:0;
    }

    .tech-total{
        height:clamp(36px,7vh,58px)!important;
        border-radius:clamp(10px,1.8vw,18px);
        font-size:clamp(16px,2.8vw,24px)!important;
    }

    .tech-total-title{
        font-size:clamp(13px,2.4vw,22px)!important;
        line-height:1;
    }
    .pre-row{height:36px;grid-template-columns:52px 1fr 52px;gap:6px}
    .pre-row.cutoff{grid-template-columns:62px 1fr}
    .pre-btn{height:36px;border-radius:11px;font-size:14px}
    .pre-label{font-size:13px}
    .pre-row-slider{
        display:grid;
        grid-template-columns:55px 1fr 55px 1fr;
        gap:8px;
        align-items:center;
        min-height:58px;
    }

    .pre-slider-box{
        display:flex;
        flex-direction:column;
        gap:4px;
    }

    .pre-slider{
        width:100%;
        height:26px;
        accent-color:#00c853;
    }

    .pre-value{
        text-align:center;
        font-size:20px;
        font-weight:900;
        color:white;
    }
    .send{height:58px;border-radius:16px;font-size:22px}

    .fs-bottom{padding:8px 18px;gap:7px}
    .fs-title-row{height:46px;grid-template-columns:1fr 150px}
    .fs-title-row .send{height:42px!important;font-size:17px!important}
    .fs-card{padding:8px 14px;gap:4px}
    .fs-row{height:35px;grid-template-columns:210px repeat(10,1fr);gap:4px}
    .fs-row>div:first-child{font-size:13px!important}
    .num-btn{height:31px;font-size:13px;border-radius:6px}

    .demo-card{grid-template-columns:1.2fr .8fr;padding:10px 16px;gap:14px}
    .demo-row{height:42px;grid-template-columns:155px 55px 1fr;gap:7px}
    .demo-row div{font-size:14px!important}
    .demo-row input{height:28px}
    .ded-row{height:37px;grid-template-columns:58px 45px 45px 45px;gap:7px}
    .mini-btn{height:31px;font-size:16px}

    .logout{top:5px;right:5px;height:28px;padding:0 10px;font-size:11px;border-radius:9px}
}
.slider-popup{
    position:fixed;
    inset:0;
    z-index:9998;
    display:none;
    align-items:center;
    justify-content:center;
    background:rgba(0,0,0,.45);
}

.slider-popup-box{
    width:min(560px,90vw);

    border-radius:24px;

    padding:20px 26px 14px;

    background:#101827;
    border:1px solid rgba(255,255,255,.18);
    box-shadow:0 30px 80px rgba(0,0,0,.6);
}

.slider-popup-title{
    font-size:24px;
    font-weight:900;
    color:var(--gold);
    text-align:center;
    margin-bottom:10px;
}

.slider-popup-value{
    font-size:54px;
    font-weight:900;
    text-align:center;
    color:white;
    margin-bottom:18px;
}

.popup-range{
    width:100%;
    height:68px;

    background:transparent;

    -webkit-appearance:none;
    appearance:none;

    cursor:pointer;
}

/* =========================
   TRACK
========================= */

.popup-range::-webkit-slider-runnable-track{
    height:16px;

    border-radius:999px;

    background:
        linear-gradient(
            90deg,
            rgba(0,255,140,.95) 0%,
            rgba(0,220,255,.95) 100%
        );

    box-shadow:
        0 0 18px rgba(0,255,170,.35),
        inset 0 0 10px rgba(255,255,255,.18);

    border:1px solid rgba(255,255,255,.15);
}

/* =========================
   THUMB WEBKIT
========================= */

.popup-range::-webkit-slider-thumb{
    -webkit-appearance:none;
    appearance:none;

    width:44px;
    height:44px;

    border-radius:50%;

    background:
        radial-gradient(
            circle at 30% 30%,
            #ffffff,
            #9dffca 35%,
            #00e676 70%
        );

    border:4px solid #eafff4;

    margin-top:-14px;

    box-shadow:
        0 0 24px rgba(0,255,140,.95),
        0 0 50px rgba(0,255,170,.55),
        0 6px 18px rgba(0,0,0,.45);

    transition:.12s;
}

.popup-range::-webkit-slider-thumb:hover{
    transform:scale(1.08);
}

/* =========================
   FIREFOX
========================= */

.popup-range::-moz-range-track{
    height:16px;

    border-radius:999px;

    background:
        linear-gradient(
            90deg,
            rgba(0,255,140,.95) 0%,
            rgba(0,220,255,.95) 100%
        );

    box-shadow:
        0 0 18px rgba(0,255,170,.35),
        inset 0 0 10px rgba(255,255,255,.18);

    border:1px solid rgba(255,255,255,.15);
}

.popup-range::-moz-range-thumb{
    width:44px;
    height:44px;

    border-radius:50%;

    background:
        radial-gradient(
            circle at 30% 30%,
            #ffffff,
            #9dffca 35%,
            #00e676 70%
        );

    border:4px solid #eafff4;

    box-shadow:
        0 0 24px rgba(0,255,140,.95),
        0 0 50px rgba(0,255,170,.55),
        0 6px 18px rgba(0,0,0,.45);
}

/* Firefox */
.popup-range::-moz-range-track{
    height:18px;
    border-radius:999px;
    background:#243447;
}

.popup-range::-moz-range-thumb{
    width:46px;
    height:46px;
    border-radius:50%;

    background:#00c853;
    border:4px solid #eafff1;

    box-shadow:
        0 0 18px rgba(0,200,83,.65),
        0 4px 12px rgba(0,0,0,.45);
}

.slider-popup-actions{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:8px;
    margin-top:4px;
}

.slider-popup-actions.one-btn{
    grid-template-columns:1fr;
}

.slider-popup-actions button{
    height:58px;
    border:0;
    border-radius:16px;
    font-size:22px;
    font-weight:900;
    color:white;
}

.btn-cancel{background:#555}
.btn-ok{background:#00a84f}
.flag{
    width:72px;
    height:48px;
    border-radius:8px;
    overflow:hidden;
    background:rgba(255,255,255,.08);
    border:1px solid rgba(255,255,255,.22);
    display:flex;
    align-items:center;
    justify-content:center;
    flex-shrink:0;
}

.flag img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
}

.flag-text{
    font-size:18px;
    font-weight:900;
    color:white;
}

.noc{
    font-size:38px;
    font-weight:900;
}

.athlete{
    font-size:21px;
    font-weight:800;
}

.score-page{
    background:#030303;
}

.score-top{
    height:220px;
    grid-template-columns:34% 32% 34%;
}

.center-info{
    background:#030303;
    justify-content:center;
}

.score-bottom{
    grid-template-columns:30% 40% 30%;
}

.mid-score{
    border-radius:0;
}

.side-score{
    justify-content:center;
}

.pre-btn{
    background:#0d56a8;
    color:white;
    box-shadow:inset 0 -4px 0 rgba(0,0,0,.25);
}

.pre-btn.red{
    background:#b3131d;
}

.send{
    background:#00c853;
    color:white;
}

/* ===== MOBILE LANDSCAPE FIXED LAYOUT ===== */
@media screen and (orientation:landscape) and (max-height:600px){

    html, body, #appRoot{
        width:100dvw;
        height:100dvh;
        overflow:hidden!important;
    }

    .score-page{
        width:100dvw;
        height:100dvh;
        display:grid;
        grid-template-rows:33dvh 67dvh;
        overflow:hidden;
    }

    .score-top{
        height:33dvh!important;
        display:grid;
        grid-template-columns:34% 32% 34%;
    }

    .top-side{
        padding:clamp(5px,1.2vw,12px);
        gap:clamp(2px,.6vh,6px);
        overflow:hidden;
    }

    .flag{
        width:clamp(42px,8vw,72px);
        height:clamp(28px,5.3vw,48px);
    }

    .noc{
        font-size:clamp(22px,4vw,38px)!important;
        line-height:1;
    }

    .athlete{
        font-size:clamp(11px,2.2vw,21px)!important;
        line-height:1.15;
        white-space:nowrap;
        overflow:hidden;
        text-overflow:ellipsis;
    }

    .center-info{
        padding:clamp(3px,.8vw,8px);
        gap:clamp(1px,.5vh,4px);
        justify-content:center;
        overflow:hidden;
    }

    .division{
        font-size:clamp(10px,1.7vw,15px);
        padding:clamp(4px,.8vw,8px);
        border-radius:clamp(8px,1.8vw,16px);
    }

    .timer{
        font-size:clamp(28px,6vw,52px);
        line-height:1;
    }

    .small{
        font-size:clamp(9px,1.6vw,14px);
        line-height:1.05;
    }

    .poomsae{
        font-size:clamp(9px,1.5vw,13px);
        line-height:1.05;
    }

    .score-cards{
        display:none!important;
    }

    .score-bottom{
        min-height:67dvh!important;
        height:auto!important;
        display:grid;
        grid-template-columns:30% 40% 30%;
        overflow:hidden;
    }

    .side-score{
        padding:clamp(8px,2vw,24px);
        gap:clamp(4px,1vh,12px);
        justify-content:center;
        overflow:hidden;
    }

    .mid-score{
        padding:clamp(8px,1.8vw,22px);
        gap:clamp(6px,1.3vh,16px);
        overflow:hidden;
        justify-content:center;
    }

    .deduct{




        height:clamp(95px,28vh,180px);
        border-radius:clamp(14px,2.4vw,24px);
        font-size:clamp(32px,7vw,58px);

        color:white;
        font-weight:900;
        text-shadow:
            0 0 8px rgba(0,0,0,.65),
            0 2px 6px rgba(0,0,0,.7);
    }

    .count{
        font-size:clamp(16px,3vw,26px);
        line-height:1;
    }

    .score-summary{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:clamp(8px,1.4vw,18px);
    }

    .score-summary-card{
        background:#070707;
        border-radius:clamp(10px,1.8vw,18px);
        text-align:center;
        padding:clamp(5px,1vw,12px);
        font-weight:900;
    }

    .score-summary-num{
        font-size:clamp(20px,4vw,34px);
        line-height:1;
    }

    .score-summary-label{
        font-size:clamp(14px,2.5vw,28px);
        line-height:1.1;
    }

    .pre-row{
        height:clamp(38px,8vh,62px);
        grid-template-columns:clamp(58px,9vw,90px) 1fr clamp(58px,9vw,90px);
        gap:clamp(6px,1vw,12px);
    }

    .pre-btn{
        height:clamp(36px,7vh,58px);
        border-radius:clamp(10px,1.8vw,18px);
        font-size:clamp(16px,2.8vw,24px);
    }

    .pre-label{
        font-size:clamp(13px,2.4vw,22px);
        line-height:1;
        white-space:nowrap;
    }

    .send{
        height:clamp(55px,12vh,105px);
        border-radius:clamp(14px,2.2vw,24px);
        font-size:clamp(24px,5vw,44px);
    }

    .logout{
        top:clamp(4px,.8vw,10px);
        right:clamp(4px,.8vw,10px);
        height:clamp(26px,5vh,38px);
        font-size:clamp(10px,1.5vw,14px);
    }
}

.demo-mobile-layout{
    min-height:67dvh;
    height:auto;
    display:grid;
    grid-template-columns:62% 38%;
    gap:clamp(8px,1.5vw,18px);
    padding:clamp(8px,1.5vw,18px);
    background:#050505;
    overflow:hidden;
}

.demo-left,
.demo-right{
    overflow:auto;
    background:#111;
    border-radius:clamp(12px,2vw,24px);
    padding:clamp(8px,1.5vw,18px);
}

.demo-left{
    display:grid;
    grid-template-rows:repeat(4,1fr);
    gap:clamp(6px,1vh,12px);
}

.demo-score-row{
    display:grid;
    grid-template-columns:34% 14% 52%;
    align-items:center;
    gap:clamp(6px,1vw,12px);
}

.demo-score-title{
    font-size:clamp(13px,2.3vw,24px);
    font-weight:900;
    color:white;
    line-height:1;
}

.demo-score-value{
    font-size:clamp(18px,3vw,32px);
    font-weight:900;
    color:var(--gold);
    text-align:center;
}

.demo-score-slider{
    width:100%;
    height:58px;
    background:transparent;
    -webkit-appearance:none;
    appearance:none;
    cursor:pointer;
}

/* Demon slider track - Chrome / Edge / Android */
.demo-score-slider::-webkit-slider-runnable-track{
    height:14px;
    border-radius:999px;

    background:
        linear-gradient(
            90deg,
            rgba(0,255,140,.95) 0%,
            rgba(0,220,255,.95) 100%
        );

    box-shadow:
        0 0 16px rgba(0,255,170,.32),
        inset 0 0 8px rgba(255,255,255,.16);

    border:1px solid rgba(255,255,255,.15);
}

.demo-score-slider::-webkit-slider-thumb{
    -webkit-appearance:none;
    appearance:none;

    width:40px;
    height:40px;
    border-radius:50%;

    background:
        radial-gradient(
            circle at 30% 30%,
            #ffffff,
            #9dffca 35%,
            #00e676 70%
        );

    border:4px solid #eafff4;
    margin-top:-13px;

    box-shadow:
        0 0 22px rgba(0,255,140,.9),
        0 0 44px rgba(0,255,170,.5),
        0 6px 16px rgba(0,0,0,.45);
}

/* Demon slider - Firefox */
.demo-score-slider::-moz-range-track{
    height:14px;
    border-radius:999px;

    background:
        linear-gradient(
            90deg,
            rgba(0,255,140,.95) 0%,
            rgba(0,220,255,.95) 100%
        );

    box-shadow:
        0 0 16px rgba(0,255,170,.32),
        inset 0 0 8px rgba(255,255,255,.16);

    border:1px solid rgba(255,255,255,.15);
}

.demo-score-slider::-moz-range-thumb{
    width:40px;
    height:40px;
    border-radius:50%;

    background:
        radial-gradient(
            circle at 30% 30%,
            #ffffff,
            #9dffca 35%,
            #00e676 70%
        );

    border:4px solid #eafff4;

    box-shadow:
        0 0 22px rgba(0,255,140,.9),
        0 0 44px rgba(0,255,170,.5),
        0 6px 16px rgba(0,0,0,.45);
}

.demo-right{
    display:grid;
    grid-template-rows:auto 1fr auto;
    gap:clamp(8px,1.5vh,16px);
}

.demo-ded-title{
    font-size:clamp(18px,3vw,34px);
    font-weight:900;
    color:#ff4040;
    text-align:center;
}

.demo-ded-list{
    display:grid;
    grid-template-rows:repeat(3,1fr);
    gap:clamp(6px,1vh,12px);
}

.demo-ded-row{
    display:grid;
    grid-template-columns:1fr 48px 48px 48px;
    align-items:center;
    gap:clamp(5px,.8vw,10px);
}

.demo-ded-label{
    font-size:clamp(16px,2.4vw,28px);
    font-weight:900;
}

.demo-ded-count{
    font-size:clamp(18px,2.8vw,30px);
    font-weight:900;
    text-align:center;
}

.demo-ded-btn{
    height:clamp(34px,7vh,56px);
    border:0;
    border-radius:clamp(8px,1.4vw,14px);
    background:#444;
    color:white;
    font-size:clamp(18px,3vw,30px);
    font-weight:900;
}

.demo-ded-btn.plus{
    background:#c90000;
}

.demo-send{
    width:100%;
}

.fs-mobile-layout{
    height:67dvh;
    padding:clamp(8px,1.5vw,18px);
    background:#050505;
    overflow:hidden;
    display:grid;
    grid-template-rows:auto 1fr;
    gap:clamp(8px,1.5vh,16px);
}

.fs-header-row{
    display:grid;
    grid-template-columns:1fr clamp(120px,20vw,220px);
    align-items:center;
    gap:clamp(8px,1.5vw,18px);
}

.fs-main-title{
    font-size:clamp(20px,3.5vw,38px);
    font-weight:900;
    color:white;
    line-height:1;
}

.fs-send{
    height:clamp(44px,9vh,76px);
    font-size:clamp(20px,3.5vw,34px);
    border-radius:clamp(14px,2vw,24px);
}

.fs-score-list{
    background:#111;
    border-radius:clamp(12px,2vw,24px);
    padding:clamp(8px,1.5vw,18px);
    display:grid;
    grid-template-rows:repeat(6,1fr);
    gap:clamp(5px,1vh,10px);
    overflow:hidden;
}

.fs-score-row{
    display:grid;
    grid-template-columns:clamp(145px,25vw,280px) 1fr;
    align-items:center;
    gap:clamp(6px,1vw,14px);
}

.fs-score-label{
    font-size:clamp(12px,2vw,22px);
    font-weight:900;
    color:white;
    line-height:1;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}

.fs-button-grid{
    display:grid;
    grid-template-columns:repeat(10,1fr);
    gap:clamp(3px,.6vw,8px);
}

.num-btn{
    width:100%;
    height:clamp(28px,6vh,52px);
    border:0;
    border-radius:clamp(6px,1vw,12px);
    background:#17263a;
    color:white;
    font-size:clamp(12px,2vw,20px);
    font-weight:900;
}

.num-btn.selected{
    background:#00c853;
    color:white;
}

.fs-pre-list{
    grid-template-rows:repeat(4,1fr);
}

.fs-pre-row{
    grid-template-columns:clamp(190px,30vw,360px) 1fr;
}

.ready-page{
    width:100dvw;
    height:100dvh;
    overflow:hidden;
    background:radial-gradient(circle at 50% 0%,#102340 0,#05070d 48%,#020308 100%);
    display:grid;
    grid-template-rows:clamp(135px, 23vh, 185px) 1fr;
    padding:clamp(8px,1.5vw,18px);
    gap:clamp(8px,1.5vh,16px);
}

.ready-title{
    text-align:center;
    font-size:clamp(22px,4vw,44px);
    font-weight:900;
    color:#2fd8ff;
}

.ready-info{
    justify-self:center;
    text-align:center;
    background:#111;
    border-radius:clamp(12px,2vw,22px);
    padding:clamp(6px,1vh,10px) clamp(18px,3vw,36px);
    font-size:clamp(13px,2.2vw,24px);
    font-weight:900;
    line-height:1.12;
    color:white;
    margin-bottom:0!important;
    position:relative;
    z-index:90;
}

.ready-body{
    display:grid;
    align-items:center;
    gap:clamp(10px,2vw,24px);
}

.ready-body.single{
    grid-template-columns:1fr 1fr;
}

.ready-body.cutoff{
    grid-template-columns:1fr;
}

.ready-team{
    height:100%;
    min-height:0;
    border-radius:clamp(18px,3vw,34px);
    padding:clamp(14px,2.5vw,34px);
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    gap:clamp(8px,1.5vh,18px);
    overflow:hidden;
    border:3px solid rgba(255,255,255,.15);
}

.ready-team.blue{
    background:linear-gradient(145deg,#06264f,#071426);
    border-color:#1e88ff;
}

.ready-team.red{
    background:linear-gradient(145deg,#520609,#160305);
    border-color:#ff303a;
}

.ready-team.cutoff-one{
    width:min(720px,80vw);
    justify-self:center;
    background:linear-gradient(145deg,#111,#050505);
    border-color:#ffd447;
}

.ready-team-top{
    display:flex;
    align-items:center;
    justify-content:center;
    gap:clamp(10px,1.8vw,22px);
}

.ready-team .flag{
    width:clamp(64px,12vw,150px);
    height:clamp(42px,8vw,96px);
}

.ready-noc{
    font-size:clamp(38px,8vw,96px);
    font-weight:900;
    line-height:1;
}

.ready-athlete{
    max-width:100%;
    font-size:clamp(18px,4vw,48px);
    font-weight:900;
    text-align:center;
    line-height:1.1;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}

.send-row .send{
    height:clamp(44px,8vh,70px)!important;
    font-size:clamp(12px,2.2vw,24px)!important;
    line-height:1.05!important;
    padding:2px 4px!important;
    border-radius:clamp(10px,1.8vw,18px)!important;
}

.locked-control{
    opacity:.28!important;
    filter:grayscale(1)!important;
    pointer-events:none!important;
}

@media screen and (orientation:landscape) and (max-height:600px){
    .page.center{
        height:100dvh;
        width:100dvw;
        padding:clamp(6px,1vh,12px);
        justify-content:center;
        overflow:hidden;
    }

    .login-card{
        width:min(520px,74vw);
        max-height:96dvh;
        padding:clamp(10px,2vh,18px) clamp(18px,3vw,32px);
        display:flex;
        flex-direction:column;
        justify-content:center;
        gap:clamp(5px,1vh,10px);
    }

    .logo{
        font-size:clamp(24px,6vh,42px);
        line-height:1.05;
    }

    .sub{
        font-size:clamp(13px,3vh,22px);
        margin:0 0 clamp(4px,1vh,10px);
    }

    .field{
        margin:clamp(4px,1vh,8px) 0;
    }

    .field label{
        font-size:clamp(11px,2.5vh,16px);
        margin-bottom:clamp(3px,.7vh,6px);
    }

    select,input{
        height:clamp(34px,8vh,54px);
        font-size:clamp(17px,4vh,28px);
        border-radius:clamp(8px,1.5vw,14px);
    }

    .btn-main{
        height:clamp(40px,9vh,62px);
        font-size:clamp(18px,4vh,30px);
        margin-top:clamp(6px,1vh,12px);
        border-radius:clamp(12px,2vw,22px);
    }
}

.ready-page{
    background:
        radial-gradient(circle at 18% 20%, rgba(0,220,255,.22), transparent 28%),
        radial-gradient(circle at 82% 35%, rgba(0,255,130,.13), transparent 30%),
        linear-gradient(135deg,#02050c 0%,#071629 45%,#020308 100%)!important;
    position:relative;
}

.ready-page:before{
    content:"";
    position:absolute;
    inset:0;
    pointer-events:none;
    opacity:.22;
    background-image:
        linear-gradient(rgba(0,255,255,.18) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,255,255,.18) 1px, transparent 1px);
    background-size:42px 42px;
}

.ready-page:after{
    content:"";
    position:absolute;
    inset:0;
    pointer-events:none;
    background:radial-gradient(circle at 50% 50%, transparent 0%, rgba(0,0,0,.45) 72%);
}

.waiting-glass{
    position:fixed;
    left:50%;
    top:62%;
    transform:translate(-50%,-50%);
    z-index:70;
    padding:clamp(18px,3vw,34px) clamp(28px,5vw,56px);
    border-radius:clamp(18px,3vw,32px);
    background:rgba(8,18,32,.12);
    backdrop-filter:blur(3px);
    -webkit-backdrop-filter:blur(3px);
    border:1px solid rgba(80,220,255,.35);
    opacity:.88;
    box-shadow:
        0 0 28px rgba(0,220,255,.28),
        inset 0 0 20px rgba(255,255,255,.06);
    text-align:center;
    color:white;
    font-weight:900;
    font-size:clamp(22px,4vw,46px);
    letter-spacing:1px;
}

.waiting-glass span{
    display:block;
    margin-top:8px;
    color:#ffd447;
    font-size:clamp(13px,2vw,22px);
}

.match-line{
    font-size:clamp(10px,1.8vw,16px);
    font-weight:900;
    color:white;
    line-height:1;
}

.poomsae-box{
    margin-top:2px;
    padding:3px 8px;
    border:2px solid #ffd447;
    border-radius:8px;
    color:#ffd447;
    font-size:clamp(9px,1.6vw,14px);
    font-weight:900;
    line-height:1.05;
    white-space:nowrap;
}

.top-side .athlete{
    font-size:clamp(18px,3vw,34px)!important;
    font-weight:900!important;
}


.toast{
    position:fixed;
    left:50%;
    top:50%;
    transform:translate(-50%,-50%);
    z-index:10000;
    display:none;

    min-width:min(260px,58vw);

    padding:clamp(12px,2vw,20px)
            clamp(22px,4vw,38px);

    border-radius:clamp(16px,2vw,24px);

    background:rgba(187,247,208,.38);

    backdrop-filter:blur(6px);
    -webkit-backdrop-filter:blur(6px);

    border:1.5px solid rgba(34,197,94,.38);

    box-shadow:
        0 0 22px rgba(34,197,94,.18),
        inset 0 0 10px rgba(255,255,255,.05);

    color:#ecfff4;

    font-size:clamp(20px,3.2vw,38px);

    font-weight:900;
    text-align:center;
    letter-spacing:.3px;
}

.toast.warn{
    background:rgba(254,249,195,.88);
    border-color:rgba(234,179,8,.75);
    color:#713f12;
    box-shadow:0 0 35px rgba(234,179,8,.38);
}

.toast.ok{
    background:rgba(120,255,170,.22);
    border-color:rgba(120,255,170,.35);
    color:#f4fff8;
}

/* ===== FIX FREESTYLE TECH/PRE ON IPHONE XS MAX LANDSCAPE ===== */
@media screen and (orientation:landscape) and (max-height:600px){

    .fs-mobile-layout{
        min-height:67dvh!important;
        height:auto!important;
        overflow:auto!important;
        grid-template-rows:auto auto!important;
        padding-bottom:24px!important;
    }

    .fs-score-list{
        min-height:max-content!important;
        height:auto!important;
        overflow:visible!important;
        grid-template-rows:none!important;
        display:flex!important;
        flex-direction:column!important;
        gap:clamp(4px,.8vh,8px)!important;
        padding-bottom:20px!important;
    }

    .fs-score-row{
        min-height:clamp(30px,7vh,46px)!important;
        height:auto!important;
    }

    .fs-button-grid{
        min-height:clamp(28px,6vh,42px)!important;
    }

    .num-btn{
        min-height:clamp(26px,5.8vh,40px)!important;
        height:auto!important;
    }
}

</style>
</head>
<body>
<div class="rotate-lock">
  <div class="rotate-lock-box">
    <div class="rotate-lock-icon">📱↔️</div>
    <div class="rotate-lock-title">PLEASE ROTATE PHONE</div>
    <div class="rotate-lock-text">
      Màn hình chấm thi chỉ dùng chế độ ngang.<br>
      Vui lòng xoay điện thoại sang ngang để tiếp tục.
    </div>
  </div>
</div>
{% if not judge_id %}
<div class="page center">
  <form class="login-card" method="post" action="/login">
    <div class="logo">POOMSAE SCORING</div>
    <div class="sub">JUDGE CONTROL PANEL</div>
    <div class="field"><label>SELECT JUDGE</label><select name="judge_id">{% for i in range(1,8) %}<option>Judge {{i}}</option>{% endfor %}</select></div>
    <div class="field"><label>SELECT COURT</label><select name="court_id">{% for i in range(0,7) %}<option>Court {{i}}</option>{% endfor %}</select></div>
    <button class="btn btn-main" type="submit">ACCEPT</button>
  </form>
</div>
{% else %}
<button class="logout" onclick="openLogoutPopup()">Logout</button>
<div id="appRoot"></div>
<div id="toast" class="toast"></div>
<div id="logoutConfirm" style="
    position:fixed;
    inset:0;
    background:rgba(0,0,0,.55);

    backdrop-filter:blur(4px);
    -webkit-backdrop-filter:blur(4px);

    display:none;
    align-items:center;
    justify-content:center;

    z-index:99999;
">

    <div style="
        width:min(420px,86vw);
        border-radius:26px;

        background:rgba(8,12,20,.96);

        border:2px solid rgba(255,255,255,.08);

        padding:28px 24px;

        text-align:center;

        box-shadow:
            0 0 40px rgba(0,0,0,.55),
            0 0 24px rgba(0,255,180,.08);
    ">

        <div style="
            font-size:clamp(22px,4vw,38px);
            font-weight:900;
            color:#ffd54a;
            margin-bottom:14px;
        ">
            LOG OUT
        </div>

        <div style="
            font-size:clamp(14px,2vw,22px);
            color:#d7dde7;
            margin-bottom:28px;
        ">
            Do you want to log out?
        </div>

        <div style="
            display:flex;
            gap:16px;
            justify-content:center;
        ">

            <button onclick="confirmLogout()" style="
                border:none;
                border-radius:16px;
                padding:14px 34px;
                font-size:20px;
                font-weight:900;
                cursor:pointer;

                background:#00d26a;
                color:white;
            ">
                YES
            </button>

            <button onclick="closeLogoutPopup()" style="
                border:none;
                border-radius:16px;
                padding:14px 34px;
                font-size:20px;
                font-weight:900;
                cursor:pointer;

                background:#2b3444;
                color:white;
            ">
                NO
            </button>

        </div>
    </div>
</div>

<div id="sliderPopup" class="slider-popup">
  <div class="slider-popup-box">
    <div id="sliderPopupTitle" class="slider-popup-title">Score</div>
    <div id="sliderPopupValue" class="slider-popup-value">2.0</div>
    <input id="sliderPopupRange" class="popup-range" type="range" min="0.5" max="2" step="0.01" value="2">
    <div class="slider-popup-actions one-btn">
    </div>
  </div>
</div>
<script>
const STATE = {
    judge_id: {{judge_id|tojson}},
    court_id: {{court_id|tojson}},
    screen:'wait',
    match:null,
    ready:{slot:'',poomsae:''},
    freestyleTech:null,
    scores:{},
    timerText:'00:00',
    timerColor:'#ffef00'
};
async function lockLandscapeAndFullscreen(){
    try{
        if(document.documentElement.requestFullscreen && !document.fullscreenElement){
            await document.documentElement.requestFullscreen();
        }
    }catch(e){}

    try{
        if(screen.orientation && screen.orientation.lock){
            await screen.orientation.lock('landscape');
        }
    }catch(e){}

    setTimeout(()=>window.scrollTo(0,1),80);
}

window.addEventListener('load',()=>setTimeout(()=>window.scrollTo(0,1),120));
window.addEventListener('orientationchange',()=>setTimeout(()=>window.scrollTo(0,1),250));
document.addEventListener('click',lockLandscapeAndFullscreen,{once:true});
document.addEventListener('touchend',lockLandscapeAndFullscreen,{once:true});

function api(url, options={}){return fetch(url,{headers:{'Content-Type':'application/json'},...options}).then(r=>r.json())}
function openLogoutPopup(){
    document.getElementById('logoutConfirm').style.display='flex';
}

function closeLogoutPopup(){
    document.getElementById('logoutConfirm').style.display='none';
}

function confirmLogout(){

    // XÓA draft local
    localStorage.clear();

    // logout flask session
    window.location.href='/logout';
}
function fmtName(s){return s||''}
function toast(msg, type='ok', after){
    const t = document.getElementById('toast');

    t.className = 'toast ' + type;
    t.innerText = msg;
    t.style.display = 'block';

    const delay = type === 'ok' ? 1200 : 1000;

    setTimeout(()=>{
        t.style.display = 'none';
        if(after) after();
    }, delay);
}function scoreInit(){return {b03:0,b01:0,r03:0,r01:0,bt:4,rt:4,bs:2,br:2,bk:2,rs:2,rr:2,rk:2,c03:0,c01:0,ct:4,cs:2,cr:2,ck:2,demo:{Yeonmu:2,'Self-Defense':2,Breaking:5,Composition:1},ded:{'-0.1':0,'-0.3':0,'-0.5':0}}}
function resetScores(){STATE.scores=scoreInit()}
function scoreDraftKey(){
    const match = STATE.match?.Match || 'no_match';
    const slot = STATE.ready?.slot || 'no_slot';
    const judge = STATE.judge_id || 'no_judge';

    let screenGroup = STATE.screen;
    if(STATE.screen === 'freestyle_tech' || STATE.screen === 'freestyle_pre'){
        screenGroup = 'freestyle';
    }

    return `poomsae_draft_${judge}_${match}_${slot}_${screenGroup}`;
}

function saveScoreDraft(){
    try{
        localStorage.setItem(scoreDraftKey(), JSON.stringify({
            scores: STATE.scores,
            fsTech: STATE.fsTech || null,
            fsPre: STATE.fsPre || null,
            freestyleTech: STATE.freestyleTech || null
        }));
    }catch(e){}
}

function loadScoreDraft(){
    try{
        const raw = localStorage.getItem(scoreDraftKey());
        if(!raw) return false;

        const data = JSON.parse(raw);
        if(data.scores) STATE.scores = data.scores;
        if(data.fsTech) STATE.fsTech = data.fsTech;
        if(data.fsPre) STATE.fsPre = data.fsPre;
        if(data.freestyleTech) STATE.freestyleTech = data.freestyleTech;

        return true;
    }catch(e){
        return false;
    }
}
function clearScoreDraft(){
    try{
        localStorage.removeItem(scoreDraftKey());
    }catch(e){}
}
function pageWait(title='WAITING START MATCH',sub='System is waiting for controller action...'){
    document.getElementById('appRoot').innerHTML=`
    <div class="ready-page">
        <div class="ready-title">POOMSAE SCORING SYSTEM</div>

        <div style="
            flex:1;
            display:flex;
            align-items:flex-start;
            justify-content:center;
            padding:clamp(4px,1vh,10px) 10px 10px 10px;
            overflow:hidden;
        ">
            <div style="
                width:min(780px,88vw);

                min-height:clamp(260px,42vh,420px);

                max-height:82dvh;

                padding:
                    clamp(24px,4vh,44px)
                    clamp(28px,5vw,58px);

                overflow:hidden;

                display:flex;
                flex-direction:column;
                justify-content:center;
                border-radius:clamp(22px,4vw,40px);
                background:rgba(8,18,32,.42);
                border:1px solid rgba(80,220,255,.35);
                box-shadow:0 0 40px rgba(0,220,255,.22);
                text-align:center;
                backdrop-filter:blur(8px);
                -webkit-backdrop-filter:blur(8px);
            ">
                <div style="
                    font-size:clamp(34px,6vw,72px);
                    color:var(--gold);
                    font-weight:900;
                    line-height:1;
                    margin-bottom:clamp(10px,2vh,20px);
                ">${title}</div>

                <div style="
                    font-size:clamp(16px,2.8vw,28px);
                    color:#dcecff;
                    font-weight:900;
                    margin-bottom:clamp(16px,3vh,30px);
                ">${sub}</div>

                <div style="
                    display:inline-block;
                    padding:10px 22px;
                    border-radius:999px;
                    background:rgba(0,255,117,.12);
                    border:1px solid rgba(0,255,117,.35);
                    color:#51ff8c;
                    font-size:clamp(16px,2.8vw,26px);
                    font-weight:900;
                ">${STATE.judge_id} | ${STATE.court_id}</div>
            </div>
        </div>
    </div>`;
}
function flag(noc){
    const code = (noc||'').split(' ')[0].toUpperCase();

    return `
    <div class="flag">
        <img src="flags/${code}.png"
             onerror="this.style.display='none'; this.parentElement.innerHTML='<span class=&quot;flag-text&quot;>${code}</span>'">
    </div>`;
}
function pageReady(row,readyText){
    let method = (row.Method || '').toLowerCase();
    let division = (row.Division || '').toLowerCase();

    let isCut = method.includes('cut');
    let isObo = division.includes('pair') || division.includes('team');

    let judgeStatus = (STATE.judge_status || '').toLowerCase();

    // =========================
    // OBO: chỉ lấy trạng thái đúng Judge hiện tại
    // =========================
    let currentJudgeStatus = String(
        row[STATE.judge_id] || ''
    ).trim().toLowerCase();

    if(currentJudgeStatus){
        judgeStatus = currentJudgeStatus;
    }

    let isPoomsaeReady = readyText.includes('POOMSAE READY');

    let readyLines = readyText
        .replace('Waiting Start Time...', '')
        .replaceAll('\n', '<br>');

    let info = `
        <div class="ready-info">
            ${isPoomsaeReady ? readyLines + '<br>' : readyLines + '<br><br>'}
            ${row.Match || ''} | ${row.Phase || ''}<br>
            ${row.Division || ''}
        </div>
    `;

    let body = '';

    function dimStyle(active){
        if(active){
            return '';
        }

        return `
            filter:grayscale(1);
            opacity:.34;
            border-color:rgba(255,255,255,.12)!important;
        `;
    }

    function textDimStyle(active, color){
        if(active){
            return `color:${color}`;
        }

        return `
            color:rgba(255,255,255,.42);
            text-shadow:none;
        `;
    }

    // =========================
    // RECOGNIZED ONE BY ONE
    // Pair / Team: Blue trước, Red sau
    // =========================
    let blueActive = true;
    let redActive = true;

    if(isObo && !isCut){
        if(
            judgeStatus.includes('blue 1 done') ||
            judgeStatus.includes('blue 2 done')
        ){
            blueActive = false;
            redActive = true;
        }else{
            blueActive = true;
            redActive = false;
        }
    }

    if(isCut){
        body = `
        <div class="ready-body cutoff">
            <div class="ready-team cutoff-one">
                <div class="ready-team-top">
                    ${flag(row['NOC Blue'])}
                    <div class="ready-noc" style="color:#ffd447">${row['NOC Blue'] || ''}</div>
                </div>
                <div class="ready-athlete">${row['Athlete Blue'] || ''}</div>
            </div>
        </div>`;
    }else{
        body = `
        <div class="ready-body single">
            <div class="ready-team blue" style="${dimStyle(blueActive)}">
                <div class="ready-team-top">
                    ${flag(row['NOC Blue'])}
                    <div class="ready-noc" style="${textDimStyle(blueActive, '#5ab5ff')}">
                        ${row['NOC Blue'] || ''}
                    </div>
                </div>

                <div class="ready-athlete" style="${textDimStyle(blueActive, '#5ab5ff')}">
                    ${row['Athlete Blue'] || ''}
                </div>
            </div>

            <div class="ready-team red" style="${dimStyle(redActive)}">
                <div class="ready-team-top">
                    <div class="ready-noc" style="${textDimStyle(redActive, '#ff7878')}">
                        ${row['NOC Red'] || ''}
                    </div>
                    ${flag(row['NOC Red'])}
                </div>

                <div class="ready-athlete" style="${textDimStyle(redActive, '#ff7878')}">
                    ${row['Athlete Red'] || ''}
                </div>
            </div>
        </div>`;
    }

    document.getElementById('appRoot').innerHTML = `
    <div class="ready-page">
        <div>
            <div class="ready-title" style="
                margin-bottom:clamp(8px,2vh,18px);
            ">
                POOMSAE SCORING SYSTEM
            </div>
            ${info}
        </div>
        ${body}
        ${readyText.includes('Waiting Start Time') ? `
            <div class="waiting-glass">
                WAITING TIME...
                <span>Please wait for Start</span>
            </div>
        ` : ``}
    </div>`;
}
function header(row,title,total=''){return `<div class="score-top"><div class="top-side blue-bg"><div style="display:flex;gap:12px;align-items:center">${flag(row['NOC Blue'])}<div class="noc" style="font-size:36px;color:#5ab5ff">${row['NOC Blue']||''}</div></div><div class="athlete" style="text-align:left;color:#5ab5ff">${row['Athlete Blue']||''}</div></div><div class="center-info"><div class="division">${title||row.Division||''}</div><div class="timer" id="timer" style="color:${STATE.timerColor}">${STATE.timerText}</div>
<div class="match-line">${row.Match||''} - ${row.Phase||''}</div><div class="poomsae-box">Poomsae&nbsp; [ ${STATE.ready.poomsae||''} ]</div></div><div class="top-side" style="align-items:center;justify-content:center"><div style="font-size:36px;font-weight:900">${total}</div><div style="font-size:24px;color:#00ff75;font-weight:900">${STATE.judge_id}</div></div></div>`}
function s(){return STATE.scores}
let CURRENT_SLIDER_KEY = null;
let CURRENT_SLIDER_RENDER = null;

function openScoreSlider(title,key,renderName){
    CURRENT_SLIDER_KEY = key;
    CURRENT_SLIDER_RENDER = renderName;

    const popup = document.getElementById('sliderPopup');
    const titleEl = document.getElementById('sliderPopupTitle');
    const valueEl = document.getElementById('sliderPopupValue');
    const rangeEl = document.getElementById('sliderPopupRange');

    titleEl.innerText = title;
    rangeEl.value = s()[key];
    valueEl.innerText = Number(rangeEl.value).toFixed(1);

    rangeEl.oninput = function(){
        valueEl.innerText = Number(this.value).toFixed(1);
    };

    rangeEl.onchange = function(){
        saveScoreSlider();
    };

    rangeEl.onpointerup = function(){
        saveScoreSlider();
    };

    rangeEl.ontouchend = function(){
        saveScoreSlider();
    };

    popup.style.display = 'flex';
}

function closeScoreSlider(){
    document.getElementById('sliderPopup').style.display = 'none';
    CURRENT_SLIDER_KEY = null;
    CURRENT_SLIDER_RENDER = null;
}

function saveScoreSlider(){
    if(!CURRENT_SLIDER_KEY) return;

    const rangeEl = document.getElementById('sliderPopupRange');
    s()[CURRENT_SLIDER_KEY] = Math.round(Number(rangeEl.value) * 10) / 10;
    saveScoreDraft();

    closeScoreSlider();

    if(CURRENT_SLIDER_RENDER === 'cutoff'){
        renderCutoff(false);
    }else{
        renderScoring(false);
    }
}
function setVal(k,v){s()[k]=Math.max(0,Math.round(v*10)/10); renderScoring(false)}
function inc(k){s()[k]++; if(k==='b03')s().bt=Math.max(0,Math.round((s().bt-.3)*10)/10); if(k==='b01')s().bt=Math.max(0,Math.round((s().bt-.1)*10)/10); if(k==='r03')s().rt=Math.max(0,Math.round((s().rt-.3)*10)/10); if(k==='r01')s().rt=Math.max(0,Math.round((s().rt-.1)*10)/10); if(k==='c03')s().ct=Math.max(0,Math.round((s().ct-.3)*10)/10); if(k==='c01')s().ct=Math.max(0,Math.round((s().ct-.1)*10)/10);saveScoreDraft(); renderScoring(false)}
function preSlider(title,bkey,rkey){
    let obo = (STATE.screen === 'recognized_obo');

    return `
    <div class="pre-row">
        <button class="pre-btn blue-side-control"
            onclick="${obo ? "lockSide('blue'); " : ""}openScoreSlider('${title} BLUE','${bkey}','recognized')">
            ${s()[bkey].toFixed(1)}
        </button>

        <div class="pre-label">${title}</div>

        <button class="pre-btn red red-side-control"
            onclick="${obo ? "lockSide('red'); " : ""}openScoreSlider('${title} RED','${rkey}','recognized')">
            ${s()[rkey].toFixed(1)}
        </button>
    </div>`;
}
function lockSide(side){
    if(side === 'blue'){
        document.querySelectorAll('.red-side-control').forEach(b=>{
            b.disabled = true;
            b.classList.add('locked-control');
        });
        document.querySelectorAll('.blue-side-control').forEach(b=>{
            b.disabled = false;
            b.classList.remove('locked-control');
        });
    }

    if(side === 'red'){
        document.querySelectorAll('.blue-side-control').forEach(b=>{
            b.disabled = true;
            b.classList.add('locked-control');
        });
        document.querySelectorAll('.red-side-control').forEach(b=>{
            b.disabled = false;
            b.classList.remove('locked-control');
        });
    }
}

function askVal(k,min,max){let v=prompt('Input score '+min+' - '+max, s()[k]); if(v===null)return; v=parseFloat(v); if(isNaN(v))return; setVal(k,Math.min(max,Math.max(min,v)))}
function renderScoring(reset=true){
    if(reset){
        resetScores();
        loadScoreDraft();
    }

    const row=STATE.match;
    const screen=STATE.screen;

    if(screen==='recognized_cutoff')return renderCutoff(false);
    if(screen==='freestyle_tech')return renderFreestyleTech(reset);
    if(screen==='freestyle_pre')return renderFreestylePre(reset);
    if(screen==='demonstration')return renderDemo(reset);

    let bluePre=s().bs+s().br+s().bk;
    let redPre=s().rs+s().rr+s().rk;
    let hideSummary = (
        screen === 'recognized_obo' ||
        screen === 'recognized_sbs'
    );

    let obo = (screen === 'recognized_obo');

    document.getElementById('appRoot').innerHTML=`
    <div class="score-page">

        <div class="score-top">
            <div class="top-side blue-bg">
                <div style="display:flex;gap:12px;align-items:center">
                    ${flag(row['NOC Blue'])}
                    <div class="noc" style="color:#5ab5ff">${row['NOC Blue']||''}</div>
                </div>
                <div class="athlete" style="color:#5ab5ff">${row['Athlete Blue']||''}</div>
            </div>

            <div class="center-info">
                <div class="division">${row.Division||''}</div>
                <div class="timer" id="timer" style="color:${STATE.timerColor}">${STATE.timerText}</div>
                <div class="match-line">${row.Match||''} - ${row.Phase||''}</div>
                <div class="poomsae-box">Poomsae&nbsp; [ ${STATE.ready.poomsae||''} ]</div>
            </div>

            <div class="top-side red-bg">
                <div style="display:flex;gap:12px;align-items:center;justify-content:flex-end">
                    <div class="noc" style="color:#ff7878">${row['NOC Red']||''}</div>
                    ${flag(row['NOC Red'])}
                </div>
                <div class="athlete" style="color:#ff7878;text-align:right">${row['Athlete Red']||''}</div>
            </div>
        </div>

        <div class="score-bottom">
            <div class="side-score blue-bg">
                <button class="deduct blue-side-control" onclick="lockSide('blue'); inc('b03')">0.3</button>
                <div class="count">${s().b03}</div>
                <button class="deduct blue-side-control" onclick="lockSide('blue'); inc('b01')">0.1</button>
                <div class="count">${s().b01}</div>
            </div>

            <div class="mid-score">
                ${!hideSummary ? `
                <div class="score-summary">
                    <div class="score-summary-card">
                        <div class="score-summary-num">${s().bt.toFixed(1)}</div>
                        <div class="score-summary-label">TECHNICAL</div>
                    </div>

                    <div class="score-summary-card">
                        <div class="score-summary-num">${bluePre.toFixed(1)}</div>
                        <div class="score-summary-label">PRESENTATION</div>
                    </div>
                </div>
                ` : ``}

                <div class="tech-total-row">
                    <div class="tech-total blue-tech">
                        ${s().bt.toFixed(1)}
                    </div>

                    <div class="tech-total-title">
                        TECHNICAL
                    </div>

                    <div class="tech-total red-tech">
                        ${s().rt.toFixed(1)}
                    </div>
                </div>

                ${preSlider('Speed&Power','bs','rs')}
                ${preSlider('Rhythm','br','rr')}
                ${preSlider('Ki','bk','rk')}

                ${obo
                    ? `<div class="send-row">
                            <button class="send send-blue blue-side-control" onclick="sendRecognized('blue')">SEND<br>BLUE</button>
                            <button class="send send-red red-side-control" onclick="sendRecognized('red')">SEND<br>RED</button>
                       </div>`
                    : `<button class="send" onclick="sendRecognized('both')">SEND</button>`
                }

                <div style="text-align:center;color:#00ff75;font-weight:900">${STATE.judge_id}</div>
            </div>

            <div class="side-score red-bg">
                <button class="deduct red red-side-control" onclick="lockSide('red'); inc('r03')">0.3</button>
                <div class="count">${s().r03}</div>
                <button class="deduct red red-side-control" onclick="lockSide('red'); inc('r01')">0.1</button>
                <div class="count">${s().r01}</div>
            </div>
        </div>
    </div>`;
    if(obo){
        const st = (STATE.judge_status || '').toLowerCase();

        if(st.includes('blue 1 done') || st.includes('blue 2 done')){
            lockSide('red');
        }else{
            lockSide('blue');
        }
    }
    pollTime();
}
function cutoffSlider(title,key){
    return `
    <div class="pre-row cutoff">
        <button class="pre-btn" onclick="openScoreSlider('${title}','${key}','cutoff')">${s()[key].toFixed(1)}</button>
        <div class="pre-label">${title}</div>
    </div>`;
}
function renderCutoff(reset=true){
    if(reset){
        resetScores();
        loadScoreDraft();
    }

    const row=STATE.match;
    let pre=s().cs+s().cr+s().ck;

    document.getElementById('appRoot').innerHTML=`
    <div class="score-page">
        ${header(row,row.Division||'')}

        <div class="score-bottom">
            <div class="side-score">
                <button class="deduct" style="height:210px;background:#0b3860" onclick="inc('c03')">0.3</button>
                <div class="count">${s().c03}</div>
            </div>

            <div class="mid-score">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
                    <div class="score-card" style="background:#111">${s().ct.toFixed(1)}\nTECHNICAL</div>
                    <div class="score-card" style="background:#111">${pre.toFixed(1)}\nPRESENTATION</div>
                </div>

                ${cutoffSlider('Speed&Power','cs')}
                ${cutoffSlider('Rhythm','cr')}
                ${cutoffSlider('Ki','ck')}

                <button class="send" onclick="sendCutoff()">SEND</button>
                <div style="text-align:center;color:#00ff75;font-weight:900">${STATE.judge_id}</div>
            </div>

            <div class="side-score">
                <button class="deduct" style="height:210px;background:#0b3860" onclick="inc('c01')">0.1</button>
                <div class="count">${s().c01}</div>
            </div>
        </div>
    </div>`;

    pollTime();
}
function scoreButtons(group,item){
    let html='';
    for(let i=1;i<=10;i++){
        html+=`
        <button class="num-btn ${(group[item]===i)?'selected':''}"
            onclick="${group===STATE.fsTech?'setFsTech':'setFsPre'}('${item}',${i})">
            ${i}
        </button>`;
    }
    return html;
}
function renderFreestyleTech(reset=true){
    if(reset){
        STATE.fsTech={
            'Jumping Side Kick':0,
            'Multiple Kick':0,
            'Spining Kick':0,
            'Consecutive Kick':0,
            'Acrobatic Kick':0,
            'Basic Movement':0
        };
        loadScoreDraft();
    }

    let total=Object.values(STATE.fsTech).reduce((a,b)=>a+b,0);
    const row=STATE.match;

    let rows=Object.keys(STATE.fsTech).map(k=>`
        <div class="fs-score-row">
            <div class="fs-score-label">${k}</div>
            <div class="fs-button-grid">
                ${scoreButtons(STATE.fsTech,k)}
            </div>
        </div>
    `).join('');

    document.getElementById('appRoot').innerHTML=`
    <div class="score-page">
        ${header(row,'FREESTYLE TECHNICAL','TOTAL: '+total)}

        <div class="fs-mobile-layout">
            <div class="fs-header-row">
                <div class="fs-main-title">TECHNICAL SCORING</div>
                <button class="send fs-send" onclick="sendFsTech()">SEND</button>
            </div>

            <div class="fs-score-list">
                ${rows}
            </div>
        </div>
    </div>`;

    pollTime();
}
function setFsTech(k,v){
    STATE.fsTech[k]=v;
    saveScoreDraft();
    renderFreestyleTech(false);
}
function renderFreestylePre(reset=true){
    if(reset){
        STATE.fsPre={
            'Creativeness':0,
            'Harmony':0,
            'Expression Of Energy':0,
            'Music & Choreography':0
        };
        loadScoreDraft();
    }

    let total=Object.values(STATE.fsPre).reduce((a,b)=>a+b,0);
    const row=STATE.match;

    let rows=Object.keys(STATE.fsPre).map(k=>`
        <div class="fs-score-row fs-pre-row">
            <div class="fs-score-label">${k}</div>
            <div class="fs-button-grid">
                ${scoreButtons(STATE.fsPre,k)}
            </div>
        </div>
    `).join('');

    document.getElementById('appRoot').innerHTML=`
    <div class="score-page">
        ${header(row,'FREESTYLE PRESENTATION','TOTAL: '+total)}

        <div class="fs-mobile-layout">
            <div class="fs-header-row">
                <div class="fs-main-title">PRESENTATION SCORING</div>
                <button class="send fs-send" onclick="sendFsPre()">SEND</button>
            </div>

            <div class="fs-score-list fs-pre-list">
                ${rows}
            </div>
        </div>
    </div>`;

    pollTime();
}
function setFsPre(k,v){
    STATE.fsPre[k]=v;
    saveScoreDraft();
    renderFreestylePre(false);
}
function renderDemo(reset=true){
    if(reset){
        resetScores();
        loadScoreDraft();
    }

    let totalDemo = Object.values(s().demo).reduce((a,b)=>a+b,0);
    let ded = s().ded['-0.1']*.1 + s().ded['-0.3']*.3 + s().ded['-0.5']*.5;
    let total = Math.max(0, Math.round((totalDemo-ded)*10)/10);

    const row = STATE.match;

    function demoSliderRow(title,key,maxScore){
        const valueId = `demo_value_${key.replace(/[^a-zA-Z0-9]/g,'_')}`;

        return `
        <div class="demo-score-row">
            <div class="demo-score-title">${title}</div>

            <div id="${valueId}" class="demo-score-value">
                ${Number(s().demo[key]).toFixed(1)}
            </div>

            <input class="demo-score-slider"
                type="range"
                min="0"
                max="${maxScore}"
                step="0.01"
                value="${s().demo[key]}"

                oninput="
                    document.getElementById('${valueId}').innerText = Number(this.value).toFixed(1);
                "

                onchange="
                    s().demo['${key}'] = Math.round(parseFloat(this.value)*10)/10;
                    saveScoreDraft();
                    renderDemo(false);
                "

                onpointerup="
                    s().demo['${key}'] = Math.round(parseFloat(this.value)*10)/10;
                    saveScoreDraft();
                    renderDemo(false);
                "

                ontouchend="
                    s().demo['${key}'] = Math.round(parseFloat(this.value)*10)/10;
                    saveScoreDraft();
                    renderDemo(false);
                "
            >
        </div>`;
    }

    function dedRow(key){
        return `
        <div class="demo-ded-row">
            <div class="demo-ded-label">${key}</div>

            <button class="demo-ded-btn" onclick="
                s().ded['${key}']=Math.max(0,s().ded['${key}']-1);
                saveScoreDraft();
                renderDemo(false);
            ">-</button>

            <div class="demo-ded-count">${s().ded[key]}</div>

            <button class="demo-ded-btn plus" onclick="
                s().ded['${key}']++;
                saveScoreDraft();
                renderDemo(false);
            ">+</button>
        </div>`;
    }

    document.getElementById('appRoot').innerHTML=`
    <div class="score-page">
        ${header(row,'DEMONSTRATION SCORING','TOTAL: '+total.toFixed(1))}

        <div class="demo-mobile-layout">
            <div class="demo-left">
                ${demoSliderRow('Yeonmu','Yeonmu',2)}
                ${demoSliderRow('Self-Defense','Self-Defense',2)}
                ${demoSliderRow('Breaking','Breaking',5)}
                ${demoSliderRow('Composition','Composition',1)}
            </div>

            <div class="demo-right">
                <div class="demo-ded-title">DEDUCTION</div>

                <div class="demo-ded-list">
                    ${dedRow('-0.1')}
                    ${dedRow('-0.3')}
                    ${dedRow('-0.5')}
                </div>

                <button class="send demo-send" onclick="sendDemo()">SEND</button>
            </div>
        </div>
    </div>`;

    pollTime();
}async function canSend(){let r=await api('/api/time'); return r.control==='stop'}
async function sendRecognized(side){
    if(!(await canSend())) return toast('The match not finish!','warn');

    let body = {
        side,
        screen: STATE.screen,
        ready: STATE.ready,
        scores: s()
    };

    let r = await api('/api/send_recognized',{
        method:'POST',
        body:JSON.stringify(body)
    });

    if(r.ok){
        toast('Sent Success!','ok',()=>{
            clearScoreDraft();
            STATE.screen='wait';
            pageWait();
        });
    }else{
        toast(r.error || 'Send error','warn');
    }
}

async function sendCutoff(){
    if(!(await canSend())) return toast('The match not finish!','warn');

    let r = await api('/api/send_cutoff',{
        method:'POST',
        body:JSON.stringify({
            ready: STATE.ready,
            scores: s()
        })
    });

    if(r.ok){
        toast('Sent Success!','ok',()=>{
            clearScoreDraft();
            STATE.screen='wait';
            pageWait();
        });
    }else{
        toast(r.error || 'Send error','warn');
    }
}

async function sendFsTech(){
    if(!(await canSend())) return toast('The match not finish!','warn');

    if(Object.values(STATE.fsTech).some(v=>v===0)){
        return toast('Please score all 6 fields!','warn');
    }

    STATE.freestyleTech = {
        ...STATE.fsTech,
        Tech:Object.values(STATE.fsTech).reduce((a,b)=>a+b,0)
    };

    saveScoreDraft();

    STATE.screen='freestyle_pre';
    renderFreestylePre(true);
    toast('Technical saved!','ok');
}

async function sendFsPre(){
    if(!(await canSend())) return toast('The match not finish!','warn');

    if(!STATE.freestyleTech) return toast('Technical missing!','warn');

    if(Object.values(STATE.fsPre).some(v=>v===0)){
        return toast('Please score all 4 fields!','warn');
    }

    let r = await api('/api/send_freestyle',{
        method:'POST',
        body:JSON.stringify({
            ready: STATE.ready,
            tech: STATE.freestyleTech,
            pre: STATE.fsPre
        })
    });

    if(r.ok){
        toast('Sent Success!','ok',()=>{
            clearScoreDraft();
            STATE.freestyleTech=null;
            STATE.screen='wait';
            pageWait();
        });
    }else{
        toast(r.error || 'Send error','warn');
    }
}

async function sendDemo(){
    if(!(await canSend())) return toast('The match not finish!','warn');

    let r = await api('/api/send_demo',{
        method:'POST',
        body:JSON.stringify({
            ready: STATE.ready,
            scores: s()
        })
    });

    if(r.ok){
        toast('Sent Success!','ok',()=>{
            clearScoreDraft();
            STATE.screen='wait';
            pageWait();
        });
    }else{
        toast(r.error || 'Send error','warn');
    }
}
async function pollTime(){
    if(!STATE.match) return;

    try{
        let r = await api('/api/time');
        let el = document.getElementById('timer');
        let sec = r.seconds;
        let min = r.minutes;

        if(sec < 0){
            let o = Math.abs(sec);
            STATE.timerText = '+' + String(Math.floor(o / 60)).padStart(2,'0') + ':' + String(o % 60).padStart(2,'0');
            STATE.timerColor = '#ff2a2a';
        }else{
            STATE.timerText = String(min).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
            STATE.timerColor = r.control === 'stop' ? '#00ff75' : '#ffef00';
        }

        if(el){
            el.innerText = STATE.timerText;
            el.style.color = STATE.timerColor;
        }

    }catch(e){}
}

async function poll(){
    try{
        let r = await api('/api/active_match');

        if(!r.ok){
            STATE.match = null;
            STATE.screen = 'wait';
            pageWait();
            return;
        }

        STATE.match = r.row;
        STATE.ready = r.ready;
        STATE.judge_status = r.judge_status;

        if(!r.ready.slot){
            STATE.screen = 'ready';

            // Judge đã xong bài 1, đang chờ bài 2 ready
            // Không hiện lại màn hình ready bài 1 nữa
            if((r.judge_status || '').toLowerCase() === 'finish 1'){
                pageWait(
                    'WAITING POOMSAE 2',
                    'Waiting for controller to ready Poomsae 2...'
                );
            }else{
                pageReady(r.row, r.ready.poomsae);
            }

            return;
        }

        // STOP: giữ màn hình chấm để trọng tài SEND
        if(r.control === 'stop'){
            if(
                STATE.screen === 'recognized_sbs' ||
                STATE.screen === 'recognized_obo' ||
                STATE.screen === 'recognized_cutoff' ||
                STATE.screen === 'demonstration' ||
                STATE.screen === 'freestyle_tech' ||
                STATE.screen === 'freestyle_pre'
            ){
                pollTime();
                return;
            }
        }

        // PAUSE / READY / NULL: quay về màn hình chờ
        if(r.control !== 'start'){
            STATE.screen = 'ready';
            pageReady(r.row, `POOMSAE READY\n${r.ready.poomsae}\nWaiting Start Time...`);
            return;
        }

        // Chỉ khi START mới vào màn hình chấm
        if(STATE.screen !== r.screen){
            STATE.screen = r.screen;
            renderScoring(true);
        }else{
            pollTime();
        }

    }catch(e){
        pageWait('Lỗi mạng/Supabase', String(e));
    }
}
pageWait();
setInterval(poll,3000);
setInterval(pollTime,1000);
poll();
</script>
{% endif %}
</body></html>
'''

# =========================
# ROUTES
# =========================
@app.route("/", methods=["GET"])
def index():
    return render_template_string(PAGE, judge_id=session.get("judge_id"), court_id=session.get("court_id"), range=range)


@app.route("/login", methods=["POST"])
def login():
    judge_id = request.form.get("judge_id", "Judge 1")
    court_id = request.form.get("court_id", "Court 0")
    court_no = court_id.replace("Court", "").strip()
    session["judge_id"] = judge_id
    session["court_id"] = court_id
    session["schedule_table"] = f"Schedule_court_{court_no}"
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def require_login():
    judge_id = session.get("judge_id")
    schedule_table = session.get("schedule_table")
    if not judge_id or not schedule_table:
        return None, None
    return judge_id, schedule_table


@app.route("/api/active_match")
def api_active_match():
    try:
        judge_id, schedule_table = require_login()

        if not judge_id:
            return jsonify(ok=False, error="Not logged in")

        row = get_active_match(schedule_table, judge_id)

        if not row:
            return jsonify(ok=False, error="No active match")

        judge_status = str(row.get(judge_id) or "").strip().lower()
        ready = resolve_ready(row, judge_status)
        control = str(row.get("Control time") or "").strip().lower()

        return jsonify(
            ok=True,
            row=row,
            ready=ready,
            control=control,
            screen=detect_screen(row),
            judge_status=judge_status
        )

    except Exception as e:
        return jsonify(ok=False, error=f"api_active_match error: {str(e)}")


@app.route("/api/time")
def api_time():
    try:
        judge_id, schedule_table = require_login()

        if not judge_id:
            return jsonify(ok=False, error="Not logged in")

        match_no = request.args.get("match")

        if not match_no:
            row = get_active_match(schedule_table, judge_id)
            match_no = row.get("Match") if row else ""

        if not match_no:
            return jsonify(ok=True, minutes=0, seconds=0, control="")

        minutes, seconds, control = get_match_time(schedule_table, match_no)

        return jsonify(ok=True, minutes=minutes, seconds=seconds, control=control)

    except Exception as e:
        return jsonify(ok=False, minutes=0, seconds=0, control="", error=f"api_time error: {str(e)}")


def active_context():
    judge_id, schedule_table = require_login()
    if not judge_id:
        raise RuntimeError("Not logged in")
    row = get_active_match(schedule_table, judge_id)
    if not row:
        raise RuntimeError("No active match")
    return judge_id, schedule_table, row


@app.route("/api/send_recognized", methods=["POST"])
def api_send_recognized():
    try:
        judge_id, schedule_table, info = active_context()
        payload = request.get_json(force=True)
        sc = payload.get("scores", {})
        ready = payload.get("ready", {})
        side = payload.get("side", "both")
        match = info.get("Match", "")
        selected_poomsae = ready.get("poomsae", "")
        slot = ready.get("slot", "1")
        _, _, control = get_match_time(schedule_table, match)
        if control != "stop":
            return jsonify(ok=False, error="The match not finish!")

        def send_side(color: str):
            is_blue = color == "blue"
            pre = round(float(sc.get("bs" if is_blue else "rs", 2)) + float(sc.get("br" if is_blue else "rr", 2)) + float(sc.get("bk" if is_blue else "rk", 2)), 1)
            send_judge_score({
                "Judge": judge_id,
                "Match": match,
                "NOC": info.get("NOC Blue" if is_blue else "NOC Red", ""),
                "Name": info.get("Athlete Blue" if is_blue else "Athlete Red", ""),
                "Tech -1": str(sc.get("b01" if is_blue else "r01", 0)),
                "Tech -3": str(sc.get("b03" if is_blue else "r03", 0)),
                "Speed/power": str(sc.get("bs" if is_blue else "rs", 2)),
                "Rhythm": str(sc.get("br" if is_blue else "rr", 2)),
                "KI": str(sc.get("bk" if is_blue else "rk", 2)),
                "Tech": str(round(float(sc.get("bt" if is_blue else "rt", 4)), 1)),
                "Pre": str(pre),
                "Poomsae": selected_poomsae,
            })

        if side == "blue":
            send_side("blue")
            clear_control_time(schedule_table, match)
            mark_judge_finish(schedule_table, match, judge_id, "Blue 1 Done" if slot == "1" else "Blue 2 Done")
        elif side == "red":
            send_side("red")
            mark_judge_finish(schedule_table, match, judge_id, "Finish 1" if slot == "1" else "Finish")
        else:
            send_side("blue")
            send_side("red")
            mark_judge_finish(schedule_table, match, judge_id, "Finish 1" if slot == "1" else "Finish")
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/send_cutoff", methods=["POST"])
def api_send_cutoff():
    try:
        judge_id, schedule_table, info = active_context()
        payload = request.get_json(force=True)
        sc = payload.get("scores", {})
        ready = payload.get("ready", {})
        match = info.get("Match", "")
        _, _, control = get_match_time(schedule_table, match)
        if control != "stop":
            return jsonify(ok=False, error="The match not finish!")
        pre = round(float(sc.get("cs", 2)) + float(sc.get("cr", 2)) + float(sc.get("ck", 2)), 1)
        send_judge_score({
            "Judge": judge_id,
            "Match": match,
            "Poomsae": ready.get("poomsae", ""),
            "NOC": info.get("NOC Blue", ""),
            "Name": info.get("Athlete Blue", ""),
            "Tech -1": str(sc.get("c01", 0)),
            "Tech -3": str(sc.get("c03", 0)),
            "Speed/power": str(sc.get("cs", 2)),
            "Rhythm": str(sc.get("cr", 2)),
            "KI": str(sc.get("ck", 2)),
            "Tech": str(round(float(sc.get("ct", 4)), 1)),
            "Pre": str(pre),
        })
        mark_judge_finish(schedule_table, match, judge_id, "Finish 1" if ready.get("slot") == "1" else "Finish")
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/send_freestyle", methods=["POST"])
def api_send_freestyle():
    try:
        judge_id, schedule_table, info = active_context()
        payload = request.get_json(force=True)
        tech = payload.get("tech", {})
        pre = payload.get("pre", {})
        ready = payload.get("ready", {})
        match = info.get("Match", "")
        _, _, control = get_match_time(schedule_table, match)
        if control != "stop":
            return jsonify(ok=False, error="The match not finish!")
        data = {
            "Judge": judge_id,
            "Match": match,
            "Poomsae": "1 - Free",
            "NOC": info.get("NOC Blue", ""),
            "Name": info.get("Athlete Blue", ""),
            "Jumping Side Kick": str(tech.get("Jumping Side Kick", 0)),
            "Multiple Kick": str(tech.get("Multiple Kick", 0)),
            "Spining Kick": str(tech.get("Spining Kick", 0)),
            "Consecutive Kick": str(tech.get("Consecutive Kick", 0)),
            "Acrobatic Kick": str(tech.get("Acrobatic Kick", 0)),
            "Basic Movement": str(tech.get("Basic Movement", 0)),
            "Tech": str(tech.get("Tech", 0)),
            "Creativeness": str(pre.get("Creativeness", 0)),
            "Harmony": str(pre.get("Harmony", 0)),
            "Expression Of Energy": str(pre.get("Expression Of Energy", 0)),
            "Music & Choreography": str(pre.get("Music & Choreography", 0)),
            "Pre": str(sum(int(v) for v in pre.values())),
        }
        send_judge_score(data)
        mark_judge_finish(schedule_table, match, judge_id, "Finish")
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/send_demo", methods=["POST"])
def api_send_demo():
    try:
        judge_id, schedule_table, info = active_context()
        payload = request.get_json(force=True)
        sc = payload.get("scores", {})
        demo = sc.get("demo", {})
        ded = sc.get("ded", {})
        ready = payload.get("ready", {})
        match = info.get("Match", "")
        _, _, control = get_match_time(schedule_table, match)
        if control != "stop":
            return jsonify(ok=False, error="The match not finish!")
        deduction = round(float(ded.get("-0.1", 0)) * 0.1 + float(ded.get("-0.3", 0)) * 0.3 + float(ded.get("-0.5", 0)) * 0.5, 1)
        final_total = round(max(0, sum(float(v) for v in demo.values()) - deduction), 1)
        send_judge_score({
            "Judge": judge_id,
            "Match": match,
            "Poomsae": "1 - Demon",
            "NOC": info.get("NOC Blue", ""),
            "Name": info.get("Athlete Blue", ""),
            "Yeonmu": str(demo.get("Yeonmu", 2)),
            "Self-Defense": str(demo.get("Self-Defense", 2)),
            "Breaking": str(demo.get("Breaking", 5)),
            "Composition": str(demo.get("Composition", 1)),
            "Deduction": str(deduction),
            "Tech": str(final_total),
            "Pre": "0",
        })
        mark_judge_finish(schedule_table, match, judge_id, "Finish")
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/flags/<path:filename>')
def serve_flag(filename):
    return send_from_directory('flags', filename)

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Poomsae Scoring System",
        "short_name": "Poomsae",
        "start_url": "/",
        "display": "fullscreen",
        "background_color": "#02040a",
        "theme_color": "#02040a",
        "orientation": "landscape"
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )

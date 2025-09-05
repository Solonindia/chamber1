import re, csv, json
from datetime import timedelta, datetime

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.timezone import make_aware, is_naive
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from .models import Chamber1Data, Chamber2Data, Chamber3Data, ChamberAccess

# ---------------- Chamber mapping ----------------

# views_admin.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from .models import ChamberAccess

MODEL_BY_CH = {
    "ch1": Chamber1Data,
    "ch2": Chamber2Data,
    "ch3": Chamber3Data,
}

# ---------------- Access check ----------------
def _user_has_access(user, ch):
    if user.is_superuser:
        return True
    return ChamberAccess.objects.filter(user=user, chamber=ch).exists()

# ---------------- Helpers ----------------
def _parse_span(s: str) -> timedelta:
    s = (s or "1m").strip().lower()
    m = re.fullmatch(r"(\d+)\s*([mh])", s)
    if not m:
        return timedelta(minutes=1)
    qty, unit = int(m.group(1)), m.group(2)
    return timedelta(hours=max(1, min(12, qty))) if unit == "h" else timedelta(minutes=max(1, min(720, qty)))

from django.utils.timezone import make_aware, is_naive
from datetime import datetime

def _floor_minute(dt):
    return dt.replace(second=0, microsecond=0)

def _select_rows_actual(qs, step):
    """
    Walk through queryset (ordered by created_at).
    Only include real rows, spaced at least `step` apart.
    """
    rows = []
    last_dt = None
    IST = timezone.get_current_timezone()

    for r in qs:
        dt = timezone.localtime(r.created_at, IST)
        if last_dt is None or dt >= last_dt + step:
            rows.append({
                "date": dt.date().isoformat(),
                "time": dt.strftime("%H:%M:%S"),
                "temperature": r.temperature,
                "pressure": r.pressure,
                "humidity": r.humidity,
                "co2": r.co2,
            })
            last_dt = dt
    return rows

def _select_rows_by_step(qs, start_dt, end_dt, step):
    """
    qs: queryset ordered by created_at ASC (from a single chamber's table)
    step: timedelta (1m, 5m, 30m ...)

    - If multiple rows exist within the same minute, pick the **last** one.
    - Walk at 'step' cadence starting from start minute.
    """
    tz = timezone.get_current_timezone()

    # Build "latest per minute" map
    per_minute = {}
    for r in qs.order_by("created_at"):
        loc = timezone.localtime(r.created_at, tz)
        # round DOWN to minute
        slot = loc.replace(second=0, microsecond=0)
        if slot not in per_minute:
            per_minute[slot] = r   # keep first row of that minute

    # Walk aligned to start
    selected = []
    slot = _floor_minute(timezone.localtime(start_dt, tz))
    end_local = timezone.localtime(end_dt, tz)
    while slot <= end_local:
        if slot in per_minute:
            selected.append(per_minute[slot])
        slot += step
    return selected

# ---------------- Page routes ----------------
def redirect_to_ch1(request):
    return redirect("sensor_data_page", ch="ch1")

@login_required
def chambers_home(request):
    if request.user.is_superuser:
        allowed = ["ch1", "ch2", "ch3"]
    else:
        allowed = list(
            ChamberAccess.objects.filter(user=request.user).values_list("chamber", flat=True)
        )
    return render(request, "chambers_home.html", {"allowed": allowed})

@login_required
def minute_table(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse({"error": "Access denied"}, status=403)

    # build allowed list for the navbar
    if request.user.is_superuser:
        allowed = ["ch1", "ch2", "ch3"]
    else:
        allowed = list(
            ChamberAccess.objects.filter(user=request.user).values_list("chamber", flat=True)
        )

    return render(request, "dashboard.html", {"chamber": ch, "allowed": allowed})


@login_required
def chart_page(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse({"error": "Access denied"}, status=403)

    if request.user.is_superuser:
        allowed = ["ch1", "ch2", "ch3"]
    else:
        allowed = list(
            ChamberAccess.objects.filter(user=request.user).values_list("chamber", flat=True)
        )

    return render(request, "chart.html", {"chamber": ch, "allowed": allowed})


# ---------------- Table API ----------------
@login_required
def range_rows(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse([], safe=False)

    Model = MODEL_BY_CH[ch]
    every = request.GET.get("every", "1m")
    step = _parse_span(every)

    qs = Model.objects.order_by("created_at")
    if not qs.exists():
        return JsonResponse([], safe=False)

    rows = []
    last_dt = None

    for r in qs:
        dt = timezone.make_aware(datetime.combine(r.date, r.time))
        # always take the first row, then take a new one only if >= step later
        if last_dt is None or dt >= last_dt + step:
            rows.append({
                "date": r.date.isoformat(),
                "time": r.time.strftime("%H:%M"),
                "temperature": r.temperature,
                "pressure": r.pressure,
                "humidity": r.humidity,
                "co2": r.co2,
            })
            last_dt = dt

    return JsonResponse(rows, safe=False)

# ---------------- Chart data API ----------------
@login_required
@csrf_exempt
def chart_data(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse({"labels": [], "temperature": [], "pressure": [], "humidity": [], "co2": []}, status=403)

    Model = MODEL_BY_CH[ch]
    qs = Model.objects.order_by("created_at")  # oldest → newest
    data = {
        "labels": [f"{r.date} {r.time.strftime('%H:%M')}" for r in qs],
        "temperature": [r.temperature for r in qs],
        "pressure": [r.pressure for r in qs],
        "humidity": [r.humidity for r in qs],
        "co2": [r.co2 for r in qs],
    }
    return JsonResponse(data)

# ---------------- Ingest (device POST) ----------------
from json import JSONDecodeError

@csrf_exempt
def ingest_sensor_data(request, ch):
    """Device endpoint (NO login required)."""
    if ch not in MODEL_BY_CH:
        return JsonResponse({"error": "Invalid chamber"}, status=400)
    Model = MODEL_BY_CH[ch]

    if request.method == "GET":
        last = Model.objects.order_by("-created_at").first()
        return JsonResponse({
            "ok": True,
            "chamber": ch,
            "expect_json_fields": ["temperature", "pressure", "humidity", "co2"],
            "hint": "POST JSON to this URL with Content-Type: application/json",
            "last": None if not last else {
                "id": last.id,
                "date": last.date.isoformat(),
                "time": last.time.strftime("%H:%M:%S"),
                "temperature": last.temperature,
                "pressure": last.pressure,
                "humidity": last.humidity,
                "co2": last.co2,
                "created_at": timezone.localtime(last.created_at).isoformat(timespec="seconds"),
            },
        })

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ctype = (request.META.get("CONTENT_TYPE") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        return JsonResponse({"error": "Content-Type must be application/json"}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    required = ["temperature", "pressure", "humidity", "co2"]
    missing = [f for f in required if f not in payload]
    if missing:
        return JsonResponse({"error": f"Missing fields: {', '.join(missing)}"}, status=400)

    row = Model.objects.create(
        temperature=float(payload["temperature"]),
        pressure=float(payload["pressure"]),
        humidity=float(payload["humidity"]),
        co2=float(payload["co2"]),
    )

    return JsonResponse({
        "status": "ok",
        "chamber": ch,
        "id": row.id,
        "date": row.date.isoformat(),
        "time": row.time.strftime("%H:%M:%S"),
        "created_at": timezone.localtime(row.created_at).isoformat(timespec="seconds"),
    }, status=201)

import csv
from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# ======= DEBUG SWITCH =======
DEBUG_DL = True
def dbg(*args, **kwargs):
    if DEBUG_DL:
        print("[DLDEBUG]", *args, **kwargs)

# ---------- Parse span helper ----------
def _parse_span(every: str) -> timedelta:
    if not every:
        return timedelta(minutes=1)
    every = every.strip().lower()
    if every.endswith("m"):
        val = int(every[:-1] or 1)
        step = timedelta(minutes=val)
    elif every.endswith("h"):
        val = int(every[:-1] or 1)
        step = timedelta(hours=val)
    else:
        step = timedelta(minutes=1)
    dbg("step parsed from 'every':", every, "=>", step)
    return step

# ---------- Parse frontend datetime ----------
def parse_local(dt_str: str):
    """
    Parse frontend datetime string into naive datetime (IST already).
    DO NOT shift here; DB date+time are also local/naive.
    """
    dbg("parse_local IN:", dt_str)
    if not dt_str:
        return None
    out = None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            out = datetime.strptime(dt_str.strip(), fmt)
            break
        except ValueError:
            continue
    dbg("parse_local OUT:", out)
    return out

# ---------- Query helper ----------
from django.utils import timezone
import pytz

IST = pytz.timezone("Asia/Kolkata")

def _query_range(Model, start_dt, end_dt):
    """
    Query using created_at (stored in UTC).
    Convert frontend IST datetimes → UTC aware.
    """
    # Mark frontend inputs as IST
    if timezone.is_naive(start_dt):
        start_dt = IST.localize(start_dt)
    if timezone.is_naive(end_dt):
        end_dt = IST.localize(end_dt)

    # Convert IST → UTC
    start_dt = start_dt.astimezone(pytz.UTC)
    end_dt = end_dt.astimezone(pytz.UTC)

    return Model.objects.filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt
    ).order_by("created_at")

# ---------- CSV Export ----------
@login_required
def download_csv(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse({"error": "Access denied"}, status=403)

    Model = MODEL_BY_CH[ch]
    dbg("CSV REQUEST chamber:", ch, "GET:", request.GET.dict())

    start, end, every = request.GET.get("start"), request.GET.get("end"), request.GET.get("every", "1m")
    if not start or not end:
        return JsonResponse({"error": "Start and End datetime required"}, status=400)

    start_dt, end_dt = parse_local(start), parse_local(end)
    if not start_dt or not end_dt:
        return JsonResponse({"error": "Invalid datetime format"}, status=400)

    # include whole last minute
    end_dt = end_dt.replace(second=59, microsecond=999999)
    step = _parse_span(every)
    dbg("CSV window:", start_dt, "→", end_dt, "| step:", step)

    qs = _query_range(Model, start_dt, end_dt)
    if not qs.exists():
        dbg("CSV: NO DATA in this window")
        return JsonResponse({"error": "No data available"}, status=404)

    rows = _select_rows_actual(qs, step)


    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="Chamber_{ch}_{start_dt.date()}_{end_dt.date()}_{every}.csv"'
    )
    response.write("\ufeff")  # BOM for Excel

    writer = csv.writer(response)
    writer.writerow(["Date", "Time", "Temperature (°C)", "Temperature1 (°C)", "Humidity (%)", "Humidity1 (%)"])
    for r in rows:
        writer.writerow([
            r["date"], r["time"],
            "" if r["temperature"]  is None else f'{r["temperature"]:.2f}',
            "" if r["pressure"] is None else f'{r["pressure"]:.2f}',
            "" if r["humidity"]     is None else f'{r["humidity"]:.2f}',
            "" if r["co2"]    is None else f'{r["co2"]:.2f}',
        ])
    dbg("CSV: wrote", len(rows), "rows")
    return response

# ---------- PDF Export ----------
@login_required
def download_pdf(request, ch):
    if ch not in MODEL_BY_CH or not _user_has_access(request.user, ch):
        return JsonResponse({"error": "Access denied"}, status=403)

    Model = MODEL_BY_CH[ch]
    dbg("PDF REQUEST chamber:", ch, "GET:", request.GET.dict())

    start, end, every = request.GET.get("start"), request.GET.get("end"), request.GET.get("every", "1m")
    if not start or not end:
        return JsonResponse({"error": "Start and End datetime required"}, status=400)

    start_dt, end_dt = parse_local(start), parse_local(end)
    if not start_dt or not end_dt:
        return JsonResponse({"error": "Invalid datetime format"}, status=400)

    end_dt = end_dt.replace(second=59, microsecond=999999)
    step = _parse_span(every)
    dbg("PDF window:", start_dt, "→", end_dt, "| step:", step)

    qs = _query_range(Model, start_dt, end_dt)
    if not qs.exists():
        dbg("PDF: NO DATA in this window")
        return JsonResponse({"error": "No data available"}, status=404)

    rows = _select_rows_actual(qs, step)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Chamber_{ch}_{start_dt.date()}_{end_dt.date()}_{every}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                            rightMargin=18, leftMargin=18, topMargin=24, bottomMargin=18)
    styles = getSampleStyleSheet()
    title = Paragraph(f"Chamber {ch.upper()} — Sensor Data (every {every})", styles["Heading3"])

    data = [["Date", "Time", "Temperature (°C)", "Temperature1 (°C)", "Humidity (%)", "Humidity1 (%)"]]
    for r in rows:
        data.append([
            r["date"], r["time"],
            "" if r["temperature"]  is None else f'{r["temperature"]:.2f}',
            "" if r["pressure"] is None else f'{r["pressure"]:.2f}',
            "" if r["humidity"]     is None else f'{r["humidity"]:.2f}',
            "" if r["co2"]    is None else f'{r["co2"]:.2f}',
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.HexColor("#111827")),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0), 10),
        ("FONTSIZE",   (0,1), (-1,-1), 9),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#111111")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7fafc")]),
    ]))
    doc.build([title, Spacer(1, 8), table])
    dbg("PDF: wrote", len(rows), "rows")
    return response

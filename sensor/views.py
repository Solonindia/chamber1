import re, random
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from .models import MinuteReading
from datetime import datetime


RANGES = {
    "temperature": (18.0, 30.0),
    "humidity":    (35.0, 70.0),
    "pressure":    (990.0, 1020.0),
    "co2":         (420.0, 1200.0),
}
def _rand(lo, hi, nd=2): return round(random.uniform(lo, hi), nd)

def _parse_span(s: str) -> timedelta:
    s = (s or '1m').strip().lower()
    m = re.fullmatch(r'(\d+)\s*([mh])', s)
    if not m: return timedelta(minutes=1)
    qty, unit = int(m.group(1)), m.group(2)
    if unit == 'h': return timedelta(hours=max(1, min(12, qty)))
    return timedelta(minutes=max(1, min(720, qty)))

def _ensure_current_minute_reading(chamber="Chamber A"):
    now = timezone.localtime()
    slot = now.replace(second=0, microsecond=0)
    d, t = slot.date(), slot.time()
    obj, _ = MinuteReading.objects.get_or_create(
        chamber=chamber, date=d, time=t,
        defaults={
            "temperature": _rand(*RANGES["temperature"]),
            "humidity":    _rand(*RANGES["humidity"]),
            "pressure":    _rand(*RANGES["pressure"]),
            "co2":         _rand(*RANGES["co2"], nd=0),
        }
    )
    return obj

def minute_table(request):
    return render(request, "dashboard.html")

def range_rows(request):
    every = request.GET.get('every', '1m')
    step = _parse_span(every)
    minutes = int(step.total_seconds() // 60)  # step size

    # make sure current row exists
    _ensure_current_minute_reading()

    # fetch all rows oldest → newest
    qs = MinuteReading.objects.filter(chamber="Chamber A").order_by('date', 'time')

    kept = []
    seen_slots = set()

    if not qs.exists():
        return JsonResponse([], safe=False)

    # take the first record as the starting point
    first_row = qs.first()
    slot_dt = timezone.make_aware(
        timezone.datetime.combine(first_row.date, first_row.time)
    )

    # build a dict for quick lookup
    readings = {(r.date, r.time): r for r in qs}

    # step forward until the latest record
    last_row = qs.last()
    last_dt = timezone.make_aware(
        timezone.datetime.combine(last_row.date, last_row.time)
    )

    while slot_dt <= last_dt:
        sig = (slot_dt.date(), slot_dt.time())
        if sig in readings and sig not in seen_slots:
            r = readings[sig]
            kept.append({
                "date": r.date.isoformat(),
                "time": r.time.strftime("%H:%M"),
                "temperature": r.temperature,
                "humidity": r.humidity,
                "pressure": r.pressure,
                "co2": r.co2,
            })
            seen_slots.add(sig)
        slot_dt += step

    # 🔽 reverse list before returning → newest at top
    kept.reverse()

    return JsonResponse(kept, safe=False)

from django.http import JsonResponse, HttpResponse
from django.utils.timezone import make_aware, is_naive
from datetime import datetime
import csv

def parse_local(dt_str):
    """Accepts YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS"""
    try:
        # Try with seconds
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            # Fallback without seconds
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            return None

    # Make timezone-aware if needed
    if is_naive(dt):
        dt = make_aware(dt)
    return dt

def download_csv(request):
    start = request.GET.get("start")
    end   = request.GET.get("end")

    if not start or not end:
        return JsonResponse({"error": "Start and End datetime required"}, status=400)

    start_dt = parse_local(start)
    end_dt   = parse_local(end)

    if not start_dt or not end_dt:
        return JsonResponse({"error": "Data for the specified period is unavailable"}, status=400)

    # Expand end to include the full minute
    end_dt = end_dt.replace(second=59, microsecond=999999)

    # Query data
    rows = MinuteReading.objects.filter(
        chamber="Chamber A",
        created_at__gte=start_dt,
        created_at__lte=end_dt
    ).order_by("created_at")

    if not rows.exists():
        return JsonResponse({"error": "No data available for that period"}, status=404)

    # Generate CSV
    response = HttpResponse(content_type="text/csv")
    response['Content-Disposition'] = (
        f'attachment; filename="Chamber1_{start_dt.date()}_{end_dt.date()}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(["Date", "Time", "Temperature (°C)", "Humidity (%)", "Pressure (hPa)", "CO2 (ppm)"])

    for r in rows:
        writer.writerow([r.date, r.time, r.temperature, r.humidity, r.pressure, r.co2])

    return response


from django.views.decorators.csrf import csrf_exempt

def chart_page(request):
    return render(request, "chart.html")

@csrf_exempt
def chart_data(request):
    # fetch last N records (say 200) sorted oldest → newest
    qs = MinuteReading.objects.filter(chamber="Chamber A").order_by("created_at")[:200]

    data = {
        "labels": [f"{r.date} {r.time.strftime('%H:%M')}" for r in qs],
        "temperature": [r.temperature for r in qs],
        "humidity": [r.humidity for r in qs],
        "pressure": [r.pressure for r in qs],
        "co2": [r.co2 for r in qs],
    }
    return JsonResponse(data)
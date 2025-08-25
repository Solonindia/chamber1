from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import SensorData

@csrf_exempt
def sensor_data(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            SensorData.objects.create(
                temperature=data.get("temperature"),
                humidity=data.get("humidity")
            )
            return JsonResponse({"status": "success"}, status=201)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"message": "Only POST allowed"}, status=405)


import json
from django.shortcuts import render
from .models import SensorData

def dashboard(request):
    data = SensorData.objects.order_by("created_at")
    temps = [d.temperature for d in data]
    hums = [d.humidity for d in data]
    # include both date and time
    times = [d.created_at.strftime("%Y-%m-%d %H:%M:%S") for d in data]

    rows = list(zip(times, temps, hums))

    context = {
        "temps": json.dumps(temps),
        "hums": json.dumps(hums),
        "times": json.dumps(times),
        "rows": rows
    }
    return render(request, "dashboard1.html", context)



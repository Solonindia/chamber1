from django.db import models

class MinuteReading(models.Model):
    chamber     = models.CharField(max_length=50, db_index=True, default="Chamber A")
    # separate columns as requested
    date        = models.DateField(db_index=True)
    time        = models.TimeField(db_index=True)

    temperature = models.FloatField()  # °C
    humidity    = models.FloatField()  # %
    pressure    = models.FloatField()  # hPa
    co2         = models.FloatField()  # ppm

    created_at  = models.DateTimeField(auto_now_add=True, db_index=True) 
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chamber", "date", "time"], name="uniq_chamber_minute"),
        ]
        ordering = ["-date", "-time"]

    def __str__(self):
        return f"{self.chamber} {self.date} {self.time}"

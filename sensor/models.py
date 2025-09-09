from django.db import models
from django.utils import timezone
from django.db.models import Q, CheckConstraint


class BaseSensorData(models.Model):
    date = models.DateField(db_index=True, null=True, blank=True)
    time = models.TimeField(db_index=True, null=True, blank=True)

    temperature = models.FloatField(null=True, blank=True)
    pressure    = models.FloatField(null=True, blank=True)
    humidity    = models.FloatField(null=True, blank=True)
    co2         = models.FloatField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ["-date", "-time"]
        constraints = [
            CheckConstraint(
                check=Q(temperature__gte=-50) & Q(temperature__lte=150),
                name="temp_0_in_range"
            ),
            CheckConstraint(
                check=Q(humidity__gte=0) & Q(humidity__lte=100),
                name="hum_0_in_range"
            ),
        ]

    def save(self, *args, **kwargs):
        # auto-fill if missing
        if not self.date or not self.time:
            now = timezone.localtime()
            if not self.date:
                self.date = now.date()
            if not self.time:
                self.time = now.time().replace(microsecond=0)
        return super().save(*args, **kwargs)


class Chamber1Data(BaseSensorData):
    class Meta:
        db_table   = "chamber1_data"
        verbose_name = "Chamber 1 Reading"
        verbose_name_plural = "Chamber 1 Readings"


class Chamber2Data(BaseSensorData):
    class Meta:
        db_table   = "chamber2_data"
        verbose_name = "Chamber 2 Reading"
        verbose_name_plural = "Chamber 2 Readings"


class Chamber3Data(BaseSensorData):
    class Meta:
        db_table   = "chamber3_data"
        verbose_name = "Chamber 3 Reading"
        verbose_name_plural = "Chamber 3 Readings"


from django.contrib.auth.models import User

class ChamberAccess(models.Model):
    CHOICES = [
        ("ch1", "Chamber 1"),
        ("ch2", "Chamber 2"),
        ("ch3", "Chamber 3"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    chamber = models.CharField(max_length=3, choices=CHOICES)

    def __str__(self):
        return f"{self.user.username} → {self.get_chamber_display()}"

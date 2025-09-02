from django.contrib import admin

# Register your models here.
from .models import ChamberAccess

@admin.register(ChamberAccess)
class ChamberAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "chamber")
    list_filter = ("chamber",)
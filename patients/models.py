from django.db import models

class Patient(models.Model):
    full_name = models.CharField("姓名", max_length=50)
    national_id = models.CharField("身分證", max_length=10, unique=True)
    nhi_no = models.CharField("健保卡號", max_length=20, blank=True)
    birth_date = models.DateField("生日")
    phone = models.CharField("電話", max_length=20, blank=True)
    chart_no = models.CharField("病歷號", max_length=20, unique=True)
    address = models.CharField("地址", max_length=200, blank=True)

    def __str__(self):
        return f"{self.chart_no} {self.full_name}" 

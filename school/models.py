from django.db import models



class School(models.Model):
    name = models.CharField(max_length=255)
    motto = models.CharField(max_length=255, blank=True, null=True)
    signee_name = models.CharField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    logo = models.ImageField(
        upload_to="school_logo/",
        blank=True,
        null=True
    )

    signature = models.ImageField(
        upload_to="school_signature/",
        blank=True,
        null=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

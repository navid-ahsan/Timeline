from django.db import models


class LawKBVersion(models.Model):
    source = models.CharField(max_length=200)
    version_date = models.DateField()
    file_hash = models.CharField(max_length=64)
    sections_updated = models.JSONField(default=list)
    indexed_chunks = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        get_latest_by = "updated_at"

    def __str__(self):
        return f"{self.source} @ {self.version_date}"

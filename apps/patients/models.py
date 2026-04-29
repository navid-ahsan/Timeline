from django.db import models


class Patient(models.Model):
    patient_id = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.patient_id


def document_upload_path(instance, filename):
    return f"patient_docs/{instance.patient.patient_id}/{filename}"


class PatientDocument(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to=document_upload_path)
    original_name = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=50, default="asiakirja")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    indexed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.patient.patient_id} / {self.original_name}"


class LifeEvent(models.Model):
    SEVERITY_CHOICES = [(i, str(i)) for i in range(1, 6)]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="events")
    date = models.CharField(max_length=10)  # YYYY-MM-DD
    event_type = models.CharField(max_length=60)
    description = models.TextField()
    severity = models.IntegerField(choices=SEVERITY_CHOICES)
    source_document = models.CharField(max_length=255)
    legal_basis = models.CharField(max_length=255)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "event_type": self.event_type,
            "description": self.description,
            "severity": self.severity,
            "source_document": self.source_document,
            "legal_basis": self.legal_basis,
            "approved": self.approved,
        }


class AuditLog(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="audit_logs")
    worker_id = models.CharField(max_length=100, default="unknown")
    action = models.CharField(max_length=50)
    llm_suggestion = models.JSONField(default=dict)
    human_decision = models.JSONField(default=dict)
    diff = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

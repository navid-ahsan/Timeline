import os
import sys
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser

from .models import Patient, PatientDocument, LifeEvent, AuditLog

# LangGraph imports (PYTHONPATH includes src/)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from pipeline import build_graph
from chat_graph import build_chat_graph


def _db_url():
    return settings.LANGCHAIN_DATABASE_URL


class PatientListView(APIView):
    def get(self, request):
        patients = Patient.objects.order_by("-updated_at").values(
            "patient_id", "created_at", "updated_at"
        )
        result = []
        for p in patients:
            doc_count = PatientDocument.objects.filter(patient__patient_id=p["patient_id"]).count()
            event_count = LifeEvent.objects.filter(
                patient__patient_id=p["patient_id"], approved=True
            ).count()
            result.append({**p, "doc_count": doc_count, "event_count": event_count})
        return Response(result)

    def post(self, request):
        patient_id = request.data.get("patient_id", "").strip()
        if not patient_id:
            return Response({"error": "patient_id required"}, status=400)
        patient, created = Patient.objects.get_or_create(patient_id=patient_id)
        return Response({"patient_id": patient.patient_id, "created": created})


class PatientDocumentUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, patient_id):
        patient, _ = Patient.objects.get_or_create(patient_id=patient_id)
        files = request.FILES.getlist("documents")

        if not files:
            return Response({"error": "No files provided"}, status=400)

        created_ids = []
        for f in files:
            if not f.name.lower().endswith(".pdf"):
                return Response({"error": f"{f.name} is not a PDF"}, status=400)
            if f.size > 15 * 1024 * 1024:
                return Response({"error": f"{f.name} exceeds 15 MB limit"}, status=400)

            doc = PatientDocument.objects.create(
                patient=patient,
                file=f,
                original_name=f.name,
                doc_type="asiakirja",
            )
            created_ids.append(doc.id)

        return Response({
            "uploaded": len(created_ids),
            "document_ids": created_ids,
            "patient_id": patient_id,
        })

    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, patient_id=patient_id)
        docs = patient.documents.values("id", "original_name", "doc_type", "uploaded_at", "indexed")
        return Response(list(docs))


class AnalyzeView(APIView):
    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, patient_id=patient_id)

        # Use only un-indexed docs; if all indexed, re-use all
        docs_qs = patient.documents.filter(indexed=False)
        if not docs_qs.exists():
            docs_qs = patient.documents.all()

        if not docs_qs.exists():
            return Response({"error": "No documents uploaded for this patient"}, status=400)

        doc_list = [{"path": d.file.path, "doc_type": d.doc_type} for d in docs_qs]

        try:
            with PostgresSaver.from_conn_string(_db_url()) as checkpointer:
                checkpointer.setup()
                graph = build_graph(checkpointer)
                config = {"configurable": {"thread_id": patient_id}}
                result = graph.invoke(
                    {"patient_id": patient_id, "current_documents": doc_list},
                    config=config,
                )

            # Persist proposed (unapproved) events
            patient.events.filter(approved=False).delete()
            proposed = result.get("top_10_timeline", [])
            for ev in proposed:
                LifeEvent.objects.create(
                    patient=patient,
                    date=ev.get("date", ""),
                    event_type=ev.get("event_type", "muu_kriittinen"),
                    description=ev.get("description", ""),
                    severity=int(ev.get("severity", 3)),
                    source_document=ev.get("source_document", ""),
                    legal_basis=ev.get("legal_basis", ""),
                    approved=False,
                )

            docs_qs.update(indexed=True)

            return Response({
                "patient_id": patient_id,
                "top_10_timeline": proposed,
                "total_events_found": len(result.get("all_events", [])),
            })

        except Exception as exc:
            return Response({"error": str(exc)}, status=500)


class ApproveView(APIView):
    def post(self, request, patient_id):
        patient = get_object_or_404(Patient, patient_id=patient_id)
        worker_id = request.data.get("worker_id", "unknown")
        timeline = request.data.get("timeline")

        proposed = list(patient.events.filter(approved=False).values())

        try:
            with PostgresSaver.from_conn_string(_db_url()) as checkpointer:
                graph = build_graph(checkpointer)
                config = {"configurable": {"thread_id": patient_id}}
                graph.invoke(Command(resume=timeline or [e["to_dict"] for e in proposed]), config=config)
        except Exception:
            pass  # interrupt resume may raise; events already saved

        # Mark proposed events as approved
        patient.events.filter(approved=False).update(approved=True)

        AuditLog.objects.create(
            patient=patient,
            worker_id=worker_id,
            action="timeline_approved",
            llm_suggestion={"events": proposed},
            human_decision={"events": timeline or []},
            diff={},
        )

        return Response({"status": "approved", "patient_id": patient_id})


class TimelineView(APIView):
    def get(self, request, patient_id):
        patient = get_object_or_404(Patient, patient_id=patient_id)
        approved = patient.events.filter(approved=True)
        proposed = patient.events.filter(approved=False)
        return Response({
            "patient_id": patient_id,
            "approved": [e.to_dict() for e in approved],
            "proposed": [e.to_dict() for e in proposed],
            "doc_count": patient.documents.count(),
        })


class ChatView(APIView):
    def post(self, request, patient_id):
        get_object_or_404(Patient, patient_id=patient_id)
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"error": "question required"}, status=400)

        try:
            with PostgresSaver.from_conn_string(_db_url()) as checkpointer:
                graph = build_chat_graph(checkpointer)
                config = {
                    "configurable": {
                        "thread_id": f"chat_{patient_id}",
                        "patient_id": patient_id,
                    }
                }
                result = graph.invoke(
                    {"messages": [HumanMessage(content=question)], "patient_id": patient_id},
                    config=config,
                )
            answer = result["messages"][-1].content
            return Response({"answer": answer})
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

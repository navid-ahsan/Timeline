import os
import sys

from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings

# LangGraph RAG imports
from rag import get_retriever


class LawSearchView(APIView):
    """Return relevant law excerpts for a given event type and description."""

    def get(self, request):
        event_type = request.query_params.get("event_type", "")
        query = request.query_params.get("query", "")
        search = f"{event_type} {query}".strip()

        if not search:
            return Response({"laws": []})

        try:
            retriever = get_retriever(k=5)
            docs = retriever.invoke(search)
            laws = [
                {
                    "reference": doc.metadata.get("source", ""),
                    "section": doc.metadata.get("section", ""),
                    "excerpt": doc.page_content,
                }
                for doc in docs
            ]
            return Response({"laws": laws})
        except Exception as exc:
            # Law KB may be empty until build_knowledge_base.py is run
            return Response({"laws": [], "note": str(exc)})

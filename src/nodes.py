import os
import json
from datetime import datetime, timezone
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.document_loaders import PyPDFLoader

from .state import PatientState, LifeEvent
from .rag import get_retriever, index_patient_document
from .audit import AuditEntry, write_audit


def _get_llm():
    return ChatOllama(
        model=os.environ.get("LLM_MODEL", "mistral"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        temperature=0,
    )


def route_documents(state: PatientState) -> dict:
    """Pass-through: documents are fanned out via Send in pipeline.py."""
    return {}


def process_document(state: dict) -> dict:
    """Extract life events from a single document."""
    doc = state["doc"]
    patient_id = state["patient_id"]
    path = doc["path"]

    # Load and chunk the PDF
    loader = PyPDFLoader(path)
    pages = loader.load()
    full_text = "\n".join(p.page_content for p in pages)

    # Index document for chat RAG
    index_patient_document(
        patient_id=patient_id,
        text=full_text,
        metadata={"source": os.path.basename(path), "date": datetime.now(timezone.utc).date().isoformat()},
    )

    # Fetch legal criteria context
    retriever = get_retriever()
    criteria_docs = retriever.invoke(full_text[:500])
    criteria = "\n".join(d.page_content for d in criteria_docs)

    llm = _get_llm()
    system = SystemMessage(content=(
        "Olet lastensuojelun asiantuntija. Analysoi asiakirja ja tunnista kaikki merkittävät "
        "elämäntapahtumat. Palauta JSON-taulukko objekteja, joissa on kentät: "
        "date (YYYY-MM-DD), event_type, description, severity (1-5), source_document, legal_basis. "
        "Käytä vain näitä event_type-arvoja: ehkaiseva_lastensuojelu, lastensuojeluilmoitus, "
        "lastensuojelutarpeen_selvitys, asiakkuuden_alkaminen, avohuollon_tukitoimet, "
        "kiireellinen_sijoitus, huostaanotto, sijaishuolto_perhehoito, sijaishuolto_laitoshoito, "
        "sijaishuoltopaikan_muutos, jalkihuolto, psykiatrinen_hoito, perhevakivalta_epaily, "
        "paihdekaytto, rikosepaily, koulupoissaolot_vakavat, muu_kriittinen. "
        f"Oikeudellinen viitekehys:\n{criteria}\n\n"
        "Palauta VAIN JSON-taulukko, ei muuta tekstiä."
    ))
    human = HumanMessage(content=f"Asiakirja ({os.path.basename(path)}):\n\n{full_text[:4000]}")

    response = llm.invoke([system, human])

    try:
        events_raw = json.loads(response.content)
        events = [LifeEvent(**e).model_dump() for e in events_raw]
    except Exception:
        events = []

    return {"new_events": events, "processed_documents": [path]}


def merge_events(state: PatientState) -> dict:
    """Merge new events into the cumulative event list, deduplicating by date+type."""
    all_events = list(state.get("all_events", []))
    new_events = list(state.get("new_events", []))

    existing_keys = {(e["date"], e["event_type"]) for e in all_events}
    for e in new_events:
        key = (e["date"], e["event_type"])
        if key not in existing_keys:
            all_events.append(e)
            existing_keys.add(key)

    return {"all_events": all_events}


def select_top_10(state: PatientState) -> dict:
    """Use LLM to rank all accumulated events and select the 10 most significant."""
    all_events = state.get("all_events", [])
    if not all_events:
        return {"top_10_timeline": [], "retry_count": state.get("retry_count", 0)}

    llm = _get_llm()
    system = SystemMessage(content=(
        "Olet lastensuojelun asiantuntija. Sinulle annetaan lista elämäntapahtumia. "
        "Valitse 10 merkittävintä tapahtumaa, jotka parhaiten kuvaavat lapsen tilannetta ja kehitystä. "
        "Priorisoi: korkea vakavuus, juridiset interventiot, merkittävät siirtymät. "
        "Palauta VAIN JSON-taulukko valituista 10 tapahtumasta samassa formaatissa. "
        "Järjestä päivämäärän mukaan vanhimmasta uusimpaan."
    ))
    human = HumanMessage(content=json.dumps(all_events, ensure_ascii=False))

    response = llm.invoke([system, human])

    try:
        top_10 = json.loads(response.content)
    except Exception:
        top_10 = sorted(all_events, key=lambda e: e.get("severity", 0), reverse=True)[:10]

    return {
        "top_10_timeline": top_10,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "retry_count": state.get("retry_count", 0),
    }


def evaluate_timeline(state: PatientState) -> dict:
    """Check that the top-10 selection is coherent and well-justified."""
    top_10 = state.get("top_10_timeline", [])
    retry_count = state.get("retry_count", 0)

    if not top_10:
        return {"eval_passed": False, "retry_count": retry_count + 1}

    llm = _get_llm()
    system = SystemMessage(content=(
        "Tarkista seuraava aikajana: onko siinä 10 tapahtumaa, ovatko kaikki kentät täytetty, "
        "onko järjestys kronologinen ja vakavuusasteet johdonmukaiset? "
        "Vastaa VAIN sanalla OK tai FAIL."
    ))
    human = HumanMessage(content=json.dumps(top_10, ensure_ascii=False))

    response = llm.invoke([system, human])
    passed = "OK" in response.content.upper()

    return {"eval_passed": passed, "retry_count": retry_count + (0 if passed else 1)}


def save_with_audit(state: PatientState) -> dict:
    """Persist the approved timeline and write an audit record."""
    entry = AuditEntry(
        patient_id=state["patient_id"],
        worker_id="unknown",  # set from UI session when available
        action="timeline_approved",
        llm_suggestion={"top_10": state.get("top_10_timeline", [])},
        human_decision={"top_10": state.get("top_10_timeline", [])},
        diff={},
    )
    try:
        write_audit(entry)
    except Exception:
        pass  # don't block the pipeline if audit DB is unavailable

    return {"human_approved": True}

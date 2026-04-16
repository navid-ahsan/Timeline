# Lastensuojelun Elämäntapahtumaaikajana — LangGraph RAG Pipeline

> **Tärkeä huomio:** Tämä järjestelmä on päätöksenteon tukityökalu.
> Kaikki lopulliset päätökset tekee aina vastuullinen sosiaalityöntekijä.
> LLM ei korvaa ammattilaista eikä juridista harkintaa.

---

## Yleiskuvaus

Sovellus on **sosiaalityöntekijän työväline** joka tekee kaksi asiaa:

**1. Perehdytys** — Kun sosiaalityöntekijä ottaa uuden potilaan, sovellus analysoi kaikki asiakirjat ja tuottaa automaattisesti 10 merkittävintä elämäntapahtumaa aikajanalla. Uusi työntekijä saa kokonaiskuvan minuuteissa, ei päivissä.

**2. Chat** — Sosiaalityöntekijä voi esittää vapaita kysymyksiä potilaan historiasta luonnollisella kielellä. LLM vastaa potilaan omien asiakirjojen pohjalta ja viittaa aina lähteeseen.

```
"Milloin viimeisin lastensuojeluilmoitus tehtiin?"
"Mitä terapiakäynneistä tiedetään?"
"Onko perheen päihdehistoriasta merkintöjä?"
```

Kaikki tieto pysyy lokaalisti — ei pilveen, ei ulkopuolisille.

---

## Miksi tämä on tarpeellinen

Lastensuojelussa asiakkuus voi sisältää satoja dokumentteja vuosien ajalta. Sosiaalityöntekijät vaihtuvat, tieto hukkuu, perehdytys vie aikaa. Tämä sovellus:

- Nopeuttaa perehdytystä uuteen asiakkaaseen (aikajana ensisilmäyksellä)
- Antaa sosiaalityöntekijälle mahdollisuuden kysyä tarkentavia kysymyksiä ilman manuaalista asiakirjaselailua
- Viittaa aina alkuperäiseen asiakirjaan — ei mustalaatikkovastausta
- Tukee asiakassuunnitelman laadintaa (lastensuojelulaki 417/2007, 30 §)

---

## Arkkitehtuuri

Sovelluksessa on kaksi LangGraph-graafia jotka jakavat saman potilasmuistin:

```
┌─────────────────────────────────────────────────────────┐
│                    STREAMLIT UI                         │
│                                                         │
│   [📋 Aikajana-välilehti]    [💬 Chat-välilehti]        │
└───────────┬──────────────────────────┬──────────────────┘
            │                          │
            ▼                          ▼
┌───────────────────┐      ┌───────────────────────┐
│  TIMELINE GRAPH   │      │     CHAT GRAPH        │
│                   │      │                       │
│  route_documents  │      │  load_patient_context │
│       │           │      │        │              │
│  [Workers x N]    │      │  retrieve_from_docs   │
│       │           │      │   (potilaskohtainen   │
│  merge_events     │      │    PGVector-haku)     │
│       │           │      │        │              │
│  select_top_10    │      │   llm_answer          │
│       │           │      │   + lähdeviitteet     │
│  human_review     │      │        │              │
│       │           │      │   save_to_chat_memory │
│  save + audit     │      │                       │
└─────────┬─────────┘      └───────────┬───────────┘
          │                            │
          └──────────┬─────────────────┘
                     ▼
        ┌────────────────────────┐
        │   POSTGRESQL           │
        │                        │
        │  • LangGraph muisti    │  ← sessioiden välinen tila
        │    (checkpointer)      │
        │  • Potilasindeksi      │  ← patient_{id} collection
        │    (PGVector)          │
        │  • STM/THL indeksi     │  ← lastensuojelukriteerit
        │    (PGVector)          │
        │  • Audit trail         │
        └────────────────────────┘
                     ▲
        ┌────────────┴───────────┐
        │       OLLAMA           │
        │  mistral (chat+reasoning)
        │  nomic-embed-text      │
        └────────────────────────┘
```

---

## LangGraph-patternit ja perustelut

| Pattern | Rooli | Miksi valittu |
|---|---|---|
| **Persistence (PostgreSQL)** | Potilaskohtainen muisti sessioiden yli | Asiakkuus voi kestää vuosia, tieto ei saa kadota |
| **Routing** | Dokumenttityypin tunnistus | Eri dokumentit vaativat eri RAG-kontekstin |
| **Orchestrator-Worker** | Rinnakkaisajo per dokumentti | Yksittäinen asiakkuus voi sisältää kymmeniä asiakirjoja |
| **Evaluator-Optimizer** | Top-10 valinta ja perustelu | Valinnan on oltava perusteltavissa, ei pelkkä rankinglista |
| **Human-in-the-loop** | Sosiaalityöntekijän hyväksyntä | Juridinen vastuu pysyy ihmisellä |
| **RAG (PGVector)** | STM/THL kriteerit kontekstina | LLM:llä oltava ajantasainen lakitietämys |

---

## Lastensuojelun vaiheet — tapahtumakategoriat

Järjestelmä tunnistaa ja kategorisoi tapahtumat STM:n lastensuojeluprosessin vaiheiden mukaan:

```python
EventType = Literal[
    "ehkaiseva_lastensuojelu",      # neuvola, päivähoito, koulu
    "lastensuojeluilmoitus",         # vireilletulo
    "lastensuojelutarpeen_selvitys", # 7 arkipäivän arvio
    "asiakkuuden_alkaminen",         # sosiaalityöntekijä nimetty
    "avohuollon_tukitoimet",         # terapia, tukihenkilö, perhetyö
    "kiireellinen_sijoitus",         # välitön vaara
    "huostaanotto",                  # vakava vaara, avohuolto ei riittänyt
    "sijaishuolto_perhehoito",       # sijaisperhe
    "sijaishuolto_laitoshoito",      # lastenkoti, koulukoti
    "sijaishuoltopaikan_muutos",     # siirtymä sijaishuollossa
    "jalkihuolto",                   # ikäraja 23 vuotta (LSL 75 §)
    "psykiatrinen_hoito",            # erikoissairaanhoito
    "perhevakivalta_epaily",         # lastensuojelulaki 25 §
    "paihdekaytto",                  # lapsen tai huoltajan
    "rikosepaily",                   # alle tai yli rikosvastuuiän
    "koulupoisssaolot_vakavat",      # toistuva luvaton poissaolo
    "muu_kriittinen"
]
```

### Vakavuusasteikko (1–5)

| Taso | Kuvaus | Esimerkit |
|---|---|---|
| 1 | Ehkäisevä tuki | Neuvola-asiointi, kouluohjaus |
| 2 | Varhainen puuttuminen | Avohuollon aloitus, perhetyö |
| 3 | Merkittävä interventio | Lastensuojeluilmoitus, selvitys |
| 4 | Kriittinen toimenpide | Kiireellinen sijoitus, huostaanotto |
| 5 | Välitön hengenvaara | Akuutti väkivalta, hätäsijoitus |

---

## Tekninen stack

```
LLM (lokaali):     Ollama + Mistral 7B tai Llama 3.1 8B
                   → Mistral parempi eurooppalaiselle tekstille
                   → Lämpötila 0 deterministisyyttä varten

Muisti:            LangGraph PostgresSaver (checkpointer)
Vektoriindeksi:    PGVector (PostgreSQL-laajennus)
Embeddings:        nomic-embed-text (lokaali, Ollaman kautta)
Framework:         LangGraph 0.2+, LangChain Core
Infrastruktuuri:   Docker Compose (ollama + postgres + app)
```

---

## Chat-graafi — potilaskohtainen RAG

Chat-graafi on erillinen LangGraph-graafi joka käyttää samaa PostgreSQL-muistia. Se hakee vastaukset **yksinomaan potilaan omista asiakirjoista** — ei yleisestä tietokannasta.

### src/chat_graph.py

```python
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.messages import SystemMessage, HumanMessage
import os


def build_chat_graph(checkpointer):
    llm = ChatOllama(
        model=os.environ.get("LLM_MODEL", "mistral"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        temperature=0.2,  # hieman joustoa keskusteluun, ei täysin deterministinen
    )

    def get_patient_retriever(patient_id: str):
        """Haku vain tämän potilaan asiakirjoista."""
        embeddings = OllamaEmbeddings(
            model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        )
        return PGVector(
            collection_name=f"patient_{patient_id}",  # potilaskohtainen collection
            connection_string=os.environ["DATABASE_URL"],
            embedding_function=embeddings,
        ).as_retriever(search_kwargs={"k": 5})

    def retrieve_and_answer(state: MessagesState) -> dict:
        patient_id = state.get("patient_id")
        question = state["messages"][-1].content

        # Hae relevantti konteksti potilaan asiakirjoista
        retriever = get_patient_retriever(patient_id)
        docs = retriever.invoke(question)

        # Rakenna konteksti lähdeviitteineen
        context_parts = []
        for doc in docs:
            source = doc.metadata.get("source", "tuntematon asiakirja")
            date   = doc.metadata.get("date", "")
            context_parts.append(f"[Lähde: {source} {date}]\n{doc.page_content}")

        context = "\n\n---\n\n".join(context_parts)

        system = SystemMessage(content=(
            "Olet lastensuojelun asiantuntija-assistentti. "
            "Vastaat sosiaalityöntekijän kysymyksiin lapsen historiasta. "
            "Käytä VAIN alla olevaa kontekstia. "
            "Viittaa aina lähteeseen vastauksessasi. "
            "Jos tieto puuttuu kontekstista, sano se suoraan. "
            "Älä koskaan spekuloi tai keksi tietoja.\n\n"
            f"Potilaan asiakirjoista löydetty konteksti:\n{context}"
        ))

        response = llm.invoke([system] + state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("answer", retrieve_and_answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)

    return builder.compile(checkpointer=checkpointer)
```

---

## Streamlit UI

Sosiaalityöntekijä käyttää sovellusta Streamlit-käyttöliittymän kautta. Kaksi välilehteä: perehdytys ja chat.

### src/ui.py

```python
import streamlit as st
import os
from pipeline import get_pipeline
from chat_graph import build_chat_graph
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage

st.set_page_config(
    page_title="Lastensuojelu — Potilastyökalu",
    page_icon="🏥",
    layout="wide",
)

# ── Sidebar: potilaan valinta ──────────────────────────────────────────────
with st.sidebar:
    st.header("Potilas")
    patient_id = st.text_input("Potilaan ID", placeholder="esim. 12345")
    uploaded_files = st.file_uploader(
        "Lisää asiakirjoja",
        type=["pdf"],
        accept_multiple_files=True,
    )
    if st.button("Analysoi asiakirjat") and patient_id and uploaded_files:
        with st.spinner("Analysoidaan..."):
            # Tallenna uploadatut tiedostot väliaikaisesti
            docs = []
            for f in uploaded_files:
                tmp_path = f"/tmp/{f.name}"
                with open(tmp_path, "wb") as out:
                    out.write(f.read())
                docs.append({"path": tmp_path, "doc_type": "asiakirja"})

            pipeline = get_pipeline()
            config = {"configurable": {"thread_id": patient_id}}
            st.session_state["pipeline_result"] = pipeline.invoke(
                {"patient_id": patient_id, "current_documents": docs},
                config=config,
            )
        st.success("Aikajana päivitetty.")

# ── Päänäkymä: kaksi välilehteä ───────────────────────────────────────────
tab_timeline, tab_chat = st.tabs(["📋 Aikajana", "💬 Chat"])

# ── TAB 1: Aikajana ────────────────────────────────────────────────────────
with tab_timeline:
    st.header("10 merkittävintä elämäntapahtumaa")

    result = st.session_state.get("pipeline_result")
    if not result:
        st.info("Valitse potilas ja lisää asiakirjat vasemmalta.")
    else:
        for i, event in enumerate(result.get("top_10_timeline", []), 1):
            severity_color = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "⛔"}.get(
                event["severity"], "⚪"
            )
            with st.expander(
                f"{severity_color} {i}. [{event['date']}] {event['event_type']}"
            ):
                st.write(event["description"])
                st.caption(f"Lähde: {event['source_document']}")
                st.caption(f"Oikeusperuste: {event['legal_basis']}")

        # Human-in-the-loop: sosiaalityöntekijä hyväksyy
        if not result.get("human_approved"):
            st.divider()
            st.subheader("Hyväksy tai muokkaa aikajana")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Hyväksy", type="primary"):
                    pipeline = get_pipeline()
                    config = {"configurable": {"thread_id": patient_id}}
                    pipeline.invoke(result["top_10_timeline"], config=config)
                    st.success("Aikajana tallennettu.")
            with col2:
                if st.button("🔄 Analysoi uudelleen"):
                    st.rerun()

# ── TAB 2: Chat ────────────────────────────────────────────────────────────
with tab_chat:
    st.header(f"Kysy potilaan historiasta")

    if not patient_id:
        st.info("Valitse ensin potilas vasemmalta.")
    else:
        # Alusta chat history session stateen
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        # Näytä aiemmat viestit
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Käyttäjän syöte
        if prompt := st.chat_input("Esim. 'Milloin viimeisin lastensuojeluilmoitus tehtiin?'"):
            st.session_state["chat_history"].append(
                {"role": "user", "content": prompt}
            )
            with st.chat_message("user"):
                st.write(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Haetaan asiakirjoista..."):
                    db_url = os.environ["DATABASE_URL"]
                    with PostgresSaver.from_conn_string(db_url) as checkpointer:
                        chat_graph = build_chat_graph(checkpointer)
                        config = {
                            "configurable": {
                                "thread_id": f"chat_{patient_id}",
                                "patient_id": patient_id,
                            }
                        }
                        response = chat_graph.invoke(
                            {
                                "messages": [HumanMessage(content=prompt)],
                                "patient_id": patient_id,
                            },
                            config=config,
                        )
                    answer = response["messages"][-1].content
                    st.write(answer)
                    st.session_state["chat_history"].append(
                        {"role": "assistant", "content": answer}
                    )
```

---

## Päivitetty projektirakenne

```
lastensuojelu-aikajana/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── scripts/
│   ├── init_models.sh
│   └── build_knowledge_base.py
├── sql/
│   └── init.sql
└── src/
    ├── ui.py               # Streamlit UI (perehdytys + chat)
    ├── pipeline.py         # Timeline LangGraph-graafi
    ├── chat_graph.py       # Chat LangGraph-graafi
    ├── nodes.py            # Graafien nodet
    ├── state.py            # TypedDict-tila
    ├── rag.py              # PGVector retriever
    └── audit.py            # Audit trail
```

---

## Päivitetty Docker Compose (+ Streamlit)

Lisää `app`-serviceen:

```yaml
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ls_app
    depends_on:
      ollama:
        condition: service_healthy
      ollama-init:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/lastensuojelu_db
      LLM_MODEL: ${LLM_MODEL:-mistral}
      EMBED_MODEL: ${EMBED_MODEL:-nomic-embed-text}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8501:8501"       # Streamlit (oli 8080)
    command: streamlit run src/ui.py --server.port 8501 --server.address 0.0.0.0
```

Sovellus käynnistyksen jälkeen: **http://localhost:8501**

---



### Projektirakenne

```
lastensuojelu-aikajana/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── scripts/
│   ├── init_models.sh          # Lataa Ollama-mallit käynnistyksen yhteydessä
│   └── build_knowledge_base.py # Vektorisoi lakidokumentit
├── sql/
│   └── init.sql                # PostgreSQL + pgvector alustus
├── src/
│   ├── pipeline.py             # LangGraph-graafi
│   ├── nodes.py                # Graafin nodet
│   ├── state.py                # TypedDict-tila
│   ├── rag.py                  # PGVector retriever
│   └── audit.py                # Audit trail
└── data/
    └── knowledge_base/         # PDF-lähteet RAG:lle
```

---

### docker-compose.yml

```yaml
services:

  # ── Ollama: lokaalit LLM-mallit ────────────────────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: ls_ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Mallien lataus (ajaa kerran, sitten sammuu) ─────────────────────────
  ollama-init:
    image: ollama/ollama:latest
    container_name: ls_ollama_init
    depends_on:
      ollama:
        condition: service_healthy
    volumes:
      - ollama_data:/root/.ollama
      - ./scripts/init_models.sh:/init_models.sh
    entrypoint: ["/bin/sh", "/init_models.sh"]
    environment:
      OLLAMA_HOST: http://ollama:11434
    restart: "no"

  # ── PostgreSQL + pgvector: muisti ja vektoriindeksi ────────────────────
  postgres:
    image: pgvector/pgvector:pg16
    container_name: ls_postgres
    environment:
      POSTGRES_DB: lastensuojelu_db
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d lastensuojelu_db"]
      interval: 5s
      timeout: 5s
      retries: 10

  # ── Sovellus: LangGraph-pipeline ───────────────────────────────────────
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ls_app
    depends_on:
      ollama:
        condition: service_healthy
      ollama-init:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/lastensuojelu_db
      LLM_MODEL: ${LLM_MODEL:-mistral}
      EMBED_MODEL: ${EMBED_MODEL:-nomic-embed-text}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8080:8080"

volumes:
  ollama_data:
  pgdata:
```

---

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Riippuvuudet ensin — Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/

CMD ["python", "-m", "src.pipeline"]
```

### requirements.txt

```
langchain-core>=0.3
langchain-ollama>=0.2
langchain-community>=0.3
langgraph>=0.2
psycopg2-binary>=2.9
pgvector>=0.3
pydantic>=2.0
pypdf>=4.0
python-dotenv>=1.0
```

---

### scripts/init_models.sh

```bash
#!/bin/sh
# Lataa mallit Ollama-palvelimelle käynnistyksen yhteydessä.
# ollama-init-container ajaa tämän kerran ja sammuu.

set -e
export OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"

echo ">>> Ladataan LLM-malli: mistral"
ollama pull mistral

echo ">>> Ladataan embedding-malli: nomic-embed-text"
ollama pull nomic-embed-text

echo ">>> Mallit ladattu."
```

---

### sql/init.sql

```sql
-- pgvector-laajennus
CREATE EXTENSION IF NOT EXISTS vector;

-- LangGraph checkpointer -taulut (PostgresSaver luo nämä automaattisesti,
-- mutta skeemat voi esialustaa tässä)
CREATE SCHEMA IF NOT EXISTS langgraph;

-- Vektoriindeksi RAG-lähteille
CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    name      VARCHAR PRIMARY KEY,
    cmetadata JSON,
    uuid      UUID DEFAULT gen_random_uuid()
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    collection_id VARCHAR REFERENCES langchain_pg_collection(name) ON DELETE CASCADE,
    embedding  VECTOR(768),
    document   TEXT,
    cmetadata  JSON
);

CREATE INDEX IF NOT EXISTS idx_embedding_cosine
    ON langchain_pg_embedding USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    patient_id      TEXT NOT NULL,        -- pseudonymisoitu hash
    worker_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    llm_suggestion  JSONB,
    human_decision  JSONB,
    diff            JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
```

---

### .env.example

```env
DB_USER=ls_user
DB_PASSWORD=vaihda_tama_salasana
LLM_MODEL=mistral
EMBED_MODEL=nomic-embed-text
LOG_LEVEL=INFO
```

---

### src/state.py

```python
from typing import TypedDict, Annotated
from datetime import datetime
import operator
from pydantic import BaseModel, Field
from typing import Literal


EventType = Literal[
    "ehkaiseva_lastensuojelu",
    "lastensuojeluilmoitus",
    "lastensuojelutarpeen_selvitys",
    "asiakkuuden_alkaminen",
    "avohuollon_tukitoimet",
    "kiireellinen_sijoitus",
    "huostaanotto",
    "sijaishuolto_perhehoito",
    "sijaishuolto_laitoshoito",
    "sijaishuoltopaikan_muutos",
    "jalkihuolto",
    "psykiatrinen_hoito",
    "perhevakivalta_epaily",
    "paihdekaytto",
    "rikosepaily",
    "koulupoissaolot_vakavat",
    "muu_kriittinen",
]


class LifeEvent(BaseModel):
    date: str
    event_type: EventType
    description: str
    severity: int = Field(ge=1, le=5)
    source_document: str
    legal_basis: str


class PatientState(TypedDict):
    # Pysyvät — akkumuloituu sessioiden yli
    patient_id: str
    all_events: Annotated[list, operator.add]
    processed_documents: Annotated[list, operator.add]

    # Päivitetään joka sessio
    top_10_timeline: list
    last_updated: str

    # Sessiospesifiset
    current_documents: list
    new_events: Annotated[list, operator.add]
    retry_count: int
    human_approved: bool
```

---

### src/pipeline.py

```python
import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Send, interrupt

from .state import PatientState
from .nodes import (
    route_documents,
    process_document,
    merge_events,
    select_top_10,
    evaluate_timeline,
    save_with_audit,
)


def build_graph(checkpointer) -> StateGraph:
    builder = StateGraph(PatientState)

    builder.add_node("route_documents",  route_documents)
    builder.add_node("process_document", process_document)
    builder.add_node("merge_events",     merge_events)
    builder.add_node("select_top_10",    select_top_10)
    builder.add_node("evaluate",         evaluate_timeline)
    builder.add_node("human_review",     human_review_node)
    builder.add_node("save",             save_with_audit)

    # Reunat
    builder.add_edge(START, "route_documents")
    builder.add_conditional_edges(
        "route_documents",
        lambda s: [Send("process_document", {"doc": d, "patient_id": s["patient_id"]})
                   for d in s["current_documents"]],
        ["process_document"],
    )
    builder.add_edge("process_document", "merge_events")
    builder.add_edge("merge_events",     "select_top_10")
    builder.add_edge("select_top_10",    "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        lambda s: (
            "human_review" if s.get("eval_passed")
            else ("select_top_10" if s.get("retry_count", 0) < 2
                  else "human_review")   # pakko-exit max-retrylle
        ),
    )
    builder.add_edge("human_review", "save")
    builder.add_edge("save", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],  # pysähdy ennen ihmisreviä
    )


def human_review_node(state: PatientState) -> dict:
    """LangGraph interrupt — sosiaalityöntekijä hyväksyy tai muokkaa."""
    approved_timeline = interrupt({
        "proposed_timeline": state["top_10_timeline"],
        "total_events_found": len(state["all_events"]),
        "message": "Tarkista ja hyväksy aikajana.",
    })
    return {
        "top_10_timeline": approved_timeline,
        "human_approved": True,
    }


def get_pipeline():
    db_url = os.environ["DATABASE_URL"]
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        return build_graph(checkpointer)


# ── Käyttöesimerkki ────────────────────────────────────────────────────────
if __name__ == "__main__":
    pipeline = get_pipeline()

    config = {"configurable": {"thread_id": "patient_12345"}}

    # Sessio 1
    result = pipeline.invoke(
        {
            "patient_id": "12345",
            "current_documents": [
                {"path": "data/ilmoitus_2021.pdf", "doc_type": "lastensuojeluilmoitus"},
                {"path": "data/arvio_2022.pdf",    "doc_type": "lastensuojelutarpeen_selvitys"},
            ],
        },
        config=config,
    )

    # Interrupt: sosiaalityöntekijä tarkistaa tässä kohdassa.
    # Kun hyväksytty, jatka:
    final = pipeline.invoke(None, config=config)

    for i, event in enumerate(final["top_10_timeline"], 1):
        print(f"{i}. [{event['date']}] {event['event_type']} (vakavuus {event['severity']}/5)")
        print(f"   {event['description']}")
        print(f"   Oikeusperuste: {event['legal_basis']}\n")
```

---

### src/rag.py

```python
import os
from langchain_community.vectorstores import PGVector
from langchain_ollama import OllamaEmbeddings

_retriever = None


def get_retriever(k: int = 4):
    """Singleton retriever — yhteys avataan kerran."""
    global _retriever
    if _retriever is None:
        embeddings = OllamaEmbeddings(
            model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        )
        vectorstore = PGVector(
            collection_name="lastensuojelu_kriteerit",
            connection_string=os.environ["DATABASE_URL"],
            embedding_function=embeddings,
        )
        _retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    return _retriever
```

---

## Asennus

```bash
# 1. Kloonaa repo
git clone https://github.com/org/lastensuojelu-aikajana
cd lastensuojelu-aikajana

# 2. Ympäristömuuttujat
cp .env.example .env
# Muokkaa DB_PASSWORD

# 3. Käynnistä kaikki palvelut
#    Ollama-init lataa mallit automaattisesti
docker compose up -d

# 4. Seuraa mallien latausta (kestää ~5 min ensimmäisellä kerralla)
docker compose logs -f ollama-init

# 5. Vektorisoi lakidokumentit RAG-indeksiin
docker compose exec app python scripts/build_knowledge_base.py \
  --sources data/knowledge_base/lastensuojelulaki.pdf \
            data/knowledge_base/thl_kasikirja/ \
            data/knowledge_base/stm_laatusuositus_2019.pdf

# 6. Testaa pipeline
docker compose exec app python -m src.pipeline
```

---

## Käyttö

```python
from pipeline import ChildProtectionTimeline

timeline = ChildProtectionTimeline()

# Lisää dokumentteja — muisti akkumuloituu automaattisesti
result = timeline.process(
    patient_id="12345",
    documents=[
        {"path": "docs/ilmoitus_2021.pdf", "type": "lastensuojeluilmoitus"},
        {"path": "docs/arvio_2022.pdf",    "type": "lastensuojelutarpeen_selvitys"},
    ]
)

# Myöhemmin — uudet dokumentit lisätään, aiempi historia säilyy
result = timeline.process(
    patient_id="12345",
    documents=[
        {"path": "docs/huostaanotto_2023.pdf", "type": "huostaanottopäätös"},
    ]
)

# Tulostus
for i, event in enumerate(result.top_10_timeline, 1):
    print(f"{i}. [{event.date}] {event.event_type} (vakavuus: {event.severity}/5)")
    print(f"   {event.description}")
    print(f"   Oikeusperuste: {event.legal_basis}\n")
```

---

## RAG-tietolähteet (vektoriindeksi)

Järjestelmä hakee kriteerit näistä lähteistä:

| Lähde | Käyttötarkoitus |
|---|---|
| Lastensuojelulaki 417/2007 (ajantasainen) | Juridinen viitekehys tapahtumien luokitteluun |
| THL: Lastensuojelun käsikirja | Käytännön arviointikriteerit |
| STM: Lastensuojelun laatusuositus 2019:8 | Palvelun laadun arviointi |
| YK:n lapsen oikeuksien yleissopimus | Kansainvälinen normisto |
| Euroopan ihmisoikeussopimus | Perusoikeusviitekehys |

> **Huomio lakiuudistuksesta:** Lastensuojelulainsäädännön kokonaisuudistuksen
> ensimmäinen vaihe tuli voimaan **1.1.2026**. Toinen vaihe on valmistelussa
> vuodelle 2026. Vektoriindeksi on päivitettävä lakimuutosten yhteydessä.
> Katso: [STM lastensuojelun lainsäädännön kokonaisuudistus](https://stm.fi/hanke?tunnus=STM009:00/2024)

---

## Tietosuoja ja turvallisuus

Lastensuojelun asiakastiedot ovat erityisen arkaluonteisia. Tämä järjestelmä on suunniteltu täysin lokaaliin käyttöön.

### Vaatimukset

- **Ei pilvipalveluja** — kaikki LLM-inferenssi ja data pysyy on-premise
- **Enkryptaus at-rest** — PostgreSQL full-disk encryption
- **Enkryptaus in-transit** — TLS kaikessa sisäisessä liikenteessä
- **Pääsynhallinta** — RBAC, sosiaalityöntekijä näkee vain omat asiakkaansa
- **Audit trail** — jokainen operaatio lokitetaan: kuka, milloin, mitä muutoksia

### Relevantti lainsäädäntö

- **GDPR** (EU 2016/679) — erityisesti arkaluonteiset henkilötiedot (art. 9)
- **Laki sosiaalihuollon asiakasasiakirjoista** (254/2015)
- **Laki sosiaalihuollon asiakkaan asemasta ja oikeuksista** (812/2000)
- **Tietosuojalaki** (1050/2018)

```python
# Audit log -esimerkki
@dataclass
class AuditEntry:
    timestamp: datetime
    patient_id: str          # pseudonymisoitu
    worker_id: str           # sosiaalityöntekijän ID
    action: str              # "timeline_viewed" | "timeline_approved" | "event_modified"
    llm_suggestion: dict     # mitä LLM ehdotti
    human_decision: dict     # mitä ihminen hyväksyi/muutti
    diff: dict               # muutokset ehdotukseen
```

---

## Human-in-the-loop — työnkulku

```
LLM ehdottaa top-10 →
  Sosiaalityöntekijä saa notifikaation →
    Tarkistaa ehdotuksen →
      Hyväksyy / muokkaa / hylkää →
        Kirjataan audit logiin →
          Tallennetaan potilasmuistiin
```

Sosiaalityöntekijä voi:
- **Hyväksyä** ehdotuksen sellaisenaan
- **Muokata** tapahtumien järjestystä tai kuvauksia
- **Lisätä** tapahtumia joita LLM ei tunnistanut
- **Poistaa** väärin tunnistettuja tapahtumia
- **Hylätä** koko ehdotuksen ja pyytää uudelleenanalyysi

---

## Rajoitukset

Järjestelmällä on tunnettuja rajoituksia, jotka sosiaalityöntekijän on tiedostettava:

| Rajoitus | Kuvaus |
|---|---|
| **Hallusinaatiot** | LLM voi luoda tapahtumia joita dokumenteissa ei ole. Lähdeviitteet aina tarkistettava. |
| **Puuttuva data** | Järjestelmä ei tiedä mitä dokumentteja ei ole syötetty. Aikajana on niin kattava kuin syötetty data. |
| **Kielieroavaisuudet** | Suomenkielinen lokaalit mallit (Mistral/Llama) ovat heikompia kuin GPT-4. Monimutkaiset lauserakenteet voivat tulkita väärin. |
| **Kulttuurinen konteksti** | LLM ei tunne kaikkia suomalaisen lastensuojelun käytäntöjä tai alueellisia eroja hyvinvointialueiden välillä. |
| **Ei reaaliaikaista tietoa** | LLM:n koulutusdata on menneisyydestä. Tuoreet lakimuutokset (esim. LSL 1.1.2026) on päivitettävä RAG-indeksiin manuaalisesti. |
| **Numeerinen epätarkkuus** | Päivämäärät ja ikälaskelmat on aina tarkistettava alkuperäisestä dokumentista. |

---

## Projektin tila

| Vaihe | Status |
|---|---|
| LangGraph-graafi + persistence | ✅ Valmis |
| Docker Compose + Ollama-init | ✅ Valmis |
| RAG-indeksi (PGVector) | ✅ Valmis |
| Human-in-the-loop interrupt | ✅ Valmis |
| Audit trail | ✅ Valmis |
| Lakiuudistuksen (1.1.2026) integrointi RAG-indeksiin | 🔄 Kesken |
| UI sosiaalityöntekijälle | 📋 Suunniteltu |
| Testit + CI/CD | 📋 Suunniteltu |

---

## Linkit

- [Lastensuojelulaki 417/2007 (Finlex)](https://finlex.fi/eli?uri=http://data.finlex.fi/eli/sd/2007/417/ajantasa/2024-06-07/fin)
- [THL: Lastensuojelun käsikirja](https://thl.fi/julkaisut/kasikirjat/lastensuojelun-kasikirja)
- [STM: Lastensuojelun laatusuositus 2019:8](http://urn.fi/URN:ISBN:978-952-00-4067-3)
- [STM: Lastensuojelulainsäädännön kokonaisuudistus](https://stm.fi/hanke?tunnus=STM009:00/2024)
- [LangGraph dokumentaatio](https://docs.langchain.com/oss/python/langgraph/overview)
- [Ollama](https://ollama.com)
- [PGVector](https://github.com/pgvector/pgvector)
import os
import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from pipeline import get_pipeline
from chat_graph import build_chat_graph

st.set_page_config(
    page_title="Lastensuojelu — Elämäntapahtumaaikajana",
    page_icon="🏥",
    layout="wide",
)

SEVERITY_ICON = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "⛔"}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Potilas")
    patient_id = st.text_input("Potilaan ID", placeholder="esim. 12345")
    worker_id = st.text_input("Työntekijän ID", placeholder="esim. sw_001")

    uploaded_files = st.file_uploader(
        "Lisää asiakirjoja (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if st.button("Analysoi asiakirjat", type="primary") and patient_id and uploaded_files:
        with st.spinner("Analysoidaan asiakirjoja..."):
            docs = []
            for f in uploaded_files:
                tmp_path = f"/tmp/{f.name}"
                with open(tmp_path, "wb") as out:
                    out.write(f.read())
                docs.append({"path": tmp_path, "doc_type": "asiakirja"})

            pipeline = get_pipeline()
            config = {"configurable": {"thread_id": patient_id}}
            result = pipeline.invoke(
                {"patient_id": patient_id, "current_documents": docs},
                config=config,
            )
            st.session_state["pipeline_result"] = result
            st.session_state["pipeline_config"] = config
        st.success("Analyysi valmis.")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_timeline, tab_chat = st.tabs(["📋 Aikajana", "💬 Chat"])

# ── TAB 1: Timeline ────────────────────────────────────────────────────────────
with tab_timeline:
    st.header("10 merkittävintä elämäntapahtumaa")

    result = st.session_state.get("pipeline_result")
    if not result:
        st.info("Valitse potilas ja lisää asiakirjat vasemmalta paneelista.")
    else:
        for i, event in enumerate(result.get("top_10_timeline", []), 1):
            icon = SEVERITY_ICON.get(event.get("severity"), "⚪")
            with st.expander(f"{icon} {i}. [{event.get('date')}] {event.get('event_type')}"):
                st.write(event.get("description"))
                st.caption(f"Lähde: {event.get('source_document')}")
                st.caption(f"Oikeusperuste: {event.get('legal_basis')}")
                st.caption(f"Vakavuus: {event.get('severity')}/5")

        if not result.get("human_approved"):
            st.divider()
            st.subheader("Hyväksy aikajana")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Hyväksy", type="primary"):
                    pipeline = get_pipeline()
                    config = st.session_state.get("pipeline_config", {"configurable": {"thread_id": patient_id}})
                    final = pipeline.invoke(result["top_10_timeline"], config=config)
                    st.session_state["pipeline_result"] = final
                    st.success("Aikajana tallennettu.")
                    st.rerun()
            with col2:
                if st.button("🔄 Analysoi uudelleen"):
                    del st.session_state["pipeline_result"]
                    st.rerun()

# ── TAB 2: Chat ────────────────────────────────────────────────────────────────
with tab_chat:
    st.header("Kysy potilaan historiasta")

    if not patient_id:
        st.info("Valitse ensin potilas vasemmalta paneelista.")
    else:
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        if prompt := st.chat_input("Esim. 'Milloin viimeisin lastensuojeluilmoitus tehtiin?'"):
            st.session_state["chat_history"].append({"role": "user", "content": prompt})
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
                            {"messages": [HumanMessage(content=prompt)], "patient_id": patient_id},
                            config=config,
                        )
                    answer = response["messages"][-1].content
                    st.write(answer)
                    st.session_state["chat_history"].append({"role": "assistant", "content": answer})

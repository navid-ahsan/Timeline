import os
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage

from rag import get_patient_retriever


def build_chat_graph(checkpointer):
    llm = ChatOllama(
        model=os.environ.get("LLM_MODEL", "mistral"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        temperature=0.2,
    )

    def retrieve_and_answer(state: MessagesState) -> dict:
        patient_id = state.get("patient_id")
        question = state["messages"][-1].content

        retriever = get_patient_retriever(patient_id)
        docs = retriever.invoke(question)

        context_parts = []
        for doc in docs:
            source = doc.metadata.get("source", "tuntematon asiakirja")
            date = doc.metadata.get("date", "")
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

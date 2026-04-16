import os
from langchain_community.vectorstores import PGVector
from langchain_ollama import OllamaEmbeddings

_retriever = None


def get_embeddings():
    return OllamaEmbeddings(
        model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
    )


def get_retriever(k: int = 4):
    """Singleton retriever for the child welfare criteria knowledge base."""
    global _retriever
    if _retriever is None:
        vectorstore = PGVector(
            collection_name="lastensuojelu_kriteerit",
            connection_string=os.environ["DATABASE_URL"],
            embedding_function=get_embeddings(),
        )
        _retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    return _retriever


def get_patient_retriever(patient_id: str, k: int = 5):
    """Per-patient retriever — searches only this patient's indexed documents."""
    vectorstore = PGVector(
        collection_name=f"patient_{patient_id}",
        connection_string=os.environ["DATABASE_URL"],
        embedding_function=get_embeddings(),
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})


def index_patient_document(patient_id: str, text: str, metadata: dict):
    """Add a document chunk to the patient's vector collection."""
    vectorstore = PGVector(
        collection_name=f"patient_{patient_id}",
        connection_string=os.environ["DATABASE_URL"],
        embedding_function=get_embeddings(),
    )
    vectorstore.add_texts([text], metadatas=[metadata])

"""
Vectorize law documents and THL guidelines into the shared knowledge base.

Usage:
  docker compose exec app python scripts/build_knowledge_base.py \
    --sources data/knowledge_base/lastensuojelulaki.pdf \
              data/knowledge_base/thl_kasikirja.pdf
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from src.rag import get_embeddings

load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", required=True, help="PDF files to index")
    args = parser.parse_args()

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    all_docs = []

    for path in args.sources:
        print(f"Loading {path}...")
        loader = PyPDFLoader(path)
        pages = loader.load()
        chunks = splitter.split_documents(pages)
        for chunk in chunks:
            chunk.metadata["source"] = os.path.basename(path)
        all_docs.extend(chunks)

    print(f"Indexing {len(all_docs)} chunks into 'lastensuojelu_kriteerit'...")
    PGVector.from_documents(
        documents=all_docs,
        embedding=get_embeddings(),
        collection_name="lastensuojelu_kriteerit",
        connection_string=os.environ["DATABASE_URL"],
    )
    print("Done.")


if __name__ == "__main__":
    main()

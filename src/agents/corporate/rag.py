# agents/corporate/rag.py
import os, json, hashlib
from typing import List, Tuple
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
from langchain.vectorstores import FAISS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DOCS_PATH = os.path.join(DATA_DIR, "policy_corpus.json")  # vezi mai jos exemplu
INDEX_DIR = os.path.join(DATA_DIR, "faiss_index")
HASH_PATH = os.path.join(INDEX_DIR, "docs.hash")


def _require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return api_key


def _embedder() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        api_key=_require_api_key(),
    )


def _load_docs() -> List[Document]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DOCS_PATH):
        # pune aici politicile companiei (ce e semnat la început) – traseu, mijloc de transport, etc.
        sample = [
            {
                "id": "policy-1",
                "text": (
                    "Company commutes covered only when traveling from home to client office "
                    "by bicycle or public transit on the officially declared route. "
                    "Incidents must occur during work hours or on direct route. "
                    "Leisure detours are excluded."
                ),
            }
        ]
        with open(DOCS_PATH, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    docs = [
        Document(page_content=it["text"], metadata={"id": it.get("id", "doc")})
        for it in raw
    ]
    return docs


def _hash_docs(docs: List[Document]) -> str:
    payload = json.dumps(
        [{"t": d.page_content, "m": d.metadata} for d in docs], sort_keys=True
    )
    import hashlib

    return hashlib.sha256(payload.encode()).hexdigest()


def get_vectorstore():
    os.makedirs(INDEX_DIR, exist_ok=True)
    docs = _load_docs()
    h = _hash_docs(docs)
    if os.path.exists(HASH_PATH):
        try:
            with open(HASH_PATH, "r", encoding="utf-8") as f:
                oh = f.read().strip()
            if oh == h and any(os.scandir(INDEX_DIR)):
                return FAISS.load_local(
                    INDEX_DIR, _embedder(), allow_dangerous_deserialization=True
                )
        except Exception:
            pass
    vs = FAISS.from_documents(docs, _embedder())
    vs.save_local(INDEX_DIR)
    with open(HASH_PATH, "w", encoding="utf-8") as f:
        f.write(h)
    return vs


def retrieve(query: str, k: int = 4) -> List[str]:
    vs = get_vectorstore()
    hits = vs.similarity_search(query, k=k)
    return [d.page_content for d in hits]

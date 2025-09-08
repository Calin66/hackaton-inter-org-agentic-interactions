import os, json, hashlib
from typing import List, Tuple
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
from langchain.vectorstores import FAISS
from rapidfuzz import fuzz
from .db import get_procedure_catalog_rows

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_DIR = os.path.join(DATA_DIR, "faiss_index")
HASH_PATH = os.path.join(INDEX_DIR, "catalog.hash")

def _require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment. Load it via .env or export it before running.")
    return api_key

def _embedder() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        api_key=_require_api_key(),  # <-- explicit
    )

def _build_docs(rows: List[dict]) -> List[Document]:
    docs = []
    for r in rows:
        alias_text = ", ".join(r.get("aliases", []))
        text = f"{r['name']} | category: {r['category']} | price: {r['price']} | aliases: {alias_text}"
        docs.append(Document(
            page_content=text,
            metadata={"name": r["name"], "category": r["category"], "price": r["price"]}
        ))
    return docs

def _hash_rows(rows: List[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def get_vectorstore():
    rows = get_procedure_catalog_rows()
    if not rows:
        raise RuntimeError("procedure_catalog is empty. Insert procedures into DB before adjudication.")
    os.makedirs(INDEX_DIR, exist_ok=True)
    cat_hash = _hash_rows(rows)

    if os.path.exists(HASH_PATH):
        try:
            with open(HASH_PATH, "r", encoding="utf-8") as f:
                old_hash = f.read().strip()
            if old_hash == cat_hash and any(os.scandir(INDEX_DIR)):
                return FAISS.load_local(INDEX_DIR, _embedder(), allow_dangerous_deserialization=True)
        except Exception:
            pass  # rebuild if anything goes wrong

    docs = _build_docs(rows)
    vs = FAISS.from_documents(docs, _embedder())
    vs.save_local(INDEX_DIR)
    with open(HASH_PATH, "w", encoding="utf-8") as f:
        f.write(cat_hash)
    return vs

def match_procedure(query: str) -> Tuple[str, str, float, str]:
    """
    Returns (canonical_name, category, ref_price, debug_text)
    Combines semantic score (embeddings) with fuzzy ratio.
    """
    vs = get_vectorstore()
    hits = vs.similarity_search_with_score(query, k=4)
    best = None
    best_score = -1.0
    dbg = []
    for doc, sem_score in hits:
        meta = doc.metadata
        cand = meta["name"]
        fz = fuzz.token_sort_ratio(query, cand)
        sem_norm = 1.0/(1.0 + sem_score)
        composite = 0.6*sem_norm + 0.4*(fz/100.0)
        dbg.append(f"{cand}: sem={sem_score:.3f} semN={sem_norm:.3f} fz={fz} -> {composite:.3f}")
        if composite > best_score:
            best_score = composite
            best = meta
    assert best is not None
    return best["name"], best["category"], float(best["price"]), "\n".join(dbg)

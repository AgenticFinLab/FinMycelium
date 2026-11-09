from finmy.runner.source_documents import prepare_documents

def source_batch(documents, query, keywords, config, save_dir, **kwargs):
    docs = prepare_documents(documents, query, keywords, config, save_dir,
        document_id_offset=kwargs.get("document_id_offset", 0))
    return {"documents": docs, "decisions": [], "contents": [d["raw_text"] for d in docs]}

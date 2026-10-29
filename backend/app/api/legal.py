"""Exact consent text served from the same registry whose bytes are recorded at sign-up."""

import hashlib
import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from app.api.errors import not_found
from app.auth.login import DOCUMENTS
from app.legal.documents import VERSIONS, UnknownDocument, text_path

router = APIRouter(prefix="/legal")
PUBLIC_DOCUMENTS = DOCUMENTS | {"privacy", "cookies", "requisites"}


@router.get("/documents/{document}")
def document_text(request: Request, document: str,
                  version: Annotated[str | None, Query(max_length=32)] = None, locale: Literal["ru-RU"] = "ru-RU"):
    if document not in PUBLIC_DOCUMENTS:
        raise not_found()
    if version is None:
        version = VERSIONS[document][-1]
    try:
        raw = text_path(document, version, locale).read_bytes()
    except UnknownDocument:
        raise not_found() from None
    digest = hashlib.sha256(raw).hexdigest()
    approved = hmac.compare_digest(request.app.state.settings.signup_approved_hashes.get(document, ""), digest)
    return {"document": document, "version": version, "locale": locale, "sha256": digest,
            "text": raw.decode("utf-8"), "approved": approved}

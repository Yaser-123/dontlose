import pytest

from app.validate import NotFound


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DONTLOSE_DATA_DIR", str(tmp_path))
    from app import db as database

    database.reset_connection()
    yield
    database.reset_connection()


def test_manual_item_creates_real_deadlines(db):
    from app import store

    item_id = store.create_manual_item(
        {
            "title": "SoundBar 500",
            "merchant": "Acme",
            "category": "receipt",
            "price": "249.00",
            "currency": "USD",
            "purchase_date": "2026-03-02",
            "return_days": "30",
            "warranty_months": "12",
        }
    )
    detail = store.item_detail_record(item_id)
    by_kind = {row["kind"]: row for row in detail["deadlines"]}
    assert by_kind["return_window"]["due_date"] == "2026-04-01"
    assert by_kind["warranty_end"]["due_date"] == "2027-03-02"
    assert by_kind["return_window"]["provisional"] == 0
    assert "Using values you confirmed." in by_kind["return_window"]["basis"]


def test_rejecting_a_fact_removes_its_deadline(db):
    from app import store

    item_id = store.create_manual_item(
        {
            "title": "Headphones",
            "purchase_date": "2026-03-02",
            "return_days": "30",
            "warranty_months": "12",
        }
    )
    warranty = next(
        fact for fact in store.item_detail_record(item_id)["facts"] if fact["field_name"] == "warranty_months"
    )
    store.mutate_fact(warranty["id"], "reject")
    kinds = {row["kind"] for row in store.item_detail_record(item_id)["deadlines"]}
    assert kinds == {"return_window"}


def test_related_items_can_be_merged(db):
    from app import store

    first = store.create_manual_item(
        {
            "title": "SoundBar 500",
            "merchant": "Acme",
            "purchase_date": "2026-03-02",
            "return_days": "30",
        }
    )
    second = store.create_manual_item({"title": "SoundBar 500 case", "merchant": "Acme"})
    suggestions = store.suggestions_for(first)
    assert any(row["item_id"] == second for row in suggestions)
    store.merge_items(first, second)
    with pytest.raises(NotFound):
        store.item_detail_record(first)
    detail = store.item_detail_record(second)
    assert any(row["kind"] == "return_window" for row in detail["deadlines"])


def test_pdf_text_layer_does_not_need_tesseract(db, tmp_path):
    import pymupdf

    from app.ocr import extract_text

    path = tmp_path / "receipt.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "SoundBar 500\nMarch 2, 2026\nTotal 249.00")
    document.save(path)
    document.close()
    text, pages = extract_text(path)
    assert "SoundBar" in text
    assert pages == 1


def test_api_manual_item(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        created = client.post(
            "/items",
            json={
                "title": "City parking permit",
                "category": "document",
                "expiry_date": "2026-12-31",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["deadlines"][0]["due_date"] == "2026-12-31"
        assert body["deadlines"][0]["kind"] == "document_expiry"
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database"] is True

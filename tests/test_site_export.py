"""M1 - site export contract (spec 18 / Fase 5)."""

import ast
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.site_export import (
    DEAL_KEYS,
    DOCUMENT_KEYS,
    EXPORT_VERSION,
    HISTORY_POINT_KEYS,
    SiteHistoryPoint,
    SitePublication,
    build_document,
    serialize_document,
    utc_stamp,
    validate_document,
    write_document_atomic,
)

UTC = timezone.utc

GENERATED_AT = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)

PUBLISHED_AT = datetime(
    2026, 9, 28, 17, 2, 19, tzinfo=UTC
)


def make_publication(**overrides):
    fields = {
        "product_id": "B0TEST1",
        "title": "Test Product",
        "price": 75.0,
        "published_at": PUBLISHED_AT,
        "affiliate_url": (
            "https://www.amazon.com/dp/B0TEST1?tag=test-20"
        ),
        "score": 88.0,
        "label": "GREAT",
        "discount_vs_30d": 0.25,
        "source_query": "gaming mouse",
    }
    fields.update(overrides)

    return SitePublication(**fields)


def make_point(price, recorded_at):
    return SiteHistoryPoint(
        price=price,
        recorded_at=recorded_at,
    )


def build_single(publication, history=()):
    return build_document(
        [publication],
        {publication.product_id: list(history)},
        generated_at=GENERATED_AT,
    )


# ---------------------------------------------------------------------------
# Contract v1
# ---------------------------------------------------------------------------


def test_build_document_follows_contract_v1():
    document = build_single(
        make_publication(),
        [
            make_point(
                80.0,
                datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
            )
        ],
    )

    assert set(document) == set(DOCUMENT_KEYS)
    assert document["version"] == EXPORT_VERSION == 1
    assert document["generated_at"] == "2026-10-02T12:00:00Z"
    assert isinstance(document["deals"], list)

    deal = document["deals"][0]

    assert set(deal) == set(DEAL_KEYS)
    assert deal == {
        "id": "B0TEST1",
        "title": "Test Product",
        "price": 75.0,
        "currency": "USD",
        "previous_price": 80.0,
        "discount_pct": 25,
        "score": 88.0,
        "label": "GREAT",
        "image": None,
        "url": (
            "https://www.amazon.com/dp/B0TEST1?tag=test-20"
        ),
        "published_at": "2026-09-28T17:02:19Z",
        "source_query": "gaming mouse",
        "history": [
            {"date": "2026-09-27", "price": 80.0}
        ],
    }

    validate_document(document)


def test_empty_input_produces_empty_document():
    document = build_document(
        [],
        {},
        generated_at=GENERATED_AT,
    )

    assert document == {
        "version": 1,
        "generated_at": "2026-10-02T12:00:00Z",
        "deals": [],
    }

    validate_document(document)


def test_deals_are_sorted_newest_first_and_deduplicated():
    old_a = make_publication(
        product_id="A",
        title="Old A",
        published_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    new_a = make_publication(
        product_id="A",
        title="New A",
        published_at=datetime(2026, 9, 28, tzinfo=UTC),
    )
    product_b = make_publication(
        product_id="B",
        title="Product B",
        published_at=datetime(2026, 9, 27, 12, tzinfo=UTC),
    )

    document = build_document(
        [old_a, product_b, new_a],
        {},
        generated_at=GENERATED_AT,
    )

    deals = document["deals"]

    assert [deal["id"] for deal in deals] == ["A", "B"]
    assert deals[0]["title"] == "New A"
    assert len(deals) == 2


# ---------------------------------------------------------------------------
# Field rules
# ---------------------------------------------------------------------------


def test_score_zero_and_null_are_not_exported():
    zero = build_single(make_publication(score=0.0))
    missing = build_single(make_publication(score=None))

    assert zero["deals"][0]["score"] is None
    assert missing["deals"][0]["score"] is None
    assert zero["deals"][0]["label"] == "GREAT"


def test_discount_pct_conversion():
    with_discount = build_single(
        make_publication(discount_vs_30d=0.25)
    )
    without = build_single(
        make_publication(discount_vs_30d=None)
    )

    assert (
        with_discount["deals"][0]["discount_pct"] == 25
    )
    assert without["deals"][0]["discount_pct"] is None


def test_null_title_exports_empty_string_and_null_source():
    document = build_single(
        make_publication(
            title=None,
            source_query=None,
            label=None,
        )
    )

    deal = document["deals"][0]

    assert deal["title"] == ""
    assert deal["source_query"] is None
    assert deal["label"] is None

    validate_document(document)


def test_image_is_null_when_the_publication_has_none():
    document = build_single(make_publication())

    assert document["deals"][0]["image"] is None


def test_image_is_exported_when_the_publication_carries_it():
    document = build_single(
        make_publication(
            image_url="https://images.example.com/lego.jpg"
        )
    )

    deal = document["deals"][0]

    assert (
        deal["image"]
        == "https://images.example.com/lego.jpg"
    )
    assert set(deal) == set(DEAL_KEYS)

    validate_document(document)


def test_image_is_dropped_unless_it_is_an_absolute_url():
    unusable = (
        None,
        "",
        "   ",
        "images.example.com/lego.jpg",
        "javascript:alert(1)",
        42,
    )

    for value in unusable:
        document = build_single(
            make_publication(image_url=value)
        )

        assert document["deals"][0]["image"] is None, value


def test_validate_rejects_a_non_http_image():
    document = build_single(make_publication())
    document["deals"][0]["image"] = (
        "ftp://example.com/lego.jpg"
    )

    with pytest.raises(ValueError, match="image"):
        validate_document(document)


def test_price_is_rounded_to_two_decimals():
    document = build_single(
        make_publication(price=74.999)
    )

    assert document["deals"][0]["price"] == 75.0


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def test_utc_stamp_converts_fixed_offset_to_z():
    value = datetime(
        2026,
        9,
        28,
        15,
        0,
        0,
        tzinfo=timezone(timedelta(hours=2)),
    )

    assert utc_stamp(value) == "2026-09-28T13:00:00Z"


def test_utc_stamp_naive_uses_local_time_and_drops_microseconds():
    naive = datetime(2026, 9, 28, 17, 2, 19, 945242)

    expected = (
        naive.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    assert utc_stamp(naive) == expected
    assert utc_stamp(naive).endswith("Z")
    assert "." not in utc_stamp(naive)


# ---------------------------------------------------------------------------
# previous_price / history
# ---------------------------------------------------------------------------


def test_previous_price_is_latest_point_before_publication():
    history = [
        make_point(
            90.0,
            datetime(2026, 9, 20, tzinfo=UTC),
        ),
        make_point(
            85.0,
            datetime(2026, 9, 25, tzinfo=UTC),
        ),
        make_point(
            70.0,
            datetime(2026, 9, 30, tzinfo=UTC),
        ),
    ]

    document = build_single(make_publication(), history)

    deal = document["deals"][0]

    assert deal["previous_price"] == 85.0
    assert len(deal["history"]) == 3


def test_previous_price_null_without_older_history():
    history = [
        make_point(
            70.0,
            datetime(2026, 9, 30, tzinfo=UTC),
        )
    ]

    document = build_single(make_publication(), history)

    deal = document["deals"][0]

    assert deal["previous_price"] is None
    assert len(deal["history"]) == 1


def test_previous_price_null_when_history_is_empty():
    document = build_single(make_publication())

    deal = document["deals"][0]

    assert deal["previous_price"] is None
    assert deal["history"] == []


def test_history_is_windowed_capped_and_ascending():
    history = [
        make_point(
            float(index + 1),
            GENERATED_AT
            - timedelta(days=offset),
        )
        for offset, index in enumerate(range(40))
    ]
    history.append(
        make_point(
            999.0,
            GENERATED_AT - timedelta(days=100),
        )
    )

    document = build_single(
        make_publication(),
        history,
    )

    points = document["deals"][0]["history"]

    assert len(points) == 30

    dates = [point["date"] for point in points]

    assert dates == sorted(dates)
    assert all(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
        for date in dates
    )
    assert all(
        point["price"] != 999.0 for point in points
    )


def test_history_uses_stored_date_not_utc_conversion():
    document = build_single(
        make_publication(),
        [
            make_point(
                80.0,
                datetime(2026, 9, 27, 23, 30),
            )
        ],
    )

    assert (
        document["deals"][0]["history"][0]["date"]
        == "2026-09-27"
    )


# ---------------------------------------------------------------------------
# Whitelist / validation / secrets
# ---------------------------------------------------------------------------


def test_validate_rejects_extra_keys_anywhere():
    document = build_single(make_publication())

    document["telegram_token"] = "1:secret"

    with pytest.raises(ValueError, match="document keys"):
        validate_document(document)

    document = build_single(make_publication())
    document["deals"][0]["status"] = "PUBLISHED"

    with pytest.raises(ValueError, match="keys must be"):
        validate_document(document)

    document = build_single(
        make_publication(),
        [
            make_point(
                80.0,
                datetime(2026, 9, 27, tzinfo=UTC),
            )
        ],
    )
    document["deals"][0]["history"][0]["internal"] = 1

    with pytest.raises(ValueError, match="keys must be"):
        validate_document(document)


def test_validate_rejects_wrong_version_and_bad_dates():
    document = build_single(make_publication())
    document["version"] = 99

    with pytest.raises(ValueError, match="version"):
        validate_document(document)

    document = build_single(make_publication())
    document["generated_at"] = "2026-10-02 12:00:00"

    with pytest.raises(
        ValueError, match="generated_at"
    ):
        validate_document(document)

    document = build_single(make_publication())
    document["deals"][0]["published_at"] = "not-a-date"

    with pytest.raises(
        ValueError, match="published_at"
    ):
        validate_document(document)


def test_validate_rejects_non_contract_value_types():
    document = build_single(make_publication())
    document["deals"][0]["price"] = "75.0"

    with pytest.raises(ValueError, match="price"):
        validate_document(document)

    document = build_single(make_publication())
    document["deals"][0]["discount_pct"] = 25.5

    with pytest.raises(
        ValueError, match="discount_pct"
    ):
        validate_document(document)

    document = build_single(make_publication())
    document["deals"][0]["url"] = "javascript:void(0)"

    with pytest.raises(ValueError, match="url"):
        validate_document(document)


def test_serialized_document_has_no_secret_shapes():
    document = build_single(make_publication())
    text = serialize_document(document)

    assert re.search(
        r"\d{6,}:[A-Za-z0-9_-]{20,}", text
    ) is None

    for forbidden in (
        "token",
        "chat_id",
        "message_id",
        "password",
        "secret",
        "status",
        "db_path",
        "sqlite",
    ):
        assert forbidden not in text


def test_site_export_avoids_forbidden_dependencies():
    source = Path(
        "app/services/site_export.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(
                alias.name for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)

    roots = {name.split(".")[0] for name in imported}

    assert roots.isdisjoint(
        {"flask", "telebot", "requests", "dotenv"}
    )

    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "environ" not in attributes
    assert "getenv" not in attributes


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_document_atomic_creates_file(
    tmp_path,
):
    target = tmp_path / "site" / "deals.json"
    document = build_single(make_publication())

    write_document_atomic(target, document)

    assert target.is_file()
    assert json.loads(
        target.read_text(encoding="utf-8")
    ) == document
    assert list(target.parent.glob("*.tmp")) == []


def test_write_document_atomic_keeps_previous_file_on_invalid_document(
    tmp_path,
):
    target = tmp_path / "deals.json"

    write_document_atomic(
        target,
        build_single(make_publication()),
    )

    original = target.read_bytes()

    invalid = build_single(make_publication())
    invalid["version"] = 99

    with pytest.raises(ValueError):
        write_document_atomic(target, invalid)

    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_document_atomic_removes_temp_when_replace_fails(
    tmp_path,
    monkeypatch,
):
    import os

    target = tmp_path / "deals.json"

    write_document_atomic(
        target,
        build_single(make_publication()),
    )

    original = target.read_bytes()

    def failing_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        write_document_atomic(
            target,
            build_single(
                make_publication(title="Second")
            ),
        )

    monkeypatch.undo()

    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# CLI (export_site.py)
# ---------------------------------------------------------------------------


def create_database(path, rows):
    from app.services.database import connect

    connection = connect(str(path))

    try:
        for row in rows:
            connection.execute(
                """
                INSERT INTO publications (
                    product_id,
                    affiliate_url,
                    price,
                    published_at,
                    title,
                    score,
                    label,
                    discount_vs_30d,
                    source_query,
                    status,
                    channel
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

        connection.commit()
    finally:
        connection.close()


def publication_row(
    product_id,
    status="PUBLISHED",
    published_at="2026-09-28T17:02:19.945242",
    title="Test Product",
    channel="WEBSITE",
):
    return (
        product_id,
        f"https://www.amazon.com/dp/{product_id}"
        "?tag=test-20",
        75.0,
        published_at,
        title,
        88.0,
        "GREAT",
        0.25,
        "gaming mouse",
        status,
        channel,
    )


def test_cli_exports_published_rows_into_contract(
    tmp_path,
    capsys,
):
    import export_site

    db = tmp_path / "deal_hunter.db"

    create_database(
        db,
        [
            publication_row("B0PUBL1"),
            publication_row(
                "B0SEND",
                status="SENDING",
            ),
            publication_row(
                "B0DUP1",
                published_at="2026-09-27T10:00:00",
            ),
        ],
    )

    connection = sqlite3.connect(str(db))
    connection.execute(
        """
        INSERT INTO price_history (
            product_id, price, currency, recorded_at
        ) VALUES (?, ?, ?, ?)
        """,
        ("B0PUBL1", 80.0, "USD", "2026-09-27T12:00:00"),
    )
    connection.commit()
    connection.close()

    output = tmp_path / "site" / "deals.json"

    code = export_site.main(
        ["--db", str(db), "--out", str(output)]
    )

    captured = capsys.readouterr()

    assert code == 0
    assert "Exported 2 deals" in captured.out

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    ids = [deal["id"] for deal in document["deals"]]

    assert ids == ["B0PUBL1", "B0DUP1"]
    assert "B0SEND" not in ids

    published = document["deals"][0]

    assert published["previous_price"] == 80.0
    assert published["history"] == [
        {"date": "2026-09-27", "price": 80.0}
    ]


def test_cli_never_writes_to_the_database(
    tmp_path,
):
    import export_site

    db = tmp_path / "deal_hunter.db"
    create_database(db, [publication_row("B0PUBL1")])

    before = db.read_bytes()

    output = tmp_path / "site" / "deals.json"

    assert (
        export_site.main(
            ["--db", str(db), "--out", str(output)]
        )
        == 0
    )

    assert db.read_bytes() == before
    assert output.is_file()


def test_open_read_only_blocks_writes(tmp_path):
    import export_site

    db = tmp_path / "deal_hunter.db"
    create_database(db, [publication_row("B0PUBL1")])

    connection = export_site.open_read_only(db)

    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "DELETE FROM publications"
            )
    finally:
        connection.close()


def test_cli_missing_database_fails_cleanly(
    tmp_path,
    capsys,
):
    import export_site

    output = tmp_path / "deals.json"

    code = export_site.main(
        [
            "--db",
            str(tmp_path / "missing.db"),
            "--out",
            str(output),
        ]
    )

    captured = capsys.readouterr()

    assert code == 1
    assert "export failed" in captured.err
    assert not output.exists()


def test_cli_empty_database_exports_empty_deals(
    tmp_path,
    capsys,
):
    import export_site

    db = tmp_path / "deal_hunter.db"
    create_database(db, [])

    output = tmp_path / "site" / "deals.json"

    assert (
        export_site.main(
            ["--db", str(db), "--out", str(output)]
        )
        == 0
    )

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    assert document["deals"] == []
    assert "Exported 0 deals" in capsys.readouterr().out


def test_cli_exports_only_website_channel_rows(
    tmp_path,
    capsys,
):
    """Only WEBSITE rows are projected (spec 2.2/18.1)."""
    import export_site

    db = tmp_path / "deal_hunter.db"

    create_database(
        db,
        [
            publication_row(
                "B0WEB1",
                published_at="2026-09-28T17:02:19.945242",
                channel="WEBSITE",
            ),
            publication_row(
                "B0TEL1",
                published_at="2026-09-28T18:00:00.000000",
                channel="TELEGRAM",
            ),
            publication_row(
                "B0TEL2",
                published_at="2026-09-27T09:00:00.000000",
                channel="TELEGRAM",
            ),
        ],
    )

    output = tmp_path / "site" / "deals.json"

    code = export_site.main(
        ["--db", str(db), "--out", str(output)]
    )

    captured = capsys.readouterr()

    assert code == 0
    assert "Exported 1 deals" in captured.out

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    ids = [deal["id"] for deal in document["deals"]]

    assert ids == ["B0WEB1"]
    assert "B0TEL1" not in ids
    assert "B0TEL2" not in ids


def test_cli_telegram_only_database_exports_nothing(
    tmp_path,
    capsys,
):
    """A telegram-only run leaves the public site empty."""
    import export_site

    db = tmp_path / "deal_hunter.db"

    create_database(
        db,
        [
            publication_row("B0TEL1", channel="TELEGRAM"),
            publication_row("B0TEL2", channel="TELEGRAM"),
        ],
    )

    output = tmp_path / "site" / "deals.json"

    code = export_site.main(
        ["--db", str(db), "--out", str(output)]
    )

    captured = capsys.readouterr()

    assert code == 0
    assert "Exported 0 deals" in captured.out

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    assert document["deals"] == []


def test_cli_channel_filter_keeps_website_row_per_product(
    tmp_path,
):
    """The newest WEBSITE row wins, telegram rows never shadow it."""
    import export_site

    db = tmp_path / "deal_hunter.db"

    create_database(
        db,
        [
            publication_row(
                "B0SAME",
                title="Telegram newest",
                published_at="2026-09-29T10:00:00.000000",
                channel="TELEGRAM",
            ),
            publication_row(
                "B0SAME",
                title="Website older",
                published_at="2026-09-27T10:00:00.000000",
                channel="WEBSITE",
            ),
            publication_row(
                "B0SAME",
                title="Website newest",
                published_at="2026-09-28T10:00:00.000000",
                channel="WEBSITE",
            ),
        ],
    )

    output = tmp_path / "site" / "deals.json"

    assert (
        export_site.main(
            ["--db", str(db), "--out", str(output)]
        )
        == 0
    )

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    assert [deal["id"] for deal in document["deals"]] == ["B0SAME"]
    assert document["deals"][0]["title"] == "Website newest"


def test_cli_exports_the_publication_image_url(tmp_path):
    import export_site

    db = tmp_path / "deal_hunter.db"
    create_database(db, [publication_row("B0IMGED")])

    connection = sqlite3.connect(str(db))
    connection.execute(
        "UPDATE publications SET image_url = ? "
        "WHERE product_id = ?",
        ("https://images.example.com/lego.jpg", "B0IMGED"),
    )
    connection.commit()
    connection.close()

    output = tmp_path / "site" / "deals.json"

    assert (
        export_site.main(
            ["--db", str(db), "--out", str(output)]
        )
        == 0
    )

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    assert document["deals"][0]["image"] == (
        "https://images.example.com/lego.jpg"
    )


def test_cli_exports_null_image_for_a_row_without_one(
    tmp_path,
):
    import export_site

    db = tmp_path / "deal_hunter.db"
    create_database(db, [publication_row("B0NOIMG")])

    output = tmp_path / "site" / "deals.json"

    assert (
        export_site.main(
            ["--db", str(db), "--out", str(output)]
        )
        == 0
    )

    document = json.loads(
        output.read_text(encoding="utf-8")
    )

    validate_document(document)

    assert document["deals"][0]["image"] is None

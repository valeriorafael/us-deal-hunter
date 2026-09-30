from app.services.keyword_config import KeywordConfigLoader


def test_keyword_config_loader_reads_publication_limit(
    tmp_path,
):
    path = tmp_path / "keywords.json"

    path.write_text(
        """
        {
          "max_publications_per_run": 5,
          "keywords": [
            {
              "query": "gaming mouse"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    config = KeywordConfigLoader.load_config(
        str(path)
    )

    assert config.max_publications_per_run == 5
    assert len(config.keywords) == 1


def test_keyword_config_loader_rejects_invalid_publication_limit(
    tmp_path,
):
    path = tmp_path / "keywords.json"

    path.write_text(
        """
        {
          "max_publications_per_run": 0,
          "keywords": [
            {
              "query": "gaming mouse"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    try:
        KeywordConfigLoader.load_config(
            str(path)
        )
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError(
            "Invalid publication limit should raise ValueError."
        )


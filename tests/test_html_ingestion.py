from app.ingestion.parser import parse_document


def test_html_parser_keeps_notification_text_and_drops_scripts(tmp_path) -> None:
    source = tmp_path / "notification.aspx"
    source.write_text("""
    <html><head><style>.hidden { display:none; }</style><script>ignore_me()</script></head>
    <body><h1>Penal Charges in Loan Accounts</h1><p>Penal charges shall not be capitalised.</p></body></html>
    """, encoding="utf-8")

    parsed = parse_document(source, "text/html")

    assert parsed.page_count == 1
    assert "Penal Charges in Loan Accounts" in parsed.pages[0]
    assert "Penal charges shall not be capitalised." in parsed.pages[0]
    assert "ignore_me" not in parsed.pages[0]

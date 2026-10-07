from app.ingestion.parser import extract_html_text, parse_document


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


def test_extract_html_text_ignores_page_scripts_and_styles() -> None:
    text = extract_html_text("<style>volatile { value: 1; }</style><p>RBI lending rule</p><script>window.tick = Date.now()</script>")

    assert text == "RBI lending rule"


def test_notification_body_excludes_legacy_site_navigation_and_preserves_amendment_table() -> None:
    text = extract_html_text('''<html><body><div>Skip to main content Not Pressed</div>
    <div id="NotificationUser"><h2>Priority Sector Lending Amendment</h2>
    <p>The directions are modified as below:</p><table><tr><td>Paragraph 7</td>
    <td>Loans to eligible borrowers shall qualify from April 1.</td></tr></table></div>
    <div>Search the Website Annual Publications</div></body></html>''')
    assert "Paragraph 7" in text
    assert "Loans to eligible borrowers" in text
    assert "Search the Website" not in text
    assert "Not Pressed" not in text

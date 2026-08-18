import grafocodigo as mapa
import pytest

pytestmark = pytest.mark.browser


def test_layout_filtro_relacoes_e_exportacao(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "a.py").write_text(
        "import b\n\nclass A:\n"
        + "\n".join(f"    def m{i}(self): pass" for i in range(16)),
        encoding="utf-8",
    )
    (projeto / "b.py").write_text("import c\n", encoding="utf-8")
    (projeto / "c.py").write_text("pass\n", encoding="utf-8")
    (projeto / "isolado.md").write_text("# isolado\n", encoding="utf-8")
    nos, arestas, relatorio = mapa.construir_dados(projeto, detalhado=True)
    saida = tmp_path / "mapa.html"
    saida.write_text(
        mapa.gerar_html(nos, arestas, "Teste", relatorio), encoding="utf-8"
    )

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        erros = []
        page.on("pageerror", lambda erro: erros.append(str(erro)))
        page.goto(saida.as_uri())

        def colisoes():
            return page.evaluate("""() => {
              const cards=[...document.querySelectorAll('.modulo')].filter(e=>getComputedStyle(e).display!=='none').map(e=>({id:e.id,x:parseFloat(e.style.left),y:parseFloat(e.style.top),w:e.offsetWidth,h:e.offsetHeight}));
              const out=[]; for(let i=0;i<cards.length;i++) for(let j=i+1;j<cards.length;j++){const a=cards[i],b=cards[j];if(!(a.x+a.w+10<=b.x||b.x+b.w+10<=a.x||a.y+a.h+10<=b.y||b.y+b.h+10<=a.y))out.push([a.id,b.id]);} return out;
            }""")

        assert colisoes() == []
        page.click("#ocultar-solitarios")
        page.click("#btn-reorganizar")
        assert colisoes() == []

        page.click("#no-0")
        page.click('[data-dir="deps"]')
        page.click('[data-prof="all"]')
        assert page.locator("#evidencias .ev-item").count() >= 1
        assert "linha" in page.locator("#evidencias").inner_text()

        page.click("#btn-relatorio")
        assert page.locator("#report-overlay").get_attribute("class").endswith("ativo")
        assert "Analisados" in page.locator("#report-content").inner_text()
        page.click("#report-fechar")

        with page.expect_download() as download_info:
            page.click("#btn-exportar")
            page.click("text=SVG vetorial")
        assert download_info.value.suggested_filename.endswith(".svg")
        assert erros == []
        browser.close()

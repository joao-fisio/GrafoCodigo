from pathlib import Path

import app_gui
import pytest


def test_geracao_grafica_compartilha_nucleo_e_e_atomica(tmp_path):
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "a.py").write_text("import b\n", encoding="utf-8")
    (projeto / "b.py").write_text("pass\n", encoding="utf-8")
    saida = tmp_path / "resultado" / "grafo.html"

    resumo = app_gui.gerar_arquivo(projeto, saida)

    assert resumo["arquivos_analisados"] == 2
    assert resumo["conexoes"] == 1
    assert saida.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert not Path(str(saida) + ".tmp").exists()


def test_falha_nao_substitui_html_existente(tmp_path, monkeypatch):
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "a.py").write_text("pass\n", encoding="utf-8")
    saida = tmp_path / "grafo.html"
    saida.write_text("versão anterior", encoding="utf-8")

    def falhar(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(app_gui, "gerar_html", falhar)

    with pytest.raises(RuntimeError, match="falha simulada"):
        app_gui.gerar_arquivo(projeto, saida)

    assert saida.read_text(encoding="utf-8") == "versão anterior"
    assert not Path(str(saida) + ".tmp").exists()


@pytest.mark.parametrize("destino", ["", ".", ".."])
def test_destino_sem_nome_exibe_erro_claro(tmp_path, destino):
    projeto = tmp_path / "projeto"
    projeto.mkdir()

    with pytest.raises(ValueError, match="nome e o local"):
        app_gui.gerar_arquivo(projeto, Path(destino))


def test_destino_precisa_ser_html(tmp_path):
    projeto = tmp_path / "projeto"
    projeto.mkdir()

    with pytest.raises(ValueError, match=r"\.html ou \.htm"):
        app_gui.gerar_arquivo(projeto, tmp_path / "grafo.txt")

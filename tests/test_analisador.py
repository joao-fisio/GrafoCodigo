import json
from pathlib import Path

import grafocodigo as mapa
import pytest


def escrever(raiz: Path, relativo: str, conteudo: str, encoding="utf-8") -> Path:
    destino = raiz / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding=encoding)
    return destino


def por_arquivo(nos):
    return {no["arquivo"]: no for no in nos}


def aresta(nos, arestas, origem, destino):
    ids = {no["arquivo"]: no["id"] for no in nos}
    return next(
        a for a in arestas if a["de"] == ids[origem] and a["para"] == ids[destino]
    )


def test_python_tem_proveniencia_alta(tmp_path):
    escrever(tmp_path, "app.py", "from pacote.servico import executar\n")
    escrever(tmp_path, "pacote/servico.py", "def executar():\n    return 1\n")

    nos, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)

    a = aresta(nos, arestas, "app.py", "pacote/servico.py")
    assert a["confianca"] == "alta"
    assert a["evidencias"] == [
        {
            "arquivo": "app.py",
            "referencia": "pacote.servico",
            "linha": 1,
            "regra": "python_import_from",
            "confianca": "alta",
        }
    ]
    assert relatorio["resumo"]["erros"] == 0
    assert len(por_arquivo(nos)["app.py"]["sha256"]) == 64


def test_importacao_relativa_apenas_com_ponto_nao_falha(tmp_path):
    escrever(tmp_path, "pacote/__init__.py", "from . import util\n")
    escrever(tmp_path, "pacote/util.py", "valor = 1\n")

    nos, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)

    assert len(nos) == 2
    assert arestas == []
    assert relatorio["resumo"]["erros"] == 0


def test_heuristica_e_caminho_citado_nao_se_confundem(tmp_path):
    escrever(
        tmp_path, "main.ts", "import {x} from './dep';\nconst exemplo = 'nota.md';\n"
    )
    escrever(tmp_path, "dep.ts", "export const x = 1;\n")
    escrever(tmp_path, "nota.md", "texto\n")

    nos, arestas = mapa.construir_dados(tmp_path)

    assert aresta(nos, arestas, "main.ts", "dep.ts")["confianca"] == "media"
    assert aresta(nos, arestas, "main.ts", "nota.md")["confianca"] == "baixa"


def test_referencia_ambigua_nao_cria_aresta(tmp_path):
    escrever(tmp_path, "main.js", "import x from 'util';\n")
    escrever(tmp_path, "a/util.js", "export default 1;\n")
    escrever(tmp_path, "b/util.js", "export default 2;\n")

    _, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)

    assert arestas == []
    assert len(relatorio["ambiguas"]) == 1
    assert relatorio["ambiguas"][0]["candidatos"] == ["a/util.js", "b/util.js"]


def test_erro_python_e_exposto_sem_inventar_relacoes(tmp_path):
    escrever(tmp_path, "quebrado.py", "def x(:\n")
    escrever(tmp_path, "outro.py", "pass\n")

    nos, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)

    assert por_arquivo(nos)["quebrado.py"]["erro"] is True
    assert arestas == []
    assert relatorio["erros"] == [
        {"arquivo": "quebrado.py", "motivo": "sintaxe_python_invalida"}
    ]


def test_codificacao_python_declarada(tmp_path):
    destino = tmp_path / "latin.py"
    destino.write_bytes("# -*- coding: latin-1 -*-\nnome = 'ação'\n".encode("latin-1"))

    nos, _ = mapa.construir_dados(tmp_path)

    assert por_arquivo(nos)["latin.py"]["encoding"].lower() in {"iso-8859-1", "latin-1"}


def test_extensao_desconhecida_e_textual(tmp_path):
    escrever(tmp_path, "modulo.xyzabc", "function iniciar() {}\n")

    nos, _ = mapa.construir_dados(tmp_path)

    no = por_arquivo(nos)["modulo.xyzabc"]
    assert no["tipo"] == "XYZABC"
    assert no["parser"] == "heuristica_regex"


def test_saida_e_link_simbolico_sao_ignorados(tmp_path):
    escrever(tmp_path, "main.py", "pass\n")
    saida = escrever(tmp_path, "grafo.html", "gerado\n")
    externo = escrever(tmp_path.parent, "externo.py", "def segredo(): pass\n")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(externo)
    except OSError:
        pytest.skip("sistema sem suporte a link simbólico")

    nos, _, relatorio = mapa.construir_dados(tmp_path, detalhado=True, excluir={saida})

    assert [n["arquivo"] for n in nos] == ["main.py"]
    motivos = {i["arquivo"]: i["motivo"] for i in relatorio["ignorados"]}
    assert motivos == {"grafo.html": "arquivo_de_saida", "link.py": "link_simbolico"}


def test_resultado_deterministico(tmp_path):
    escrever(tmp_path, "z.py", "import a\n")
    escrever(tmp_path, "a.py", "pass\n")

    assert mapa.construir_dados(tmp_path, detalhado=True) == mapa.construir_dados(
        tmp_path, detalhado=True
    )


def test_html_offline_e_json_auditavel(tmp_path):
    escrever(tmp_path, "a.py", "import b\n")
    escrever(tmp_path, "b.py", "pass\n")
    nos, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)

    html = mapa.gerar_html(nos, arestas, "Projeto <privado>", relatorio)

    assert "https://" not in html
    assert "<script src=" not in html
    assert "cdnjs" not in html
    assert "default-src 'none'" in html
    assert "Projeto &lt;privado&gt;" in html
    assert '"evidencias"' in html
    assert '"sha256"' in html


def test_nome_hostil_nao_fecha_script(tmp_path):
    escrever(tmp_path, "arquivo.txt", "texto\n")
    nos, arestas, relatorio = mapa.construir_dados(tmp_path, detalhado=True)
    nome = 'x"><img src=x onerror=alert(1)>.txt'
    nos[0]["nome"] = nome
    nos[0]["arquivo"] = nome

    html = mapa.gerar_html(nos, arestas, "seguro", relatorio)

    assert "<img src=x onerror=alert(1)>" not in html
    assert "\\u003cimg src=x onerror=alert(1)\\u003e" in html


def test_auditoria_serializavel(tmp_path):
    escrever(tmp_path, "a.py", "pass\n")
    resultado = mapa.construir_dados(tmp_path, detalhado=True)
    json.dumps(resultado, ensure_ascii=False)

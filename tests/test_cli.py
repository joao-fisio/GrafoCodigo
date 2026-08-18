import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "mapear_codigo_atualizado.py"


def test_cli_gera_html_e_auditoria(tmp_path):
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "a.py").write_text("import b\n", encoding="utf-8")
    (projeto / "b.py").write_text("pass\n", encoding="utf-8")
    html = tmp_path / "mapa.html"
    audit = tmp_path / "mapa.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(projeto),
            "--saida",
            str(html),
            "--auditoria",
            str(audit),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert html.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert (
        json.loads(audit.read_text(encoding="utf-8"))["relatorio"]["resumo"]["conexoes"]
        == 1
    )


def test_modo_estrito_falha_com_ambiguidade(tmp_path):
    projeto = tmp_path / "projeto"
    (projeto / "x").mkdir(parents=True)
    (projeto / "y").mkdir()
    (projeto / "main.js").write_text("import x from 'util';\n", encoding="utf-8")
    (projeto / "x" / "util.js").write_text("export default 1;\n", encoding="utf-8")
    (projeto / "y" / "util.js").write_text("export default 2;\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(projeto),
            "--saida",
            str(tmp_path / "mapa.html"),
            "--estrito",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 3
    assert "Modo estrito" in proc.stderr


def test_interface_informa_versao_sem_abrir_janela():
    app = SCRIPT.with_name("app_gui.py")
    proc = subprocess.run(
        [sys.executable, str(app), "--version"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout.strip() == "GrafoCódigo 1.1.0"

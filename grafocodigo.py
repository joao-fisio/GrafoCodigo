# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Pedro Conceição

"""
mapear_codigo.py
----------------
Analisa uma pasta e gera um diagrama interativo (HTML).
Reconhece dezenas de linguagens e aceita qualquer nova extensão textual.
"""

import argparse
import ast
import hashlib
import html
import json
import mimetypes
import os
import platform
import re
import sys
import tokenize
from pathlib import Path

__version__ = "1.1.0"

EXTENSOES_CONHECIDAS = {
    ".py": "Python",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".json": "JSON",
    ".db": "Banco de Dados",
    ".sqlite": "Banco de Dados",
    ".sql": "SQL",
    ".md": "Markdown",
    ".txt": "Texto",
    ".env": "Config",
    ".yaml": "Config",
    ".yml": "Config",
    ".toml": "Config",
    ".ini": "Config",
    ".cfg": "Config",
    ".xml": "XML",
    ".csv": "Dados",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C/C++",
    ".cs": "C#",
    ".fs": "F#",
    ".fsx": "F#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".r": "R",
    ".R": "R",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".clj": "Clojure",
    ".cljs": "ClojureScript",
    ".groovy": "Groovy",
    ".gradle": "Gradle",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
    ".sol": "Solidity",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".ipynb": "Jupyter",
    ".tex": "LaTeX",
}

NOMES_CONHECIDOS = {
    "Dockerfile": "Docker",
    "Containerfile": "Container",
    "Makefile": "Make",
    "CMakeLists.txt": "CMake",
    "Gemfile": "Ruby",
    "Rakefile": "Ruby",
    "Jenkinsfile": "Groovy",
    "Procfile": "Config",
}

# Arquivos textuais de extensões ainda desconhecidas também entram no grafo.
# Assim o programa não fica preso a uma lista fechada de linguagens.
MAX_TAMANHO_TEXTO = 5 * 1024 * 1024

IGNORAR_PASTAS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "env",
}
IGNORAR_ARQUIVOS = set()


def resultado_vazio(linhas=0, erro=False, parser="nenhum", encoding=None):
    return {
        "referencias": [],
        "funcoes": [],
        "classes": [],
        "linhas": linhas,
        "erro": erro,
        "parser": parser,
        "encoding": encoding,
    }


def ler_texto(caminho: Path, python=False):
    """Lê texto de modo determinístico e informa o motivo de qualquer recusa."""
    try:
        if caminho.stat().st_size > MAX_TAMANHO_TEXTO:
            return None, None, "arquivo_maior_que_5_mib", None
        bruto = caminho.read_bytes()
        digest = hashlib.sha256(bruto).hexdigest()
        if b"\x00" in bruto[:8192]:
            return None, None, "conteudo_binario", digest
        if python:
            try:
                encoding, _ = tokenize.detect_encoding(
                    iter(bruto.splitlines(keepends=True)).__next__
                )
                return bruto.decode(encoding), encoding, None, digest
            except (SyntaxError, UnicodeError, StopIteration) as exc:
                return (
                    None,
                    None,
                    f"encoding_python_invalido:{type(exc).__name__}",
                    digest,
                )
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return bruto.decode(encoding), encoding, None, digest
            except UnicodeError:
                pass
        return None, None, "encoding_nao_suportado", digest
    except OSError as exc:
        return None, None, f"falha_de_leitura:{type(exc).__name__}", None


def extrair_py(caminho: Path, codigo: str, encoding: str) -> dict:
    try:
        tree = ast.parse(codigo)
    except SyntaxError:
        return resultado_vazio(len(codigo.splitlines()), True, "python_ast", encoding)

    referencias, funcoes, classes = [], [], []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                referencias.append(
                    {
                        "valor": alias.name,
                        "linha": node.lineno,
                        "regra": "python_import",
                        "confianca": "alta",
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            modulo = ("." * node.level) + (node.module or "")
            if modulo:
                referencias.append(
                    {
                        "valor": modulo,
                        "linha": node.lineno,
                        "regra": "python_import_from",
                        "confianca": "alta",
                    }
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcoes.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            for item in node.body:
                if isinstance(
                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not item.name.startswith("_"):
                    funcoes.append(f"{node.name}.{item.name}")

    linhas = len(codigo.splitlines())
    referencias = list(
        {(r["valor"], r["linha"], r["regra"]): r for r in referencias}.values()
    )
    return {
        "referencias": referencias,
        "funcoes": funcoes,
        "classes": classes,
        "linhas": linhas,
        "erro": False,
        "parser": "python_ast",
        "encoding": encoding,
    }


def extrair_generico(caminho: Path, texto: str, tipo: str, encoding: str) -> dict:
    """Extrai símbolos e referências locais sem depender de uma linguagem única."""
    refs = []
    padroes_refs = [
        (
            "import_export",
            r'\b(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?["\']([^"\']+)["\']',
        ),
        (
            "require_include",
            r'\b(?:require|require_relative|include|include_once|require_once)\s*\(?\s*["\']([^"\']+)["\']',
        ),
        ("import_quoted", r'\b(?:import|part|source)\s*["\']([^"\']+)["\']'),
        ("import_namespace", r"^\s*(?:use|using|import)\s+([A-Za-z_][\w.:/\\-]*)"),
        ("module_declaration", r"^\s*(?:mod)\s+([A-Za-z_]\w*)\s*;"),
        ("include_c", r'^\s*#\s*include\s*[<"]([^>"]+)[>"]'),
        ("html_asset", r'(?:src|href)\s*=\s*["\']([^"\']+)["\']'),
        ("css_import", r'@import\s+(?:url\()?\s*["\']?([^"\')\s;]+)'),
        ("lua_require", r'\b(?:require|dofile)\s*\(?\s*["\']([^"\']+)["\']'),
        ("shell_source", r'^\s*(?:source|\.)\s+["\']?([^"\'\s]+)'),
    ]
    for regra, padrao in padroes_refs:
        for match in re.finditer(padrao, texto, flags=re.MULTILINE):
            refs.append(
                {
                    "valor": match.group(1),
                    "linha": texto.count("\n", 0, match.start(1)) + 1,
                    "regra": regra,
                    "confianca": "media",
                }
            )

    # Captura caminhos locais explícitos em manifests/configurações e linguagens novas.
    padrao_caminho = r'["\']((?!https?://|//|data:|#)[^"\'\n]+\.[A-Za-z][A-Za-z0-9]{0,11})(?:[?#][^"\']*)?["\']'
    for match in re.finditer(padrao_caminho, texto):
        refs.append(
            {
                "valor": match.group(1),
                "linha": texto.count("\n", 0, match.start(1)) + 1,
                "regra": "caminho_citado",
                "confianca": "baixa",
            }
        )

    classes = []
    funcoes = []
    for padrao in (
        r"\b(?:class|interface|struct|enum|trait|protocol|record|module)\s+([A-Za-z_$][\w$]*)",
        r"\b(?:defmodule|defprotocol)\s+([A-Za-z_][\w.]*)",
    ):
        classes.extend(re.findall(padrao, texto))
    for padrao in (
        r"\b(?:def|function|func|fn|fun|sub)\s+([A-Za-z_$][\w$!?]*)\s*\(?",
        r"\b(?:public|private|protected|internal|static|async|export\s+)*\s*(?:void|int|string|bool|float|double|[A-Z]\w*(?:<[^>]+>)?)\s+([A-Za-z_$][\w$]*)\s*\(",
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
    ):
        funcoes.extend(re.findall(padrao, texto))

    limpar = lambda valores: list(dict.fromkeys(v for v in valores if len(v) <= 160))
    refs_unicas = {}
    ordem_conf = {"baixa": 0, "media": 1, "alta": 2}
    for ref in refs:
        ref["valor"] = ref["valor"].strip()
        if not ref["valor"]:
            continue
        chave = (ref["valor"], ref["linha"])
        if (
            chave not in refs_unicas
            or ordem_conf[ref["confianca"]]
            > ordem_conf[refs_unicas[chave]["confianca"]]
        ):
            refs_unicas[chave] = ref
    return {
        "referencias": sorted(
            refs_unicas.values(), key=lambda r: (r["linha"], r["valor"])
        ),
        "funcoes": limpar(funcoes),
        "classes": limpar(classes),
        "linhas": len(texto.splitlines()),
        "erro": False,
        "parser": "heuristica_regex",
        "encoding": encoding,
    }


def tipo_arquivo(caminho: Path) -> str:
    if caminho.name in NOMES_CONHECIDOS:
        return NOMES_CONHECIDOS[caminho.name]
    ext = caminho.suffix.lower()
    if ext in EXTENSOES_CONHECIDAS:
        return EXTENSOES_CONHECIDAS[ext]
    return ext[1:].upper() if ext else "Outro"


def avaliar_textual(caminho: Path):
    if (
        caminho.name in NOMES_CONHECIDOS
        or caminho.suffix.lower() in EXTENSOES_CONHECIDAS
    ):
        return True, None
    mime, _ = mimetypes.guess_type(caminho.name)
    if mime and not (
        mime.startswith("text/")
        or mime in {"application/json", "application/xml", "application/javascript"}
    ):
        return False, f"mime_nao_textual:{mime}"
    texto, _, motivo, _ = ler_texto(caminho, python=caminho.suffix.lower() == ".py")
    return texto is not None, motivo


def parece_textual(caminho: Path) -> bool:
    return avaliar_textual(caminho)[0]


def resolver_referencia(
    ref: str, origem: Path, por_rel: dict, por_modulo: dict, por_stem: dict
):
    ref = ref.strip().split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    if not ref or re.match(r"^(?:https?:|data:|mailto:|//)", ref):
        return set()

    candidatos = set()
    base_origem = origem.parent
    nivel = len(ref) - len(ref.lstrip("."))
    sem_pontos = ref.lstrip(".")
    if nivel and "/" not in sem_pontos:
        base_origem = origem.parent
        for _ in range(max(0, nivel - 1)):
            base_origem = base_origem.parent

    formas = {sem_pontos, sem_pontos.replace("::", "/").replace(".", "/")}
    formas.add(ref)
    extensoes = tuple(EXTENSOES_CONHECIDAS.keys())
    for forma in formas:
        forma = forma.strip("/ ")
        # Importações relativas como ``from . import modulo`` produzem apenas
        # pontos. Elas não identificam um arquivo por si sós e Path('.').with_suffix
        # falha no Windows com "has an empty name".
        if not forma or not forma.strip("."):
            continue
        for base in (base_origem, Path(".")):
            rel = (base / forma).as_posix().lstrip("./")
            tentativas = [rel]
            if not Path(rel).suffix:
                tentativas.extend(rel + ext for ext in extensoes)
                tentativas.extend(
                    (Path(rel) / ("index" + ext)).as_posix() for ext in extensoes
                )
                tentativas.extend(
                    (Path(rel) / ("mod" + ext)).as_posix() for ext in extensoes
                )
            for tentativa in tentativas:
                normal = os.path.normpath(tentativa).replace("\\", "/").lstrip("./")
                if normal in por_rel:
                    candidatos.add(por_rel[normal])

        modulo = str(Path(forma).with_suffix("")).replace("\\", "/").strip("/")
        candidatos.update(por_modulo.get(modulo, ()))
        candidatos.update(por_modulo.get(modulo.replace(".", "/"), ()))

    ultimo = Path(sem_pontos.replace("::", "/").replace(".", "/")).stem
    candidatos.update(por_stem.get(ultimo, ()))
    return candidatos


def construir_dados(pasta: Path, detalhado=False, excluir=None):
    excluir = {Path(p).resolve() for p in (excluir or set())}
    relatorio = {
        "versao_ferramenta": __version__,
        "pasta": pasta.name,
        "analisados": [],
        "ignorados": [],
        "pastas_ignoradas": [],
        "erros": [],
        "nao_resolvidas": [],
        "ambiguas": [],
    }
    todos_arquivos = []
    for raiz, dirs, arquivos in os.walk(pasta):
        dirs_validos = []
        for diretorio in sorted(dirs):
            caminho_dir = Path(raiz) / diretorio
            rel_dir = caminho_dir.relative_to(pasta).as_posix()
            if diretorio in IGNORAR_PASTAS:
                relatorio["pastas_ignoradas"].append(
                    {"pasta": rel_dir, "motivo": "politica_de_exclusao"}
                )
            elif caminho_dir.is_symlink():
                relatorio["pastas_ignoradas"].append(
                    {"pasta": rel_dir, "motivo": "link_simbolico"}
                )
            else:
                dirs_validos.append(diretorio)
        dirs[:] = dirs_validos
        for arq in sorted(arquivos):
            if arq in IGNORAR_ARQUIVOS:
                continue
            p = Path(raiz) / arq
            if p.resolve() in excluir:
                relatorio["ignorados"].append(
                    {
                        "arquivo": p.relative_to(pasta).as_posix(),
                        "motivo": "arquivo_de_saida",
                    }
                )
                continue
            if p.is_symlink():
                relatorio["ignorados"].append(
                    {
                        "arquivo": p.relative_to(pasta).as_posix(),
                        "motivo": "link_simbolico",
                    }
                )
                continue
            textual, motivo_textual = avaliar_textual(p)
            if textual:
                todos_arquivos.append(p)
            else:
                relatorio["ignorados"].append(
                    {
                        "arquivo": p.relative_to(pasta).as_posix(),
                        "motivo": motivo_textual or "nao_textual",
                    }
                )

    if not todos_arquivos:
        motivos = (
            ", ".join(sorted({i["motivo"] for i in relatorio["ignorados"]}))
            or "pasta vazia"
        )
        raise ValueError(
            f"Nenhum arquivo textual analisável em '{pasta}'. Motivos: {motivos}"
        )

    modulos = {}
    for arq in todos_arquivos:
        nome = arq.stem
        ext = arq.suffix.lower()
        rel = str(arq.relative_to(pasta))
        tipo = tipo_arquivo(arq)
        texto, encoding, motivo, digest = ler_texto(arq, python=ext == ".py")
        if texto is None:
            relatorio["ignorados"].append(
                {
                    "arquivo": rel.replace("\\", "/"),
                    "motivo": motivo or "falha_de_leitura",
                }
            )
            continue

        if ext == ".py":
            info = extrair_py(arq, texto, encoding)
        else:
            info = extrair_generico(arq, texto, tipo, encoding)

        chave = rel.replace("\\", "/")
        info["arquivo"] = rel
        info["nome"] = nome
        info["ext"] = ext
        info["tipo"] = tipo
        info["sha256"] = digest
        modulos[chave] = info
        relatorio["analisados"].append(
            {
                "arquivo": rel.replace("\\", "/"),
                "parser": info["parser"],
                "encoding": info["encoding"],
                "sha256": info["sha256"],
            }
        )
        if info.get("erro"):
            relatorio["erros"].append(
                {"arquivo": rel.replace("\\", "/"), "motivo": "sintaxe_python_invalida"}
            )

    if not modulos:
        motivos = (
            ", ".join(sorted({i["motivo"] for i in relatorio["ignorados"]}))
            or "falha desconhecida"
        )
        raise ValueError(
            f"Nenhum arquivo textual pôde ser analisado. Motivos: {motivos}"
        )

    stem_para_chaves = {}
    rel_para_chave = {}
    modulo_para_chaves = {}
    for chave, info in modulos.items():
        stem = info["nome"]
        stem_para_chaves.setdefault(stem, []).append(chave)
        rel_norm = Path(info["arquivo"]).as_posix()
        rel_para_chave[rel_norm] = chave
        modulo = str(Path(rel_norm).with_suffix("")).replace("\\", "/")
        modulo_para_chaves.setdefault(modulo, []).append(chave)

    nos, arestas = [], []
    ids = {}
    for i, (chave, info) in enumerate(modulos.items()):
        ids[chave] = i
        nos.append(
            {
                "id": i,
                "chave": chave,
                "nome": info["nome"],
                "arquivo": info["arquivo"],
                "ext": info["ext"],
                "tipo": info["tipo"],
                "linhas": info["linhas"],
                "funcoes": info["funcoes"],
                "classes": info["classes"],
                "erro": info.get("erro", False),
                "parser": info["parser"],
                "encoding": info["encoding"],
                "sha256": info["sha256"],
            }
        )

    evidencias_por_aresta = {}
    for chave, info in modulos.items():
        origem = Path(info["arquivo"])
        for ref in info["referencias"]:
            candidatos = resolver_referencia(
                ref["valor"],
                origem,
                rel_para_chave,
                modulo_para_chaves,
                stem_para_chaves,
            )
            candidatos.discard(chave)
            registro = {
                "arquivo": info["arquivo"],
                "referencia": ref["valor"],
                "linha": ref["linha"],
                "regra": ref["regra"],
                "confianca": ref["confianca"],
            }
            if len(candidatos) == 1:
                cand = next(iter(candidatos))
                evidencias_por_aresta.setdefault((ids[chave], ids[cand]), []).append(
                    registro
                )
            elif len(candidatos) > 1:
                relatorio["ambiguas"].append(
                    {
                        **registro,
                        "candidatos": sorted(modulos[c]["arquivo"] for c in candidatos),
                    }
                )
            else:
                relatorio["nao_resolvidas"].append(registro)

    ordem_conf = {"baixa": 0, "media": 1, "alta": 2}
    arestas = []
    for (de, para), evidencias in sorted(evidencias_por_aresta.items()):
        evidencias = sorted(
            evidencias, key=lambda e: (e["linha"], e["referencia"], e["regra"])
        )
        confianca = max((e["confianca"] for e in evidencias), key=ordem_conf.get)
        arestas.append(
            {"de": de, "para": para, "confianca": confianca, "evidencias": evidencias}
        )

    relatorio["resumo"] = {
        "arquivos_analisados": len(nos),
        "arquivos_ignorados": len(relatorio["ignorados"]),
        "pastas_ignoradas": len(relatorio["pastas_ignoradas"]),
        "erros": len(relatorio["erros"]),
        "conexoes": len(arestas),
        "referencias_nao_resolvidas": len(relatorio["nao_resolvidas"]),
        "referencias_ambiguas": len(relatorio["ambiguas"]),
    }
    if detalhado:
        return nos, arestas, relatorio
    return nos, arestas


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>__TITULO__</title>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f0f2fa; --surface: #fff; --border: #dde2f0; --border-h: #7b93e8;
  --accent: #4a6cf7; --accent-l: #eef1fe;
  --text: #1a1f36; --muted: #6b7594;
  --fn-bg:#eef1fe; --fn-c:#3451c7; --fn-b:#c5cffa;
  --cls-bg:#fdeef4; --cls-c:#b8275e; --cls-b:#f7bdd6;
  --shadow: 0 2px 12px rgba(74,108,247,.10);
  --shadow-h: 0 6px 24px rgba(74,108,247,.18);
}
body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; overflow:hidden; }

header { background:var(--surface); border-bottom:1px solid var(--border); padding:9px 16px; display:flex; align-items:center; gap:10px; flex-shrink:0; z-index:10; }
header h1 { font-size:13px; font-weight:600; color:var(--accent); white-space:nowrap; }
.search-box { padding:5px 11px; background:var(--bg); border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:13px; width:180px; outline:none; }
.search-box:focus { border-color:var(--accent); }
.btn { padding:5px 11px; background:var(--accent-l); border:1px solid var(--fn-b); border-radius:8px; color:var(--accent); font-size:12px; cursor:pointer; font-weight:500; white-space:nowrap; }
.btn:hover { background:#dde5fd; }
.stats { font-size:11px; color:var(--muted); white-space:nowrap; }
.sep { width:1px; height:20px; background:var(--border); flex-shrink:0; }

main { display:flex; flex:1; overflow:hidden; }

#sidebar { width:220px; flex-shrink:0; background:var(--surface); border-right:1px solid var(--border); display:flex; flex-direction:column; overflow:hidden; }
.sb-header { padding:10px 12px 8px; border-bottom:1px solid var(--border); }
.sb-title { font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; margin-bottom:8px; }
.sb-actions { display:flex; gap:6px; }
.sb-btn { flex:1; padding:4px 0; background:var(--bg); border:1px solid var(--border); border-radius:6px; font-size:11px; color:var(--muted); cursor:pointer; text-align:center; }
.sb-btn:hover { background:var(--accent-l); color:var(--accent); border-color:var(--fn-b); }
.sb-list { flex:1; overflow-y:auto; padding:6px 0; }
.sb-group { margin-bottom:2px; }
.sb-group-title { padding:5px 12px 3px; font-size:10px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:600; }
.sb-item { display:flex; align-items:center; gap:8px; padding:4px 12px; cursor:pointer; transition:background .1s; }
.sb-item:hover { background:var(--bg); }
.sb-item input[type=checkbox] { cursor:pointer; accent-color:var(--accent); width:13px; height:13px; flex-shrink:0; }
.sb-item-nome { font-size:12px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.sb-item.oculto .sb-item-nome { color:var(--muted); text-decoration:line-through; }
.ext-badge { font-size:10px; padding:1px 5px; border-radius:4px; font-weight:600; flex-shrink:0; }

.sb-filtros { padding:9px 12px; border-top:1px solid var(--border); background:var(--surface); }
.sb-toggle { display:flex; align-items:center; gap:7px; font-size:11px; color:var(--text); cursor:pointer; }
.sb-toggle input { accent-color:var(--accent); }
.rel-panel { padding:10px 12px; border-top:1px solid var(--border); background:var(--surface); }
.rel-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px; }
.rel-grid.direcao { grid-template-columns:1fr 1fr; }
.rel-btn { min-height:31px; padding:6px 7px; border:1px solid var(--border); background:var(--bg); border-radius:7px; font-size:10.5px; color:var(--muted); cursor:pointer; font-weight:600; transition:background .15s,border-color .15s,box-shadow .15s,color .15s; }
.rel-btn:hover { color:var(--accent); border-color:var(--border-h); background:var(--accent-l); }
.rel-btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.rel-btn.ativo { color:#fff; border-color:var(--accent); background:var(--accent); box-shadow:0 2px 7px rgba(74,108,247,.25); }
.rel-btn.limpar { color:#8b3a3a; }
.rel-btn.limpar:hover { color:#b42318; border-color:#f0a6a0; background:#fff0ef; }
.rel-status { margin-top:8px; padding:7px 8px; min-height:44px; border-radius:7px; background:var(--bg); font-size:10.5px; line-height:1.4; color:var(--muted); }
.evidencias { margin-top:7px; max-height:128px; overflow:auto; font-size:10px; color:var(--muted); }
.ev-item { padding:6px 7px; margin-bottom:5px; background:#fff; border:1px solid var(--border); border-radius:6px; line-height:1.35; }
.ev-ref { color:var(--text); font-family:'Cascadia Code','Consolas',monospace; word-break:break-all; }
.conf { display:inline-block; padding:1px 5px; border-radius:4px; font-size:9px; font-weight:700; text-transform:uppercase; }
.conf-alta { background:#dcfce7;color:#166534; } .conf-media { background:#fef3c7;color:#92400e; } .conf-baixa { background:#fee2e2;color:#991b1b; }
.sb-legenda { padding:10px 12px; border-top:1px solid var(--border); }
.leg-title { font-size:10px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:600; margin-bottom:6px; }
.leg-item { display:flex; align-items:center; gap:7px; margin-bottom:5px; font-size:12px; color:var(--text); }
.leg-box { width:28px; height:16px; border-radius:4px; flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:700; }

/* CANVAS */
#canvas { flex:1; overflow:hidden; position:relative; cursor:default; }
#svg-bg { position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; overflow:visible; transform-origin: 0 0; }
.conn-line { fill:none; stroke:#7b93e8; stroke-width:1.5; opacity:.4; transition:opacity .2s,stroke-width .2s; marker-end:url(#seta); }
.conn-line.conf-media { stroke:#d97706; } .conn-line.conf-baixa { stroke:#dc2626; stroke-dasharray:5 4; }
.conn-line.destaque { opacity:1; stroke-width:2.5; marker-end:url(#seta-d); }
.conn-line.desfocado { opacity:.05; }
#world { position:absolute; top:0; left:0; transform-origin:0 0; }

.modulo { position:absolute; background:var(--surface); border:1.5px solid var(--border); border-radius:12px; box-shadow:var(--shadow); width:210px; transition:box-shadow .2s,border-color .2s,opacity .2s; cursor:pointer; user-select:none; }
.modulo:hover { box-shadow:var(--shadow-h); border-color:var(--border-h); z-index:10; }
.modulo.selecionado { border-color:var(--accent); box-shadow:0 0 0 3px rgba(74,108,247,.2),var(--shadow-h); z-index:20; }
.modulo.multiselecionado { border-color:#7c3aed; box-shadow:0 0 0 3px rgba(124,58,237,.16),var(--shadow-h); z-index:19; }
.modulo.vizinho { border-color:var(--border-h); z-index:5; }
.modulo.desfocado { opacity:.16; }
.modulo.rel-1 { border-color:#2563eb; box-shadow:0 0 0 3px rgba(37,99,235,.15); z-index:18; }
.modulo.rel-2 { border-color:#0891b2; box-shadow:0 0 0 3px rgba(8,145,178,.13); z-index:17; }
.modulo.rel-3 { border-color:#059669; box-shadow:0 0 0 3px rgba(5,150,105,.12); z-index:16; }
.modulo.rel-4 { border-color:#7c3aed; box-shadow:0 0 0 3px rgba(124,58,237,.11); z-index:15; }
.mod-header { padding:9px 12px 7px; border-bottom:1px solid var(--border); border-radius:12px 12px 0 0; background:var(--tipo-bg,#f5f5f5); }
.mod-nome { font-size:13px; font-weight:600; word-break:break-word; color:var(--tipo-c,var(--text)); }
.mod-meta { font-size:11px; color:var(--muted); margin-top:2px; }
.mod-body { padding:7px 8px; display:flex; flex-direction:column; gap:3px; }
.item { padding:3px 8px; border-radius:5px; font-size:11.5px; font-family:'Cascadia Code','Fira Code','Consolas',monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.item.fn { background:var(--fn-bg); color:var(--fn-c); border:1px solid var(--fn-b); }
.item.cls { background:var(--cls-bg); color:var(--cls-c); border:1px solid var(--cls-b); font-weight:600; }

.mais { font-size:11px; color:var(--muted); padding:2px 8px 5px; font-style:italic; }
.btn-expandir { cursor: pointer; user-select: none; }
.btn-expandir:hover { color: var(--accent); text-decoration: underline; }

.hint { position:fixed; bottom:14px; left:50%; transform:translateX(-50%); font-size:11px; color:var(--muted); background:var(--surface); padding:6px 14px; border-radius:20px; border:1px solid var(--border); pointer-events:none; white-space:nowrap; z-index:5; }
::-webkit-scrollbar { width:5px; } ::-webkit-scrollbar-track { background:transparent; } ::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }

/* MODAL DE EXPORTAÇÃO CLEAN */
#export-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:1000; align-items:center; justify-content:center; }
#export-overlay.ativo { display:flex; }
.modal-overlay { display:none; position:fixed; inset:0; padding:28px; background:rgba(0,0,0,.45); z-index:1000; align-items:center; justify-content:center; }
.modal-overlay.ativo { display:flex; }
.report-card { background:var(--surface); border-radius:16px; padding:24px; width:min(820px,96vw); max-height:88vh; overflow:auto; box-shadow:0 8px 40px rgba(0,0,0,.18); }
.report-card h2 { font-size:18px; margin-bottom:8px; } .report-card h3 { font-size:13px; margin:18px 0 7px; }
.report-card p,.report-card li { font-size:12px; line-height:1.55; color:var(--muted); }
.report-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:8px; margin:14px 0; }
.report-metric { padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.report-metric strong { display:block; font-size:18px; color:var(--text); }
.report-list { max-height:150px; overflow:auto; border:1px solid var(--border); border-radius:8px; padding:8px 10px 8px 28px; }
.export-card { background:var(--surface); border-radius:16px; padding:28px 32px; width:480px; box-shadow:0 8px 40px rgba(0,0,0,.18); }
.export-card h2 { font-size:18px; font-weight:600; color:var(--text); margin-bottom:6px; }
.export-card p { font-size:13px; color:var(--muted); margin-bottom:20px; line-height:1.6; }
.export-opcoes { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
.export-btn { padding:12px 16px; border-radius:10px; border:1px solid var(--border); background:var(--bg); color:var(--text); font-size:13px; cursor:pointer; text-align:left; transition:background .15s; display:flex; align-items:center; gap:10px; }
.export-btn:hover { background:var(--accent-l); border-color:var(--fn-b); }
.export-btn span.icon { font-size:20px; }
.export-fechar { margin-top:16px; width:100%; padding:10px; border-radius:8px; border:none; background:transparent; color:var(--muted); font-size:13px; font-weight:500; cursor:pointer; }
.export-fechar:hover { color:var(--text); background: #f5f5f5;}

/* CORES POR TIPO */
.tipo-Python .mod-header { background:#eef1fe; } .tipo-Python .mod-nome { color:#3451c7; }
.tipo-HTML .mod-header { background:#fff3e0; } .tipo-HTML .mod-nome { color:#b45309; }
.tipo-CSS .mod-header { background:#e8f5e9; } .tipo-CSS .mod-nome { color:#2e7d32; }
.tipo-JavaScript .mod-header { background:#fffde7; } .tipo-JavaScript .mod-nome { color:#b07d00; }
.tipo-TypeScript .mod-header { background:#e3f2fd; } .tipo-TypeScript .mod-nome { color:#1565c0; }
.tipo-JSON .mod-header { background:#f3e5f5; } .tipo-JSON .mod-nome { color:#6a1b9a; }
.tipo-Config .mod-header { background:#fce4ec; } .tipo-Config .mod-nome { color:#880e4f; }
.tipo-SQL .mod-header { background:#e0f2f1; } .tipo-SQL .mod-nome { color:#00695c; }
.tipo-Banco-de-Dados .mod-header { background:#e0f2f1; } .tipo-Banco-de-Dados .mod-nome { color:#00695c; }
.tipo-Markdown .mod-header { background:#f5f5f5; } .tipo-Markdown .mod-nome { color:#424242; }
.tipo-Texto .mod-header { background:#f5f5f5; } .tipo-Texto .mod-nome { color:#424242; }
.tipo-XML .mod-header { background:#fbe9e7; } .tipo-XML .mod-nome { color:#bf360c; }
.tipo-Dados .mod-header { background:#e8f5e9; } .tipo-Dados .mod-nome { color:#1b5e20; }
@media print {
  header,#sidebar,.hint,#export-overlay,#report-overlay { display:none!important; }
  body,main,#canvas { overflow:visible!important; width:auto!important; height:auto!important; background:#fff!important; }
}
</style>
</head>
<body>

<header>
  <h1>&#9670; __TITULO__</h1>
  <input class="search-box" type="text" id="busca" placeholder="Buscar módulo..." />
  <div class="sep"></div>
  <button class="btn" id="btn-reorganizar">Reorganizar</button>
  <button class="btn" id="btn-relatorio">Relatório</button>
  <button class="btn" id="btn-exportar">&#8595; Exportar</button>
  <div class="sep"></div>
  <span class="stats" id="stat-info"></span>
</header>

<main>
  <div id="sidebar">
    <div class="sb-header">
      <div class="sb-title">Arquivos do projeto</div>
      <div class="sb-actions">
        <div class="sb-btn" id="sb-todos">Todos</div>
        <div class="sb-btn" id="sb-nenhum">Nenhum</div>
      </div>
    </div>
    <div class="sb-list" id="sb-list"></div>

    <div class="sb-filtros">
      <div class="sb-title" style="margin-bottom:6px">Visualização</div>
      <label class="sb-toggle">
        <input type="checkbox" id="ocultar-solitarios">
        Ocultar módulos solitários
      </label>
    </div>

    <div class="rel-panel">
      <div class="sb-title" style="margin-bottom:0">Relações do módulo</div>
      <div class="rel-grid direcao" role="group" aria-label="Direção das relações">
        <button class="rel-btn ativo" data-dir="deps" aria-pressed="true" title="Arquivos usados pelo módulo selecionado">&#8593; Ascendentes</button>
        <button class="rel-btn" data-dir="dependentes" aria-pressed="false" title="Arquivos que usam o módulo selecionado">&#8595; Descendentes</button>
        <button class="rel-btn" data-dir="ambos" aria-pressed="false" title="Mostra as duas direções">&#8597; Ambos</button>
        <button class="rel-btn limpar" id="rel-limpar" title="Limpa a seleção e os destaques">Limpar</button>
      </div>
      <div class="rel-grid" role="group" aria-label="Profundidade das relações">
        <button class="rel-btn ativo" data-prof="1" aria-pressed="true">1 nível</button>
        <button class="rel-btn" data-prof="2" aria-pressed="false">2 níveis</button>
        <button class="rel-btn" data-prof="3" aria-pressed="false">3 níveis</button>
        <button class="rel-btn" data-prof="all" aria-pressed="false">Todos</button>
      </div>
      <div class="rel-status" id="rel-status">Selecione um módulo para explorar suas relações.</div>
      <div class="evidencias" id="evidencias"></div>
    </div>

    <div class="sb-legenda">
      <div class="leg-title">Legenda</div>
      <div class="leg-item"><div class="leg-box" style="background:#eef1fe;color:#3451c7;border:1px solid #c5cffa;">ƒ</div> Função</div>
      <div class="leg-item"><div class="leg-box" style="background:#fdeef4;color:#b8275e;border:1px solid #f7bdd6;">■</div> Classe</div>
      <div class="leg-item"><div style="width:28px;height:2px;background:#7b93e8;border-radius:2px;flex-shrink:0;"></div> Importa / referencia</div>
    </div>
  </div>

  <div id="canvas">
    <svg id="svg-bg">
      <defs>
        <marker id="seta" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L0,6 L7,3 z" fill="#7b93e8" opacity=".6"/>
        </marker>
        <marker id="seta-d" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L0,6 L7,3 z" fill="#4a6cf7"/>
        </marker>
      </defs>
    </svg>
    <div id="world"></div>
  </div>
</main>

<div class="hint">Scroll: zoom &nbsp;·&nbsp; Fundo: mover &nbsp;·&nbsp; Shift+clique: multisseleção &nbsp;·&nbsp; Arraste um selecionado: mover grupo</div>

<div id="export-overlay">
  <div class="export-card">
    <h2>Exportar diagrama</h2>
    <p>Formatos locais e reprodutíveis. Nenhum dado é enviado pela rede.</p>
    <div class="export-opcoes">
      <button class="export-btn" onclick="exportar('html')">
        <span class="icon">&#128196;</span>
        <div><strong>HTML Interativo</strong><br><small style="color:var(--muted)">Arquivo completo e offline</small></div>
      </button>
      <button class="export-btn" onclick="exportar('svg')">
        <span class="icon">&#128444;</span>
        <div><strong>SVG vetorial</strong><br><small style="color:var(--muted)">Ideal para publicação</small></div>
      </button>
      <button class="export-btn" onclick="exportar('json')">
        <span class="icon">&#123;&#125;</span>
        <div><strong>Auditoria JSON</strong><br><small style="color:var(--muted)">Dados, evidências e diagnósticos</small></div>
      </button>
      <button class="export-btn" onclick="exportar('imprimir')">
        <span class="icon">&#128193;</span>
        <div><strong>Imprimir / PDF</strong><br><small style="color:var(--muted)">Pelo navegador</small></div>
      </button>
    </div>
    <button class="export-fechar" id="exp-fechar">Cancelar</button>
  </div>
</div>

<div id="report-overlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="report-title">
  <div class="report-card">
    <h2 id="report-title">Relatório de análise</h2>
    <p>Este mapa é uma análise estática. Relações Python obtidas por AST têm confiança alta; as demais são inferências heurísticas e devem ser verificadas.</p>
    <div id="report-content"></div>
    <button class="export-fechar" id="report-fechar">Fechar</button>
  </div>
</div>

<script>
const DADOS = __DADOS__;
const nos = DADOS.nos;
const arestas = DADOS.arestas;
const relatorio = DADOS.relatorio || {resumo:{},analisados:[],ignorados:[],pastas_ignoradas:[],erros:[],nao_resolvidas:[],ambiguas:[]};
const metadados = DADOS.metadados || {};

const importaPara = {}, importadoPor = {};
nos.forEach(n => { importaPara[n.id] = []; importadoPor[n.id] = []; });
arestas.forEach(a => { importaPara[a.de].push(a.para); importadoPor[a.para].push(a.de); });

const grau = {};
nos.forEach(n => grau[n.id] = importaPara[n.id].length + importadoPor[n.id].length);
function eSolitario(id) { return grau[id] === 0; }

const escolhido = {};
nos.forEach(n => escolhido[n.id] = true);
let ocultarSolitarios = false;
function estaVisivel(id) { return !!escolhido[id] && !(ocultarSolitarios && eSolitario(id)); }
function nosVisiveis() { return nos.filter(n => estaVisivel(n.id)); }

const tiposUnicos = {};
nos.forEach(n => {
  const t = n.tipo.replace(/\s+/g,'-');
  if (!tiposUnicos[t]) tiposUnicos[t] = { tipo: n.tipo, nos: [] };
  tiposUnicos[t].nos.push(n);
});

const CORES = {
  'Python':       { bg:'#eef1fe', c:'#3451c7' },
  'HTML':         { bg:'#fff3e0', c:'#b45309' },
  'CSS':          { bg:'#e8f5e9', c:'#2e7d32' },
  'JavaScript':   { bg:'#fffde7', c:'#b07d00' },
  'TypeScript':   { bg:'#e3f2fd', c:'#1565c0' },
  'JSON':         { bg:'#f3e5f5', c:'#6a1b9a' },
  'Config':       { bg:'#fce4ec', c:'#880e4f' },
  'SQL':          { bg:'#e0f2f1', c:'#00695c' },
  'Banco de Dados':{ bg:'#e0f2f1', c:'#00695c' },
  'Markdown':     { bg:'#f5f5f5', c:'#424242' },
  'Texto':        { bg:'#f5f5f5', c:'#424242' },
  'XML':          { bg:'#fbe9e7', c:'#bf360c' },
  'Dados':        { bg:'#e8f5e9', c:'#1b5e20' },
};

const sbList = document.getElementById('sb-list');
function corTipo(tipo) { return CORES[tipo] || { bg:'#f0f0f0', c:'#555' }; }
function esc(valor) {
  return String(valor).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function renderSidebar() {
  sbList.innerHTML = '';
  Object.values(tiposUnicos).forEach((grupo, grupoIndex) => {
    const cor = corTipo(grupo.tipo);
    const gDiv = document.createElement('div');
    gDiv.className = 'sb-group';
    
    const todosVisiveis = grupo.nos.every(n => escolhido[n.id]);
    const groupId = 'cb-group-' + grupoIndex;

    gDiv.innerHTML = `
      <div class="sb-group-title" style="display:flex; align-items:center; gap:6px; cursor:pointer;">
        <input type="checkbox" class="cb-grupo" id="${groupId}" ${todosVisiveis ? 'checked' : ''} style="cursor:pointer; accent-color:var(--muted); width:12px; height:12px;">
        <label for="${groupId}" style="cursor:pointer; flex:1; padding:4px 0;">${esc(grupo.tipo)}</label>
      </div>`;
      
    grupo.nos.forEach(no => {
      const item = document.createElement('div');
      item.className = 'sb-item' + (escolhido[no.id] ? '' : ' oculto');
      item.id = 'sb-' + no.id;
      item.innerHTML = `
        <input type="checkbox" ${escolhido[no.id] ? 'checked' : ''} data-id="${no.id}" aria-label="Exibir ${esc(no.arquivo)}">
        <span class="sb-item-nome" title="${esc(no.arquivo)}">${esc(no.nome)}${esc(no.ext)}</span>
        <span class="ext-badge" style="background:${cor.bg};color:${cor.c}">${esc(no.ext.replace('.','') || no.tipo)}</span>`;
      item.addEventListener('click', e => {
        if (e.target.tagName !== 'INPUT') selecionar(no, e.shiftKey);
      });
      gDiv.appendChild(item);
    });
    sbList.appendChild(gDiv);
  });

  sbList.querySelectorAll('.cb-grupo').forEach(cb => {
    cb.addEventListener('change', function(e) {
      e.stopPropagation();
      const isChecked = this.checked;
      const groupDiv = this.closest('.sb-group');
      groupDiv.querySelectorAll('.sb-item input[type=checkbox]').forEach(itemCb => {
        if (itemCb.checked !== isChecked) {
          itemCb.checked = isChecked;
          const id = +itemCb.getAttribute('data-id');
          escolhido[id] = isChecked;
          document.getElementById('sb-' + id).className = 'sb-item' + (isChecked ? '' : ' oculto');
        }
      });
      atualizarExibicao();
    });
  });

  sbList.querySelectorAll('.sb-item input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', function() {
      const id = +this.getAttribute('data-id');
      escolhido[id] = this.checked;
      document.getElementById('sb-' + id).className = 'sb-item' + (this.checked ? '' : ' oculto');
      const groupDiv = this.closest('.sb-group');
      const groupCb = groupDiv.querySelector('.cb-grupo');
      const allItems = Array.from(groupDiv.querySelectorAll('.sb-item input[type=checkbox]'));
      groupCb.checked = allItems.every(i => i.checked);
      atualizarExibicao();
    });
  });
}

document.getElementById('sb-todos').addEventListener('click', () => { nos.forEach(n => escolhido[n.id] = true); renderSidebar(); atualizarExibicao(); });
document.getElementById('sb-nenhum').addEventListener('click', () => { nos.forEach(n => escolhido[n.id] = false); renderSidebar(); atualizarExibicao(); });

document.getElementById('ocultar-solitarios').addEventListener('change', function() {
  ocultarSolitarios = this.checked;
  atualizarExibicao();
  reorganizarLayout(false);
});

document.querySelectorAll('.rel-btn[data-dir]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.rel-btn[data-dir]').forEach(b => b.classList.remove('ativo'));
    document.querySelectorAll('.rel-btn[data-dir]').forEach(b => b.setAttribute('aria-pressed', 'false'));
    btn.classList.add('ativo');
    btn.setAttribute('aria-pressed', 'true');
    relDirecao = btn.dataset.dir;
    aplicarRelacoes();
  });
});
document.querySelectorAll('.rel-btn[data-prof]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.rel-btn[data-prof]').forEach(b => { b.classList.remove('ativo'); b.setAttribute('aria-pressed', 'false'); });
    btn.classList.add('ativo');
    btn.setAttribute('aria-pressed', 'true');
    relProfundidade = btn.dataset.prof === 'all' ? Infinity : +btn.dataset.prof;
    aplicarRelacoes();
  });
});
document.getElementById('rel-limpar').addEventListener('click', limpar);

const pos = {};
nos.forEach(n => pos[n.id] = {x:0,y:0});
function hashTexto(texto) {
  let h = 2166136261;
  for (let i=0; i<texto.length; i++) { h ^= texto.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(36);
}
const ASSINATURA_GRAFO = hashTexto(JSON.stringify(nos.map(n => n.arquivo)) + JSON.stringify(arestas));
const CHAVE_MEMORIA = 'mapa_codigo_layout_v4_' + ASSINATURA_GRAFO;
function assinaturaVisibilidade() { return nosVisiveis().map(n => n.id).join(','); }
function salvarPosicoes() {
  const memoria = { versao:4, visiveis:assinaturaVisibilidade(), posicoes:pos };
  try { localStorage.setItem(CHAVE_MEMORIA, JSON.stringify(memoria)); } catch (e) {}
}

function tamanhoNo(id) {
  const el = elems[id];
  return { w: el ? el.offsetWidth : 210, h: el ? el.offsetHeight : 110 };
}

function componentesVisiveis() {
  const ids = new Set(nosVisiveis().map(n => n.id));
  const vistos = new Set(), componentes = [];
  [...ids].forEach(inicio => {
    if (vistos.has(inicio)) return;
    const comp = [], fila = [inicio]; vistos.add(inicio);
    while (fila.length) {
      const id = fila.shift(); comp.push(id);
      [...(importaPara[id] || []), ...(importadoPor[id] || [])].forEach(v => {
        if (ids.has(v) && !vistos.has(v)) { vistos.add(v); fila.push(v); }
      });
    }
    componentes.push(comp);
  });
  return componentes.sort((a,b) => b.length-a.length || a[0]-b[0]);
}

function organizarComponente(ids) {
  const conjunto = new Set(ids), indeg = {}, camada = {};
  ids.forEach(id => indeg[id] = (importaPara[id] || []).filter(v => conjunto.has(v)).length);
  const fila = ids.filter(id => indeg[id] === 0).sort((a,b) => grau[b]-grau[a]);
  fila.forEach(id => camada[id] = 0);
  for (let i=0; i<fila.length; i++) {
    const id = fila[i];
    (importadoPor[id] || []).forEach(dep => {
      if (!conjunto.has(dep)) return;
      camada[dep] = Math.max(camada[dep] || 0, camada[id] + 1);
      if (--indeg[dep] === 0) fila.push(dep);
    });
  }
  // Ciclos ficam juntos, em uma camada próxima de seus vizinhos já resolvidos.
  ids.filter(id => camada[id] === undefined).sort((a,b) => grau[b]-grau[a]).forEach(id => {
    const c = [...importaPara[id], ...importadoPor[id]].filter(v => camada[v] !== undefined).map(v => camada[v]);
    camada[id] = c.length ? Math.round(c.reduce((s,v)=>s+v,0)/c.length) : 0;
  });

  const linhas = {};
  ids.forEach(id => (linhas[camada[id]] ||= []).push(id));
  Object.values(linhas).forEach(lista => lista.sort((a,b) => grau[b]-grau[a] || nos[a].nome.localeCompare(nos[b].nome)));
  const GAP_X = 30, GAP_Y = 62;
  const medidas = {};
  ids.forEach(id => medidas[id] = tamanhoNo(id));
  const dadosLinhas = Object.keys(linhas).map(Number).sort((a,b)=>a-b).map(c => {
    const lista = linhas[c], largura = lista.reduce((s,id)=>s+medidas[id].w,0) + Math.max(0,lista.length-1)*GAP_X;
    const altura = Math.max(...lista.map(id=>medidas[id].h));
    return {lista, largura, altura};
  });
  const largura = Math.max(...dadosLinhas.map(l=>l.largura), 210);
  let y = 0; const locais = {};
  dadosLinhas.forEach(linha => {
    let x = (largura-linha.largura)/2;
    linha.lista.forEach(id => { locais[id] = {x, y}; x += medidas[id].w + GAP_X; });
    y += linha.altura + GAP_Y;
  });
  return { locais, largura, altura:Math.max(1,y-GAP_Y) };
}

function calcularLayout() {
  nos.forEach(n => pos[n.id] = {x:0,y:0});
  const blocos = componentesVisiveis().map(organizarComponente);
  const area = blocos.reduce((s,b)=>s+(b.largura+70)*(b.altura+70),0);
  const limiteLinha = Math.max(760, Math.min(1900, Math.sqrt(area)*1.45));
  let cursorX = 45, cursorY = 45, alturaFaixa = 0;
  blocos.forEach(bloco => {
    if (cursorX > 45 && cursorX + bloco.largura > limiteLinha) {
      cursorX = 45; cursorY += alturaFaixa + 80; alturaFaixa = 0;
    }
    Object.entries(bloco.locais).forEach(([id,p]) => pos[id] = {x:cursorX+p.x,y:cursorY+p.y});
    cursorX += bloco.largura + 80;
    alturaFaixa = Math.max(alturaFaixa, bloco.altura);
  });
}

function posicoesSemColisao(candidatas) {
  const ids = nosVisiveis().map(n=>n.id);
  for (let i=0; i<ids.length; i++) {
    const a = candidatas[ids[i]], ma = tamanhoNo(ids[i]);
    if (!a || !Number.isFinite(a.x) || !Number.isFinite(a.y) || Math.abs(a.x)>50000 || Math.abs(a.y)>50000) return false;
    for (let j=i+1; j<ids.length; j++) {
      const b = candidatas[ids[j]], mb = tamanhoNo(ids[j]);
      if (!b) return false;
      const separadas = a.x+ma.w+12 <= b.x || b.x+mb.w+12 <= a.x || a.y+ma.h+12 <= b.y || b.y+mb.h+12 <= a.y;
      if (!separadas) return false;
    }
  }
  return true;
}

function restaurarPosicoes() {
  try {
    const memoria = JSON.parse(localStorage.getItem(CHAVE_MEMORIA));
    if (!memoria || memoria.versao !== 4 || memoria.visiveis !== assinaturaVisibilidade()) return false;
    if (!posicoesSemColisao(memoria.posicoes)) return false;
    nosVisiveis().forEach(n => pos[n.id] = {...memoria.posicoes[n.id]});
    return true;
  } catch (e) { return false; }
}

function aplicarPosicoes() {
  nos.forEach(n => {
    if (!elems[n.id]) return;
    elems[n.id].style.left = pos[n.id].x + 'px';
    elems[n.id].style.top = pos[n.id].y + 'px';
  });
  desenharLinhas();
}

function reorganizarLayout(tentarMemoria=false) {
  if (!(tentarMemoria && restaurarPosicoes())) calcularLayout();
  aplicarPosicoes();
  salvarPosicoes();
  centralizarCamera();
}

let cam = { x: 20, y: 20, scale: 1 };
const canvas = document.getElementById('canvas');
const world = document.getElementById('world');
const svgBg = document.getElementById('svg-bg');

function applyCamera() {
  const t = `translate(${cam.x}px,${cam.y}px) scale(${cam.scale})`;
  world.style.transform = t;
  svgBg.style.transform = t;
  desenharLinhas();
}

function centralizarCamera() {
  const visiveis = nosVisiveis();
  if (visiveis.length === 0) return;
  
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  visiveis.forEach(n => {
    const el = document.getElementById('no-' + n.id);
    const elW = el ? el.offsetWidth : 210;
    const elH = el ? el.offsetHeight : 200;

    if (pos[n.id].x < minX) minX = pos[n.id].x;
    if (pos[n.id].y < minY) minY = pos[n.id].y;
    if (pos[n.id].x + elW > maxX) maxX = pos[n.id].x + elW;
    if (pos[n.id].y + elH > maxY) maxY = pos[n.id].y + elH;
  });

  const cw = canvas.clientWidth || window.innerWidth;
  const ch = canvas.clientHeight || window.innerHeight;

  const pad = 100;
  const w = (maxX - minX) + pad * 2;
  const h = (maxY - minY) + pad * 2;

  const scaleX = cw / w;
  const scaleY = ch / h;
  let s = Math.min(scaleX, scaleY);
  s = Math.max(0.15, Math.min(1, s)); 

  cam.scale = s;
  cam.x = (cw / 2) - ((minX + maxX) / 2) * s;
  cam.y = (ch / 2) - ((minY + maxY) / 2) * s;
  applyCamera();
}

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const r = canvas.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const f = e.deltaY < 0 ? 1.1 : 0.91;
  const ns = Math.max(0.05, Math.min(3, cam.scale * f));
  cam.x = mx - (mx - cam.x) * (ns / cam.scale);
  cam.y = my - (my - cam.y) * (ns / cam.scale);
  cam.scale = ns;
  applyCamera();
}, { passive: false });

let pan = null;
canvas.addEventListener('mousedown', e => {
  if (e.target === canvas || e.target === svgBg || e.target.tagName === 'svg' || e.target.tagName === 'path')
    pan = { x: e.clientX - cam.x, y: e.clientY - cam.y };
});
window.addEventListener('mousemove', e => {
  if (pan) { cam.x = e.clientX - pan.x; cam.y = e.clientY - pan.y; applyCamera(); }
});
window.addEventListener('mouseup', () => { pan = null; });
canvas.addEventListener('click', e => {
  if (e.target === canvas || e.target === svgBg || e.target.tagName === 'svg') limpar();
});

// FUNÇÃO GLOBAL DE EXPANDIR
window.toggleExpandir = function(e, btn) {
  e.stopPropagation();
  const ocultos = btn.previousElementSibling;
  if (ocultos.style.display === 'none') {
      ocultos.style.display = 'flex';
      btn.textContent = 'Ocultar...';
  } else {
      ocultos.style.display = 'none';
      const resto = ocultos.children.length;
      btn.textContent = `+ ${resto} mais...`;
  }
  requestAnimationFrame(() => reorganizarLayout(false));
};

const elems = {};
let dragAtual = null;

function criarModulos() {
  world.innerHTML = '';
  nos.forEach(no => {
    const div = document.createElement('div');
    const tipoClass = 'tipo-' + no.tipo.replace(/\s+/g,'-');
    div.className = `modulo ${tipoClass}`;
    div.id = 'no-' + no.id;

    const MAX = 7;
    const todosItens = [];
    no.classes.forEach(c => todosItens.push(`<div class="item cls" title="${esc(c)}">&#9632; ${esc(c)}</div>`));
    no.funcoes.forEach(f => todosItens.push(`<div class="item fn" title="${esc(f)}">&#402; ${esc(f)}</div>`));

    const visiveisHTML = todosItens.slice(0, MAX).join('');
    const ocultosHTML = todosItens.slice(MAX).join('');
    
    let bodyHTML = visiveisHTML;
    if (ocultosHTML) {
      bodyHTML += `
        <div class="itens-ocultos" style="display:none; flex-direction:column; gap:3px;">${ocultosHTML}</div>
        <div class="mais btn-expandir" onclick="toggleExpandir(event, this)" onmousedown="event.stopPropagation()">+ ${todosItens.length - MAX} mais...</div>
      `;
    }

    const cor = corTipo(no.tipo);
    div.style.setProperty('--tipo-bg', cor.bg);
    div.style.setProperty('--tipo-c', cor.c);
    div.setAttribute('role', 'button');
    div.setAttribute('tabindex', '0');
    div.setAttribute('aria-label', `${no.nome}${no.ext}, ${no.tipo}, ${no.linhas} linhas`);
    div.innerHTML = `
      <div class="mod-header">
        <div class="mod-nome">${esc(no.nome)}<span style="font-weight:400;opacity:.6">${esc(no.ext)}</span></div>
        <div class="mod-meta">${no.linhas} linhas &nbsp;·&nbsp; <span style="background:${cor.bg};color:${cor.c};padding:1px 5px;border-radius:4px;font-size:10px;font-weight:600">${esc(no.tipo)}</span></div>
      </div>
      <div class="mod-body">${bodyHTML}</div>`;

    div.style.left = pos[no.id].x + 'px';
    div.style.top = pos[no.id].y + 'px';
    div.style.display = estaVisivel(no.id) ? '' : 'none';
    div.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selecionar(no, e.shiftKey); }
    });

    div.addEventListener('mousedown', e => {
      e.stopPropagation();

      // Shift adiciona/remove da seleção sem iniciar drag imediato.
      if (e.shiftKey) {
        selecionar(no, true);
      } else if (!selecionados.has(no.id)) {
        selecionar(no, false);
      }

      const idsMover = selecionados.has(no.id) ? [...selecionados] : [no.id];
      const origens = {};
      idsMover.forEach(id => { origens[id] = { x: pos[id].x, y: pos[id].y }; });
      dragAtual = { sx:e.clientX, sy:e.clientY, ids:idsMover, origens, shift:e.shiftKey, no };
    });

    world.appendChild(div);
    elems[no.id] = div;
  });
}

window.addEventListener('mousemove', e => {
  if (!dragAtual) return;
  const dx = (e.clientX - dragAtual.sx) / cam.scale;
  const dy = (e.clientY - dragAtual.sy) / cam.scale;
  if (Math.abs(dx) < 2/cam.scale && Math.abs(dy) < 2/cam.scale) return;
  dragAtual.ids.forEach(id => {
    pos[id].x = dragAtual.origens[id].x + dx;
    pos[id].y = dragAtual.origens[id].y + dy;
    if (elems[id]) {
      elems[id].style.left = pos[id].x + 'px';
      elems[id].style.top = pos[id].y + 'px';
    }
  });
  desenharLinhas();
});

window.addEventListener('mouseup', e => {
  if (!dragAtual) return;
  const moveu = Math.abs(e.clientX-dragAtual.sx) >= 5 || Math.abs(e.clientY-dragAtual.sy) >= 5;
  if (!moveu && !dragAtual.shift) selecionar(dragAtual.no, false);
  dragAtual = null;
  salvarPosicoes();
});

function centro(id) {
  const el = elems[id];
  return { x: pos[id].x + el.offsetWidth / 2, y: pos[id].y + el.offsetHeight / 2 };
}

function desenharLinhas() {
  svgBg.querySelectorAll('path.conn-line').forEach(p => p.remove());
  arestas.forEach((a, indice) => {
    if (!estaVisivel(a.de) || !estaVisivel(a.para)) return;
    const de = centro(a.de), para = centro(a.para);
    const dx = para.x - de.x;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M${de.x},${de.y} C${de.x+dx*.4},${de.y} ${para.x-dx*.4},${para.y} ${para.x},${para.y}`);
    path.setAttribute('class', `conn-line conf-${a.confianca || 'baixa'}`);
    path.setAttribute('data-de', a.de);
    path.setAttribute('data-para', a.para);
    path.setAttribute('data-edge', indice);
    svgBg.appendChild(path);
  });
}

function atualizarExibicao() {
  nos.forEach(n => {
    if (elems[n.id]) elems[n.id].style.display = estaVisivel(n.id) ? '' : 'none';
  });
  [...selecionados].forEach(id => { if (!estaVisivel(id)) selecionados.delete(id); });
  const total = nosVisiveis().length;
  const conn = arestas.filter(a => estaVisivel(a.de) && estaVisivel(a.para)).length;
  const sol = nos.filter(n => estaVisivel(n.id) && eSolitario(n.id)).length;
  document.getElementById('stat-info').textContent = `${total} módulos · ${conn} conexões${sol ? ` · ${sol} solitários` : ''}`;
  desenharLinhas();
  aplicarRelacoes();
}

let selecionado = null;
const selecionados = new Set();
let relDirecao = 'deps';
let relProfundidade = 1;

function limparClassesRelacao() {
  Object.values(elems).forEach(el => {
    el.classList.remove('vizinho','desfocado','rel-1','rel-2','rel-3','rel-4');
  });
  svgBg.querySelectorAll('path.conn-line').forEach(p => p.classList.remove('destaque','desfocado'));
}

function atualizarClasseSelecao() {
  Object.values(elems).forEach(el => {
    const id = +el.id.replace('no-', '');
    el.classList.toggle('selecionado', selecionados.size === 1 && selecionados.has(id));
    el.classList.toggle('multiselecionado', selecionados.size > 1 && selecionados.has(id));
  });
}

function vizinhosDirecao(id, direcao) {
  if (direcao === 'deps') return importaPara[id] || [];
  if (direcao === 'dependentes') return importadoPor[id] || [];
  return [...new Set([...(importaPara[id] || []), ...(importadoPor[id] || [])])];
}

function distanciasRelacao(origem, direcao) {
  const dist = {[origem]: 0};
  const fila = [origem];
  let i = 0;
  while (i < fila.length) {
    const atual = fila[i++];
    vizinhosDirecao(atual, direcao).forEach(v => {
      if (estaVisivel(v) && dist[v] === undefined) {
        dist[v] = dist[atual] + 1;
        fila.push(v);
      }
    });
  }
  return dist;
}

function aplicarRelacoes() {
  limparClassesRelacao();
  atualizarClasseSelecao();

  if (selecionados.size !== 1) {
    document.getElementById('evidencias').innerHTML = '';
    document.getElementById('rel-status').textContent =
      selecionados.size > 1 ? `${selecionados.size} módulos selecionados. Relações exigem seleção única.` :
      'Selecione um módulo para explorar suas relações.';
    return;
  }

  const origem = [...selecionados][0];
  const noOrigem = nos.find(n => n.id === origem);
  const dist = distanciasRelacao(origem, relDirecao);
  let cont = 0;

  Object.entries(dist).forEach(([idStr, d]) => {
    const id = +idStr;
    if (id === origem || !estaVisivel(id)) return;
    const entra = d >= 1 && d <= relProfundidade;
    if (!entra) return;
    cont++;
    const classe = d >= 4 ? 'rel-4' : `rel-${d}`;
    if (elems[id]) elems[id].classList.add(classe);
  });

  Object.values(elems).forEach(el => {
    const id = +el.id.replace('no-', '');
    if (!estaVisivel(id) || id === origem) return;
    const d = dist[id];
    const entra = d !== undefined && d >= 1 && d <= relProfundidade;
    if (!entra) el.classList.add('desfocado');
  });

  svgBg.querySelectorAll('path.conn-line').forEach(p => {
    const de = +p.getAttribute('data-de'), para = +p.getAttribute('data-para');
    const dd = dist[de], dp = dist[para];
    let relevante = false;
    if (relDirecao === 'deps') relevante = dd !== undefined && dp !== undefined && dp === dd + 1;
    else if (relDirecao === 'dependentes') relevante = dd !== undefined && dp !== undefined && dd === dp + 1;
    else relevante = (dd !== undefined && dp !== undefined && Math.abs(dd-dp) === 1);

    if (relevante && Math.max(dd || 0, dp || 0) <= relProfundidade) p.classList.add('destaque');
    else p.classList.add('desfocado');
  });

  const rotulo = relDirecao === 'deps' ? 'dependências' : relDirecao === 'dependentes' ? 'dependentes' : 'relações';
  const prof = relProfundidade === Infinity ? 'todos os níveis' : `até ${relProfundidade} nível${relProfundidade>1?'is':''}`;
  document.getElementById('rel-status').textContent = `${noOrigem.nome}${noOrigem.ext}: ${cont} ${rotulo}, ${prof}.`;
  renderEvidencias();
}

function renderEvidencias() {
  const indices = [...svgBg.querySelectorAll('path.conn-line.destaque')].map(p => +p.dataset.edge);
  const itens = [];
  indices.forEach(indice => {
    const a = arestas[indice];
    (a.evidencias || []).forEach(ev => itens.push({a, ev}));
  });
  const area = document.getElementById('evidencias');
  if (!itens.length) { area.innerHTML = '<div class="ev-item">Nenhuma evidência no recorte selecionado.</div>'; return; }
  area.innerHTML = itens.slice(0, 80).map(({a,ev}) => `
    <div class="ev-item">
      <span class="conf conf-${esc(ev.confianca)}">${esc(ev.confianca)}</span>
      ${esc(nos[a.de].arquivo)} → ${esc(nos[a.para].arquivo)}<br>
      <span class="ev-ref">${esc(ev.referencia)}</span> · linha ${ev.linha} · ${esc(ev.regra)}
    </div>`).join('') + (itens.length>80 ? `<div class="ev-item">+ ${itens.length-80} evidências no JSON de auditoria.</div>` : '');
}

function selecionar(no, aditivo=false) {
  selecionado = no;
  if (aditivo) {
    if (selecionados.has(no.id)) selecionados.delete(no.id);
    else selecionados.add(no.id);
  } else {
    selecionados.clear();
    selecionados.add(no.id);
  }
  aplicarRelacoes();
}

function limpar() {
  selecionado = null;
  selecionados.clear();
  limparClassesRelacao();
  atualizarClasseSelecao();
  document.getElementById('rel-status').textContent = 'Selecione um módulo para explorar suas relações.';
  document.getElementById('evidencias').innerHTML = '';
}

document.getElementById('busca').addEventListener('input', function() {
  const q = this.value.toLowerCase().trim();
  if (!q) { limpar(); return; }
  const found = nos.find(n => (n.nome + n.ext).toLowerCase().includes(q) && estaVisivel(n.id));
  if (found) {
    selecionar(found);
    const r = canvas.getBoundingClientRect();
    cam.x = r.width / 2 - (pos[found.id].x + 105) * cam.scale;
    cam.y = r.height / 2 - (pos[found.id].y + 80) * cam.scale;
    applyCamera();
  }
});

document.getElementById('btn-reorganizar').addEventListener('click', () => {
  localStorage.removeItem(CHAVE_MEMORIA);
  reorganizarLayout(false);
  limpar();
});

// Relatório e exportação — implementados apenas com APIs nativas do navegador.
const overlay = document.getElementById('export-overlay');
const reportOverlay = document.getElementById('report-overlay');
document.getElementById('btn-exportar').addEventListener('click', () => overlay.classList.add('ativo'));
document.getElementById('exp-fechar').addEventListener('click', () => overlay.classList.remove('ativo'));
overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.remove('ativo'); });

function listaRelatorio(titulo, itens, formatar) {
  if (!itens || !itens.length) return `<h3>${esc(titulo)}</h3><p>Nenhum registro.</p>`;
  return `<h3>${esc(titulo)} (${itens.length})</h3><ul class="report-list">${itens.slice(0,200).map(i=>`<li>${formatar(i)}</li>`).join('')}${itens.length>200?`<li>+ ${itens.length-200} registros no JSON de auditoria.</li>`:''}</ul>`;
}

function renderRelatorio() {
  const r = relatorio.resumo || {};
  const metricas = [
    ['Analisados',r.arquivos_analisados||0],['Arquivos ignorados',r.arquivos_ignorados||0],['Pastas ignoradas',r.pastas_ignoradas||0],
    ['Conexões',r.conexoes||0],['Erros',r.erros||0],
    ['Não resolvidas',r.referencias_nao_resolvidas||0],['Ambíguas',r.referencias_ambiguas||0]
  ];
  document.getElementById('report-content').innerHTML = `
    <p>Ferramenta ${esc(relatorio.versao_ferramenta||metadados.versao||'')} · análise local · conteúdo-fonte não incorporado.</p>
    <div class="report-summary">${metricas.map(([k,v])=>`<div class="report-metric"><strong>${v}</strong>${esc(k)}</div>`).join('')}</div>
    ${listaRelatorio('Erros',relatorio.erros,i=>`${esc(i.arquivo)} — ${esc(i.motivo)}`)}
    ${listaRelatorio('Arquivos ignorados',relatorio.ignorados,i=>`${esc(i.arquivo)} — ${esc(i.motivo)}`)}
    ${listaRelatorio('Pastas ignoradas',relatorio.pastas_ignoradas,i=>`${esc(i.pasta)} — ${esc(i.motivo)}`)}
    ${listaRelatorio('Referências ambíguas',relatorio.ambiguas,i=>`${esc(i.arquivo)}:${i.linha} — <span class="ev-ref">${esc(i.referencia)}</span> → ${esc((i.candidatos||[]).join(', '))}`)}
    ${listaRelatorio('Referências não resolvidas',relatorio.nao_resolvidas,i=>`${esc(i.arquivo)}:${i.linha} — <span class="ev-ref">${esc(i.referencia)}</span> (${esc(i.regra)})`)}
    ${listaRelatorio('Manifesto analisado',relatorio.analisados,i=>`${esc(i.arquivo)} — ${esc(i.parser)}, ${esc(i.encoding||'')} — SHA-256 ${esc((i.sha256||'').slice(0,16))}…`)}
  `;
}
document.getElementById('btn-relatorio').addEventListener('click', () => { renderRelatorio(); reportOverlay.classList.add('ativo'); });
document.getElementById('report-fechar').addEventListener('click', () => reportOverlay.classList.remove('ativo'));
reportOverlay.addEventListener('click', e => { if (e.target === reportOverlay) reportOverlay.classList.remove('ativo'); });

function nomeBase() { return (document.title || 'mapa-codigo').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-zA-Z0-9_-]+/g,'-').replace(/^-|-$/g,'').toLowerCase() || 'mapa-codigo'; }
function baixar(conteudo, tipo, nome) {
  const url = URL.createObjectURL(new Blob([conteudo], {type:tipo}));
  const a = document.createElement('a'); a.href=url; a.download=nome; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function limitesExportacao() {
  const visiveis=nosVisiveis(); let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  visiveis.forEach(n=>{const m=tamanhoNo(n.id);minX=Math.min(minX,pos[n.id].x);minY=Math.min(minY,pos[n.id].y);maxX=Math.max(maxX,pos[n.id].x+m.w);maxY=Math.max(maxY,pos[n.id].y+m.h);});
  return {visiveis,minX,minY,maxX,maxY,pad:50,w:maxX-minX+100,h:maxY-minY+100};
}
function truncar(t,n=31){return t.length>n?t.slice(0,n-1)+'…':t;}
function gerarSvg() {
  const b=limitesExportacao(); if(!b.visiveis.length) return null;
  const dx=-b.minX+b.pad,dy=-b.minY+b.pad;
  const linhas=arestas.filter(a=>estaVisivel(a.de)&&estaVisivel(a.para)).map(a=>{const d=centro(a.de),p=centro(a.para),x1=d.x+dx,y1=d.y+dy,x2=p.x+dx,y2=p.y+dy,dd=x2-x1;const cor=a.confianca==='alta'?'#4a6cf7':a.confianca==='media'?'#d97706':'#dc2626';const dash=a.confianca==='baixa'?' stroke-dasharray="5 4"':'';return `<path d="M${x1},${y1} C${x1+dd*.4},${y1} ${x2-dd*.4},${y2} ${x2},${y2}" fill="none" stroke="${cor}" stroke-width="1.6" opacity=".65" marker-end="url(#arrow)"${dash}/>`;}).join('');
  const cards=b.visiveis.map(n=>{const m=tamanhoNo(n.id),x=pos[n.id].x+dx,y=pos[n.id].y+dy,c=corTipo(n.tipo);const itens=[...n.classes.map(v=>'■ '+v),...n.funcoes.map(v=>'ƒ '+v)].slice(0,7);return `<g transform="translate(${x} ${y})"><rect width="${m.w}" height="${m.h}" rx="12" fill="#fff" stroke="#cfd6e8"/><path d="M12 0H${m.w-12}Q${m.w} 0 ${m.w} 12V45H0V12Q0 0 12 0" fill="${c.bg}"/><text x="12" y="20" font-size="13" font-weight="600" fill="${c.c}">${esc(truncar(n.nome+n.ext,27))}</text><text x="12" y="37" font-size="10" fill="#6b7594">${n.linhas} linhas · ${esc(n.tipo)}</text>${itens.map((v,i)=>`<text x="12" y="${64+i*20}" font-size="10.5" font-family="monospace" fill="#334155">${esc(truncar(v))}</text>`).join('')}</g>`;}).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${b.w}" height="${b.h}" viewBox="0 0 ${b.w} ${b.h}" role="img" aria-label="Mapa de dependências ${esc(document.title)}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#64748b"/></marker></defs><rect width="100%" height="100%" fill="#f0f2fa"/>${linhas}${cards}<text x="${b.w-12}" y="${b.h-12}" text-anchor="end" font-size="9" fill="#6b7594">Gerado por GrafoCódigo ${esc(metadados.versao||'')}</text></svg>`;
}

function exportar(formato) {
  overlay.classList.remove('ativo'); const base=nomeBase();
  if(formato==='html') return baixar('<!DOCTYPE html>\n'+document.documentElement.outerHTML,'text/html;charset=utf-8',base+'.html');
  if(formato==='json') return baixar(JSON.stringify(DADOS,null,2),'application/json;charset=utf-8',base+'-auditoria.json');
  const svg=gerarSvg(); if(!svg) return alert('Nenhum módulo visível para exportar.');
  if(formato==='svg') return baixar(svg,'image/svg+xml;charset=utf-8',base+'.svg');
  if(formato==='imprimir') { const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'})); const janela=window.open(url,'_blank'); if(!janela) alert('Permita pop-ups e tente novamente.'); else setTimeout(()=>{janela.focus();janela.print();},500); setTimeout(()=>URL.revokeObjectURL(url),60000); }
}

// Iniciando a Interface
criarModulos();
renderSidebar();
atualizarExibicao();
// offsetWidth/offsetHeight forçam uma medição antes do primeiro quadro visível,
// evitando que todos os cartões apareçam empilhados durante a abertura.
reorganizarLayout(true);
</script>
</body>
</html>"""


def gerar_html(nos, arestas, titulo: str, relatorio=None) -> str:
    metadados = {
        "versao": __version__,
        "python": platform.python_version(),
        "plataforma": platform.system(),
        "metodo": "analise_estatica_local",
    }
    dados_js = json.dumps(
        {
            "nos": nos,
            "arestas": arestas,
            "relatorio": relatorio or {},
            "metadados": metadados,
        },
        ensure_ascii=False,
    )
    dados_js = dados_js.replace("<", "\\u003c").replace(">", "\\u003e")

    return HTML_TEMPLATE.replace("__TITULO__", html.escape(titulo, quote=True)).replace(
        "__DADOS__", dados_js
    )


def main():
    parser = argparse.ArgumentParser(
        description="Gera um diagrama interativo de dependências."
    )
    parser.add_argument("pasta", help="Pasta com os arquivos do projeto")
    parser.add_argument(
        "--saida",
        default="grafo_codigo.html",
        help="Nome do arquivo HTML de saída (padrão: grafo_codigo.html)",
    )
    parser.add_argument("--auditoria", help="Salva também o relatório completo em JSON")
    parser.add_argument(
        "--estrito",
        action="store_true",
        help="Retorna erro se houver arquivos com falha ou referências ambíguas",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    pasta = Path(args.pasta).resolve()
    if not pasta.is_dir():
        print(f"Erro: '{pasta}' não é uma pasta válida.")
        sys.exit(1)

    saida = Path(args.saida).resolve()
    auditoria = Path(args.auditoria).resolve() if args.auditoria else None
    print(f"Analisando localmente: {pasta}")
    try:
        nos, arestas, relatorio = construir_dados(
            pasta, detalhado=True, excluir={p for p in (saida, auditoria) if p}
        )
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print(f"  → {len(nos)} arquivos encontrados")
    print(f"  → {len(arestas)} conexões mapeadas")

    resumo = relatorio["resumo"]
    print(
        f"  → {resumo['arquivos_ignorados']} arquivos ignorados (documentados no relatório)"
    )
    print(
        f"  → {resumo['pastas_ignoradas']} pastas ignoradas pela política de exclusão"
    )
    print(f"  → {resumo['referencias_ambiguas']} referências ambíguas")
    print(
        f"  → {resumo['referencias_nao_resolvidas']} referências não resolvidas/externas"
    )

    html = gerar_html(nos, arestas, pasta.name, relatorio)
    saida.write_text(html, encoding="utf-8")
    if auditoria:
        auditoria.write_text(
            json.dumps(
                {"nos": nos, "arestas": arestas, "relatorio": relatorio},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  → auditoria: {auditoria}")
    print(f"\nPronto! Abra no navegador:\n  {saida}")
    if args.estrito and (relatorio["erros"] or relatorio["ambiguas"]):
        print(
            "Modo estrito: análise concluída com erros ou ambiguidades.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

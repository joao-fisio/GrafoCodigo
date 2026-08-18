# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Pedro Conceição

"""Interface gráfica minimalista do GrafoCódigo."""

import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path

from grafocodigo import __version__, construir_dados, gerar_html

try:
    from tkinter import (
        Canvas,
        Entry,
        Frame,
        Label,
        StringVar,
        Tk,
        filedialog,
        messagebox,
        ttk,
    )
except ImportError:  # permite usar e testar o núcleo em ambientes Python sem Tcl/Tk
    Canvas = Entry = Frame = Label = StringVar = Tk = filedialog = messagebox = ttk = (
        None
    )

BaseCanvas = Canvas if Canvas is not None else object


CORES = {
    "fundo": "#08151a",
    "painel": "#10252b",
    "painel_2": "#17343a",
    "borda": "#29515a",
    "texto": "#eaf6ef",
    "suave": "#91adb0",
    "verde": "#b8f34a",
    "verde_hover": "#d5ff7c",
    "ciano": "#47d7c4",
    "ambar": "#ffba49",
    "escuro": "#071014",
}


class BotaoPixel(BaseCanvas):
    """Botão acessível, desenhado em pixels e animado sem imagens externas."""

    def __init__(self, master, text, command, icon="seta", primary=False, width=180):
        self.command = command
        self.texto = text
        self.icone = icon
        self.primary = primary
        self.estado = "normal"
        self.hover = False
        self.pressionado = False
        super().__init__(
            master,
            width=width,
            height=48,
            background=CORES["painel"],
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", self._sair)
        self.bind("<ButtonPress-1>", self._pressionar)
        self.bind("<ButtonRelease-1>", self._soltar)
        self.bind("<Return>", self._teclado)
        self.bind("<space>", self._teclado)
        self.bind("<FocusIn>", lambda _e: self._desenhar())
        self.bind("<FocusOut>", lambda _e: self._desenhar())
        self._desenhar()

    def configure(self, cnf=None, **kwargs):
        estado = kwargs.pop("state", None)
        if estado is not None:
            self.estado = str(estado)
            super().configure(cursor="" if self.estado == "disabled" else "hand2")
            self._desenhar()
        if cnf or kwargs:
            return super().configure(cnf or {}, **kwargs)
        return None

    config = configure

    def _cores(self):
        if self.estado == "disabled":
            return CORES["painel_2"], CORES["borda"], "#647d80"
        if self.primary:
            fundo = CORES["verde_hover"] if self.hover else CORES["verde"]
            return fundo, CORES["verde_hover"], CORES["escuro"]
        fundo = "#21464c" if self.hover else CORES["painel_2"]
        return fundo, CORES["ciano"], CORES["texto"]

    def _desenhar_icone(self, x, y, cor):
        blocos = {
            "pasta": [
                (0, 1),
                (1, 1),
                (1, 0),
                (2, 1),
                (3, 1),
                (0, 2),
                (1, 2),
                (2, 2),
                (3, 2),
            ],
            "arquivo": [(0, 0), (1, 0), (2, 1), (0, 1), (0, 2), (1, 2), (2, 2)],
            "seta": [(0, 1), (1, 1), (2, 0), (2, 1), (2, 2), (3, 1)],
            "abrir": [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (3, 0), (3, 1)],
        }.get(self.icone, [])
        tamanho = 4
        for px, py in blocos:
            self.create_rectangle(
                x + px * tamanho,
                y + py * tamanho,
                x + (px + 1) * tamanho,
                y + (py + 1) * tamanho,
                fill=cor,
                outline=cor,
            )

    def _desenhar(self):
        self.delete("all")
        fundo, borda, texto = self._cores()
        deslocamento = 2 if self.pressionado else 0
        self.create_rectangle(
            2, 2, int(self["width"]) - 3, 44, fill=CORES["escuro"], outline=""
        )
        self.create_rectangle(
            1 + deslocamento,
            1 + deslocamento,
            int(self["width"]) - 5 + deslocamento,
            41 + deslocamento,
            fill=fundo,
            outline=borda,
            width=2,
        )
        if self.focus_get() == self:
            self.create_rectangle(
                5, 5, int(self["width"]) - 9, 37, outline=CORES["ambar"], dash=(2, 2)
            )
        self._desenhar_icone(16 + deslocamento, 14 + deslocamento, texto)
        self.create_text(
            42 + deslocamento,
            21 + deslocamento,
            text=self.texto,
            fill=texto,
            anchor="w",
            font=("Consolas", 10, "bold"),
        )

    def _entrar(self, _evento):
        if self.estado != "disabled":
            self.hover = True
            self._desenhar()

    def _sair(self, _evento):
        self.hover = self.pressionado = False
        self._desenhar()

    def _pressionar(self, _evento):
        if self.estado != "disabled":
            self.pressionado = True
            self._desenhar()

    def _soltar(self, evento):
        ativo = (
            self.pressionado
            and 0 <= evento.x <= int(self["width"])
            and 0 <= evento.y <= 48
        )
        self.pressionado = False
        self._desenhar()
        if ativo and self.estado != "disabled":
            self.command()

    def _teclado(self, _evento):
        if self.estado != "disabled":
            self.pressionado = True
            self._desenhar()
            self.after(90, self._ativar_teclado)
        return "break"

    def _ativar_teclado(self):
        self.pressionado = False
        self._desenhar()
        self.command()


class LogoGrafoPixel(BaseCanvas):
    """Pequeno grafo pixelado que pulsa e reage ao ponteiro."""

    def __init__(self, master):
        super().__init__(
            master,
            width=116,
            height=92,
            background=CORES["painel"],
            highlightthickness=0,
            cursor="hand2",
        )
        self.fase = 0
        self.rapido = False
        self.bind("<Enter>", lambda _e: self._mudar_ritmo(True))
        self.bind("<Leave>", lambda _e: self._mudar_ritmo(False))
        self.bind("<Button-1>", self._clique)
        self._animar()

    def _mudar_ritmo(self, rapido):
        self.rapido = rapido

    def _clique(self, _evento):
        self.fase += 3
        self._desenhar(CORES["ambar"])

    def _desenhar(self, destaque=None):
        self.delete("all")
        nos = [(18, 46), (55, 20), (55, 70), (94, 46)]
        for a, b in ((0, 1), (0, 2), (1, 3), (2, 3)):
            x1, y1 = nos[a]
            x2, y2 = nos[b]
            self.create_line(x1, y1, x2, y2, fill=CORES["borda"], width=4)
        ativo = self.fase % len(nos)
        for i, (x, y) in enumerate(nos):
            cor = destaque or (CORES["verde"] if i == ativo else CORES["ciano"])
            margem = 2 if i == ativo else 0
            self.create_rectangle(
                x - 7 - margem,
                y - 7 - margem,
                x + 7 + margem,
                y + 7 + margem,
                fill=cor,
                outline=CORES["escuro"],
                width=2,
            )
            self.create_rectangle(
                x - 2, y - 2, x + 2, y + 2, fill=CORES["texto"], outline=""
            )

    def _animar(self):
        self._desenhar()
        self.fase += 1
        self.after(180 if self.rapido else 520, self._animar)


def gerar_arquivo(pasta: Path, saida: Path):
    """Gera o HTML atomicamente; nunca deixa um arquivo parcial no destino."""
    pasta = Path(pasta)
    saida = Path(saida)
    if not pasta.is_dir():
        raise ValueError("Escolha uma pasta válida contendo o código.")
    if not saida.name or saida.name in {".", ".."}:
        raise ValueError("Escolha o nome e o local do arquivo HTML de saída.")
    if saida.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("O arquivo de saída precisa terminar em .html ou .htm.")

    # Construção por concatenação também evita depender de ``with_name`` em
    # implementações de Path específicas de cada sistema operacional.
    temporario = Path(f"{saida}.tmp")
    try:
        saida.parent.mkdir(parents=True, exist_ok=True)
        nos, arestas, relatorio = construir_dados(
            pasta, detalhado=True, excluir={saida, temporario}
        )
        temporario.write_text(
            gerar_html(nos, arestas, pasta.name, relatorio), encoding="utf-8"
        )
        os.replace(temporario, saida)
        return relatorio["resumo"]
    except Exception:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class GrafoCodigoApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"GrafoCódigo {__version__}")
        self.root.geometry("780x535")
        self.root.minsize(690, 500)
        self.root.configure(background=CORES["fundo"])

        self.pasta = StringVar()
        self.saida = StringVar()
        self.status = StringVar(value="Escolha a pasta que contém o código.")
        self.ultima_saida = None
        self.resultados = queue.Queue()

        self._configurar_estilo()
        self._montar_interface()

    def _configurar_estilo(self):
        estilo = ttk.Style(self.root)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure(
            "Pixel.Horizontal.TProgressbar",
            troughcolor=CORES["painel_2"],
            background=CORES["verde"],
            bordercolor=CORES["borda"],
            lightcolor=CORES["verde"],
            darkcolor=CORES["ciano"],
            thickness=9,
        )

    def _montar_interface(self):
        painel = Frame(
            self.root,
            background=CORES["painel"],
            highlightbackground=CORES["borda"],
            highlightthickness=2,
            padx=28,
            pady=24,
        )
        painel.grid(row=0, column=0, sticky="nsew")
        self.root.grid_columnconfigure(0, weight=1, pad=24)
        self.root.grid_rowconfigure(0, weight=1, pad=24)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        painel.columnconfigure(0, weight=1)

        cabecalho = Frame(painel, background=CORES["painel"])
        cabecalho.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        cabecalho.columnconfigure(0, weight=1)
        textos = Frame(cabecalho, background=CORES["painel"])
        textos.grid(row=0, column=0, sticky="w")
        Label(
            textos,
            text="GRAFO//CÓDIGO",
            background=CORES["painel"],
            foreground=CORES["texto"],
            font=("Consolas", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        Label(
            textos,
            text="GERADOR DE GRAFOS DE DEPENDÊNCIAS",
            background=CORES["painel"],
            foreground=CORES["verde"],
            font=("Consolas", 9, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        Label(
            textos,
            text="local • offline • auditável",
            background=CORES["painel"],
            foreground=CORES["suave"],
            font=("Consolas", 9),
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        LogoGrafoPixel(cabecalho).grid(row=0, column=1, rowspan=3, sticky="e")

        self._montar_campo(
            painel,
            row=1,
            numero="01",
            titulo="PASTA DO CÓDIGO",
            variavel=self.pasta,
            texto_botao="ESCOLHER PASTA",
            icone="pasta",
            comando=self.escolher_pasta,
        )
        self._montar_campo(
            painel,
            row=2,
            numero="02",
            titulo="ARQUIVO HTML DE SAÍDA",
            variavel=self.saida,
            texto_botao="ESCOLHER DESTINO",
            icone="arquivo",
            comando=self.escolher_saida,
        )

        botoes = Frame(painel, background=CORES["painel"])
        botoes.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        botoes.columnconfigure(0, weight=1)
        self.botao_gerar = BotaoPixel(
            botoes,
            text="GERAR GRAFO",
            icon="seta",
            primary=True,
            command=self.iniciar,
            width=470,
        )
        self.botao_gerar.grid(row=0, column=0, sticky="ew")
        self.botao_abrir = BotaoPixel(
            botoes, text="ABRIR HTML", icon="abrir", command=self.abrir_html, width=190
        )
        self.botao_abrir.grid(row=0, column=1, padx=(8, 0))
        self.botao_abrir.configure(state="disabled")

        self.progresso = ttk.Progressbar(
            painel, mode="indeterminate", style="Pixel.Horizontal.TProgressbar"
        )
        self.progresso.grid(row=4, column=0, sticky="ew", pady=(16, 9))
        status_linha = Frame(painel, background=CORES["painel"])
        status_linha.grid(row=5, column=0, sticky="ew")
        Label(
            status_linha,
            text="■",
            background=CORES["painel"],
            foreground=CORES["ambar"],
            font=("Consolas", 9),
        ).grid(row=0, column=0, sticky="n")
        Label(
            status_linha,
            textvariable=self.status,
            background=CORES["painel"],
            foreground=CORES["suave"],
            font=("Consolas", 9),
            wraplength=650,
            justify="left",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _montar_campo(
        self, master, row, numero, titulo, variavel, texto_botao, icone, comando
    ):
        caixa = Frame(master, background=CORES["painel"], pady=5)
        caixa.grid(row=row, column=0, sticky="ew", pady=(0, 11))
        caixa.columnconfigure(0, weight=1)
        rotulo = Frame(caixa, background=CORES["painel"])
        rotulo.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        Label(
            rotulo,
            text=numero,
            background=CORES["ciano"],
            foreground=CORES["escuro"],
            font=("Consolas", 8, "bold"),
            padx=5,
            pady=2,
        ).grid(row=0, column=0)
        Label(
            rotulo,
            text=titulo,
            background=CORES["painel"],
            foreground=CORES["texto"],
            font=("Consolas", 9, "bold"),
        ).grid(row=0, column=1, padx=(8, 0))
        entrada = Entry(
            caixa,
            textvariable=variavel,
            state="readonly",
            readonlybackground=CORES["escuro"],
            foreground=CORES["texto"],
            relief="flat",
            highlightbackground=CORES["borda"],
            highlightcolor=CORES["ciano"],
            highlightthickness=2,
            font=("Consolas", 9),
        )
        entrada.grid(row=1, column=0, sticky="ew", ipady=10)
        BotaoPixel(
            caixa, text=texto_botao, icon=icone, command=comando, width=205
        ).grid(row=1, column=1, padx=(8, 0))

    def escolher_pasta(self):
        escolha = filedialog.askdirectory(
            title="Escolha a pasta do código", mustexist=True
        )
        if not escolha:
            return
        self.pasta.set(escolha)
        if not self.saida.get():
            self.saida.set(
                str(Path(escolha).parent / f"grafo_{Path(escolha).name}.html")
            )
        self.status.set("Agora escolha onde salvar o HTML.")

    def escolher_saida(self):
        inicial = (
            Path(self.saida.get()).name if self.saida.get() else "grafo_codigo.html"
        )
        escolha = filedialog.asksaveasfilename(
            title="Salvar grafo como",
            defaultextension=".html",
            filetypes=[("Documento HTML", "*.html")],
            initialfile=inicial,
        )
        if escolha:
            self.saida.set(escolha)
            self.status.set("Tudo pronto. Clique em “Gerar grafo”.")

    def iniciar(self):
        pasta_texto = self.pasta.get().strip()
        saida_texto = self.saida.get().strip()
        if not pasta_texto:
            messagebox.showwarning(
                "Pasta necessária", "Escolha uma pasta válida contendo o código."
            )
            return
        if not saida_texto:
            messagebox.showwarning(
                "Destino necessário", "Escolha onde salvar o arquivo HTML."
            )
            return

        pasta = Path(pasta_texto)
        saida = Path(saida_texto)
        if not pasta.is_dir():
            messagebox.showwarning(
                "Pasta necessária", "Escolha uma pasta válida contendo o código."
            )
            return
        if not saida.name or saida.suffix.lower() not in {".html", ".htm"}:
            messagebox.showwarning(
                "Destino necessário", "Escolha um arquivo de saída com extensão .html."
            )
            return
        if saida.exists() and not messagebox.askyesno(
            "Substituir arquivo?",
            f"O arquivo já existe:\n{saida}\n\nDeseja substituí-lo?",
        ):
            return

        self.botao_gerar.configure(state="disabled")
        self.botao_abrir.configure(state="disabled")
        self.progresso.start(12)
        self.status.set("Analisando o projeto localmente…")
        threading.Thread(target=self._gerar, args=(pasta, saida), daemon=True).start()
        self.root.after(100, self._verificar_resultado)

    def _gerar(self, pasta: Path, saida: Path):
        try:
            resumo = gerar_arquivo(pasta, saida)
            mensagem = (
                f"Concluído: {resumo['arquivos_analisados']} arquivos, {resumo['conexoes']} conexões. "
                f"O relatório de auditoria está dentro do HTML."
            )
            self.resultados.put(("sucesso", saida, mensagem))
        except Exception as exc:  # noqa: BLE001 — fronteira da GUI: toda falha precisa ser exibida
            self.resultados.put(("erro", str(exc)))

    def _verificar_resultado(self):
        try:
            resultado = self.resultados.get_nowait()
        except queue.Empty:
            self.root.after(100, self._verificar_resultado)
            return
        if resultado[0] == "sucesso":
            self._sucesso(resultado[1], resultado[2])
        else:
            self._erro(resultado[1])

    def _sucesso(self, saida: Path, mensagem: str):
        self.progresso.stop()
        self.botao_gerar.configure(state="normal")
        self.botao_abrir.configure(state="normal")
        self.ultima_saida = saida
        self.status.set(mensagem)
        messagebox.showinfo(
            "Grafo criado", f"O grafo foi salvo com sucesso em:\n{saida}"
        )

    def _erro(self, mensagem: str):
        self.progresso.stop()
        self.botao_gerar.configure(state="normal")
        self.status.set(
            "Não foi possível gerar o grafo. Nenhum arquivo de saída incompleto foi mantido."
        )
        messagebox.showerror("Falha na análise", mensagem)

    def abrir_html(self):
        if self.ultima_saida and self.ultima_saida.exists():
            webbrowser.open(self.ultima_saida.resolve().as_uri())


def main():
    if "--version" in sys.argv:
        print(f"GrafoCódigo {__version__}")
        return 0
    if Tk is None:
        raise RuntimeError(
            "A interface gráfica requer uma instalação de Python com Tcl/Tk."
        )
    root = Tk()
    GrafoCodigoApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

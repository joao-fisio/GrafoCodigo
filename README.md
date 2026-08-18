# GrafoCódigo

Aplicação baseada em Python para gerar grafos interativos a partir das dependências encontradas entre os arquivos de um projeto de código.

## O que a ferramenta representa

- Cada bloco representa um arquivo textual analisado.
- Cada seta representa uma referência estática que pôde ser resolvida para outro arquivo do mesmo projeto.
- Python é analisado por AST e recebe confiança alta.
- Outras linguagens usam regras heurísticas documentadas e recebem confiança média ou baixa.
- O relatório mostra arquivos ignorados, erros, referências não resolvidas e ambiguidades.

O resultado não é um grafo de chamadas, não demonstra comportamento em tempo de execução e não prova que uma dependência será carregada durante a execução.

## Uso

### Aplicativo

Baixe o arquivo correspondente ao seu sistema na página **Releases** do GitHub, abra `GrafoCodigo` e:

1. escolha a pasta do código;
2. escolha onde salvar o HTML;
3. clique em **Gerar grafo**.

O aplicativo é portátil e não exige Python instalado. Windows, macOS e Linux usam executáveis diferentes; o workflow de release gera os três automaticamente.

### Terminal

Requer Python 3.9 ou superior e não possui dependências obrigatórias.

```bash
python grafocodigo.py caminho/do/projeto --saida grafo_codigo.html
```

Para gerar também um registro de auditoria:

```bash
python grafocodigo.py caminho/do/projeto \
  --saida grafo_codigo.html \
  --auditoria grafo_codigo.audit.json
```

O modo estrito retorna código de saída `3` quando há erro de sintaxe ou referência ambígua:

```bash
python grafocodigo.py caminho/do/projeto --estrito
```

Abra o HTML gerado diretamente no navegador. Ele funciona offline. A exportação oferece:

- HTML interativo;
- SVG vetorial para documentos e apresentações;
- JSON completo de auditoria;
- impressão ou PDF pelo navegador.

## Privacidade

A análise é local. O HTML não contém o código-fonte completo, mas contém nomes e caminhos de arquivos, nomes de classes e funções, contagens de linhas, referências resolvidas e hashes SHA-256. Revise o relatório antes de compartilhar um mapa de projeto confidencial. Links simbólicos são ignorados por padrão.

## Limites conhecidos

- Heurísticas podem produzir falsos positivos e falsos negativos.
- Imports externos aparecem como não resolvidos quando não correspondem a um arquivo local.
- Conteúdo binário e arquivos acima de 5 MiB são ignorados e registrados.
- A ferramenta não interpreta macros, resolução dinâmica, aliases configurados por ferramentas externas ou dependências carregadas em tempo de execução.
- O grafo deve ser revisado pelo usuário antes de ser compartilhado ou utilizado como documentação.

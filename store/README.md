# Publicar Altair na Microsoft Store

O projeto usa a rota **MSIX para aplicativo Win32 full trust**. O pacote inicia `Altair.exe` diretamente; ele nao inicia o antigo instalador interativo. O script de build empacota Python e dependencias com PyInstaller, baixa Node.js, instala os pacotes npm e inclui o Chromium do Puppeteer. Esses downloads ocorrem apenas na maquina de build. O MSIX resultante instala sem baixar dependencias.

O Altair ainda precisa de internet durante o uso para os provedores remotos de IA/voz e para recursos que dependem de servicos web. A chave e o provedor sao configurados pelo usuario no aplicativo.

## Preparar a maquina de build

- Windows 10/11 x64 e Windows SDK instalado (precisa de `makeappx.exe`).
- Ambiente `.venv` com `requirements.txt` e PyInstaller instalados.
- Node.js e npm nao precisam estar instalados: o build baixa o Node.js LTS portatil.
- A maquina de build precisa de internet para baixar Node.js, pacotes npm e o Chromium do Puppeteer.
- A API de controle remoto agora fica restrita a `127.0.0.1` por padrao, exige token e nao escuta a rede local sem configuracao. Para disponibiliza-la remotamente e preciso fornecer certificado TLS confiavel e chave privada por `ALTAIR_API_SSL_CERTFILE`/`ALTAIR_API_SSL_KEYFILE` e configurar `ALTAIR_API_HOST`; nao distribua uma chave privada no MSIX.
- A identidade do Partner Center informada para este app ja esta configurada no manifesto e no script: `GilbertoDellecrode.AltairAssistant`, `CN=7456B696-B094-46AF-AE42-85C96DD53848` e publicador `Gilberto Delle'crode`. Confira esses valores no Partner Center antes de submeter.

Instale/preencha os requisitos Python no ambiente de build, caso ainda nao estejam instalados:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

Gere o MSIX:

```powershell
powershell -ExecutionPolicy Bypass -File .\store\build_msix.ps1 `
  -SupportEmail 'dellecrodeengenharia@gmail.com' `
  -PrivacyPolicyUrl 'https://SEU-USUARIO.github.io/SEU-REPOSITORIO/privacidade-altair.html' `
  -Version '1.0.0.0'
```

O arquivo sai em `store/output/Altair.msix`. A cada atualizacao, incremente `Version` (quatro componentes numericos, como `1.0.1.0`). O build nao assina o MSIX: para distribuicao pela Store, a Microsoft assina depois da certificacao. Para instalar localmente, e necessario assinar com um certificado de teste confiavel na maquina; esse certificado de teste nao e o certificado de publicacao da Store.

## Testes antes da submissao

1. Instale o MSIX numa maquina limpa de teste e confirme que a janela principal abre sem permissao de administrador e sem rede.
2. Teste gravação/leitura de configuracoes, chaves, logs, memoria, perfil do Chrome e sessao WhatsApp; os dados devem permanecer em `%LOCALAPPDATA%\Altair`, fora da pasta instalada.
3. Teste as funcoes online separadamente com internet, chaves de API validas e conta WhatsApp de teste.
4. Execute o Windows App Certification Kit (WACK) na versao final assinada para teste e resolva todos os erros reportados.
5. Verifique tamanho do pacote, assinatura, arquitetura x64, atualizacao de versao, desinstalacao e preservacao/limpeza dos dados de usuario.

## Partner Center e materiais

- Criar/verificar conta de desenvolvedor, reservar o nome do app e criar uma submissao MSIX.
- Informar categoria, classificacao etaria, mercados, idiomas, preco/disponibilidade, descricao e recursos.
- Fornecer pelo menos uma captura real do app; quatro ou mais sao recomendadas. Os logos tecnicos em `Assets/` sao para o pacote e nao substituem todos os materiais da listagem.
- Fornecer URL de politica de privacidade e contatos de suporte. O Altair pode transmitir texto e audio para provedores escolhidos pelo usuario, usa WhatsApp Web e pode operar uma API local; descreva isso com precisao na politica e na listagem.
- Declarar o uso de IA generativa ao vivo na metadata e no Partner Center; a politica da Store tambem exige um canal para denunciar conteudo gerado. O app inclui permissao revogavel para servicos externos e abre um email de denuncia para o contato `SupportEmail`.
- Preencher as notas de certificacao com instrucoes para testar recursos que exigem chaves de API, login no WhatsApp ou servicos externos.
- Auditar licencas das dependencias Python, Node.js, Chromium e recursos de terceiros; incluir os avisos/licencas exigidos.
- Publicar uma versao final revisada de [`privacy-policy-draft.md`](privacy-policy-draft.md); substituir os campos pendentes por dados reais do publisher antes de enviar.

## Pendencias externas

O proprietario precisa fornecer a identidade Publisher do Partner Center, URL e responsavel legal pela politica de privacidade, contato de suporte e materiais reais de listagem. A certificacao e a publicacao so podem ser concluidas no Partner Center pelo titular da conta.

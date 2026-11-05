# Politica de privacidade do Altair — rascunho para revisao

> **Nao publique este rascunho sem preencher os campos entre colchetes e revisa-lo juridicamente.** A politica publicada deve corresponder aos provedores, configuracoes, mercados e versao final do aplicativo.

**Responsavel pelo tratamento:** [nome legal do publisher]  
**Contato de privacidade/suporte:** [email de contato]  
**Ultima atualizacao:** [data]

## Dados processados

O Altair pode processar, conforme os recursos que voce ativar:

- comandos, conversas, transcricoes e texto fornecido ao assistente;
- audio capturado pelo microfone quando voce usa os recursos de voz;
- arquivos que voce seleciona para leitura, resumo ou envio;
- texto de mensagens, arquivos e destinatarios que voce escolhe em acoes do WhatsApp;
- chaves de API, preferencias, nomes de modelos, configuracoes, memoria de arquivos, logs e dados locais de sessao.

O Altair nao precisa enviar todos esses dados em toda utilizacao. A escuta continua do microfone comeca desativada. O item **Menu > Permitir servicos externos** tambem comeca desativado e controla os recursos que enviam dados a servicos externos. A permissao pode ser revogada no mesmo menu. Sem permissao, a captura de audio para transcricao e as chamadas externas de IA, voz, clima/localizacao e envio pelo WhatsApp sao bloqueados; recursos locais continuam sujeitos a configuracao e disponibilidade.

## Servicos de terceiros

Quando voce ativa a permissao e usa o respectivo recurso, os dados necessarios podem ser enviados ao provedor configurado por voce, que pode incluir Groq, OpenAI, ElevenLabs ou um endpoint personalizado. Se voce usar WhatsApp, o aplicativo controla o WhatsApp Web local e transmite o conteudo que voce escolhe para o servico WhatsApp/Meta e os destinatarios selecionados. Consultas de clima/localizacao podem ser enviadas a OpenStreetMap/Nominatim e Open-Meteo. Buscas e links abertos por comando podem ser enviados ao site ou mecanismo de busca escolhido.

Cada provedor trata os dados conforme seus proprios termos e politicas. Consulte esses documentos antes de inserir informacoes pessoais, confidenciais ou de terceiros. Nao inclua dados de outras pessoas sem autorizacao adequada.

## Armazenamento e seguranca

Configuracoes, memoria e dados locais do Altair ficam em `%LOCALAPPDATA%\Altair`. Chaves de API, tokens e memoria de arquivos sao protegidos pelo Windows DPAPI para a conta Windows atual. A API de controle remoto e restrita a este computador por padrao; sua exposicao a outros dispositivos exige configuracao TLS, token e confirmacao na interface. A sessao do navegador WhatsApp, logs e outros dados de uso tambem podem ser gravados nessa pasta e ficam acessiveis a quem puder usar a mesma conta Windows/dispositivo. O Altair nao opera um servidor proprio para armazenar essas informacoes.

O Altair nao envia telemetria propria identificada nesta versao. O envio a terceiros ocorre conforme os recursos e provedores descritos acima.

## Controles e exclusao

- Revogue chamadas a servicos externos em **Menu > Permitir servicos externos**.
- Apague a memoria de conversa pela opcao de limpar conversa na interface.
- Para excluir configuracoes, memoria, logs, perfil e sessao locais, feche o Altair e remova `%LOCALAPPDATA%\Altair`. Isso tambem remove chaves e credenciais guardadas localmente.
- Para solicitar acesso, correcao ou esclarecimentos sobre dados enviados, contate [email de contato]. Dados enviados a terceiros tambem podem estar sujeitos aos controles e processos do provedor correspondente.

## Retencao, menores e alteracoes

Os dados locais permanecem ate voce remove-los ou desinstalar/limpar os dados conforme os controles acima. Os prazos de retencao de dados enviados a provedores externos sao definidos por esses provedores e devem ser verificados pelo publisher antes da publicacao. [Descrever a regra de idade minima e o tratamento de dados de menores apos revisao legal.] Esta politica sera atualizada quando os recursos ou provedores mudarem.

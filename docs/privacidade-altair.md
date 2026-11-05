# Política de Privacidade do Altair

**Responsável:** Gilberto Dellecrode  
**Contato para privacidade, suporte e denúncias:** [dellecrodeengenharia@gmail.com](mailto:dellecrodeengenharia@gmail.com)  
**Última atualização:** 5 de novembro de 2026

## Sobre o Altair

O Altair é um assistente para Windows. Esta política explica quais dados podem ser processados quando você usa seus recursos. O tratamento depende das funções que você escolher e dos provedores que configurar.

## Dados que podem ser processados

Conforme os recursos utilizados, o Altair pode processar comandos, conversas, transcrições, áudio capturado pelo microfone, arquivos escolhidos para análise, textos e destinatários escolhidos em ações do WhatsApp, chaves de API, preferências, memória, registros técnicos e dados de sessão.

A escuta contínua do microfone começa desativada. A permissão para serviços externos também começa desativada e pode ser revogada no menu do aplicativo. Sem essa permissão, os recursos que enviam dados a serviços externos ficam bloqueados. O uso de recursos locais continua dependendo da configuração do dispositivo.

## Serviços externos

Quando você permite serviços externos e usa uma função correspondente, os dados necessários podem ser enviados ao provedor configurado por você, que pode incluir Groq, OpenAI, ElevenLabs ou um endpoint personalizado. Recursos de clima ou localização podem consultar OpenStreetMap/Nominatim e Open-Meteo. Pesquisas e páginas abertas por comando podem transmitir dados ao mecanismo de busca ou site escolhido.

Se você usar a integração com WhatsApp, o Altair controla o WhatsApp Web no dispositivo e envia o conteúdo e os destinatários que você selecionar ao serviço WhatsApp/Meta. Os provedores externos tratam os dados conforme suas próprias políticas e prazos de retenção. Consulte essas políticas antes de enviar informações pessoais, confidenciais ou de terceiros.

## Armazenamento e segurança

Os dados locais do Altair ficam, por padrão, em `%LOCALAPPDATA%\\Altair` no Windows. Chaves, tokens e memória de arquivos são protegidos pelo Windows DPAPI para a conta Windows atual. Outros dados locais, como registros e sessão do navegador, podem permanecer nessa pasta e ser acessíveis a quem usar a mesma conta ou dispositivo. O Altair não opera um servidor próprio para armazenar esses dados.

A API de controle remoto fica restrita ao próprio computador por padrão. A exposição a outros dispositivos requer configuração de TLS, token e confirmação na interface.

O Altair não envia telemetria própria identificada. O envio a terceiros ocorre conforme os recursos e provedores descritos nesta política.

## Retenção e exclusão

Os dados locais permanecem no dispositivo até que você os apague. Para remover configurações, memória, registros, perfil e sessão locais, feche o Altair e apague a pasta `%LOCALAPPDATA%\\Altair`. Isso também remove as chaves e credenciais locais. Dados enviados a provedores externos ficam sujeitos aos prazos e controles desses provedores.

Você pode revogar a permissão de serviços externos no menu do Altair e limpar a memória de conversa pela interface do aplicativo.

## Seus pedidos e contato

Para dúvidas sobre privacidade, suporte, solicitações relacionadas a dados ou para denunciar conteúdo gerado por IA, escreva para [dellecrodeengenharia@gmail.com](mailto:dellecrodeengenharia@gmail.com). Para dados enviados a provedores externos, talvez também seja necessário usar os canais de privacidade desses provedores.

## Alterações desta política

Esta política pode ser atualizada quando os recursos, provedores ou práticas do Altair mudarem. A data no início da página indica a revisão mais recente.

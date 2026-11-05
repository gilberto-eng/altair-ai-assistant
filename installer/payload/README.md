# Payload do instalador

O script `build_installer.ps1` monta automaticamente o payload a partir do
repositorio em `installer/.build/payload` e o inclui no executavel.

Nao coloque chaves, tokens, arquivos de configuracao locais ou dados pessoais
nesta pasta. O instalador cria as pastas `configs`, `json` e `data` vazias na
instalacao para que cada usuario configure sua propria copia.

O instalador baixa/usa uma instalacao de Python existente e cria um ambiente
virtual. O build do executavel requer PyInstaller instalado no ambiente que
executa `installer/build_installer.ps1`.
    
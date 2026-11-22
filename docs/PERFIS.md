# Perfis de ECU

Um perfil é um arquivo `.json` em `%APPDATA%\MED17Programmer\profiles\` (botão **Abrir pasta de perfis**).
O programa cria `_modelo_med17.json` (em branco, nunca carregado). Copie-o, renomeie (ex.: `meu-med17.json`),
troque o campo `id` e preencha **somente com dados da documentação autorizada da sua ECU**.

- `null` = desconhecido. Valores numéricos aceitam hexadecimal em texto (`"0x7E0"`).
- Chaves com erro de digitação tornam o perfil inválido (ele é ignorado e o erro aparece no log).
- `identificacao`: regras para reconhecer a ECU, como `{"0xF191": ["MED17*"]}` (`*` e `?`, sem diferenciar
  maiúsculas). Todos os DIDs listados precisam casar. Sem regras, o perfil nunca é escolhido automaticamente.
- `memoria[].tipo`: `flash`, `eeprom_fisica` ou `nvm_emulada_em_flash`.
- `validado_leitura` / `validado_escrita`: marque `true` somente depois de validar o procedimento.
- Leitura/gravação só são liberadas se: fonte da documentação informada, protocolo completo (bitrate, formato do ID,
  tx_id, rx_id), ao menos uma região de memória totalmente definida, estratégia descrita e validação marcada.
  A gravação ainda exige regras de identificação. Perfis `simulado: true` nunca valem para hardware real.

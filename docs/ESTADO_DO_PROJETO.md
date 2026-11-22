# Estado do projeto
**Fase atual:** 3 — CAN, ISO-TP e UDS (aguardando validação).
Fases 1 e 2 validadas pelo usuário no Windows (22 testes OK; VCI2 conectou, leu versões e tensão).

| Item | Estado | Verificação |
|---|---|---|
| Fases 1–2 (estrutura, GUI, config, logs, ponte J2534) | prontas | validadas no Windows, hardware real |
| `can/` quadro CAN e `BridgeCanBus` | escrito | testado só com ponte **simulada** (loopback) |
| `isotp/` SF/FF/CF/FC, BS, STmin, WAIT/OVFLW, N_Bs/N_Cr, padding opcional | escrito | testado com ECU/barramento **virtuais** |
| `uds/` serviços 0x10 0x22 0x23 0x27 0x31 0x34 0x35 0x36 0x37 0x3E, NRCs, 0x78, Tester Present | escrito | testado com ECU **virtual**; seed/key do simulador é fictício |
| `simulator/virtual_ecu.py` | escrito | — |
| `tools/uds_probe.py` (somente leitura: 10 01 e 3E 00) | escrito | modo `--virtual` testado; **modo hardware não testado** |

Limitações: ISO-TP só com endereçamento normal e até 4095 bytes; nenhum comportamento é presumido
da ECU real (IDs, padding, STmin, serviços suportados) — tudo depende do perfil (Fase 4).
Não há interface gráfica nova nesta fase.

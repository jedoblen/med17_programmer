# Estado do projeto
**Fase atual:** 5, parte A (captura passiva). A Fase 4 aguarda o resultado do pytest do usuário.
Fases 1–3 validadas pelo usuário no Windows (44 testes OK, VCI2 conectada, sonda virtual OK).

| Item | Estado | Verificação |
|---|---|---|
| Perfis (`profiles/models.py`, `manager.py`): validação estrita, bloqueio por pendências, casamento por DIDs | escrito | testado (unitário) |
| Identificação UDS 0x22 (`ecu/identification.py`) com DIDs padrão ISO 14229-1 | escrito | testado com ECU **virtual** |
| Aba "Identificação ECU" (perfil, IDs manuais, tabela, perfis compatíveis, status leitura/gravação) | escrita | teste de GUI offscreen **ainda não executado** |
| Perfil real de MED17 | **inexistente** | exige dados da documentação do usuário; o modelo vem em branco |
| Identificação em ECU real | **não testada** | |
| Leitura/gravação de memória | não implementado | Fases 5 e 6 |

O programa não traz nenhum perfil com dados de ECU real. A ECU pode não suportar os DIDs padrão
(ou usar outro protocolo): a aba mostra o que respondeu, o NRC dos que recusou e o que ficou sem resposta.

## Fase 5, parte A — captura passiva (novo)
| Item | Estado | Verificação |
|---|---|---|
| `can/capture.py` (captura, CSV, resumo por ID, pares UDS/KWP, indício VW TP 2.0) | escrito | testado com tráfego **sintético** e barramento virtual |
| `tools/can_capture.py` | escrito | análise de CSV testável; **captura em hardware não testada** |
| Heurísticas de detecção | indícios, não prova | confirmar com a documentação |

ECU alvo informada pelo usuário: ME17.5.24 (Gol G6, peça 0261S10455) — protocolo ainda desconhecido.

## Fase 5, parte B — decodificação offline de UDS (novo)
| Item | Estado | Verificação |
|---|---|---|
| `can/decode_uds.py` (remontagem ISO-TP offline + decodificação de serviços) | escrito | testado com tráfego **sintético** |
| `tools/uds_decode.py` | escrito | só testável depois de uma captura real |

Decodifica request/response de 0x10, 0x22, 0x23, 0x27 (sem analisar semente/chave), 0x31, 0x34, 0x35, 0x36, 0x37, 0x3E.
Serve para extrair, de uma leitura feita pela Prog3, os endereços e tamanhos reais de FLASH/EEPROM da ME17.5.24.

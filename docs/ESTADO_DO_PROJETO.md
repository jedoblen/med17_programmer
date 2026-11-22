# Estado do projeto
**Fase atual:** 2 — Integração J2534 (aguardando validação). Fase 1 validada pelo usuário no Windows (8 testes OK, janela abriu).

| Item | Estado | Verificação |
|---|---|---|
| Estrutura, configuração, logs, GUI base (Fase 1) | pronto | validado no Windows |
| Constantes J2534 e wrapper ctypes (`j2534/api.py`) | escrito | testado só com **simulador** |
| Detecção de DLLs (registro) e bitness PE | escrito | bitness testado com arquivos sintéticos; leitura do registro **não testada** (exige Windows) |
| Ponte 32/64 bits (`bridge.py` + `client.py`) | escrito | testada via IPC com simulador |
| Simulador J2534 (`simulator/fake_j2534.py`) | mínimo (loopback, falhas injetáveis) | — |
| Aba Conexão (detectar, conectar, escutar passivo, desconectar) | escrita | teste de GUI com simulador **ainda não executado** |
| Carregamento de DLL real (`ctypes.WinDLL`) | escrito | **não testado com hardware** |
| CAN/ISO-TP/UDS, ECU, memórias | não implementado | Fases 3 a 7 |

Nesta fase nenhum quadro é transmitido à ECU pela interface; "Escutar CAN" é passivo.

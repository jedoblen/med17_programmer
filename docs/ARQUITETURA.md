# Arquitetura definitiva — Bosch MED17 Programmer

## Decisão crítica: 32 bits x 64 bits

As DLLs J2534 instaladas neste computador são de **32 bits**. Um processo só carrega DLLs
da mesma arquitetura, e o **PySide6 não tem versão para Windows 32 bits**. Portanto:

|Processo|Python|Conteúdo|
|-|-|-|
|**GUI / núcleo**|64 bits|PySide6, perfis, ISO-TP, UDS, memórias, DUMPs, HEX, logs|
|**Ponte J2534** (`j2534\_bridge`)|32 bits|Somente ctypes + biblioteca padrão; carrega a DLL e expõe PassThru\*|

Comunicação entre os dois: JSON linha a linha por stdin/stdout (ou socket local), com
timeout e encerramento seguro. A ponte é uma camada fina: nenhuma lógica de ECU nela.
Se uma DLL for de 64 bits, o mesmo código de ponte roda no Python 64 bits.
**Implementação da ponte: Fase 2.** Nada disso existe ainda no código.

## Camadas (dependência só para baixo)

```
gui -> operations -> memory / ecu / profiles / dumps / hexedit / integrity
                  -> uds -> isotp -> can -> j2534 (cliente) ==IPC==> j2534\_bridge (32 bits) -> DLL
simulator: implementa a mesma interface do cliente j2534 (permite testes sem hardware)
core: paths, config, logs (usado por todos)
```

## Módulos x fases

|Módulo (`src/med17/`)|Fase|
|-|-|
|core, gui (estrutura)|1 (feito)|
|j2534, ponte 32 bits|2|
|can, isotp, uds, simulator (base)|3|
|ecu, profiles|4|
|memory (leitura)|5|
|memory (gravação), operations, integrity|6|
|dumps, hexedit|7|
|testes finais, manual completo|8|

## Regras de segurança fixas

* Escrita só com perfil validado, backup, identificação conferida, integridade e alimentação estável.
* Sem endereços, algoritmos de segurança ou rotinas de bootloader inventados.
* Sem bypass de imobilizador nem exploração de vulnerabilidades.


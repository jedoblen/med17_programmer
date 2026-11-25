# Captura passiva de diagnóstico (descoberta de IDs e protocolo)

Objetivo: descobrir, com o seu scanner funcionando, quais IDs CAN, bitrate e tipo de protocolo a ECU usa.
A captura **não transmite nada**. Não faz parte de leitura/gravação.

## Ligação

1. VCI2 e scanner no mesmo barramento CAN (OBD com derivação em Y, ou ligação de bancada pelos pinos CAN H/CAN L
conforme a documentação da sua ECU). ECU alimentada de forma estável.
2. Bitrate: comece por 500 kbit/s (o programa usa o valor salvo na aba Conexão). Bitrate errado gera
quadros de erro e pode derrubar a comunicação do scanner: se isso ocorrer, desconecte e tente outro.
3. Não capture durante gravação/programação.

## Execução

```bat
python tools/can\_capture.py --segundos 90
```

Durante a captura, no scanner faça só operações de **leitura**: identificação da ECU, leitura de falhas
e dados em tempo real. Evite codificação, adaptação ou qualquer programação.

Saída: `captura.csv` e um relatório com IDs observados e candidatos a par tester → ECU.
Para reanalisar um CSV: `python tools/can\_capture.py --arquivo captura.csv`.

## Privacidade

O CSV pode conter o chassi (VIN) e números de série nos dados. Revise antes de compartilhar.

## Se nada for encontrado

O scanner pode estar usando a linha K (pino 7 do OBD), outro bitrate ou outro formato de endereçamento.
Este software só implementa CAN: se o diagnóstico da ECU for pela linha K, será preciso outro caminho.



## Decodificando os endereços (RequestDownload/Upload/ReadMemoryByAddress)

1. Rode a captura durante uma sessão de **leitura completa** no seu scanner (ex.: Launch Prog3 lendo FLASH/EEPROM).
Capturas curtas podem não cobrir todo o mapa de memória.
2. Ache os IDs candidatos: `python tools/can\_capture.py --arquivo captura.csv`
3. Decodifique a sessão completa com esses IDs:

```bat
   python tools/uds\_decode.py captura.csv --tx 0x7E0 --rx 0x7E8 --saida sessao.txt
   ```

   Isso mostra, em ordem de tempo: controle de sessão, endereço e tamanho de cada
`ReadMemoryByAddress`/`RequestDownload`/`RequestUpload`, os blocos de `TransferData`
(só o tamanho, não o conteúdo) e o `RequestTransferExit`.

4. Se aparecer `SecurityAccess`, o relatório só informa que ocorreu. A semente e a chave
capturadas não são decodificadas nem reaproveitáveis: valem só para aquela sessão.
O algoritmo de desbloqueio em si não é descoberto por este caminho, e este projeto
não o implementa (ver seção de segurança da especificação).
5. Os endereços e tamanhos encontrados são o ponto de partida para preencher `memoria\[]`
no perfil da ME17.5.24 (`docs/PERFIS.md`). Confirme-os com mais de uma leitura, se possível.

